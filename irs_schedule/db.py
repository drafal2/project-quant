import sqlite3
from datetime import date
from pathlib import Path

_db_path: str = str(Path(__file__).parent.parent / "holidays.db")


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


def get_db_path() -> str:
    return _db_path


def load_holidays(calendar: str, label: str, year: int) -> frozenset:
    with sqlite3.connect(_db_path) as conn:
        rows = conn.execute(
            "SELECT date FROM holidays "
            "WHERE calendar = ? AND label = ? AND date BETWEEN ? AND ?",
            (calendar, label, f"{year}-01-01", f"{year}-12-31"),
        ).fetchall()
    return frozenset(date.fromisoformat(row[0]) for row in rows)
