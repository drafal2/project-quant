# examples/

Jupyter notebooks demonstrating each library package.

## Conventions

Each notebook calls `setup_demo_env()` from `examples/_setup.py` as its first code cell. The helper adds the project root to `sys.path`, calls `setup_logging()` from `logging_config` (loads `logging.yaml`, INFO to stderr), redirects the DB to `examples/demo.db` via `set_db_path()`, and seeds the holidays table on first run (idempotent). The production `quant.db` is never touched. To enable per-iteration solver traces in a notebook, call `setup_logging(level="DEBUG")` after `setup_demo_env()`.

When creating a new notebook, copy `_template.ipynb` to its target name and edit cells via `NotebookEdit`. Do not derive structure or boilerplate from existing notebooks — the template is the single source of truth for layout and setup.

When committing, **clear all cell outputs first**; the `nbstripout` git hook is configured to enforce this.

When inspecting a notebook, never `Read` the whole `.ipynb` — the JSON serialisation is large and most of it is structural noise. Use `NotebookEdit` to modify cells, or `Read` a targeted line range for a single cell.

## Current notebooks

- `01_schedule_generation.ipynb` — `schedules/`
- `02_market_structures.ipynb` — `market_structures/` (curves, quotes, interpolators)
- `03_cds_pricing.ipynb` — `credit/` (single-name CDS pricing: legs, RPV01, par spread, mid-life valuation, sensitivities)
- `04_zero_curve_bootstrapping.ipynb` — `market_structures/rates/bootstrapper.py`
- `05_credit_curve_bootstrapping.ipynb` — `credit/bootstrapper.py` (sequential vs. global Newton-Raphson; three interpolation variables)
