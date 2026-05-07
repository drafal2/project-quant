# market_structures/

Objects for representing market data: yield curves, market quotes, bootstrappers, and interpolators.

## Layout

- **`rates/curve.py`** — `ZeroCurve`: interpolated zero-rate curve with discount factor, zero rate, and forward rate queries. Supports pluggable interpolators and compounding conventions. For dates before the first pillar, discount factors are log-linearly interpolated from the implicit (t=0, DF=1) anchor at `reference_date`. Accepts an optional `quotes: list[MarketQuote]` parameter (populated automatically by the bootstrapper); `summary()` prints a formatted table of instrument type, start date, maturity date, tenor, market quote, discount factor, and zero rate per pillar.
- **`rates/quotes.py`** — `MarketQuote` ABC and four concrete types: `DepositQuote`, `FuturesQuote` (IMM-dated, with convexity adjustment), `OISQuote` (self-discounting, continuous-approximation floating leg), `SwapQuote` (multi-curve: external `discount_curve`). `OISQuote` and `SwapQuote` accept `payment_lag: int = 0` (business days after accrual end) and `maturity_reference: MaturityReference` (`ACCRUAL_END` default or `PAYMENT_DATE`) controlling which date is used as the bootstrapping pillar. All concrete types implement `start_date()` (accrual start / IMM date), `quote_value()` (raw market observable), `maturity_date()`, `initial_guess()`, and `npv()`.
- **`rates/bootstrapper.py`** — `ZeroCurveBootstrapper`: sequential pillar-by-pillar bootstrap using Newton-Raphson with forward finite-difference derivative. Instruments sorted by maturity; `RuntimeError` on NR non-convergence. `QuoteHierarchy` resolves maturity-date collisions by fixed instrument-type priority (deposit > OIS > swap > futures); the lower-priority quote is discarded with a `UserWarning`.
- **`interpolation/interpolators.py`** — `LinearInterpolator`, `LogLinearInterpolator` (market standard for discount factors), `V2TInterpolator` (variance-to-time, for implied vol).

## Invariants

- Every new `MarketQuote` subclass must be added to `QuoteHierarchy._RANK` in `bootstrapper.py`, otherwise maturity-date collisions involving the new type cannot be resolved at bootstrap time.

## Logging convention

`bootstrapper.py` uses `logger = logging.getLogger(__name__)` and follows the project-wide pattern: INFO summaries on entry/exit of `bootstrap()` and once per Newton-Raphson call (converged-in-N or non-convergence ERROR before raising), plus DEBUG per-iteration traces guarded by `logger.isEnabledFor(logging.DEBUG)`. Any new solver added under `market_structures/` should follow this same INFO-summary + guarded-DEBUG-per-iteration shape.
