import sqlite3

from .connection import get_db_path


def init_db() -> None:
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                calendar    TEXT NOT NULL,
                label       TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                PRIMARY KEY (calendar, label, date)
            )
        """)
