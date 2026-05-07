"""Database initialisation and holiday seeding entry point."""

import logging
import sqlite3

from database.connection import get_db_path
from database.holidays import create_holidays_table
from scripts.holiday_generators import _eur_holidays, _gbp_holidays, _pln_holidays, _usd_holidays

logger = logging.getLogger(__name__)

# Register a create_<name>_table(conn) function here for each new feature.
_TABLE_CREATORS = [
    create_holidays_table,
]

_HOLIDAY_CALENDARS = [
    ("USD", _usd_holidays),
    ("EUR", _eur_holidays),
    ("GBP", _gbp_holidays),
    ("PLN", _pln_holidays),
]

YEAR_FROM = 2000
YEAR_TO = 2100


def init_db() -> None:
    """Create all registered domain tables in the database.

    Iterates over ``_TABLE_CREATORS`` and executes each DDL function against
    the active database path returned by ``get_db_path()``.
    """
    with sqlite3.connect(get_db_path()) as conn:
        for create in _TABLE_CREATORS:
            create(conn)


def _seed_holidays(
    conn: sqlite3.Connection,
) -> None:
    """Populate the holidays table for all calendars from YEAR_FROM to YEAR_TO.

    Parameters
    ----------
    conn
        Active SQLite connection on which the inserts are executed. Existing
        holiday rows are cleared before re-seeding.
    """
    conn.execute("DELETE FROM holidays")
    for year in range(YEAR_FROM, YEAR_TO + 1):
        for calendar, fn in _HOLIDAY_CALENDARS:
            for d, description in fn(year).items():
                conn.execute(
                    "INSERT OR IGNORE INTO holidays (calendar, label, date, description) VALUES (?, ?, ?, ?)",
                    (calendar, "BASE", d.isoformat(), description),
                )


if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging()

    init_db()
    with sqlite3.connect(get_db_path()) as conn:
        _seed_holidays(conn)
    logger.info("Initialised quant.db with data for %d-%d.", YEAR_FROM, YEAR_TO)
