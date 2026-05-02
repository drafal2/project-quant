"""Global SQLite database path management."""

from pathlib import Path

_db_path: str = str(Path(__file__).parent.parent / "quant.db")


def set_db_path(path: str) -> None:
    """Override the global database path (used by tests and notebooks)."""
    global _db_path
    _db_path = path


def get_db_path() -> str:
    """Return the current global database path."""
    return _db_path
