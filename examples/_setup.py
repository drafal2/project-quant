"""Environment bootstrap for example notebooks.

This module exposes :func:`setup_demo_env`, the single helper every example
notebook calls before doing any other work. It exists so that each notebook
does not have to repeat the same ``sys.path``, database-redirect, and
seeding boilerplate.

The helper deliberately operates on a sandbox database (``examples/demo.db``)
so notebook experiments cannot read or write the production ``quant.db``.
"""

import sqlite3
import sys
from pathlib import Path


def setup_demo_env() -> None:
    """Prepare the current Python session for an example notebook.

    Performs three steps in order:

    1. **Path** — adds the project root to ``sys.path`` so the first-party
       packages (``database``, ``schedules``, ``market_structures``,
       ``credit``, ...) import without installation.
    2. **Database redirect** — calls
       :func:`database.connection.set_db_path` to point the global
       database path at ``examples/demo.db``. The production
       ``quant.db`` is never opened by notebook code.
    3. **Schema and seed** — runs :func:`scripts.initialise.init_db` to
       create all registered domain tables, then seeds the holidays
       table (USD/EUR/GBP/PLN, years 2000-2100) **only if it is empty**.
       Re-running the cell is therefore idempotent.

    A one-line status message is printed so the notebook reader can see
    whether seeding ran or the existing demo database was reused.
    """
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from database.connection import get_db_path, set_db_path
    from scripts.initialise import _seed_holidays, init_db

    demo_db = project_root / "examples" / "demo.db"
    set_db_path(str(demo_db))
    init_db()

    with sqlite3.connect(get_db_path()) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM holidays").fetchone()
        if count == 0:
            _seed_holidays(conn)
            print(f"Initialised demo DB at {demo_db} (seeded 2000-2100 holidays).")
        else:
            print(f"Using existing demo DB at {demo_db} ({count} holiday rows already present).")
