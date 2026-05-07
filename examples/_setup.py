"""Environment bootstrap for example notebooks.

This module exposes :func:`setup_demo_env`, the single helper every example
notebook calls before doing any other work. It exists so that each notebook
does not have to repeat the same ``sys.path``, database-redirect, and
seeding boilerplate.

The helper deliberately operates on a sandbox database (``examples/demo.db``)
so notebook experiments cannot read or write the production ``quant.db``.
"""

import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


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

    Logging is configured via :func:`logging_config.setup_logging` (YAML
    ``dictConfig``) so the notebook reader sees status and bootstrap
    progress on stderr at INFO level.
    """
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from logging_config import setup_logging
    setup_logging()

    from database.connection import get_db_path, set_db_path
    from scripts.initialise import _seed_holidays, init_db

    demo_db = project_root / "examples" / "demo.db"
    set_db_path(str(demo_db))
    init_db()

    with sqlite3.connect(get_db_path()) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM holidays").fetchone()
        if count == 0:
            _seed_holidays(conn)
            logger.info("Initialised demo DB at %s (seeded 2000-2100 holidays).", demo_db)
        else:
            logger.info(
                "Using existing demo DB at %s (%d holiday rows already present).",
                demo_db,
                count,
            )
