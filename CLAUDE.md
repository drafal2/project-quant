# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# Install the project and dev dependencies
pip install -e ".[dev]"

# Register the venv as a Jupyter kernel (required to run notebooks)
.venv\Scripts\python -m pip install ipykernel
.venv\Scripts\python -m ipykernel install --user --name project-quant --display-name "project-quant"
```

## Commands

Always use `.venv\Scripts\python` instead of `python` to ensure the venv interpreter is used.

```bash
# First-time setup: create and seed the database
.venv\Scripts\python -m scripts.initialise

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

### Schedules Library (`schedules/`)

Generates accrual schedules for fixed income instruments (IRS, bonds):

- **`schedule.py`** — `Schedule` class (main entry point) and `Period` dataclass (frozen: accrual start/end, pay date, DCF). `Frequency` enum lives here (DAILY/MONTHLY/QUARTERLY/SEMI_ANNUAL/ANNUAL).
- **`conventions.py`** — `DayCountConvention`, `BusinessDayConvention`, `StubType` enums.
- **`calendars.py`** — `CalendarType` enum (USD/EUR/GBP/PLN) and `HolidayCalendar` (holiday lookup + date adjustment). Lazy-caches holidays per year via `HolidayRepository`.
- **`day_count.py`** — `day_count_fraction()`: ACT/360, ACT/365 Fixed, 30/360 Bond Basis, ACT/ACT ISDA.

### Tests (`tests/`)

- **`conftest.py`** — `seeded_test_db` autouse fixture: redirects the global DB to a temp file, calls `init_db()`, and seeds holidays for 2020–2029. All tests run in isolation with no access to `quant.db`.
- Test files cover schedule generation, calendars, day count conventions, the holiday repository, and integration scenarios.

### Examples (`examples/`)

Jupyter notebooks that demonstrate each library package. Each notebook:
- adds the project root to `sys.path`
- redirects the DB to `examples/demo.db` via `set_db_path()` (never touches `quant.db`)
- seeds `demo.db` on first run (idempotent — skips if data already present)
