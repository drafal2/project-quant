"""Bootstrap an :class:`EquityForwardCurve` from market quotes.

Unlike the rates bootstrapper (which solves a non-linear NPV residual per
pillar with Newton-Raphson), the equity forward bootstrapper has a
closed-form per-pillar solution: every quote pins one dividend yield
``q_i`` via

``q_i = -log(F_i * DF(T_i) / S0) / T_i``

for a :class:`ForwardQuote`, or directly via the quote value for a
:class:`DividendYieldQuote`. Mixed input is accepted; quotes are sorted by
maturity and duplicates on the same date are rejected.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Sequence

from market_conventions import DayCountConvention
from schedules.day_count import day_count_fraction

from ..rates.curve import ZeroCurve
from .forward_curve import DividendYieldInterpolation, EquityForwardCurve
from .quotes import DividendYieldQuote, ForwardQuote

logger = logging.getLogger(__name__)


_EQUITY_DCC = DayCountConvention.ACT_365_FIXED

EquityQuote = ForwardQuote | DividendYieldQuote


def _maturity(quote: EquityQuote) -> date:
    return quote.maturity_date


class EquityForwardCurveBootstrapper:
    """Closed-form bootstrap of an :class:`EquityForwardCurve` from market quotes.

    The bootstrapper holds the static context (spot and risk-free discount
    curve) so the same instance can be reused across calibration cycles. A
    single :meth:`bootstrap` call accepts a heterogeneous list of
    :class:`ForwardQuote` and :class:`DividendYieldQuote` instances and
    returns a fully-formed :class:`EquityForwardCurve`.

    Attributes
    ----------
    spot
        Underlying spot at the discount curve's reference date.
    zero_curve
        Risk-free discount curve providing ``reference_date`` and
        ``discount_factor(date)``.
    """

    def __init__(
        self,
        spot: float,
        zero_curve: ZeroCurve,
    ) -> None:
        """Initialise the bootstrapper from spot and a discount curve.

        Parameters
        ----------
        spot
            Underlying spot price at ``zero_curve.reference_date``; must be
            strictly positive.
        zero_curve
            Risk-free discount curve.

        Raises
        ------
        ValueError
            If ``spot`` is non-positive.
        """
        if spot <= 0.0:
            raise ValueError(f"spot must be positive, got {spot}")
        self._spot = float(spot)
        self._curve = zero_curve

    @property
    def spot(self) -> float:
        """Return the bootstrapper's spot."""
        return self._spot

    @property
    def zero_curve(self) -> ZeroCurve:
        """Return the bootstrapper's discount curve."""
        return self._curve

    def bootstrap(
        self,
        quotes: Sequence[EquityQuote],
        interpolation: DividendYieldInterpolation = DividendYieldInterpolation.FORWARD_YIELD_FLAT,
    ) -> EquityForwardCurve:
        """Bootstrap a curve from a list of forward / dividend-yield quotes.

        Quotes are sorted by maturity. For each pillar the implied
        continuous dividend yield is computed in closed form. Mixed
        :class:`ForwardQuote` and :class:`DividendYieldQuote` are accepted
        but no two quotes may share a maturity.

        Parameters
        ----------
        quotes
            Quotes to consume. Must contain at least one entry; all
            maturities must be strictly after the discount curve's
            reference date and pairwise distinct.
        interpolation
            Interpolation policy to attach to the resulting curve. Defaults
            to :attr:`DividendYieldInterpolation.FORWARD_YIELD_FLAT`.

        Returns
        -------
        EquityForwardCurve
            Curve such that :meth:`EquityForwardCurve.at_date` returns the
            input forward price at every :class:`ForwardQuote` maturity
            (to numerical precision) and the input dividend yield at every
            :class:`DividendYieldQuote` maturity.

        Raises
        ------
        ValueError
            If ``quotes`` is empty, if any quote maturity is on or before
            the reference date, if two quotes share a maturity, or if a
            :class:`ForwardQuote` implies a non-finite yield (e.g. negative
            forward, though this is rejected earlier at quote construction).
        """
        if len(quotes) == 0:
            raise ValueError("at least one quote required")
        ref = self._curve.reference_date
        for quote in quotes:
            if quote.maturity_date <= ref:
                raise ValueError(
                    f"quote maturity {quote.maturity_date} must be strictly "
                    f"after reference_date {ref}"
                )
        sorted_quotes = sorted(quotes, key=_maturity)
        for prev, curr in zip(sorted_quotes, sorted_quotes[1:]):
            if prev.maturity_date == curr.maturity_date:
                raise ValueError(
                    f"duplicate quote maturity {curr.maturity_date}"
                )

        logger.info(
            "EquityForwardCurveBootstrapper.bootstrap: n_quotes=%d spot=%.6g ref=%s",
            len(sorted_quotes),
            self._spot,
            ref,
        )

        pillar_times: list[float] = []
        pillar_yields: list[float] = []
        for quote in sorted_quotes:
            t = day_count_fraction(ref, quote.maturity_date, _EQUITY_DCC)
            if isinstance(quote, ForwardQuote):
                df = self._curve.discount_factor(quote.maturity_date)
                ratio = quote.forward_price * df / self._spot
                if ratio <= 0.0:
                    raise ValueError(
                        f"ForwardQuote at {quote.maturity_date} implies non-positive "
                        f"F*DF/S0 = {ratio}; bootstrap failed"
                    )
                q = -math.log(ratio) / t
            else:
                q = quote.continuous_yield
            pillar_times.append(t)
            pillar_yields.append(q)

        curve = EquityForwardCurve(
            spot=self._spot,
            zero_curve=self._curve,
            pillar_times=pillar_times,
            pillar_yields=pillar_yields,
            interpolation=interpolation,
        )
        logger.info(
            "EquityForwardCurveBootstrapper.bootstrap: completed n_pillars=%d",
            len(pillar_times),
        )
        return curve
