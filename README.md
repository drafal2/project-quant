# project-quant

A Python quantitative finance toolkit. Each domain lives in its own library package; the shared SQLite database (`quant.db`) holds reference data for all domains.

## Requirements

- Python 3.11+

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 2. Install the project and dev dependencies
pip install -e ".[dev]"

# 3. Register the venv as a Jupyter kernel (required to run notebooks)
.venv\Scripts\python -m pip install ipykernel
.venv\Scripts\python -m ipykernel install --user --name project-quant --display-name "project-quant"

# 4. Create and seed the database
.venv\Scripts\python -m scripts.initialise
```

## Contributing

If you plan to commit changes to notebooks, install the `nbstripout` git hook to automatically strip cell outputs before each commit:

```bash
.venv\Scripts\nbstripout --install --attributes .gitattributes
```

This is optional but recommended — notebooks committed with outputs produce noisy diffs and bloat the repository.

## Running tests

```bash
.venv\Scripts\python -m pytest tests/ -q
```

## Examples

The `examples/` folder contains Jupyter notebooks that demonstrate each library package. Open them in VS Code or Jupyter and select the `project-quant` kernel.

## Packages

| Package | Description |
|---|---|
| `credit` | Single-name CDS pricing: survival curve bootstrap, par spread, MTM, CS01, RR01 |
| `market_structures` | Zero curve with pluggable interpolators; interpolation primitives |
| `schedules` | Accrual schedule generation for fixed income instruments (IRS, bonds) |
| `database` | SQLite connection and per-domain table management |
| `scripts` | Database initialisation and seeding |
