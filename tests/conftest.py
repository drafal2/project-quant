import sqlite3

import pytest

import irs_schedule.db as irsdb
from scripts.holiday_generators import _eur_holidays, _gbp_holidays, _pln_holidays, _usd_holidays

_CALENDARS = [
    ("USD", _usd_holidays),
    ("EUR", _eur_holidays),
    ("GBP", _gbp_holidays),
    ("PLN", _pln_holidays),
]


@pytest.fixture(autouse=True)
def seeded_test_db(tmp_path):
    db_file = str(tmp_path / "test_holidays.db")
    irsdb.set_db_path(db_file)

    with sqlite3.connect(db_file) as conn:
        conn.execute("""
            CREATE TABLE holidays (
                calendar    TEXT NOT NULL,
                label       TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                PRIMARY KEY (calendar, label, date)
            )
        """)
        for year in range(2020, 2030):
            for calendar, fn in _CALENDARS:
                for d, description in fn(year).items():
                    conn.execute(
                        "INSERT OR IGNORE INTO holidays VALUES (?, ?, ?, ?)",
                        (calendar, "BASE", d.isoformat(), description),
                    )

    yield

    irsdb.set_db_path(str(__import__("pathlib").Path(irsdb.__file__).parent.parent / "holidays.db"))
