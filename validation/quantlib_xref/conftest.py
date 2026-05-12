"""Pytest configuration for the QuantLib cross-validation suite.

This directory is deliberately excluded from the default ``tests/`` pytest path
(see the root ``CLAUDE.md``). Run it explicitly with::

    .venv/Scripts/python -m pytest validation/quantlib_xref -q

The whole module is skipped if ``QuantLib`` is not importable, so the
``[validation]`` optional extra is required to exercise these checks::

    pip install -e ".[validation]"
"""

import pytest

pytest.importorskip("QuantLib", reason="install with `pip install -e \".[validation]\"`")
