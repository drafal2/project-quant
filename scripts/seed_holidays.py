import sqlite3
from irs_schedule.db import get_db_path
from scripts.holiday_generators import _usd_holidays, _eur_holidays, _gbp_holidays, _pln_holidays

CALENDARS = [
    ("USD", _usd_holidays),
    ("EUR", _eur_holidays),
    ("GBP", _gbp_holidays),
    ("PLN", _pln_holidays),
]

YEAR_FROM = 2000
YEAR_TO = 2050

with sqlite3.connect(get_db_path()) as conn:
    conn.execute("DROP TABLE IF EXISTS holidays")
    conn.execute("""
        CREATE TABLE holidays (
            calendar    TEXT NOT NULL,
            label       TEXT NOT NULL,
            date        TEXT NOT NULL,
            description TEXT,
            PRIMARY KEY (calendar, label, date)
        )
    """)
    for year in range(YEAR_FROM, YEAR_TO + 1):
        for calendar, fn in CALENDARS:
            for d, description in fn(year).items():
                conn.execute(
                    "INSERT OR IGNORE INTO holidays (calendar, label, date, description) VALUES (?, ?, ?, ?)",
                    (calendar, "BASE", d.isoformat(), description),
                )

print(f"Seeded holidays.db with BASE holidays for {YEAR_FROM}–{YEAR_TO}.")
