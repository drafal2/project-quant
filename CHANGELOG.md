# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
