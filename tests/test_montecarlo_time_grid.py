"""Tests for ``montecarlo.paths.TimeGrid``."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from montecarlo.paths import TimeGrid


def test_constructor_happy_path() -> None:
    grid = TimeGrid([0.0, 0.25, 0.5, 1.0])
    assert grid.n_steps == 3
    np.testing.assert_array_equal(grid.times, np.array([0.0, 0.25, 0.5, 1.0]))
    np.testing.assert_allclose(grid.dts, np.array([0.25, 0.25, 0.5]))
    assert len(grid) == 4


def test_constructor_accepts_numpy_array() -> None:
    grid = TimeGrid(np.linspace(0.0, 1.0, 5))
    assert grid.n_steps == 4
    np.testing.assert_allclose(grid.dts, np.full(4, 0.25))


def test_times_and_dts_are_copies() -> None:
    grid = TimeGrid([0.0, 0.5, 1.0])
    grid.times[0] = 99.0
    grid.dts[0] = 99.0
    np.testing.assert_array_equal(grid.times, np.array([0.0, 0.5, 1.0]))
    np.testing.assert_allclose(grid.dts, np.array([0.5, 0.5]))


def test_non_zero_first_element_raises() -> None:
    with pytest.raises(ValueError, match="first entry must be exactly 0.0"):
        TimeGrid([0.25, 0.5, 1.0])


def test_non_monotone_raises() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        TimeGrid([0.0, 0.5, 0.5, 1.0])
    with pytest.raises(ValueError, match="strictly increasing"):
        TimeGrid([0.0, 0.5, 0.25, 1.0])


def test_single_element_raises() -> None:
    with pytest.raises(ValueError, match="at least two entries"):
        TimeGrid([0.0])


def test_empty_raises() -> None:
    with pytest.raises(ValueError, match="at least two entries"):
        TimeGrid([])


def test_two_d_input_raises() -> None:
    with pytest.raises(ValueError, match="one-dimensional"):
        TimeGrid(np.array([[0.0, 0.5], [0.0, 1.0]]))


def test_from_year_fractions_alias() -> None:
    grid = TimeGrid.from_year_fractions([0.0, 0.5, 1.0])
    np.testing.assert_array_equal(grid.times, np.array([0.0, 0.5, 1.0]))


def test_from_dates_prepends_zero_and_uses_act_365() -> None:
    ref = date(2025, 1, 1)
    # 365 days later == year fraction 1.0 in ACT/365.
    dates = [date(2025, 7, 2), date(2026, 1, 1)]
    grid = TimeGrid.from_dates(ref, dates)
    assert grid.times[0] == 0.0
    np.testing.assert_allclose(grid.times[1], 182 / 365.0)
    np.testing.assert_allclose(grid.times[2], 365 / 365.0)


def test_from_dates_sorts_input() -> None:
    ref = date(2025, 1, 1)
    out_of_order = [date(2026, 1, 1), date(2025, 7, 2)]
    grid = TimeGrid.from_dates(ref, out_of_order)
    np.testing.assert_allclose(grid.times[1], 182 / 365.0)
    np.testing.assert_allclose(grid.times[2], 365 / 365.0)


def test_from_dates_rejects_on_or_before_reference() -> None:
    ref = date(2025, 1, 1)
    with pytest.raises(ValueError, match="strictly after reference_date"):
        TimeGrid.from_dates(ref, [date(2025, 1, 1), date(2025, 6, 1)])
    with pytest.raises(ValueError, match="strictly after reference_date"):
        TimeGrid.from_dates(ref, [date(2024, 12, 31)])


def test_from_dates_rejects_duplicates() -> None:
    ref = date(2025, 1, 1)
    with pytest.raises(ValueError, match="duplicate date"):
        TimeGrid.from_dates(ref, [date(2025, 6, 1), date(2025, 6, 1)])


def test_from_dates_rejects_empty() -> None:
    ref = date(2025, 1, 1)
    with pytest.raises(ValueError, match="at least one entry"):
        TimeGrid.from_dates(ref, [])


def test_repr_smoke() -> None:
    grid = TimeGrid([0.0, 0.5, 1.0])
    assert "n_steps=2" in repr(grid)
