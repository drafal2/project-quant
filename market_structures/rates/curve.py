"""Zero-rate curve implementation with pluggable interpolation."""

from __future__ import annotations

import math
from bisect import bisect_left
from datetime import date
from typing import TYPE_CHECKING

from market_conventions import CompoundingFrequency, CompoundingType, DayCountConvention
from schedules.day_count import day_count_fraction
from ..interpolation.interpolators import Interpolator, LogLinearInterpolator

if TYPE_CHECKING:
    from .quotes import MarketQuote


class ZeroCurve:
    """Interpolated zero-rate curve supporting discount factor and forward rate queries."""

    def __init__(
        self,
        reference_date: date,
        pillar_dates: list[date],  # TODO: it should be possible to pass tenor instead of specific date to make it more flexible
        rates: list[float],
        day_count_convention: DayCountConvention,
        compounding_type: CompoundingType = CompoundingType.CONTINUOUS,
        compounding_frequency: CompoundingFrequency | None = None,
        interpolator: Interpolator | None = None,
        quotes: list[MarketQuote] | None = None,
    ) -> None:
        """Construct a zero curve from pillar dates, rates, and compounding/interpolation settings.

        Parameters
        ----------
        reference_date
            Anchor date (t=0) where the discount factor is 1.0.
        pillar_dates
            Maturity dates corresponding to each zero rate; must all be on or
            after reference_date.
        rates
            Zero rates at each pillar in decimal form; interpreted under
            compounding_type.
        day_count_convention
            Day count convention used to compute time fractions.
        compounding_type
            Compounding convention for rate and discount factor conversions.
            Defaults to ``CompoundingType.CONTINUOUS``.
        compounding_frequency
            Required when compounding_type is ``COMPOUNDED``; ignored otherwise.
        interpolator
            Strategy used to interpolate between pillars. Defaults to
            ``LogLinearInterpolator``.
        quotes
            Raw market instruments used to build this curve; populated
            automatically by ``ZeroCurveBootstrapper``. Used by ``summary()``.

        Raises
        ------
        ValueError
            If pillar_dates and rates have different lengths, if no pillars are
            provided, if any pillar is before reference_date, or if
            compounding_frequency is missing for COMPOUNDED compounding_type.
        """
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
        self._quotes: list[MarketQuote] = list(quotes) if quotes is not None else []

        sorted_pairs = sorted(zip(pillar_dates, rates), key=lambda x: x[0])
        self._pillar_dates, self._rates = [list(x) for x in zip(*sorted_pairs)]
        self._times = [self._t(d) for d in self._pillar_dates]
        self._dfs = [self._rate_to_df(r, t) for r, t in zip(self._rates, self._times)]

    def _t(
        self,
        d: date,
    ) -> float:
        """Return the day count fraction from the reference date to d.

        Parameters
        ----------
        d
            Target date.

        Returns
        -------
        float
            Day count fraction from reference_date to d.
        """
        return day_count_fraction(self._reference_date, d, self._dcc)

    def _rate_to_df(
        self,
        rate: float,
        t: float,
    ) -> float:
        """Convert a zero rate to a discount factor at time t.

        Parameters
        ----------
        rate
            Zero rate in decimal form.
        t
            Time in years (day count fraction from reference_date).

        Returns
        -------
        float
            Discount factor corresponding to rate at time t.
        """
        if self._compounding_type == CompoundingType.CONTINUOUS:
            return math.exp(-rate * t)
        if self._compounding_type == CompoundingType.SIMPLE:
            return 1.0 / (1.0 + rate * t)
        n = self._compounding_frequency.value
        return (1.0 + rate / n) ** (-n * t)

    def _df_to_rate(
        self,
        df: float,
        t: float,
    ) -> float:
        """Convert a discount factor to a zero rate at time t.

        Parameters
        ----------
        df
            Discount factor in (0, 1].
        t
            Time in years (day count fraction from reference_date).

        Returns
        -------
        float
            Zero rate corresponding to df at time t.
        """
        if self._compounding_type == CompoundingType.CONTINUOUS:
            return -math.log(df) / t
        if self._compounding_type == CompoundingType.SIMPLE:
            return (1.0 / df - 1.0) / t
        n = self._compounding_frequency.value
        return n * (df ** (-1.0 / (n * t)) - 1.0)

    def discount_factor(
        self,
        d: date,
    ) -> float:
        """Return the discount factor for the given date.

        For dates before the first pillar, log-linearly interpolates between
        the implicit (t=0, DF=1) anchor at reference_date and the first pillar,
        rather than flat-extrapolating.

        Parameters
        ----------
        d
            Target date; must be on or after reference_date.

        Returns
        -------
        float
            Discount factor in (0, 1] — 1.0 at reference_date, declining
            monotonically for later dates.
        """
        if d == self._reference_date:
            return 1.0
        t = self._t(d)
        if t < self._times[0]:
            # Log-linear from (0, 1.0) to (t_first, df_first)
            return self._dfs[0] ** (t / self._times[0])
        return self._interpolator.interpolate(t, self._times, self._dfs)

    def zero_rate(
        self,
        d: date,
    ) -> float:
        """Return the zero rate for the given date under the curve's compounding convention.

        Parameters
        ----------
        d
            Target date; must be strictly after reference_date.

        Returns
        -------
        float
            Zero rate in decimal form.

        Raises
        ------
        ValueError
            If d equals reference_date (zero rate is undefined at t=0).
        """
        t = self._t(d)
        if t == 0.0:
            raise ValueError("zero_rate undefined at reference_date")
        return self._df_to_rate(self.discount_factor(d), t)

    def forward_rate(
        self,
        start: date,
        end: date,
    ) -> float:
        """Return the forward rate between two dates implied by the curve.

        Parameters
        ----------
        start
            Start date of the forward period; must be strictly before end.
        end
            End date of the forward period.

        Returns
        -------
        float
            Forward zero rate in decimal form under the curve's compounding convention.

        Raises
        ------
        ValueError
            If start is on or after end.
        """
        if start >= end:
            raise ValueError("start must be before end")
        df_start = self.discount_factor(start)
        df_end = self.discount_factor(end)
        t = self._t(end) - self._t(start)
        return self._df_to_rate(df_end / df_start, t)

    def summary(self) -> str:  # TODO: quote value must be printed as whole, no rounding + in %, not number
        """Return a formatted table of bootstrapping quotes with curve outputs per pillar.

        Columns: instrument type, start date, maturity date, tenor, market quote,
        discount factor, and zero rate. Returns an empty string when no quotes are stored.

        Returns
        -------
        str
            Multi-line formatted table, or empty string if no quotes were stored.
        """
        if not self._quotes:
            return ""
        header = (
            f"{'Type':<16} {'Start':>10} {'Maturity':>10} {'Tenor':>6} "
            f"{'Quote':>10} {'DF':>10} {'ZeroRate':>10}"
        )
        sep = "-" * len(header)
        rows = [header, sep]
        for q in sorted(self._quotes, key=lambda x: x.maturity_date(self._reference_date)):
            mat = q.maturity_date(self._reference_date)
            start = q.start_date(self._reference_date)
            tenor = getattr(q, 'tenor', 'N/A')
            quote_val = q.quote_value()
            df = self.discount_factor(mat)
            zr = self.zero_rate(mat)
            rows.append(
                f"{type(q).__name__:<16} {str(start):>10} {str(mat):>10} {tenor:>6} "
                f"{quote_val:>10.4f} {df:>10.6f} {zr:>10.4%}"
            )
        return "\n".join(rows)

    def add_pillar(
        self,
        d: date,
        rate: float,
    ) -> None:
        """Add a new pillar date and rate, inserting in sorted order.

        Parameters
        ----------
        d
            New pillar date; must be on or after reference_date and not already present.
        rate
            Zero rate at the new pillar, in decimal form.

        Raises
        ------
        ValueError
            If d is before reference_date or already exists in the curve.
        """
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

    def remove_pillar(
        self,
        d: date,
    ) -> None:
        """Remove a pillar date from the curve.

        Parameters
        ----------
        d
            Pillar date to remove; must exist in the curve.

        Raises
        ------
        ValueError
            If d is not a current pillar or removing it would leave the curve
            with no pillars.
        """
        if d not in self._pillar_dates:
            raise ValueError(f"pillar {d} not found")
        if len(self._pillar_dates) == 1:
            raise ValueError("curve must have at least one pillar")
        idx = self._pillar_dates.index(d)
        self._pillar_dates.pop(idx)
        self._rates.pop(idx)
        self._times.pop(idx)
        self._dfs.pop(idx)
