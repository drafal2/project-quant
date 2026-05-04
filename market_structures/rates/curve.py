"""Zero-rate curve implementation with pluggable interpolation."""

import math
from bisect import bisect_left
from datetime import date

from market_conventions import CompoundingFrequency, CompoundingType, DayCountConvention
from schedules.day_count import day_count_fraction
from ..interpolation.interpolators import Interpolator, LogLinearInterpolator


class ZeroCurve:
    """Interpolated zero-rate curve supporting discount factor and forward rate queries."""

    def __init__(
        self,
        reference_date: date,
        pillar_dates: list[date],
        rates: list[float],
        day_count_convention: DayCountConvention,
        compounding_type: CompoundingType = CompoundingType.CONTINUOUS,
        compounding_frequency: CompoundingFrequency | None = None,
        interpolator: Interpolator | None = None,
    ) -> None:
        """Construct a zero curve from pillar dates, rates, and compounding/interpolation settings."""
        if len(pillar_dates) != len(rates):
            raise ValueError("pillar_dates and rates must have the same length")
        if len(pillar_dates) == 0:
            raise ValueError("at least one pillar required")
        if any(d < reference_date for d in pillar_dates):
            raise ValueError("all pillar dates must be on or after reference_date")
        if compounding_type == CompoundingType.COMPOUNDED and compounding_frequency is None:
            raise ValueError("compounding_frequency required for COMPOUNDED compounding_type")

        self._reference_date = reference_date
        self._dcc = day_count_convention
        self._compounding_type = compounding_type
        self._compounding_frequency = compounding_frequency
        self._interpolator = interpolator or LogLinearInterpolator()

        sorted_pairs = sorted(zip(pillar_dates, rates), key=lambda x: x[0])
        self._pillar_dates, self._rates = [list(x) for x in zip(*sorted_pairs)]
        self._times = [self._t(d) for d in self._pillar_dates]
        self._dfs = [self._rate_to_df(r, t) for r, t in zip(self._rates, self._times)]

    def _t(self, d: date) -> float:
        """Return the day count fraction from the reference date to d."""
        return day_count_fraction(self._reference_date, d, self._dcc)

    def _rate_to_df(self, rate: float, t: float) -> float:
        """Convert a zero rate to a discount factor at time t."""
        if self._compounding_type == CompoundingType.CONTINUOUS:
            return math.exp(-rate * t)
        if self._compounding_type == CompoundingType.SIMPLE:
            return 1.0 / (1.0 + rate * t)
        n = self._compounding_frequency.value
        return (1.0 + rate / n) ** (-n * t)

    def _df_to_rate(self, df: float, t: float) -> float:
        """Convert a discount factor to a zero rate at time t."""
        if self._compounding_type == CompoundingType.CONTINUOUS:
            return -math.log(df) / t
        if self._compounding_type == CompoundingType.SIMPLE:
            return (1.0 / df - 1.0) / t
        n = self._compounding_frequency.value
        return n * (df ** (-1.0 / (n * t)) - 1.0)

    def discount_factor(self, d: date) -> float:
        """Return the discount factor for the given date.

        For dates before the first pillar, log-linearly interpolates between
        the implicit (t=0, DF=1) anchor at reference_date and the first pillar,
        rather than flat-extrapolating.
        """
        if d == self._reference_date:
            return 1.0
        t = self._t(d)
        if t < self._times[0]:
            # Log-linear from (0, 1.0) to (t_first, df_first)
            return self._dfs[0] ** (t / self._times[0])
        return self._interpolator.interpolate(t, self._times, self._dfs)

    def zero_rate(self, d: date) -> float:
        """Return the zero rate for the given date under the curve's compounding convention."""
        t = self._t(d)
        if t == 0.0:
            raise ValueError("zero_rate undefined at reference_date")
        return self._df_to_rate(self.discount_factor(d), t)

    def forward_rate(self, start: date, end: date) -> float:
        """Return the forward rate between two dates implied by the curve."""
        if start >= end:
            raise ValueError("start must be before end")
        df_start = self.discount_factor(start)
        df_end = self.discount_factor(end)
        t = self._t(end) - self._t(start)
        return self._df_to_rate(df_end / df_start, t)

    def add_pillar(self, d: date, rate: float) -> None:
        """Add a new pillar date and rate, inserting in sorted order."""
        if d < self._reference_date:
            raise ValueError("pillar date must be on or after reference_date")
        if d in self._pillar_dates:
            raise ValueError(f"pillar {d} already exists")

        t = self._t(d)
        df = self._rate_to_df(rate, t)
        idx = bisect_left(self._pillar_dates, d)
        self._pillar_dates.insert(idx, d)
        self._rates.insert(idx, rate)
        self._times.insert(idx, t)
        self._dfs.insert(idx, df)

    def remove_pillar(self, d: date) -> None:
        """Remove a pillar date from the curve."""
        if d not in self._pillar_dates:
            raise ValueError(f"pillar {d} not found")
        if len(self._pillar_dates) == 1:
            raise ValueError("curve must have at least one pillar")
        idx = self._pillar_dates.index(d)
        self._pillar_dates.pop(idx)
        self._rates.pop(idx)
        self._times.pop(idx)
        self._dfs.pop(idx)
