from pathlib import Path

_db_path: str = str(Path(__file__).parent.parent / "quant.db")


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


def get_db_path() -> str:
    return _db_path
