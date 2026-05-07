# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Always use `.venv\Scripts\python` instead of `python` to ensure the venv interpreter is used.

```bash
# Run all tests
.venv\Scripts\python -m pytest tests/ -q

# Run a single test file
.venv\Scripts\python -m pytest tests/test_schedule.py -q

# Run a single test by name
.venv\Scripts\python -m pytest tests/test_schedule.py::test_function_name -q
```

## Git

All new features and bug fixes must be developed on a dedicated branch, never directly on `master`. Always start from an up-to-date master:

```powershell
git checkout master
git pull
git checkout -b <type>/<description>
```

Commit and push regularly after completing meaningful work to preserve progress and maintain a clear history. Open a PR when the feature or fix is complete.

Commit messages must use the format `<type>: <description>`:

| Type | Use for |
|---|---|
| `feature` | New feature |
| `fix` | Bug fix |
| `refactor` | Code reorganisation without behaviour change |
| `docs` | Documentation only |
| `config` | Repo configuration |

## Versioning and Changelog

This project uses [Semantic Versioning](https://semver.org/) with the `MAJOR.MINOR.PATCH` scheme, currently in `0.x` initial development:

| Bump | When |
|---|---|
| `MINOR` (`0.x.0`) | New package added, or a major new capability within an existing package |
| `PATCH` (`0.x.y`) | Feature improvement, bug fix, or refactor within an existing package |
| `MAJOR` (`1.0.0`) | Core API considered stable across all domains |

`CHANGELOG.md` follows the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format. **Update `[Unreleased]` in the PR branch before opening the PR** — never after merge. Use `Added`, `Changed`, `Fixed`, or `Refactored` subsections. When cutting a release, promote `[Unreleased]` to a numbered version in a dedicated commit.

GitHub is configured to auto-delete remote branches after a PR is merged. Local branches must be cleaned up manually:

```powershell
# Delete local branches whose remote has been deleted
git fetch --prune
git branch -vv | grep "gone" | ForEach-Object { ($_ -split '\s+')[1] } | ForEach-Object { git branch -d $_ }
```

## Working Conventions

- **Docstrings** — NumPy-style with vertical signatures (one parameter per line for 2+ params beyond `self`); with type annotations present, do not repeat types in the `Parameters` section. Run `/docstring-audit` on all modified files before opening a PR.
- **Notebooks** — clear all cell outputs before committing; `nbstripout` git hook is configured to enforce this.
- **Per-package guidance** — each package directory has its own `CLAUDE.md` with module-level details. Read it when working in that subtree.
- **Docs freshness** — the `/pre-pr` skill checks whether the root `CLAUDE.md`, the relevant per-package `CLAUDE.md`, and `README.md` need updating before opening a PR. Keep doc updates in the same PR as the code change.

## Architecture

A Python quantitative finance toolkit. Each domain lives in its own library package; the shared SQLite database (`quant.db`) holds reference data for all domains. `examples/` contains Jupyter notebooks that document each package.

| Package | Purpose | Details |
|---|---|---|
| `database/` | Connection management and per-domain table DDL/repositories | [`database/CLAUDE.md`](database/CLAUDE.md) |
| `scripts/` | DB initialisation entry point and seed data generators | [`scripts/CLAUDE.md`](scripts/CLAUDE.md) |
| `market_conventions/` | Shared enums (BDC, day count, compounding, stub) used across all packages | [`market_conventions/CLAUDE.md`](market_conventions/CLAUDE.md) |
| `market_structures/` | Curves, market quotes, bootstrappers, interpolators | [`market_structures/CLAUDE.md`](market_structures/CLAUDE.md) |
| `schedules/` | Accrual schedule generation, calendars, day count fractions | [`schedules/CLAUDE.md`](schedules/CLAUDE.md) |
| `credit/` | Single-name CDS pricing on a bootstrapped survival curve | [`credit/CLAUDE.md`](credit/CLAUDE.md) |
| `tests/` | Pytest suite with isolated DB fixture | [`tests/CLAUDE.md`](tests/CLAUDE.md) |
| `examples/` | Jupyter notebooks demonstrating each package | [`examples/CLAUDE.md`](examples/CLAUDE.md) |

### Cross-package invariants

These rules touch multiple packages and must be honoured even when only one package's `CLAUDE.md` is loaded:

- **New `MarketQuote` subclass** — must be added to `QuoteHierarchy._RANK` in `market_structures/rates/bootstrapper.py`, otherwise the bootstrapper cannot resolve maturity-date collisions involving the new type.
- **New domain table** — define `create_<name>_table(conn)` in `database/<name>.py` and append it to `_TABLE_CREATORS` in `scripts/initialise.py`.
- **Test isolation** — every test must run against the temp DB provided by the `seeded_test_db` autouse fixture in `tests/conftest.py`; never touch `quant.db` directly.
