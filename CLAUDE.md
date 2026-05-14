# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Orchestration
### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity
### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
### 3. Self-Improvement Loop
- After ANY correction from the user: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project
### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it
### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how
### Task Management
- **Plan First**: Write plan to tasks/todo.md with checkable items
- **Verify Plan**: Check in before starting implementation
- **Track Progress**: Mark items complete as you go
- **Explain Changes**: High-level summary at each step
- **Document Results**: Add review section to tasks/todo.md
- **Capture Lessons**: Update tasks/lessons.md after corrections
### Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Commands

Always use `.venv/Scripts/python` instead of `python` to ensure the venv interpreter is used.

```bash
# Run all tests
.venv/Scripts/python -m pytest tests/ -q

# Run a single test file
.venv/Scripts/python -m pytest tests/test_schedule.py -q

# Run a single test by name
.venv/Scripts/python -m pytest tests/test_schedule.py::test_function_name -q
```

The default test run targets `tests/` only. The `validation/` directory holds cross-checks against external references (e.g. QuantLib) and is **not** part of the default suite — it requires optional dependencies and is run separately. See `validation/README.md` for the invocation.

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
| `perf` | Performance optimisation (behaviour-preserving but measurably faster) |
| `test` | Test-only change with no production behaviour impact |
| `docs` | Documentation only |
| `config` | Repo configuration (build, CI, tooling, dependencies) |
| `revert` | Reverting a prior commit |

If a change doesn't fit any of the above, propose a new type with reasoning and ask before using it. On approval, add the new row to this table in the same commit/PR — the table is the single source of truth.

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
- **Subagent model selection** — when delegating to a subagent, pick the model deliberately. Use **Haiku** for mechanical work (file search, symbol lookup, cross-package sweeps, mass mechanical edits) — cost win, no cache penalty. Use **Opus** for the `Plan` subagent and other delegated reasoning tasks **when the goal is to keep the parent context clean** (e.g. parent is already heavy, or reasoning would pull in many large files). Plan inline by default — only delegate planning when context isolation is the actual reason. Default to the parent's model otherwise.

## Logging

Library code is configuration-free: every module declares its own logger and installs no handlers. Output is configured at the entry point (notebook, script, or test) by calling `setup_logging()` from the top-level `logging_config.py`, which loads `logging.yaml` via `logging.config.dictConfig`.

### Adding a new module (any package)

Two lines at the top, alongside the other imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Then use `logger.info(...)`, `logger.debug(...)`, etc. throughout. Never call `logging.basicConfig()`, never attach handlers, never read `logging.yaml` from inside library code.

### Adding a new package

When you create a new top-level package (e.g. `vol/`), three places need updating in the same PR:

1. **`<package>/__init__.py`** — install a `NullHandler` so the package's logger never emits a "no handler" warning when imported with no logging configured:
   ```python
   import logging

   logging.getLogger(__name__).addHandler(logging.NullHandler())
   ```
2. **`logging.yaml`** — add a logger entry under `loggers:` matching the package name, level `INFO`, attaching the `console` handler, `propagate: false`. Copy any existing entry (e.g. `credit:`) as the template.
3. **`logging_config.py`** — append the package name to the `_PACKAGE_LOGGERS` tuple so the `setup_logging(level=...)` override applies to it.

If any of those three steps is missed, logs from the new package will either be silent (missing yaml entry) or unaffected by the `level=` override (missing tuple entry).

### Level conventions

| Level | When to use |
|---|---|
| `DEBUG` | Per-iteration / per-step traces inside hot loops (Newton-Raphson, bisection, schedule period generation). Always guard with `if logger.isEnabledFor(logging.DEBUG):` so disabled logging costs one attribute lookup. |
| `INFO` | Lifecycle summaries: entry/exit of long-running operations, solver convergence (`"converged in N iterations"`), bootstrap pillar counts, DB seeding completion. One INFO line per logical operation, not per data point. |
| `WARNING` | Degraded but recoverable conditions: solver hit max iterations but produced a usable answer, fallback path taken, deprecated input shape accepted. |
| `ERROR` | Failure paths immediately before raising an exception. The exception message carries the human-readable detail; the log line carries structured fields useful for log aggregators. |

### Performance rule

Use `%`-style lazy formatting in log calls: `logger.info("x=%d y=%.4f", x, y)`, **not** f-strings. Lazy formatting is skipped entirely when the level is disabled. For DEBUG inside hot loops, additionally guard with `isEnabledFor`:

```python
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("NR iter=%d x=%.10f f(x)=%.3e", iteration, x, fx)
```

This guard pattern is mandatory in any solver that may iterate more than ~10 times per call.

### Channel split: `warnings.warn` vs `logger`

- **`warnings.warn(..., UserWarning)`** — user-facing data-quality signals the caller might want to suppress with `warnings.filterwarnings`. Example: `QuoteHierarchy` discarding a lower-priority quote on a maturity-date collision (`market_structures/rates/bootstrapper.py`).
- **`logger.warning(...)`** — operational/diagnostic concerns the caller does not need to suppress per-call. Example: bisection hit max iterations.

If unsure: would the user want to silence this with `filterwarnings` for a specific test or call? If yes, `warnings`. Otherwise `logger`.

### Enabling output

- **Notebook** — `setup_demo_env()` (in `examples/_setup.py`) calls `setup_logging()` automatically. To see per-iteration DEBUG traces, follow it with `setup_logging(level="DEBUG")`.
- **Script** — call `setup_logging()` at the top of the `if __name__ == "__main__":` block. See `scripts/initialise.py` for the pattern.
- **Tests** — never call `setup_logging()`; rely on pytest's `caplog` fixture, which attaches a handler dynamically. Use `caplog.at_level(logging.DEBUG, logger="<package>.<module>")` to capture records.

## Architecture

A Python quantitative finance toolkit. Each domain lives in its own library package; the shared SQLite database (`quant.db`) holds reference data for all domains. `examples/` contains Jupyter notebooks that document each package.

| Package | Purpose | Details |
|---|---|---|
| `database/` | Connection management and per-domain table DDL/repositories | [`database/CLAUDE.md`](database/CLAUDE.md) |
| `scripts/` | DB initialisation entry point and seed data generators | [`scripts/CLAUDE.md`](scripts/CLAUDE.md) |
| `market_conventions/` | Shared enums (BDC, day count, compounding, stub) used across all packages | [`market_conventions/CLAUDE.md`](market_conventions/CLAUDE.md) |
| `market_structures/` | Curves, market quotes, bootstrappers, interpolators, implied-vol surfaces | [`market_structures/CLAUDE.md`](market_structures/CLAUDE.md) |
| `schedules/` | Accrual schedule generation, calendars, day count fractions | [`schedules/CLAUDE.md`](schedules/CLAUDE.md) |
| `credit/` | Single-name CDS pricing on a bootstrapped survival curve | [`credit/CLAUDE.md`](credit/CLAUDE.md) |
| `montecarlo/` | Random-number sampling (PRNGs, QMC, `U -> N` transforms, diagnostics) and diffusion-side volatility models (`ConstantVol`, `BlackTermStructureVol`, `DupireLocalVol`) | [`montecarlo/CLAUDE.md`](montecarlo/CLAUDE.md) |
| `tests/` | Pytest suite with isolated DB fixture | [`tests/CLAUDE.md`](tests/CLAUDE.md) |
| `examples/` | Jupyter notebooks demonstrating each package | [`examples/CLAUDE.md`](examples/CLAUDE.md) |
| `validation/` | Cross-checks against external references (e.g. QuantLib); run separately, not part of default `tests/` | [`validation/README.md`](validation/README.md) |

### Cross-package invariants

These rules touch multiple packages and must be honoured even when only one package's `CLAUDE.md` is loaded:

- **New `MarketQuote` subclass** — must be added to `QuoteHierarchy._RANK` in `market_structures/rates/bootstrapper.py`, otherwise the bootstrapper cannot resolve maturity-date collisions involving the new type.
- **New domain table** — define `create_<name>_table(conn)` in `database/<name>.py` and append it to `_TABLE_CREATORS` in `scripts/initialise.py`.
- **New top-level package** — install `NullHandler` in `<package>/__init__.py`, add a logger entry to `logging.yaml`, and append the package name to `_PACKAGE_LOGGERS` in `logging_config.py`. See the [Logging](#logging) section.
- **Test isolation** — every test must run against the temp DB provided by the `seeded_test_db` autouse fixture in `tests/conftest.py`; never touch `quant.db` directly.
