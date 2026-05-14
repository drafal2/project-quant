# project-quant

A Python quantitative finance toolkit for building, calibrating, and pricing instruments from scratch — no third-party pricing libraries. The current scope covers interest-rate curve construction, single-name CDS pricing on a bootstrapped survival curve, a Monte Carlo random-number sampling foundation (PRNGs, low-discrepancy sequences, `U -> N` transforms), and an implied-volatility surface layer (Black-76 pricing + Brent inversion + non-parametric surface) — all of which the upcoming equity-basket-autocall pricer will sit on top of. The shared infrastructure (schedules, calendars, day counts, market conventions) is reused across packages. Reference data (holidays, future seed instruments) lives in a shared SQLite database (`quant.db`).

The toolkit is organised as a set of independent library packages under one repo. Each package owns one domain and is documented by its own `CLAUDE.md`; the root `CLAUDE.md` lists the cross-package invariants. Jupyter notebooks under `examples/` walk through each package end-to-end.

## Capabilities

- **Accrual schedules** — IRS/bond-style period generation with `SHORT/LONG × FRONT/BACK` stubs, four business-day conventions, four day-count conventions, USD/EUR/GBP/PLN calendars, and configurable payment lag.
- **Zero-curve bootstrapping** — sequential pillar-by-pillar Newton-Raphson over deposits, IMM futures (with convexity adjustment), OIS, and multi-curve swaps. Pluggable interpolators (linear, log-linear, variance-to-time). Maturity collisions resolved by an explicit instrument-type hierarchy.
- **Credit-curve bootstrapping** — single-name CDS spreads → survival curve, in two modes: scalar Newton-Raphson per pillar (`SEQUENTIAL`) or multivariate NR on the full NPV vector with a finite-difference Jacobian (`GLOBAL`). Three interpolation variables: survival probability, default spread, or piecewise-constant forward hazard (ISDA-style).
- **Single-name CDS pricing** — protection leg, running-premium leg, accrual-on-default, RPV01, par spread, mid-life valuation (live-period DCF preserved). Sensitivities (CS01 parallel/bucket, RR01, IR01) computed by bump-and-rebootstrap.
- **Monte Carlo sampling foundation** — three from-scratch PRNGs (Knuth, L'Ecuyer MRG32k3a, Mersenne Twister), two low-discrepancy sequences (Halton, Sobol with Joe-Kuo 2008 direction numbers up to 1024 dimensions), five `U -> N` transforms (CLT, Box-Muller, Moro, Acklam, Wichura AS241), a factory that enforces the QMC / inversion pairing rule, and diagnostics (KS, chi-square, Anderson-Darling, L2 discrepancy, tail fractions, end-to-end Black-Scholes convergence).
- **Implied-volatility surfaces** — Black-76 pricer in forward-domain form, vega, static no-arbitrage price bounds, and a Brent-based implied-vol inverter. `EquityForward(spot, zero_curve, q)` for ``F(T) = S0 * exp(-q T) / DF(T)``. `VolSurface` / `DifferentiableVolSurface` ABCs anchored on total implied variance ``w(T, k_log) = sigma^2 * T``. `InterpolatedVolSurface` non-parametric surface on a per-slice variable-length log-moneyness grid, with sticky-moneyness time interpolation and flat-vol-in-time boundary extrapolation; full pipeline from option prices (`from_option_prices`) or pre-computed implied vols (`from_implied_vols`).
- **Equity forward curves** — term-structured `EquityForwardCurve` combining a continuous dividend yield, an optional borrow / repo term structure, and an optional discrete-dividend schedule (cash + proportional, Hull convention). Default inter-pillar interpolation is piecewise-flat in instantaneous forward yield (equity analogue of log-linear-in-DF). Constructors for the flat-yield, term-structured, discrete-dividend, and dividend-plus-borrow cases. Closed-form `EquityForwardCurveBootstrapper` solves the dividend pillar from each `ForwardQuote` in one log. Duck-types as the volatility stack's `ForwardCallable`.
- **Library-grade logging** — every module declares `logger = logging.getLogger(__name__)`; output is configured at the entry point via `setup_logging()` driven by `logging.yaml`. Solvers emit INFO summaries and guarded DEBUG per-iteration traces.

## Requirements

- Python 3.11+

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 2. Install the project and dev dependencies
pip install -e ".[dev]"

# 3. Register the venv as a Jupyter kernel (required to run notebooks)
.venv\Scripts\python -m pip install ipykernel
.venv\Scripts\python -m ipykernel install --user --name project-quant --display-name "project-quant"

# 4. Create and seed the database
.venv\Scripts\python -m scripts.initialise
```

## Contributing

If you plan to commit changes to notebooks, install the `nbstripout` git hook to automatically strip cell outputs before each commit:

```bash
.venv\Scripts\nbstripout --install --attributes .gitattributes
```

This is optional but recommended — notebooks committed with outputs produce noisy diffs and bloat the repository.

## Running tests

```bash
.venv\Scripts\python -m pytest tests/ -q
```

## Examples

The `examples/` folder contains Jupyter notebooks that demonstrate each library package. Open them in VS Code or Jupyter and select the `project-quant` kernel. They are the recommended starting point for understanding the toolkit.

| Notebook | Covers |
|---|---|
| `01_schedule_generation.ipynb` | accrual schedules, calendars, day counts, stubs |
| `02_market_structures.ipynb` | zero curves, market quotes, interpolators |
| `03_cds_pricing.ipynb` | single-name CDS legs, RPV01, par spread, mid-life valuation, CS01/RR01/IR01 |
| `04_zero_curve_bootstrapping.ipynb` | sequential NR bootstrap over deposits / futures / OIS / swaps |
| `05_credit_curve_bootstrapping.ipynb` | sequential vs. global NR; three interpolation variables |
| `06_random_number_sampling.ipynb` | PRNGs, Halton/Sobol QMC, five `U -> N` transforms, factory pairing rule, PRNG vs QMC convergence |
| `07_volatility_surfaces_and_local_vol.ipynb` | `InterpolatedVolSurface`, SVI / SSVI fits, arbitrage diagnostics, `ConstantVol` → `BlackTermStructureVol` → `DupireLocalVol`, MC repricing |
| `08_equity_forward_curve.ipynb` | `EquityForwardCurve` — flat / term-structured / discrete-dividend / market-quote-bootstrapped, plugged into `InterpolatedVolSurface` |

## Packages

| Package | Description |
|---|---|
| `market_conventions` | Shared enums (BDC, day count, compounding, stub) used across all packages |
| `schedules` | Accrual schedule generation, holiday calendars, day-count fractions, tenor/IMM date utilities |
| `market_structures` | `ZeroCurve` with pluggable interpolators; deposit/futures/OIS/swap quotes; sequential bootstrapper; term-structured `EquityForwardCurve` (continuous yield + borrow + discrete dividends) with closed-form bootstrapper from `ForwardQuote`s; implied-vol surface foundation (`EquityForward`, Black-76 pricing + Brent inversion, `VolSurface` ABCs, `InterpolatedVolSurface`, SVI / SSVI) |
| `credit` | `CreditCurve` (3 interpolation variants) with sequential and global bootstrappers; `SingleNameCDS` pricer |
| `montecarlo` | Uniform samplers (Knuth, MRG32k3a, MT19937, Halton, Sobol/Joe-Kuo), `U -> N` transforms (CLT, Box-Muller, Moro, Acklam, Wichura AS241), pairing-rule factory, diagnostics, plotting |
| `database` | SQLite connection management and per-domain table DDL/repositories |
| `scripts` | DB initialisation entry point and seed-data generators |
| `tests` | Pytest suite running against an isolated temp DB fixture |
| `examples` | Jupyter notebooks demonstrating each package |
