# credit/

Prices single-name Credit Default Swaps on a bootstrapped credit curve.

## Layout

- **`quotes.py`** — `CdsQuote`: tenor-based CDS spread quote bundling spread, tenor, spot_lag, pay_frequency, calendar, bdc, dcc, stub_type, `payment_lag: int = 0`, and `maturity_reference: MaturityReference` (`ACCRUAL_END` default or `PAYMENT_DATE`). `maturity_date(reference_date)` and `schedule(reference_date)` resolve dates lazily at bootstrap time. `bumped(delta)` returns a new quote with shifted spread (used for finite-difference CS01).
- **`curve.py`** — `CreditCurve` (deterministic-intensity model) and `InterpolationVariable` enum. The interpolation variable selects how the curve is parameterised between pillars: `SURVIVAL_PROBABILITY` (linear in Q), `DEFAULT_SPREAD` (linear in cumulative spread s with Q = exp(-s·t)), or `FORWARD_DEFAULT_SPREAD` (piecewise-constant forward hazard λ, ISDA-style — default). Exposes `non_default_probability(d)`, `default_probability(d)`, `default_spread(d)`, `forward_default_spread(start, end)`, and `summary()`.
- **`bootstrapper.py`** — `CreditCurveBootstrapper` with `BootstrapMode.SEQUENTIAL` (scalar Newton-Raphson per pillar; pillar i solved holding pillars < i fixed) and `BootstrapMode.GLOBAL` (multivariate Newton-Raphson on the full NPV vector system with a finite-difference Jacobian and Gaussian-elimination linear solve). Both modes converge to the same calibrated curve when the system is exactly determined and the interpolation is causal. Module-level `_solve_linear_system()` helper (Gaussian elimination with partial pivoting) drives the global step.
- **`pricing.py`** — `SingleNameCDS`: pricer with `pricing_date`, schedule-based input, and `CdsSide` (BUYER/SELLER) for NPV sign convention. Methods: `protection_leg_pv`, `premium_leg_running_pv`, `accrual_on_default_pv`, `premium_leg_pv`, `rpv01`, `par_spread`, `npv`, plus `premium_leg_summary` and `protection_leg_summary` formatted per-period breakdowns. Mid-life pricing is handled by the constructor: periods whose `accrual_end <= pricing_date` are dropped; live periods retain their original DCF (the running coupon is contractually fixed for the full accrual period).

## Numerical conventions

Protection and accrued-premium integrals use the midpoint discount factor approximation: `df_avg * (Q_s − Q_e)`, which correctly vanishes at zero hazard rate and is consistent with standard ISDA-style CDS pricing.

## Sensitivities

`SingleNameCDS` does not expose closed-form sensitivities. Compute first-order risk by **bump-and-rebootstrap**: shift the relevant input (CDS spreads via `CdsQuote.bumped(delta)`, recovery rate, or the discount curve), re-bootstrap a fresh `CreditCurve`, and re-price. The credit curve is itself a derived quantity, so naive in-place differentiation through the closed-form pricer with the curve held fixed gives the wrong answer. See `examples/03_cds_pricing.ipynb` for parallel CS01, bucket CS01, RR01, and IR01.

## Logging convention

`bootstrapper.py` uses `logger = logging.getLogger(__name__)` and follows the project-wide pattern: INFO summary on entry/exit of `bootstrap()` and once per Newton-Raphson call (converged-in-N or non-convergence ERROR before raising), plus DEBUG per-iteration traces guarded by `logger.isEnabledFor(logging.DEBUG)`. Any new solver added under `credit/` should follow this same INFO-summary + guarded-DEBUG-per-iteration shape.
