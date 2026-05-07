"""Global SQLite database path management."""

from pathlib import Path

_db_path: str = str(Path(__file__).parent.parent / "quant.db")


def set_db_path(
    path: str,
) -> None:
    """Override the global database path (used by tests and notebooks).

    Parameters
    ----------
    path
        Absolute or relative path to the SQLite database file. Replaces the
        default ``quant.db`` path for the duration of the process.
    """
    global _db_path
    _db_path = path


def get_db_path() -> str:
    """Return the current global database path.

    Returns
    -------
    str
        Path to the active SQLite database file.
    """
    return _db_path
