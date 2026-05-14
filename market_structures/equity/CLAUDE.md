# market_structures/equity/

Equity market-data objects: forward curves, dividend yields, and the quotes /
bootstrappers that build them. This package is the equity counterpart of
`market_structures/rates/` and is consumed by `market_structures/volatility/`
through the `ForwardCallable` contract.

## Layout

- **`forward_curve.py`** — `EquityForwardCurve(spot, zero_curve, pillar_times,
  pillar_yields, interpolation=FORWARD_YIELD_FLAT, discrete_dividends=(),
  borrow_pillar_times=(), borrow_pillar_yields=(), borrow_interpolation=None)`:
  term-structured forward curve combining a continuous dividend yield with
  an optional borrow / repo term structure and an optional discrete-dividend
  schedule via the Hull convention ``F(T) = (S0 * Π(1 - p_i) - Σ d_j *
  DF(ex_j)) * exp(-effective_yield(T) * T) / DF(T)``, where
  ``effective_yield(T) = dividend_yield(T) + borrow_yield(T)``. Day count is
  pinned to ACT/365; the discount curve's internal day-count convention
  does not need to match because ``DF`` is looked up by date. Exposes
  ``at_date(date)``, ``at_time(float)``, ``dividend_yield(float)``,
  ``borrow_yield(float)``, ``effective_yield(float)``, and ``__call__(when:
  float | date)`` for ``ForwardCallable`` drop-in compatibility with
  `market_structures.volatility.forward.EquityForward`. Four classmethod
  constructors:
  ``EquityForwardCurve.flat(spot, zero_curve, dividend_yield)`` builds a
  single-pillar curve numerically identical to the legacy `EquityForward`;
  ``EquityForwardCurve.from_dividend_yield_quotes(spot, zero_curve, quotes)``
  takes a list of `DividendYieldQuote`s and constructs a borrow-free curve;
  ``EquityForwardCurve.from_dividend_and_borrow_quotes(spot, zero_curve,
  dividend_quotes, borrow_quotes)`` builds a curve with two independent term
  structures (the dividend and borrow grids need not share maturities);
  ``EquityForwardCurve.from_discrete_dividends(spot, zero_curve, dividends,
  borrow_rate=0.0)`` builds a curve from a `DiscreteDividend` schedule plus
  a flat continuous carry. Raises if cash PV exceeds proportionally-adjusted
  spot at any expiry (`F(T)` non-positive).
- **`forward_curve.DividendYieldInterpolation`** — enum selecting the
  inter-pillar interpolation policy. ``FORWARD_YIELD_FLAT`` (default): the
  cumulative yield ``Q(T) = q(T) * T`` is piecewise linear in ``T`` between
  pillars, equivalently the instantaneous forward dividend yield is
  piecewise constant on each ``(T_{i-1}, T_i]`` — the equity analogue of the
  log-linear-in-DF rates convention. ``LINEAR_IN_YIELD``: ``q(T)`` itself is
  piecewise linear in ``T``; simpler but not arbitrage-aware. Both modes
  agree at pillars and extrapolate flat in ``q`` outside the grid.
- **`dividends.py`** — `DividendKind` enum (`CASH` / `PROPORTIONAL`) and
  `DiscreteDividend(ex_date, amount, kind)` frozen dataclass. Cash amounts
  must be strictly positive; proportional amounts lie in `[0, 1)`. Combined
  multiplicatively in the forward formula per the Hull convention.
- **`quotes.py`** — frozen dataclass quotes consumed by
  `EquityForwardCurveBootstrapper`:
  - `DividendYieldQuote(maturity_date, continuous_yield)` — a point on the
    equity dividend-yield term structure. Negative yields are allowed
    (hard-to-borrow names); non-finite yields raise `ValueError`.
  - `ForwardQuote(maturity_date, forward_price)` — a market-observed
    forward (futures, EFP, OTC forward). Requires `forward_price > 0`
    and finite; no static no-arbitrage check against spot / DF is enforced
    here because that requires knowing the dividend / borrow assumptions,
    which the bootstrapper exists to solve.
  - `BorrowRateQuote(maturity_date, continuous_borrow_rate)` — a point on
    the borrow / repo term structure. Convention: the rate is the
    **additional yield earned by a long-stock holder who lends out the
    share**, so positive values depress the forward (matching the
    empirical behaviour of hard-to-borrow names). Negative rates are
    allowed; non-finite rates raise `ValueError`.

  Equity quotes are not subclasses of
  `market_structures.rates.quotes.MarketQuote` — the equity bootstrap target
  is solved per-pillar in closed form, so the `npv()` residual contract is
  not applicable.
- **`bootstrapper.py`** — `EquityForwardCurveBootstrapper(spot, zero_curve)`:
  closed-form bootstrap consuming a heterogeneous list of `ForwardQuote |
  DividendYieldQuote`. Each `ForwardQuote` solves
  ``q_i = -log(F_i * DF(T_i) / S0) / T_i`` directly; each
  `DividendYieldQuote` stores its yield verbatim. Quotes are sorted by
  maturity; duplicates on the same date (across types) are rejected.
  Interpolation policy is forwarded to the resulting curve. INFO log on
  entry/exit; no per-iteration DEBUG (no iteration).

## Relationship to `market_structures/volatility/forward.py`

`EquityForward` (flat-yield only) remains in place under `volatility/`.
`EquityForwardCurve` is a strict superset; existing call sites are unchanged.
All five roadmap PRs are shipped. The bootstrapper does **not** yet
decompose `ForwardQuote`s into separate dividend and borrow components —
that joint inversion requires either a known dividend strip (to solve for
borrow) or a known borrow strip (to solve for dividend), and is left to a
follow-up PR once a real consumer needs it. Deprecation of `EquityForward`
is deliberately out of scope — it stays as the minimal flat-`q` utility
for notebooks.

## Invariants

- The time axis is ACT/365. Pillar grids are strictly positive, strictly
  increasing year fractions; yield extrapolation outside the grid is **flat**
  in ``q``.
- `EquityForwardCurve` duck-types as
  `market_structures.volatility.surface.ForwardCallable`; any change to its
  ``__call__`` signature must be mirrored by `EquityForward`.
- No DB persistence. Curves consume in-memory user-supplied inputs (spot,
  zero curve, pillar grid), consistent with the project's DB-deprecation
  direction.
- Equity quotes (introduced in PR 2 / PR 4) are **not** added to
  `QuoteHierarchy._RANK` in `market_structures/rates/bootstrapper.py`; that
  hierarchy is rates-bootstrap-specific.

## Logging convention

`forward_curve.py` and `bootstrapper.py` use
`logger = logging.getLogger(__name__)` and emit one INFO line per
`EquityForwardCurve` construction (spot, pillar count, interpolation mode,
discrete-dividend count, reference date) and one INFO line per
`EquityForwardCurveBootstrapper.bootstrap` call on entry and on completion.
No hot-loop DEBUG (the bootstrap is closed-form per pillar).
