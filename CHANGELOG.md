# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
