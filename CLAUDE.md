# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# First-time setup: create and seed the database
python -m scripts.initialise

# Run all tests
python -m pytest tests/ -q

# Run a single test file
python -m pytest tests/test_schedule.py -q

# Run a single test by name
python -m pytest tests/test_schedule.py::test_function_name -q

# Run a usage example
python example.py
```

## Architecture

A Python quantitative finance toolkit demonstrating quant skills across multiple financial domains. Each domain lives in its own library package; the shared SQLite database (`quant.db`) holds reference data for all domains.

### Database (`database/`)

Manages the connection and per-domain table definitions:

- **`connection.py`** — global DB path (`quant.db`); `set_db_path()` used by tests to swap in a temp DB
- **`holidays.py`** — `create_holidays_table(conn)` and `load_holidays()` query

### Initialisation (`scripts/initialise.py`)

Single entry point for DB setup. Owns `init_db()` (calls all registered `create_<name>_table` functions) and seeds all reference data. To add a new domain table: define `create_<name>_table(conn)` in `database/<name>.py` and register it in `_TABLE_CREATORS`.

### IRS Schedule Library (`irs_schedule/`)

Generates interest rate swap accrual schedules with configurable financial conventions:

- **`schedule.py`** — `Schedule` class: main entry point. Generates a list of `Period` objects from effective/termination dates, frequency, day count convention, business day convention, calendar, and stub type.
- **`models.py`** — `Period` dataclass (frozen): accrual start/end, pay date, day count fraction.
- **`enums.py`** — `Frequency`, `DayCountConvention`, `BusinessDayConvention`, `CalendarType`, `StubType`.
- **`calendars.py`** — `HolidayCalendar`: loads holidays from SQLite and adjusts dates per business day convention.
- **`day_count.py`** — `day_count_fraction()`: ACT/360, ACT/365, 30/360, ACT/ACT ISDA.
- **`db.py`** — thin wrapper re-exporting `get_db_path`, `set_db_path`, `load_holidays` from `database/`.

### Scripts (`scripts/`)

- **`initialise.py`** — DB setup and seeding (see above).
- **`holiday_generators.py`** — computes holiday dates for USD, EUR, GBP, PLN calendars.

### Tests (`tests/`)

- **`conftest.py`** — `seeded_test_db` fixture: spins up a temp DB, calls `init_db()`, and seeds holidays for 2020–2029. Applied to all tests automatically.
- **`test_schedule.py`** — schedule generation (stubs, frequencies, date rolling).
- **`test_calendars.py`** — business day adjustment logic.
- **`test_day_count.py`** — day count convention calculations.
- **`test_integration.py`** — end-to-end tests across conventions and calendars.
