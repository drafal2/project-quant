# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python -m pytest tests/ -q

# Run a single test file
python -m pytest tests/test_schedule.py -q

# Run a single test by name
python -m pytest tests/test_schedule.py::test_function_name -q

# Launch the Dash web UI
python app.py

# Run the CLI usage example
python example.py
```

## Architecture

This is a Python quantitative finance library for generating **IRS (Interest Rate Swap) accrual schedules**, exposed via a Dash web UI.

### Core Library (`irs_schedule/`)

The library computes periodic payment schedules with configurable financial conventions:

- **`schedule.py`** — `Schedule` class: main entry point. Takes effective/termination dates, frequency, day count convention, business day adjustment, holiday calendar, and stub type. Generates a list of `Period` objects.
- **`models.py`** — `Period` dataclass (frozen): holds start/end dates, adjusted dates, and the day count fraction for each period.
- **`enums.py`** — All domain enums: `Frequency`, `DayCountConvention`, `BusinessDayAdjustment`, `HolidayCalendarType`, `StubType`.
- **`calendars.py`** — `HolidayCalendar`: loads holidays from SQLite and adjusts dates per business day convention (following, preceding, modified following, unadjusted).
- **`day_count.py`** — `day_count_fraction()`: computes DCF for ACT/360, ACT/365, 30/360, and ACT/ACT ISDA conventions.
- **`db.py`** — SQLite interface for loading holiday data from `holidays.db` (covers 2000–2050).

### Data Flow

```
app.py (user inputs)
    → Schedule(effective, termination, frequency, dcc, bda, calendar, stub)
        → HolidayCalendar.adjust(date) [uses db.py → holidays.db]
        → day_count_fraction(start, end, dcc)
    → List[Period] (displayed as table)
```

### Scripts (`scripts/`)

- **`holiday_generators.py`** — Computes holiday dates for USD, EUR, GBP, and PLN calendars (handles Easter, observed rules, etc.).
- **`seed_holidays.py`** — Seeds the SQLite DB using the holiday generators.

### Tests (`tests/`)

- **`conftest.py`** — Pytest fixture that auto-seeds an in-memory or temp test DB with generated holidays.
- **`test_schedule.py`** — Schedule generation tests (stubs, frequencies, date rolling).
- **`test_calendars.py`** — Business day adjustment logic.
- **`test_day_count.py`** — Day count convention calculations.
- **`test_integration.py`** — End-to-end tests across multiple conventions and calendars.

### Holiday Database

`holidays.db` is a SQLite file committed to the repo. To regenerate it, run `python scripts/seed_holidays.py`. Tests use an auto-seeded fixture and do not depend on `holidays.db` directly.
