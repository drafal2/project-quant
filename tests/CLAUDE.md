# tests/

Pytest suite covering schedule generation, calendars, day count conventions, holiday repository, zero curve, interpolators, bootstrapper, survival curve, and CDS pricing.

## Fixture contract

- **`conftest.py`** — `seeded_test_db` autouse fixture: redirects the global DB to a temp file via `set_db_path()`, calls `init_db()`, and seeds holidays for 2020–2029. All tests run in isolation with no access to `quant.db`.

Tests must rely on this fixture for any DB access; never read or write `quant.db` directly.

## Conventions

- One test file per source module (`test_<module>.py`).
- Use the venv interpreter when running locally: `.venv\Scripts\python -m pytest tests/ -q`.
