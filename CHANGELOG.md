# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.9.0] - 2026-05-14

### Added
- `market_structures/equity/` subpackage — equity market-data foundation (PR 1 + PR 2 of the equity-forward-curve roadmap). `EquityForwardCurve(spot, zero_curve, pillar_times, pillar_yields, interpolation=FORWARD_YIELD_FLAT)`: term-structured forward ``F(T) = S0 * exp(-q(T) * T) / DF(T)``. Pinned to ACT/365 (equity convention); discount factors are read by date from the supplied `ZeroCurve` so its internal day-count does not need to match. Exposes `at_date(date)`, `at_time(float)`, `dividend_yield(T)`, and `__call__(when: float | date)` mirroring `EquityForward` so the curve duck-types as `market_structures.volatility.surface.ForwardCallable`. Two classmethod constructors: `EquityForwardCurve.flat(spot, zero_curve, dividend_yield)` builds a single-pillar curve numerically identical to the legacy `market_structures.volatility.forward.EquityForward` (which remains in place); `EquityForwardCurve.from_dividend_yield_quotes(spot, zero_curve, quotes)` builds the curve from a list of market quotes, sorts them by maturity, validates against the discount curve's reference date, and rejects duplicate maturities
- `DividendYieldInterpolation` enum on `EquityForwardCurve` — `FORWARD_YIELD_FLAT` (default): cumulative yield ``Q(T) = q(T) * T`` is piecewise-linear in ``T`` between pillars (instantaneous forward yield piecewise constant), the equity analogue of the log-linear-in-DF rates convention. `LINEAR_IN_YIELD`: ``q(T)`` itself is piecewise-linear in ``T``. Both modes agree at pillars and extrapolate flat in ``q`` outside the grid
- `market_structures/equity/quotes.py`:
  - `DividendYieldQuote(maturity_date, continuous_yield)` — point on the equity dividend-yield term structure. Negative yields are allowed (hard-to-borrow names); non-finite yields raise `ValueError` at construction
  - `ForwardQuote(maturity_date, forward_price)` (PR 4) — market-observed equity forward. Requires `forward_price > 0` and finite; no static no-arbitrage check against spot / DF because that requires the dividend / borrow assumption the bootstrapper solves for
  - Equity quotes are not subclasses of `market_structures.rates.quotes.MarketQuote` — the equity bootstrap target is solved per-pillar in closed form, so the rates `npv()` residual contract is not applicable
- `market_structures/equity/dividends.py` (PR 3) — `DividendKind` enum (`CASH` / `PROPORTIONAL`) and `DiscreteDividend(ex_date, amount, kind)` frozen dataclass. Cash amounts must be strictly positive; proportional amounts lie in `[0, 1)`; non-finite amounts rejected. Used by `EquityForwardCurve.from_discrete_dividends(spot, zero_curve, dividends, borrow_rate=0.0)`, which combines the schedule with an optional flat continuous carry per the Hull convention `F(T) = (S0 * Π_{ex<=T}(1-p_i) - Σ_{ex<=T} d_j*DF(ex_j)) * exp(-borrow*T) / DF(T)`. `EquityForwardCurve.__init__` also accepts a `discrete_dividends` kwarg directly so a continuous yield strip and a discrete schedule compose multiplicatively. Raises if cash PV exceeds proportionally-adjusted spot at any expiry
- `market_structures/equity/bootstrapper.py` (PR 4) — `EquityForwardCurveBootstrapper(spot, zero_curve)` with `.bootstrap(quotes, interpolation=FORWARD_YIELD_FLAT)`. Heterogeneous input of `ForwardQuote | DividendYieldQuote`; quotes sorted by maturity; duplicates on the same date (across types) rejected. Each `ForwardQuote` solves `q_i = -log(F_i * DF(T_i) / S0) / T_i` in closed form; each `DividendYieldQuote` stores its yield verbatim. INFO log on entry/exit; no per-iteration DEBUG (no iteration). Result duck-types as `market_structures.volatility.surface.ForwardCallable`
- `examples/08_equity_forward_curve.ipynb` — end-to-end notebook covering all four equity-curve constructors (flat, dividend-yield term structure with both interpolation modes, discrete dividends with cash + proportional jumps, market-quote bootstrap with round-trip recovery) and plugging the resulting curve into an `InterpolatedVolSurface`
- Tests covering `DiscreteDividend` (cash positive / proportional in `[0, 1)`, non-finite rejected, kind dispatch), Hull-formula forwards (single cash before / after expiry, single proportional before / after expiry, ex-date == expiry inclusive subtraction, mixed cash + proportional, multiple proportional compounding, borrow rate `exp(-b*T)`, internal sort order, continuous + discrete composition, negative-adjusted-spot rejection), `ForwardQuote` validation, and `EquityForwardCurveBootstrapper` (single / multiple round-trip, unsorted input, recovery of pre-built curve yields, mixed quote types, empty / on-reference-date / duplicate-maturity rejection, interpolation propagation, ForwardCallable duck-typing)
- Borrow / repo term structure on `EquityForwardCurve` (PR 5 of the equity-forward-curve roadmap). `__init__` gains optional `borrow_pillar_times`, `borrow_pillar_yields`, and `borrow_interpolation` kwargs; the borrow grid is independent of the dividend grid and may use a distinct `DividendYieldInterpolation` policy. New methods: `borrow_yield(T)` (returns 0 when no borrow curve attached), `effective_yield(T) = dividend_yield(T) + borrow_yield(T)`. The forward formula reads `effective_yield`, so a positive borrow rate depresses the forward (hard-to-borrow names). Backward-compatible: omitting borrow kwargs reproduces previous numerics exactly
- `market_structures/equity/quotes.py:BorrowRateQuote(maturity_date, continuous_borrow_rate)` — frozen dataclass for the borrow / repo term structure. Negative rates allowed; non-finite rejected. Convention: the rate is the additional yield earned by a long-stock holder who lends out the share (equivalently the cost paid by a short borrower), so positive values reduce the forward
- New classmethod `EquityForwardCurve.from_dividend_and_borrow_quotes(spot, zero_curve, dividend_quotes, borrow_quotes, interpolation=..., borrow_interpolation=...)` — builds a curve with two independent term structures. Within-list duplicate maturities raise; cross-list coincident dates are permitted (the two grids are independent)
- Tests covering `BorrowRateQuote` validation, backward-compatibility of empty-borrow curves, the `F = S * exp((r - d - b) * T)` flat-both formula, monotonicity in the borrow rate (high borrow ↓ forward), zero-borrow collapse, distinct pillar grids, pillar recovery for both legs, default vs override of `borrow_interpolation`, the full validation matrix for the borrow grid, and `from_dividend_and_borrow_quotes` round-trip / sorting / empty-list / on-reference-date / within-list-duplicate / cross-list-coincident handling
- Logging plumbing for the new subpackage: `market_structures.equity` entry in `logging.yaml`, `_PACKAGE_LOGGERS` in `logging_config.py`, `NullHandler` install in `market_structures/equity/__init__.py`
- Tests covering `EquityForwardCurve` (bit-exact parity with `EquityForward` on the flat-yield path across dates and year fractions, textbook ``exp((r-q)T)`` formula match, linear yield interpolation between pillars, flat extrapolation outside the grid, term-structured yield diverges from the flat case, duck-typing as `ForwardCallable`, full input-validation matrix)

- `montecarlo/volatility/local_vol.py` — Dupire local volatility (PR 4 of the volatility roadmap): `DupireLocalVol(surface)` is a `VolModel` that bridges any quote-side `VolSurface` to the diffusion-side coefficient ``sigma_loc(t, S)``. Dispatches on `isinstance(surface, DifferentiableVolSurface)`: for `SVISurface` / `SSVISurface` it evaluates the Gatheral form of Dupire's formula analytically on every `diffusion()` call; for plain `VolSurface` (`InterpolatedVolSurface`) it pre-computes ``sigma_loc^2`` on an auto-sized (~50×100) ``(t, k_log)`` grid via central finite differences and bilinearly interpolates at runtime. Clips to a positive ``sigma_floor`` (default ``0.01``) where the Dupire denominator collapses (butterfly arbitrage in the source surface) or the numerator goes negative (calendar arbitrage); emits a `UserWarning` if more than 1% of grid points are clipped. Public surface-coordinate query `local_variance(time_to_expiry, log_moneyness)` alongside the path-engine `diffusion(time, spot, state=None)`. Default fallback grid sizes are overridable via `t_grid` / `k_grid` constructor kwargs
- Tests covering Dupire (flat-vol identity ``sigma_loc == sigma_imp`` everywhere; Black-term-structure agreement on a flat-in-k surface; analytical-vs-numerical-FD agreement on SVI / SSVI surfaces; bilinear-grid path on `InterpolatedVolSurface`; spot-vectorisation; `state` kwarg accepted and ignored; clipping `UserWarning` on a deliberately arb-violating fixture)
- `validation/quantlib_xref/test_dupire_local_vol.py` — QuantLib cross-check of `DupireLocalVol` against `ql.LocalVolSurface` on flat and skewed surfaces (skipped cleanly if `QuantLib` is not installed)

- `market_structures/volatility/parametric/` subpackage — SVI / SSVI parametric surfaces (PR 3 of the volatility roadmap):
  - `parametric/svi.py` — raw SVI (Gatheral 2004): `SVIParameters` frozen dataclass (``a, b, rho, m, sigma``) with construction-time validation of all four standard constraints; `SVISlice(expiry, params)` with closed-form `total_variance(k)`, `dw_dk(k)`, `d2w_dk2(k)`; `SVISurface(DifferentiableVolSurface)` collection of slices with sticky-moneyness cross-T interpolation (linear in ``w`` between slices at fixed ``k_log``, flat-vol-in-time extrapolation outside the quoted range) and analytical ``dw_dT`` / ``dw_dk`` / ``d2w_dk2``
  - `parametric/ssvi.py` — surface SVI (Gatheral-Jacquier 2014): `SSVIPhiFunction` ABC with `PowerLawPhi(eta, gamma)` and `HestonLikePhi(lambda_)` concrete subclasses (Heston-like uses a small-``x`` Taylor branch to avoid ``0/0`` cancellation near ``theta = 0``); `SSVISurface(DifferentiableVolSurface)` parameterised by the ATM term structure ``theta_T`` (linearly interpolated across pillars), scalar ``rho``, and a phi function. ATM identity ``w(T, 0) = theta_T`` holds by construction. All four canonical methods and three derivatives are closed-form via chain rule
- `market_structures/volatility/calibration.py`:
  - `fit_svi_slice` — Zeliade Systems / De Marco-Martini (2009) **quasi-explicit** calibration. Inner: 7-inequality-constrained linear LSQ in ``(a, d, c)`` via SLSQP, with a feasibility-clipped unconstrained-lstsq fallback. Outer: 2-D Nelder-Mead on ``(m, sigma)``. Far more robust than direct 5-D Levenberg-Marquardt
  - `fit_svi_surface` — chains per-slice fits into an `SVISurface`
  - `fit_ssvi` — joint Levenberg-Marquardt fit of ``(rho, *phi_params)`` on the full grid; the ATM term structure ``theta_T`` is set by linear-in-``w`` per-slice interpolation at ``k = 0`` and is not iterated
  - All three entry points accept an optional ``weights`` argument; default is uniform-in-``w``. Pass a vega array (computed by the caller) for standard market vega weighting — no Black-Scholes coupling is baked into the calibrator
- `market_structures/volatility/arbitrage.py` — diagnostics for differentiable surfaces. `durrleman_g(surface, T, k_log)` returns the Roper-Gatheral butterfly density function; `check_butterfly(surface, T, k_grid)` and `check_calendar(surface, T_grid, k_grid)` evaluate ``g`` and ``dw/dT`` on user-supplied grids and return frozen-dataclass reports (`ButterflyReport`, `CalendarReport`). Diagnostics only — no arbitrage repair
- Tests covering SVI (parameter validation, slice closed-forms, analytical-vs-FD derivatives, quasi-explicit calibration synthetic recovery, vega-weighted calibration smoke check, Gatheral-Jacquier 2014 SPX literature anchor, surface cross-T interpolation), SSVI (both phi families value + derivative, ATM identity, analytical-vs-FD derivatives, calibration recovery for both phi families, arb-free and arb-violating param coverage), and arbitrage (Durrleman ``g`` on flat-slice sanity, butterfly/calendar pass and fail cases)

- `montecarlo/volatility/` subpackage — diffusion-side foundation of the volatility stack (PR 2 of the volatility roadmap):
  - `model.py` — `VolModel` ABC with `diffusion(time, spot, state=None) -> np.ndarray` returning per-path instantaneous lognormal volatility. The `state` kwarg is plumbed from day one for future stochastic-vol models (Heston, SABR) that will read `state["variance"]` / `state["alpha"]`; current models ignore it
  - `constant.py` — `ConstantVol(sigma)`: flat lognormal vol independent of time and spot. Sanity model for which closed-form vanilla prices match MC output
  - `term_structure.py` — `BlackTermStructureVol(surface)`: piecewise-constant instantaneous vol derived from the ATM column of any `VolSurface`. Solves ``w_ATM(T) = integral_0^T sigma_inst^2 du`` by ``sigma_inst^2 on (T_{i-1}, T_i] = (w_i - w_{i-1}) / (T_i - T_{i-1})`` with the anchor ``T_0 = 0``, ``w_0 = 0``. Reprices the surface's pillar ATM vanillas exactly under MC; ignores skew (the skew-aware bridge `DupireLocalVol` lands in PR 4). Calendar arbitrage in the source surface (non-monotone ATM total variance in ``T``) is rejected at construction with `ValueError`; ``t > T_N`` flat-extrapolates the last segment's vol
- `expiries` abstract property on `VolSurface` — formalises the pillar-grid contract that diffusion-side consumers (`BlackTermStructureVol`) anchor on. `InterpolatedVolSurface.expiries` already satisfied the contract; future parametric surfaces (SVI / SSVI) will expose the same property
- Logging plumbing for the new subpackage: `montecarlo.volatility` entry in `logging.yaml`, `_PACKAGE_LOGGERS` in `logging_config.py`, `NullHandler` install in `montecarlo/volatility/__init__.py`
- Tests covering `ConstantVol` (vector / 0-d spot, time-independence, state-ignored, sigma validation) and `BlackTermStructureVol` (exact pillar repricing, piecewise-constant segments with right-closed boundaries, flat extrapolation beyond the last pillar, spot-vectorisation, state ignored, flat-vol special case, calendar-arb rejection, negative-time rejection, empty-expiries rejection, defensive copies on `pillars` / `sigma_inst`)
- `market_structures/volatility/` package — quote-side foundation of the implied-volatility stack (PR 1 of the volatility roadmap):
  - `coordinates.py` — strike / log-moneyness / Black-Scholes spot-delta converters. Unadjusted spot-delta convention (``delta_call = df_funding * N(d1)``); premium-adjusted / forward-delta FX conventions are out of scope
  - `pricing.py` — `black_scholes_price` (Black-76 forward-domain form ``df * (F * N(d1) - K * N(d2))``), `black_scholes_vega`, `no_arb_price_bounds` (call: ``(df * max(F-K, 0), df * F)``; put: ``(df * max(K-F, 0), df * K)``), and `implied_vol_from_price` (Brent's method on a fixed ``[1e-8, 5.0]`` bracket with an arb-bound pre-check)
  - `forward.py` — `EquityForward(spot, zero_curve, dividend_yield)` implementing ``F(T) = S0 * exp(-q * T) / DF(T)``; pinned to ACT/365, `at_date` / `at_time` / `__call__` dispatch on the maturity argument type
  - `surface.py` — `VolSurface` ABC (`reference_date`, `forward(T)`, `implied_vol(T, K)`, `total_variance(T, k_log)`) and `DifferentiableVolSurface` ABC (adds `dw_dT`, `dw_dk`, `d2w_dk2` for analytical Dupire). Canonical coordinate is total implied variance ``w(T, k_log) = sigma^2 * T``
  - `interpolated.py` — `InterpolatedVolSurface`: non-parametric surface on a per-slice variable-length log-moneyness grid. Default within-slice interpolation is linear in ``w`` (pluggable via `Interpolator`); across slices, linear in ``w`` at fixed ``k_log`` (sticky-moneyness, Gatheral convention); outside the surface's time range, flat-vol-in-time extrapolation (boundary ``sigma(k_log)`` held constant, ``w`` rescaled linearly with ``T``). Two classmethod constructors: `from_option_prices` (Brent-inverts each quote, skips arb-bound violators with `UserWarning`) and `from_implied_vols` (bypasses inversion). Emits a calendar-arbitrage `UserWarning` when ``w`` is non-monotone in ``T`` on any node of the per-pair log-moneyness union grid
- Logging plumbing for the new package: `market_structures.volatility` entry in `logging.yaml`, `_PACKAGE_LOGGERS` in `logging_config.py`, `NullHandler` install in `market_structures/volatility/__init__.py`
- Tests covering coordinates (round-trips, admissible delta ranges), pricing (put-call parity, ATM closed-form, vega finite-difference, no-arb bounds, Brent inversion round-trip across sigma × T × moneyness × type, skipping the degenerate deep-ITM/OTM regions where vol is not identifiable from price), forward (formula correctness, dispatch, validation), and interpolated surface (flat-vol grid, node recovery, full price-pipeline recovery, time-range extrapolation, arb-violator skipping, calendar-arbitrage warning)

## [0.8.0] - 2026-05-13

### Added
- `montecarlo/` package — Step 1 (random-number sampling) of the Monte Carlo engine that will price equity basket autocalls
  - `montecarlo.Sampler` ABC with dimension-aware `next_block(n_paths, n_dimensions)` contract; concrete uniform samplers: `KnuthSampler` (subtractive `ran3`), `LecuyerMRG32k3a1999Sampler` (L'Ecuyer 1999, with `substream()` stub for the path-engine PR), `MersenneTwisterSampler` (MT19937), `HaltonSampler`, `SobolSampler` (gray-code with Joe-Kuo 2008 direction numbers up to 1024 dimensions, bundled in `_joe_kuo_data.py`)
  - `montecarlo.NormalTransform` ABC + `make_normal_sampler` factory enforcing the QMC / inversion pairing rule (Box-Muller and CLT rejected when paired with low-discrepancy samplers); concrete transforms: `CLTTransform` (pedagogy only, emits `UserWarning`), `BoxMullerTransform`, `MoroTransform` (1995), `AcklamTransform` (2003), `WichuraAS241Transform` (1988, machine-precision tails)
  - `montecarlo.diagnostics` — KS / chi-square / serial correlation / Warnock L2 discrepancy for uniforms, moments / KS-vs-`N(0,1)` / Anderson-Darling / tail-fraction comparison for normals, and end-to-end `integrate_gaussian_moment` and `bs_call_price_mc` smoke tests against closed-form benchmarks
  - `montecarlo.plotting` — `scatter_2d`, `lag_scatter`, `projection_grid` (the canonical Halton-failure visual), `qq_normal`, `marginal_histogram`, `convergence_plot`
  - `examples/06_random_number_sampling.ipynb` — PRNG and QMC tours, normal-transform accuracy table, factory pairing demo, and a PRNG vs QMC convergence study on a European call
- `scipy>=1.14` runtime dependency (used as ground truth for inverse-normal accuracy tests, KS / Anderson-Darling p-values, and Black-Scholes closed-form in the integration smoke tests; not used in library hot paths)
- `validation/quantlib_xref/` — QuantLib cross-validation suite covering every layer of `montecarlo/`: Sobol direction-number parity against `ql.SobolRsg(JoeKuoD6)`, Halton bit-parity against `ql.HaltonRsg` (both deterministic and `randomStart=True` modes), bit-exact agreement for `MersenneTwisterSampler`, `KnuthSampler`, and `LecuyerLCG1988Sampler` against the corresponding QL generators, distributional baseline for `LecuyerMRG32k3a1999Sampler` against `ql.LecuyerUniformRng`, pointwise inverse-CDF agreement (AS241 vs scipy `ndtri` to machine precision, Acklam vs scipy, Moro vs QL in both the body and the documented deep-tail degradation), and end-to-end Black-Scholes pricing for all 21 compatible (sampler, transform) pairs against `ql.BlackCalculator`. Runs separately from `tests/` via `pytest validation/quantlib_xref -q`; the assertion thresholds in each test file are the canonical residual contract
- `QuantLib>=1.42` optional dependency under the `[validation]` extra (`pip install -e ".[validation]"`); core `tests/` suite is unaffected by its presence or absence
- `montecarlo.LecuyerLCG1988Sampler` — port of L'Ecuyer's 1988 combined-LCG with Bays-Durham shuffle (Numerical Recipes `ran2`); bit-for-bit compatible with `ql.LecuyerUniformRng`. Lives alongside the existing `LecuyerMRG32k3a1999Sampler` (1999 paper) which remains the production sampler — its ~2^191 period is required for the upcoming basket-autocall path engine, whereas the 1988 LCG has only ~2^61
- `random_start: bool` and `seed: int` parameters on `HaltonSampler` — when `random_start=True`, per-dimension starting indices are drawn from MT19937 seeded with `seed`, matching `ql.HaltonRsg(d, seed, randomStart=True)` bit-for-bit (any non-zero seed). Default remains the deterministic origin-skip mode
- `MersenneTwisterSampler.next_int32_block(n)` — exposes raw tempered 32-bit MT19937 output (matches `ql.MersenneTwisterUniformRng::nextInt32`); used internally by `HaltonSampler` to replicate QL's `randomStart` offsets

### Changed
- `montecarlo.KnuthSampler` rewritten from Knuth's `ran3` subtractive integer generator (~2^55 period) to Knuth's RANARRAY lagged-Fibonacci in IEEE doubles (KK=100, LL=37, TT=70; period ~2^240) — the same algorithm shipped by `ql.KnuthUniformRng`. The new implementation is bit-for-bit compatible with QuantLib for any non-zero seed; existing callers that relied on the old `ran3` output sequence must re-seed to match the new bit pattern (the strict-(0,1) range contract is unchanged in practice but is no longer asserted at the sampler boundary because RANARRAY can in principle yield 0.0 exactly)
- `montecarlo.MRG32k3aSampler` renamed to `montecarlo.LecuyerMRG32k3a1999Sampler` to disambiguate against the newly added `LecuyerLCG1988Sampler`. The underlying file moved from `montecarlo/uniform/lecuyer.py` to `montecarlo/uniform/lecuyer_mrg.py` (git rename, history preserved)

## [0.7.2] - 2026-05-11

### Changed
- `README.md`: expanded the intro to state project scope (rate-curve construction and single-name CDS pricing from scratch, no third-party pricing libraries) and added a **Capabilities** section enumerating schedule generation, zero-curve bootstrapping, credit-curve bootstrapping (sequential vs. global, three interpolation variables), CDS pricing/sensitivities, and the logging convention; added a per-notebook table under **Examples** and sharpened the **Packages** table to name the concrete classes/instruments in each package

## [0.7.1] - 2026-05-11

### Added
- `examples/05_credit_curve_bootstrapping.ipynb`: per-quote segment-coloured plot of the bootstrapped survival curve, and a verification cell that reconstructs `Q` from the `Tenor` and `FwdHazard` columns under `FORWARD_DEFAULT_SPREAD` interpolation
- `examples/05_credit_curve_bootstrapping.ipynb` §1: named definitions of survival probability, default density, and cumulative-equivalent spread, plus a side-by-side comparison of cumulative-equivalent spread `s(t)` and market-quoted CDS par spread `s*(T)` (recovery scaling and RPV01-weighting)
- `examples/03_cds_pricing.ipynb` §1: hazard-rate interpretation of `lambda(t)` and derivation of `-dQ(t) = lambda(t) Q(t) dt`
- "Reading `CreditCurve.summary()`" column-legend markdown cells in both `examples/03_cds_pricing.ipynb` and `examples/05_credit_curve_bootstrapping.ipynb`

### Changed
- `CreditCurve.summary()`: column header `FwdHazard` renamed to `FwdHazard (lambda(t))` to make the hazard-rate column explicit; docstring expanded with a per-column legend

### Fixed
- `examples/05_credit_curve_bootstrapping.ipynb`: API drift against current `credit/` — replaced `Schedule[:n]` indexing with `list(schedule)[:n]`, removed calls to the no-longer-existing `SingleNameCDS.from_quote(...)`, and updated constructor kwargs from `reference_date`/`periods` to `pricing_date`/`schedule`

## [0.7.0] - 2026-05-08

### Added
- `credit.CreditCurveBootstrapper` with `BootstrapMode.SEQUENTIAL` (scalar Newton-Raphson per pillar) and `BootstrapMode.GLOBAL` (multivariate Newton-Raphson on the full NPV system with finite-difference Jacobian and Gaussian-elimination linear solve)
- `credit.CreditCurve` with `InterpolationVariable` enum supporting three parameterisations: `SURVIVAL_PROBABILITY` (linear in Q), `DEFAULT_SPREAD` (linear in cumulative s), and `FORWARD_DEFAULT_SPREAD` (piecewise-constant forward hazard, ISDA-style)
- `credit.CdsSide` enum and `side` parameter on `SingleNameCDS` for buyer/seller NPV sign convention
- `pricing_date` parameter on `SingleNameCDS` with automatic clipping of fully-elapsed periods, enabling mid-life trade valuation while preserving the contractual DCF on the first live period
- `SingleNameCDS.premium_leg_summary()` and `protection_leg_summary()` — formatted per-period breakdowns of the two legs
- `examples/03_cds_pricing.ipynb` — detailed CDS pricing walkthrough: deterministic-intensity model, leg decomposition, RPV01, par spread, mid-life pricing, and CS01/RR01/IR01 via bump-and-rebootstrap
- `examples/05_credit_curve_bootstrapping.ipynb` — companion notebook on credit-curve bootstrapping across the three interpolation variables and both bootstrap modes

### Changed
- `SingleNameCDS` now accepts a `Schedule` object directly (was: list of `Period`); `CdsQuote.schedule(reference_date)` returns the matching `Schedule`. The constructor calls `schedule.generate()` internally
- Converted docstrings across `credit/` (`quotes.py`, `bootstrapper.py`, `curve.py`, `pricing.py`) to NumPy style with `Parameters`, `Returns`, `Raises`, and `Attributes` sections; reformatted multi-parameter signatures to vertical style

### Fixed
- `Schedule._build_periods`: BDC adjustment is now applied to both `accrual_start` and `accrual_end` (previously only `accrual_end`)

### Refactored
- Removed legacy `credit/survival_curve.py` and `credit/cds.py`; replaced by `credit/curve.py` (`CreditCurve`) and `credit/pricing.py` (`SingleNameCDS`, `CdsSide`)

## [0.6.0] - 2026-05-07

### Added
- Logging infrastructure: per-module `getLogger(__name__)`, `NullHandler` on every package `__init__`, and YAML-driven `dictConfig` (`logging.yaml`) loaded via `logging_config.setup_logging(level=...)`. INFO-level lifecycle summaries plus DEBUG per-iteration traces (guarded by `isEnabledFor`) on the rate Newton-Raphson and CDS bisection bootstrappers
- `PyYAML>=6.0` runtime dependency for the YAML logging config
- `tests/test_logging.py` — caplog-based assertions for bootstrapper INFO/DEBUG records and a `setup_logging()` smoke test

### Changed
- `examples/_setup.py` and `scripts/initialise.py` replace `print()` status messages with `logger.info(...)` and call `setup_logging()` so notebook and CLI output flows through the configured handler
- The existing quote-collision `warnings.warn` in `ZeroCurveBootstrapper.bootstrap()` is unchanged — `warnings` remains the user-facing data-quality channel; `logger` covers operational/diagnostic concerns

## [0.5.3] - 2026-05-07

### Refactored
- Migrated the four example notebooks (`01_schedule_generation`, `02_market_structures`, `03_cds_pricing`, `04_zero_curve_bootstrapping`) to call `setup_demo_env()` from `examples/_setup.py`, replacing the per-notebook `sys.path` / `set_db_path` / `init_db` / holiday-seeding boilerplate with a single helper call matching `_template.ipynb`

## [0.5.2] - 2026-05-07

### Changed
- Split `CLAUDE.md` into a slim root file (commands, git, versioning, working conventions, package map, cross-package invariants) plus per-package `CLAUDE.md` files (`database/`, `scripts/`, `market_conventions/`, `market_structures/`, `schedules/`, `credit/`, `tests/`, `examples/`) so module-level guidance is loaded only when working in the relevant subtree
- Replaced the `Post-merge` working convention with a `Docs freshness` convention pointing to the `/pre-pr` check, since the redundant post-merge docs review was already covered pre-PR
- Added `scripts/holiday_generators.py` to package documentation (previously unmentioned)

### Fixed
- Backslash paths (`.venv\Scripts\python`) in root `CLAUDE.md` `bash`-fenced examples — replaced with forward slashes so the commands work in both PowerShell and Bash on Windows

### Added
- `Subagent model selection` working convention in root `CLAUDE.md` — Haiku for mechanical delegation, Opus for the `Plan` subagent when context isolation is the reason to delegate
- Notebook reading rule in `examples/CLAUDE.md` — avoid `Read` on whole `.ipynb` files; use `NotebookEdit` or targeted cell ranges
- `perf`, `test`, and `revert` rows to the commit type table; escape-hatch rule allowing new types to be proposed and added in the same PR when no existing type fits
- `examples/_setup.py` with `setup_demo_env()` helper — single entry point for sys.path, DB redirect, and idempotent holiday seeding
- `examples/_template.ipynb` skeleton notebook — copy-and-edit starting point for new notebooks; documents the setup helper for the human reader
- `examples/__init__.py` so `examples` is importable as a package once the project root is on `sys.path`
- Workflow rule in `examples/CLAUDE.md` — copy `_template.ipynb` and edit via `NotebookEdit`; do not derive structure from existing notebooks

## [0.5.1] - 2026-05-07

### Changed
- Added `Working Conventions` section to `CLAUDE.md` documenting docstring style, notebook output policy, and post-merge docs review requirement

## [0.5.0] - 2026-05-07

### Changed
- Converted all docstrings across `market_structures/`, `schedules/`, `database/`, `scripts/`, and `market_conventions/` to NumPy style with `Parameters`, `Returns`, `Raises`, and `Attributes` sections
- Reformatted function and method signatures to one-parameter-per-line vertical style throughout
- Added missing type annotations to `Schedule.__iter__` and `Schedule.__len__`

## [0.4.0] - 2026-05-06

### Added
- `CdsQuote`: tenor-based CDS spread quote with `maturity_date()`, `schedule()`, and `bumped()` methods
- `SurvivalCurve.from_cds_spreads()`: classmethod bootstrapping a survival curve from a list of `CdsQuote` instances via bisection per pillar
- Shared `date_utils` module with `parse_tenor`, `add_spot_lag`, `add_tenor`, and `imm_date` utilities used across rate and CDS quote types
- Optional `maturity_date` override on `DepositQuote`, `FuturesQuote`, `OISQuote`, and `SwapQuote`
- `CalendarType | HolidayCalendar` union type accepted wherever a calendar is required

### Fixed
- `Schedule`: skip LONG_BACK/LONG_FRONT stub merge when the schedule divides exactly into regular periods

### Refactored
- Removed resolved TODO comment from `Schedule` class

## [0.3.0] - 2026-05-04

### Added
- `ZeroCurveBootstrapper`: sequential pillar-by-pillar bootstrap using Newton-Raphson with forward finite-difference derivative
- `QuoteHierarchy`: fixed priority ordering to resolve maturity-date collisions between instruments at bootstrap time
- `MaturityReference` enum: controls whether the bootstrapping pillar is placed at accrual end or payment date
- `payment_lag` parameter on `OISQuote` and `SwapQuote` for business-day-offset payment dates
- `SingleNameCDS`: CDS pricer with `premium_leg_pv`, `protection_leg_pv`, `rpv01`, `par_spread`, `mtm`, `cs01` (1bp bump-and-rebootstrap), and `rr01` (1% recovery bump)
- `SurvivalCurve`: piecewise-constant hazard rate curve with `bump()` for CS01 computation
- `ZeroCurve.summary()`: formatted table of bootstrapping quotes with discount factors and zero rates per pillar
- `Schedule.summary()`: formatted header block and per-period table
- `MarketQuote.start_date()` and `quote_value()` abstract methods on the base class

### Refactored
- Bootstrapper solver extracted as a standalone `ZeroCurveBootstrapper`; `ZeroCurve` no longer handles calibration

## [0.2.0] - 2026-05-02

### Added
- `market_structures` package: `ZeroCurve` with pluggable interpolation and `discount_factor`, `zero_rate`, and `forward_rate` queries
- `LinearInterpolator`, `LogLinearInterpolator` (market standard for discount factors), and `V2TInterpolator` (variance-to-time for implied vol)
- `DepositQuote`, `FuturesQuote` (IMM-dated with convexity adjustment), `OISQuote` (self-discounting), and `SwapQuote` (multi-curve)
- `HolidayCalendar.add_holiday()`: in-memory and optionally persistent holiday addition
- Example notebooks: schedule generation and market structures (ZeroCurve, interpolators, bootstrapping)
- `nbstripout` git hook to strip notebook outputs before commits

### Changed
- Renamed `market_data` package to `market_structures`
- PEP 257 compliant docstrings added across all packages

## [0.1.0] - 2026-05-01

### Added
- IRS accrual schedule generator (`schedules/`): `Schedule`, `Period`, `Frequency`, stub types, business day conventions, and day count fractions (ACT/360, ACT/365 Fixed, 30/360 Bond Basis, ACT/ACT ISDA)
- `HolidayCalendar` with USD, EUR, GBP, and PLN holiday sets; lazy per-year DB caching
- `market_conventions` package: `BusinessDayConvention`, `DayCountConvention`, `CompoundingType`, `CompoundingFrequency`, and `StubType`
- `database` package: SQLite connection management and `HolidayRepository` (add/remove/get_by_year/get_all)
- `scripts/initialise.py`: single entry point for DB setup and holiday seeding (2000–2100)
- Project setup: `pyproject.toml`, `README.md`, `.gitignore`, `CLAUDE.md`, virtual environment workflow
