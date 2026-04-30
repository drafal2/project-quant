import sqlite3

from database import get_db_path, init_db
from scripts.holiday_generators import _eur_holidays, _gbp_holidays, _pln_holidays, _usd_holidays

CALENDARS = [
    ("USD", _usd_holidays),
    ("EUR", _eur_holidays),
    ("GBP", _gbp_holidays),
    ("PLN", _pln_holidays),
]

YEAR_FROM = 2000
YEAR_TO = 2050

init_db()

with sqlite3.connect(get_db_path()) as conn:
    conn.execute("DELETE FROM holidays")
    for year in range(YEAR_FROM, YEAR_TO + 1):
        for calendar, fn in CALENDARS:
            for d, description in fn(year).items():
                conn.execute(
                    "INSERT OR IGNORE INTO holidays (calendar, label, date, description) VALUES (?, ?, ?, ?)",
                    (calendar, "BASE", d.isoformat(), description),
                )

print(f"Seeded quant.db with BASE holidays for {YEAR_FROM}–{YEAR_TO}.")
