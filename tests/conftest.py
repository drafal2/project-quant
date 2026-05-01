import sqlite3
from pathlib import Path

import pytest

from database import set_db_path
from scripts.holiday_generators import _eur_holidays, _gbp_holidays, _pln_holidays, _usd_holidays
from scripts.initialise import init_db

_CALENDARS = [
    ("USD", _usd_holidays),
    ("EUR", _eur_holidays),
    ("GBP", _gbp_holidays),
    ("PLN", _pln_holidays),
]

_DEFAULT_DB = str(Path(__file__).parent.parent / "quant.db")


@pytest.fixture(autouse=True)
def seeded_test_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    set_db_path(db_file)
    init_db()

    with sqlite3.connect(db_file) as conn:
        for year in range(2020, 2030):
            for calendar, fn in _CALENDARS:
                for d, description in fn(year).items():
                    conn.execute(
                        "INSERT OR IGNORE INTO holidays VALUES (?, ?, ?, ?)",
                        (calendar, "BASE", d.isoformat(), description),
                    )

    yield

    set_db_path(_DEFAULT_DB)
