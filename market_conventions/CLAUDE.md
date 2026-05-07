# market_conventions/

Shared enums used across all packages. Pure-data modules with no behaviour beyond enum membership.

## Layout

- **`business_day.py`** — `BusinessDayConvention` (UNADJUSTED / FOLLOWING / PRECEDING / MODIFIED_FOLLOWING)
- **`compounding.py`** — `CompoundingType` (CONTINUOUS / SIMPLE / COMPOUNDED) and `CompoundingFrequency` (ANNUAL / SEMI_ANNUAL / QUARTERLY / MONTHLY)
- **`day_count.py`** — `DayCountConvention` (ACT_360 / ACT_365_FIXED / THIRTY_360_BOND / ACT_ACT_ISDA)
- **`stub.py`** — `StubType` (SHORT_FRONT / LONG_FRONT / SHORT_BACK / LONG_BACK)

Adding a new enum value is a `MINOR` change only if it represents a genuinely new capability across packages; otherwise treat it as `PATCH`.
