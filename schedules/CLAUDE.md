# schedules/

Generates accrual schedules for fixed income instruments (IRS, bonds) and provides the calendar / day-count primitives used by other packages.

## Layout

- **`schedule.py`** — `Schedule` class (main entry point) and `Period` dataclass (frozen: accrual start/end, pay date, DCF). `Frequency` enum lives here (DAILY / MONTHLY / QUARTERLY / SEMI_ANNUAL / ANNUAL). `payment_lag: int = 0` offsets `pay_date` by that many business days beyond the BDC-adjusted period end. `summary()` prints a header block (effective/termination dates, frequency, DCC, BDC, calendar, payment lag) followed by a per-period table (index, accrual start/end, pay date, days, DCF).
- **`calendars.py`** — `CalendarType` enum (USD/EUR/GBP/PLN) and `HolidayCalendar` (holiday lookup + date adjustment). Lazy-caches holidays per year via `HolidayRepository`. `add_holiday(d, persist=False)` updates the cache and optionally persists to DB. `add_business_days(d, n)` advances a date by `n` business days.
- **`day_count.py`** — `day_count_fraction()`: ACT/360, ACT/365 Fixed, 30/360 Bond Basis, ACT/ACT ISDA.
- **`date_utils.py`** — shared calendar-arithmetic utilities imported by rate and CDS quote types: `parse_tenor`, `add_spot_lag`, `add_tenor`, `imm_date` (3rd-Wednesday IMM date from a code such as `"H26"`).
