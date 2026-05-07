# examples/

Jupyter notebooks demonstrating each library package.

## Conventions

Each notebook:
- adds the project root to `sys.path` so the local packages are importable without installation
- redirects the DB to `examples/demo.db` via `set_db_path()` (never touches `quant.db`)
- seeds `demo.db` on first run (idempotent — skips if data already present)

When committing, **clear all cell outputs first**; the `nbstripout` git hook is configured to enforce this.

## Current notebooks

- `01_schedule_generation.ipynb` — `schedules/`
- `02_market_structures.ipynb` — `market_structures/` (curves, quotes, interpolators)
- `03_cds_pricing.ipynb` — `credit/`
- `04_zero_curve_bootstrapping.ipynb` — `market_structures/rates/bootstrapper.py`
