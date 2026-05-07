# database/

Manages the SQLite connection and per-domain table definitions. The shared DB (`quant.db`) holds reference data for all packages.

## Layout

- **`connection.py`** — global DB path (`quant.db`); `set_db_path()` lets tests and notebooks swap in an alternate DB without touching `quant.db`.
- **`holidays.py`** — `create_holidays_table(conn)` DDL and `HolidayRepository` (`add` / `remove` / `get_by_year` / `get_all`).

## Adding a new domain table

1. Create `database/<name>.py` exposing `create_<name>_table(conn)` (DDL only) and a repository class for read/write access.
2. Append `create_<name>_table` to `_TABLE_CREATORS` in `scripts/initialise.py` so `init_db()` provisions it.
3. If the table needs seed data, add a `_seed_<name>()` helper in `scripts/initialise.py` and call it from the `__main__` block.
