"""Logging configuration loader for project-quant."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml

_DEFAULT_YAML = Path(__file__).parent / "logging.yaml"

_PACKAGE_LOGGERS = (
    "database",
    "market_conventions",
    "market_structures",
    "market_structures.volatility",
    "market_structures.equity",
    "schedules",
    "credit",
    "montecarlo",
    "montecarlo.volatility",
    "scripts",
    "examples",
)


def setup_logging(
    yaml_path: Path | str | None = None,
    level: str | int | None = None,
) -> None:
    """Configure logging from a YAML ``dictConfig`` file.

    Parameters
    ----------
    yaml_path
        Path to the YAML config. Defaults to ``logging.yaml`` next to this module.
    level
        Optional override applied to every project logger after ``dictConfig``,
        useful for one-off DEBUG runs from notebooks.

    Notes
    -----
    Idempotent: calling repeatedly re-applies the configuration cleanly.
    """
    path = Path(yaml_path) if yaml_path is not None else _DEFAULT_YAML
    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    logging.config.dictConfig(config)

    if level is not None:
        normalised = level if isinstance(level, int) else level.upper()
        for name in _PACKAGE_LOGGERS:
            logging.getLogger(name).setLevel(normalised)
