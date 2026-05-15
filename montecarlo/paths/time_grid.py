"""Simulation time grid: an ordered sequence of year fractions starting at zero.

The path engine is date-system-agnostic: it consumes a :class:`TimeGrid` of
year fractions and never touches calendars or day-count conventions internally.
The convenience constructor :meth:`TimeGrid.from_dates` is the project's standard
bridge from a date schedule to a year-fraction grid (ACT/365, the equity
convention shared by ``EquityForward`` and the volatility package).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np

from market_conventions import DayCountConvention
from schedules.day_count import day_count_fraction

_TIME_GRID_DCC = DayCountConvention.ACT_365_FIXED


class TimeGrid:
    """Ordered year-fraction grid ``[0 = t_0 < t_1 < ... < t_N]``.

    The grid is the path engine's only notion of time: ``t_0`` is the simulation
    start, ``t_N`` the horizon. The grid is **inclusive of the anchor** ``t_0 = 0``
    so the engine can read ``len(times) - 1`` step lengths directly.

    Attributes
    ----------
    times
        Read-only copy of the underlying year-fraction array.
    dts
        Per-step length array, length ``n_steps``; strictly positive.
    n_steps
        Number of integration steps, equal to ``len(times) - 1``.
    """

    def __init__(
        self,
        year_fractions: Sequence[float] | np.ndarray,
    ) -> None:
        """Construct from an explicit year-fraction array starting at zero.

        Parameters
        ----------
        year_fractions
            Sequence of year fractions. Must start at ``0.0`` exactly, contain
            at least two entries, and be strictly increasing.

        Raises
        ------
        ValueError
            If the grid has fewer than two entries, does not start at zero, or
            is not strictly increasing.
        """
        arr = np.asarray(year_fractions, dtype=np.float64)
        if arr.ndim != 1:
            raise ValueError(
                f"year_fractions must be one-dimensional, got shape {arr.shape}"
            )
        if arr.size < 2:
            raise ValueError(
                f"TimeGrid requires at least two entries (t=0 plus one step), "
                f"got {arr.size}"
            )
        if arr[0] != 0.0:
            raise ValueError(
                f"first entry must be exactly 0.0, got {arr[0]!r}"
            )
        diffs = np.diff(arr)
        if np.any(diffs <= 0.0):
            raise ValueError("year_fractions must be strictly increasing")
        self._times = arr
        self._dts = diffs

    @classmethod
    def from_year_fractions(
        cls,
        year_fractions: Sequence[float] | np.ndarray,
    ) -> "TimeGrid":
        """Construct from a year-fraction sequence; alias for the constructor.

        Parameters
        ----------
        year_fractions
            Sequence of year fractions starting at ``0.0``; see
            :meth:`__init__` for the full validation rules.

        Returns
        -------
        TimeGrid
            A new grid wrapping the supplied year fractions.
        """
        return cls(year_fractions)

    @classmethod
    def from_dates(
        cls,
        reference_date: date,
        dates: Sequence[date],
    ) -> "TimeGrid":
        """Construct from a list of dates strictly after ``reference_date`` (ACT/365).

        The reference date corresponds to ``t = 0`` and is prepended to the
        resulting grid automatically; the caller supplies only the step end
        dates.

        Parameters
        ----------
        reference_date
            Anchor date for ``t = 0``.
        dates
            Sequence of dates strictly after ``reference_date``, in any order.
            The function sorts them ascending; duplicates raise.

        Returns
        -------
        TimeGrid
            Grid with ``t = 0`` prepended and the sorted dates converted to
            ACT/365 year fractions.

        Raises
        ------
        ValueError
            If ``dates`` is empty, contains a date on or before
            ``reference_date``, or contains duplicates.
        """
        if not dates:
            raise ValueError("dates must contain at least one entry")
        sorted_dates = sorted(dates)
        if sorted_dates[0] <= reference_date:
            raise ValueError(
                f"all dates must be strictly after reference_date "
                f"{reference_date}, got {sorted_dates[0]}"
            )
        for prev, nxt in zip(sorted_dates, sorted_dates[1:]):
            if prev == nxt:
                raise ValueError(f"duplicate date in grid: {prev}")
        ys = [0.0] + [
            day_count_fraction(reference_date, d, _TIME_GRID_DCC)
            for d in sorted_dates
        ]
        return cls(ys)

    @property
    def times(self) -> np.ndarray:
        """Return a copy of the year-fraction array (length ``n_steps + 1``)."""
        return self._times.copy()

    @property
    def dts(self) -> np.ndarray:
        """Return a copy of the per-step length array (length ``n_steps``)."""
        return self._dts.copy()

    @property
    def n_steps(self) -> int:
        """Return the number of integration steps."""
        return int(self._times.size - 1)

    def __len__(self) -> int:
        """Return the number of grid points, equal to ``n_steps + 1``."""
        return int(self._times.size)

    def __repr__(self) -> str:
        """Return a short representation showing the grid endpoints and step count."""
        return (
            f"TimeGrid(n_steps={self.n_steps}, "
            f"t_min={self._times[0]:.4f}, t_max={self._times[-1]:.4f})"
        )
