# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Always use `.venv\Scripts\python` instead of `python` to ensure the venv interpreter is used.

```bash
# Run all tests
.venv\Scripts\python -m pytest tests/ -q

# Run a single test file
.venv\Scripts\python -m pytest tests/test_schedule.py -q

# Run a single test by name
.venv\Scripts\python -m pytest tests/test_schedule.py::test_function_name -q
```

## Git

GitHub is configured to auto-delete remote branches after a PR is merged. Local branches must be cleaned up manually:

```powershell
# Delete local branches whose remote has been deleted
git fetch --prune
git branch -vv | grep "gone" | ForEach-Object { ($_ -split '\s+')[1] } | ForEach-Object { git branch -d $_ }
```

## Architecture

A Python quantitative finance toolkit. Each domain lives in its own library package; the shared SQLite database (`quant.db`) holds reference data for all domains. `examples/` contains Jupyter notebooks that document each package.

### Database (`database/`)

Manages the connection and per-domain table definitions:

- **`connection.py`** — global DB path (`quant.db`); `set_db_path()` lets tests swap in a temp DB without touching `quant.db`
- **`holidays.py`** — `create_holidays_table(conn)` DDL and `HolidayRepository` (add/remove/get_by_year/get_all)

### Initialisation (`scripts/initialise.py`)

Single entry point for DB setup. `init_db()` runs all registered `create_<name>_table` functions from `_TABLE_CREATORS`. `_seed_holidays()` populates the holidays table; it is called when run as `__main__`, and exposed for notebooks. To add a new domain table: define `create_<name>_table(conn)` in `database/<name>.py` and append it to `_TABLE_CREATORS`.

### Market Conventions (`market_conventions/`)

Shared enums used across all packages:

- **`business_day.py`** — `BusinessDayConvention` (UNADJUSTED/FOLLOWING/PRECEDING/MODIFIED_FOLLOWING)
- **`compounding.py`** — `CompoundingType` (CONTINUOUS/SIMPLE/COMPOUNDED) and `CompoundingFrequency` (ANNUAL/SEMI_ANNUAL/QUARTERLY/MONTHLY)
- **`day_count.py`** — `DayCountConvention` (ACT_360/ACT_365_FIXED/THIRTY_360_BOND/ACT_ACT_ISDA)
- **`stub.py`** — `StubType` (SHORT_FRONT/LONG_FRONT/SHORT_BACK/LONG_BACK)

### Market Structures (`market_structures/`)

Objects for representing market data:

- **`rates/curve.py`** — `ZeroCurve`: interpolated zero-rate curve with discount factor, zero rate, and forward rate queries. Supports pluggable interpolators and compounding conventions.
- **`interpolation/interpolators.py`** — `LinearInterpolator`, `LogLinearInterpolator` (market standard for discount factors), `V2TInterpolator` (variance-to-time, for implied vol).

### Schedules Library (`schedules/`)

Generates accrual schedules for fixed income instruments (IRS, bonds):

- **`schedule.py`** — `Schedule` class (main entry point) and `Period` dataclass (frozen: accrual start/end, pay date, DCF). `Frequency` enum lives here (DAILY/MONTHLY/QUARTERLY/SEMI_ANNUAL/ANNUAL).
- **`calendars.py`** — `CalendarType` enum (USD/EUR/GBP/PLN) and `HolidayCalendar` (holiday lookup + date adjustment). Lazy-caches holidays per year via `HolidayRepository`.
- **`day_count.py`** — `day_count_fraction()`: ACT/360, ACT/365 Fixed, 30/360 Bond Basis, ACT/ACT ISDA.

### Credit (`credit/`)

Prices single-name Credit Default Swaps using a bootstrapped survival curve:

- **`survival_curve.py`** — `SurvivalCurve`: piecewise-constant hazard rate curve. `from_spreads()` classmethod bootstraps from market CDS spreads via bisection per pillar. `bump(delta)` re-bootstraps with shifted spreads for CS01. Module-level `_par_spread_from_schedule()` helper used by bootstrap and tests.
- **`cds.py`** — `SingleNameCDS`: pricer with `premium_leg_pv`, `protection_leg_pv`, `rpv01`, `par_spread`, `mtm`, `cs01` (1 bp bump-and-rebootstrap), and `rr01` (1% recovery bump, sticky hazard rates).

Protection and accrued-premium integrals use the midpoint discount factor approximation: `df_avg * (Q_s − Q_e)`, which correctly vanishes at zero hazard rate.

### Tests (`tests/`)

- **`conftest.py`** — `seeded_test_db` autouse fixture: redirects the global DB to a temp file, calls `init_db()`, and seeds holidays for 2020–2029. All tests run in isolation with no access to `quant.db`.
- Test files cover schedule generation, calendars, day count conventions, holiday repository, zero curve, interpolators, survival curve, and CDS pricing.

### Examples (`examples/`)

Jupyter notebooks that demonstrate each library package. Each notebook:
- adds the project root to `sys.path`
- redirects the DB to `examples/demo.db` via `set_db_path()` (never touches `quant.db`)
- seeds `demo.db` on first run (idempotent — skips if data already present)
