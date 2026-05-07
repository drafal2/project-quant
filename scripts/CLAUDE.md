# scripts/

Single entry point for database setup plus reference-data generators.

## Layout

- **`initialise.py`** — `init_db()` runs all registered `create_<name>_table` functions from `_TABLE_CREATORS`. `_seed_holidays()` populates the holidays table; it is called when the module is run as `__main__`, and is also exposed for notebooks.
- **`holiday_generators.py`** — produces holiday date sets for each `CalendarType` (USD/EUR/GBP/PLN) consumed by `_seed_holidays()`.

## Adding a new domain table

Define `create_<name>_table(conn)` in `database/<name>.py` and append it to `_TABLE_CREATORS` in `initialise.py`. If the table needs seed data, add a `_seed_<name>()` helper here and call it from the `__main__` block.
