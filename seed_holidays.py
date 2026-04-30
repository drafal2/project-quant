import sqlite3
from irs_schedule.db import init_db, get_db_path
from irs_schedule.calendars import _usd_holidays, _eur_holidays, _gbp_holidays

CALENDARS = [
    ("USD", _usd_holidays),
    ("EUR", _eur_holidays),
    ("GBP", _gbp_holidays),
]

YEAR_FROM = 2000
YEAR_TO = 2050

init_db()

with sqlite3.connect(get_db_path()) as conn:
    for year in range(YEAR_FROM, YEAR_TO + 1):
        for calendar, fn in CALENDARS:
            for d in fn(year):
                conn.execute(
                    "INSERT OR IGNORE INTO holidays (calendar, label, date) VALUES (?, ?, ?)",
                    (calendar, "BASE", d.isoformat()),
                )

print(f"Seeded holidays.db with BASE holidays for {YEAR_FROM}–{YEAR_TO}.")
