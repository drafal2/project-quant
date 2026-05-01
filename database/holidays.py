import sqlite3
from datetime import date

from .connection import get_db_path


def create_holidays_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            calendar    TEXT NOT NULL,
            label       TEXT NOT NULL,
            date        TEXT NOT NULL,
            description TEXT,
            PRIMARY KEY (calendar, label, date)
        )
    """)


class HolidayRepository:
    def add(self, calendar: str, date_: date, description: str, label: str = "BASE") -> None:
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO holidays (calendar, label, date, description) VALUES (?, ?, ?, ?)",
                (calendar, label, date_.isoformat(), description),
            )

    def remove(self, calendar: str, date_: date, label: str = "BASE") -> None:
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute(
                "DELETE FROM holidays WHERE calendar = ? AND label = ? AND date = ?",
                (calendar, label, date_.isoformat()),
            )

    def get_by_year(self, calendar: str, year: int, label: str = "BASE") -> frozenset[date]:
        with sqlite3.connect(get_db_path()) as conn:
            rows = conn.execute(
                "SELECT date FROM holidays "
                "WHERE calendar = ? AND label = ? AND date BETWEEN ? AND ?",
                (calendar, label, f"{year}-01-01", f"{year}-12-31"),
            ).fetchall()
        return frozenset(date.fromisoformat(row[0]) for row in rows)

    def get_all(self, calendar: str, label: str = "BASE") -> frozenset[date]:
        with sqlite3.connect(get_db_path()) as conn:
            rows = conn.execute(
                "SELECT date FROM holidays WHERE calendar = ? AND label = ?",
                (calendar, label),
            ).fetchall()
        return frozenset(date.fromisoformat(row[0]) for row in rows)
