# credit/

Prices single-name Credit Default Swaps using a bootstrapped survival curve.

## Layout

- **`quotes.py`** — `CdsQuote`: tenor-based CDS spread quote bundling spread, tenor, spot_lag, pay_frequency, calendar, bdc, dcc, stub_type, `payment_lag: int = 0`, and `maturity_reference: MaturityReference` (`ACCRUAL_END` default or `PAYMENT_DATE`). `maturity_date(reference_date)` and `schedule(reference_date)` resolve dates lazily at bootstrap time. `bumped(delta)` returns a new quote with shifted spread.
- **`survival_curve.py`** — `SurvivalCurve`: piecewise-constant hazard rate curve. `from_cds_spreads(reference_date, quotes, discount_curve, recovery_rate)` classmethod bootstraps from a `list[CdsQuote]` via bisection per pillar. `bump(delta)` re-bootstraps via `CdsQuote.bumped(delta)` for CS01. Module-level `_par_spread_from_schedule()` helper used by bootstrap and tests.
- **`cds.py`** — `SingleNameCDS`: pricer with `premium_leg_pv`, `protection_leg_pv`, `rpv01`, `par_spread`, `mtm`, `cs01` (1 bp bump-and-rebootstrap), and `rr01` (1% recovery bump, sticky hazard rates).

## Numerical conventions

Protection and accrued-premium integrals use the midpoint discount factor approximation: `df_avg * (Q_s − Q_e)`, which correctly vanishes at zero hazard rate.

## Logging convention

`survival_curve.py` uses `logger = logging.getLogger(__name__)` and follows the project-wide pattern: INFO summary on entry/exit of `from_cds_spreads()` and once per pillar bisection (converged-in-N or WARNING on hitting the 100-iteration cap), plus DEBUG per-iteration traces guarded by `logger.isEnabledFor(logging.DEBUG)`. Any new solver added under `credit/` should follow this same shape.
