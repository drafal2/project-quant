"""Equity forward callable: ``F(T) = S0 * exp(-q * T) / DF(T)``."""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from market_conventions import DayCountConvention
from schedules.day_count import day_count_fraction

from ..rates.curve import ZeroCurve

logger = logging.getLogger(__name__)


_EQUITY_DCC = DayCountConvention.ACT_365_FIXED
_YEAR_BASIS = 365.0


class EquityForward:
    """Equity forward callable for a single underlying with a continuous dividend yield.

    Computes ``F(T) = S0 * exp(-q * T) / DF(T)`` where ``DF`` is the risk-free
    discount factor at maturity. The dividend yield is interpreted as
    continuously compounded under ACT/365 — the standard equity quoting
    convention. The discount factor is read from the supplied :class:`ZeroCurve`
    by date, so the curve's internal day-count convention does not need to
    agree with ACT/365.

    Attributes
    ----------
    spot
        Underlying spot at the reference date.
    dividend_yield
        Continuous dividend yield ``q`` in ACT/365.
    reference_date
        Anchor date; mirrors the supplied ``ZeroCurve.reference_date``.
    """

    def __init__(
        self,
        spot: float,
        zero_curve: ZeroCurve,
        dividend_yield: float,
    ) -> None:
        """Construct the forward from spot, a discount curve, and a constant dividend yield.

        Parameters
        ----------
        spot
            Underlying spot price at ``zero_curve.reference_date``; must be
            strictly positive.
        zero_curve
            Risk-free discount curve. Its ``reference_date`` defines ``t=0``
            for this forward.
        dividend_yield
            Continuous dividend yield ``q`` in ACT/365. Held constant across
            time; a term structure of dividends is out of scope for the first
            release of this module.

        Raises
        ------
        ValueError
            If ``spot`` is non-positive.
        """
        if spot <= 0.0:
            raise ValueError(f"spot must be positive, got {spot}")
        self._spot = float(spot)
        self._curve = zero_curve
        self._q = float(dividend_yield)
        self._reference_date = zero_curve.reference_date
        logger.info(
            "EquityForward built: spot=%.6g q=%.4f ref=%s",
            self._spot,
            self._q,
            self._reference_date,
        )

    @property
    def spot(self) -> float:
        """Return the underlying spot at the reference date."""
        return self._spot

    @property
    def dividend_yield(self) -> float:
        """Return the continuous dividend yield ``q``."""
        return self._q

    @property
    def reference_date(self) -> date:
        """Return the forward's reference date (curve anchor)."""
        return self._reference_date

    def at_date(
        self,
        expiry: date,
    ) -> float:
        """Return ``F(T)`` where ``T`` is the ACT/365 fraction from reference to ``expiry``.

        Parameters
        ----------
        expiry
            Forward maturity date; must be strictly after the reference date.

        Returns
        -------
        float
            Forward price ``S0 * exp(-q * T) / DF(expiry)``.

        Raises
        ------
        ValueError
            If ``expiry`` is on or before the reference date.
        """
        if expiry <= self._reference_date:
            raise ValueError(
                f"expiry {expiry} must be strictly after reference_date "
                f"{self._reference_date}"
            )
        t = day_count_fraction(self._reference_date, expiry, _EQUITY_DCC)
        df = self._curve.discount_factor(expiry)
        return self._spot * math.exp(-self._q * t) / df

    def at_time(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return ``F(T)`` for a time-to-expiry expressed in ACT/365 years.

        Internally converts ``T`` to a date via ``reference_date + round(T *
        365)`` days and queries the underlying :class:`ZeroCurve`. The
        round-trip is exact for dates originally placed on the ACT/365 grid
        and otherwise relies on the curve's internal discount-factor
        interpolation.

        Parameters
        ----------
        time_to_expiry
            Year fraction from the reference date; must be strictly positive.

        Returns
        -------
        float
            Forward price ``S0 * exp(-q * T) / DF(T)``.

        Raises
        ------
        ValueError
            If ``time_to_expiry`` is non-positive.
        """
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be positive, got {time_to_expiry}"
            )
        days = max(1, round(time_to_expiry * _YEAR_BASIS))
        expiry = self._reference_date + timedelta(days=days)
        df = self._curve.discount_factor(expiry)
        return self._spot * math.exp(-self._q * time_to_expiry) / df

    def __call__(
        self,
        when: float | date,
    ) -> float:
        """Return the forward at a maturity given as either a date or a year fraction.

        Parameters
        ----------
        when
            Either a :class:`datetime.date` (resolved by :meth:`at_date`) or a
            float year fraction in ACT/365 (resolved by :meth:`at_time`).

        Returns
        -------
        float
            Forward price.
        """
        if isinstance(when, date):
            return self.at_date(when)
        return self.at_time(float(when))
