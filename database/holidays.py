"""Holiday table DDL and repository for CRUD operations on holiday dates."""

import sqlite3
from datetime import date

from .connection import get_db_path


def create_holidays_table(
    conn: sqlite3.Connection,
) -> None:
    """Create the holidays table if it does not already exist.

    Parameters
    ----------
    conn
        Active SQLite connection on which the DDL statement is executed.
    """
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
    """SQLite-backed store for holiday dates."""

    def add(
        self,
        calendar: str,
        date_: date,
        description: str,
        label: str = "BASE",
    ) -> None:
        """Insert a holiday; silently ignores duplicates.

        Parameters
        ----------
        calendar
            Calendar identifier (e.g. ``"USD"``, ``"EUR"``).
        date_
            Holiday date to insert.
        description
            Human-readable name of the holiday (e.g. ``"Christmas Day"``).
        label
            Holiday set label within the calendar. Defaults to ``"BASE"``.
        """
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO holidays (calendar, label, date, description) VALUES (?, ?, ?, ?)",
                (calendar, label, date_.isoformat(), description),
            )

    def remove(
        self,
        calendar: str,
        date_: date,
        label: str = "BASE",
    ) -> None:
        """Delete a holiday; no-op if not found.

        Parameters
        ----------
        calendar
            Calendar identifier (e.g. ``"USD"``, ``"EUR"``).
        date_
            Holiday date to remove.
        label
            Holiday set label within the calendar. Defaults to ``"BASE"``.
        """
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute(
                "DELETE FROM holidays WHERE calendar = ? AND label = ? AND date = ?",
                (calendar, label, date_.isoformat()),
            )

    def get_by_year(
        self,
        calendar: str,
        year: int,
        label: str = "BASE",
    ) -> frozenset[date]:
        """Return all holiday dates for a given calendar, label, and year.

        Parameters
        ----------
        calendar
            Calendar identifier (e.g. ``"USD"``, ``"EUR"``).
        year
            Calendar year to query.
        label
            Holiday set label within the calendar. Defaults to ``"BASE"``.

        Returns
        -------
        frozenset[date]
            Immutable set of holiday dates for the requested year.
        """
        with sqlite3.connect(get_db_path()) as conn:
            rows = conn.execute(
                "SELECT date FROM holidays "
                "WHERE calendar = ? AND label = ? AND date BETWEEN ? AND ?",
                (calendar, label, f"{year}-01-01", f"{year}-12-31"),
            ).fetchall()
        return frozenset(date.fromisoformat(row[0]) for row in rows)

    def get_all(
        self,
        calendar: str,
        label: str = "BASE",
    ) -> frozenset[date]:
        """Return all holiday dates for a given calendar and label across all years.

        Parameters
        ----------
        calendar
            Calendar identifier (e.g. ``"USD"``, ``"EUR"``).
        label
            Holiday set label within the calendar. Defaults to ``"BASE"``.

        Returns
        -------
        frozenset[date]
            Immutable set of all holiday dates across every stored year.
        """
        with sqlite3.connect(get_db_path()) as conn:
            rows = conn.execute(
                "SELECT date FROM holidays WHERE calendar = ? AND label = ?",
                (calendar, label),
            ).fetchall()
        return frozenset(date.fromisoformat(row[0]) for row in rows)
