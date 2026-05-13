# market_structures/volatility/

Implied-volatility surface infrastructure for equity (and forward-ready for FX / commodities). This package provides the **quote-side** of the volatility stack — surfaces that store and interpolate implied vols observed in the market. The **model-side** counterpart (diffusion coefficients consumed by Monte Carlo) lives in `montecarlo/volatility/` and is built in a later PR.

## Layout

- **`coordinates.py`** — pure functions for moving between strike, log-moneyness ``k_log = log(K / F(T))``, and Black-Scholes spot delta. Log-moneyness is the canonical internal smile axis (SVI-native, calendar-arbitrage-monotone). Delta uses the **unadjusted spot-delta** convention ``delta_call = df_funding * N(d1)`` — premium-adjusted / forward-delta FX conventions are explicitly out of scope.
- **`pricing.py`** — Black-76 / Black-Scholes pricer in forward-domain form ``df * (F * N(d1) - K * N(d2))``, plus vega, static no-arbitrage price bounds, and a Brent-based implied-vol inverter (`implied_vol_from_price`). The inverter runs once per quote at construction time, never in a hot loop, so robustness (Brent on a fixed `[1e-8, 5.0]` bracket) is preferred over Newton-with-vega speed.
- **`forward.py`** — `EquityForward(spot, zero_curve, dividend_yield)`: ``F(T) = S0 * exp(-q * T) / DF(T)``. Day count is pinned to ACT/365 (equity convention); the curve's internal day-count convention does not need to match because `DF` is looked up by date.
- **`surface.py`** — `VolSurface` ABC (quote-side contract: `reference_date`, `forward(T)`, `implied_vol(T, K)`, `total_variance(T, k_log)`) and `DifferentiableVolSurface` ABC (adds `dw_dT`, `dw_dk`, `d2w_dk2` for analytical Dupire). Non-parametric surfaces do **not** inherit from `DifferentiableVolSurface`; the Dupire bridge dispatches on `isinstance` and falls back to a smoothed numerical grid.
- **`interpolated.py`** — `InterpolatedVolSurface`: non-parametric surface on a per-slice variable-length log-moneyness grid. Default interpolation is linear in ``w`` within a slice (LinearInterpolator, extrapolate=True) and linear in ``w`` across slices at fixed ``k_log`` (sticky-moneyness, Gatheral convention). Time-boundary behaviour is **flat-vol in time**: the boundary slice's ``sigma(k_log)`` is held constant and ``w`` rescales linearly with ``T`` — not raw ``w``-clamping. Two classmethod constructors: `from_option_prices` (Brent-inverts each quote; skips arb-bound violators with `UserWarning`) and `from_implied_vols` (bypasses inversion).

## Invariants

- The canonical surface coordinate is **total implied variance** ``w(T, k_log) = sigma^2 * T``. Concrete surfaces may store anything internally, but `total_variance(T, k_log)` is the public contract that downstream code (notably the Dupire bridge in PR 4) reads.
- New non-parametric `VolSurface` subclasses must extrapolate flat-vol in time outside the quoted range, not flat-``w``, otherwise short/long extrapolations recover the wrong sigma.
- New parametric surfaces with closed-form derivatives should subclass `DifferentiableVolSurface` so the Dupire bridge can use the analytical path. Surfaces without closed-form derivatives stay on plain `VolSurface`.
- No DB persistence. Surfaces consume in-memory user-supplied inputs (spot, zero curve, expiries, strikes, prices or vols); this is consistent with the project's DB-deprecation direction.

## Channel split

- **`warnings.warn(UserWarning)`** — data-quality signals the caller might want to silence with `filterwarnings`: arb-bound violators skipped in `from_option_prices`, calendar-arbitrage warnings emitted on construction when ``w`` is non-monotone in ``T``.
- **`logger.info`** — lifecycle summaries (one line per `EquityForward` / `InterpolatedVolSurface` construction; one line per `from_option_prices` summarising inverted/skipped quote counts and max residual).
- **`logger.debug`** — guarded with `isEnabledFor`, used inside the Brent inverter to log F, K, T, price, and the resolved no-arb bounds per call.

## Forward extension points

- **Parametric SVI / SSVI** — drop into this package as `svi.py` / `ssvi.py` subclassing `DifferentiableVolSurface`. The ``(T, k_log, w)`` contract is unchanged.
- **Other asset classes** — the low-level `InterpolatedVolSurface.__init__` is asset-class-agnostic: it takes any forward callable plus a pre-computed grid. Class-method constructors are equity-specific (`spot`, `zero_curve`, `dividend_yield`); add FX or commodity constructors as needed without touching the core.
- **Diffusion coefficients** — built in a later PR under `montecarlo/volatility/` (ConstantVol, BlackTermStructureVol, DupireLocalVol). Models consume a surface; surfaces never know about models.
