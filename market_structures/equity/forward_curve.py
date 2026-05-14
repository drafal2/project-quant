"""Term-structured equity forward curve.

``EquityForwardCurve`` is the equity counterpart of
:class:`market_structures.rates.curve.ZeroCurve`. It is a quote object that
exposes ``F(T)`` for the underlying given a spot, a risk-free discount curve,
and a term structure of continuously-compounded dividend yields.

This module is the foundation of the ``market_structures/equity/`` package.
PR 1 ships only the flat-yield case (with a multi-pillar grid that is held
constant for now) so that the new object can be drop-in compatible with the
existing :class:`market_structures.volatility.forward.EquityForward`. Real
dividend term structures, discrete dividends, and a bootstrapper from
``ForwardQuote`` follow in subsequent PRs (see ``tasks/equity_forward_curve.md``).
"""

from __future__ import annotations

import logging
import math
from bisect import bisect_right
from datetime import date, timedelta
from enum import Enum
from typing import Sequence

from market_conventions import DayCountConvention
from schedules.day_count import day_count_fraction

from ..rates.curve import ZeroCurve
from .dividends import DiscreteDividend, DividendKind
from .quotes import BorrowRateQuote, DividendYieldQuote

logger = logging.getLogger(__name__)


_EQUITY_DCC = DayCountConvention.ACT_365_FIXED
_YEAR_BASIS = 365.0


class DividendYieldInterpolation(Enum):
    """Interpolation policy for the dividend-yield term structure between pillars.

    Attributes
    ----------
    FORWARD_YIELD_FLAT
        Cumulative yield ``Q(T) = q(T) * T`` is piecewise-linear in ``T``,
        equivalently the instantaneous forward dividend yield is piecewise
        constant on each ``(T_{i-1}, T_i]``. Analogous to the
        log-linear-in-discount-factor convention used by `ZeroCurve`
        (`LogLinearInterpolator`) and is the equity analogue of
        piecewise-flat instantaneous forward rates. Default.
    LINEAR_IN_YIELD
        ``q(T)`` itself is piecewise-linear in ``T`` between pillars.
        Simpler but not arbitrage-aware; provided for backward compatibility
        and for cases where the input is already a smooth ``q(T)`` curve.
    """

    FORWARD_YIELD_FLAT = "forward_yield_flat"
    LINEAR_IN_YIELD = "linear_in_yield"


class EquityForwardCurve:
    """Term-structured equity forward curve ``F(T) = S0 * exp(-q(T) * T) / DF(T)``.

    The curve is parameterised by a strictly increasing grid of pillar times
    in ACT/365 years and the continuously-compounded dividend yields
    ``q(T_i)`` at those pillars. Between pillars the yield is **linearly
    interpolated**; outside the grid it is held constant at the nearest
    pillar's value (flat extrapolation in ``q``). The risk-free leg is read
    by date from the supplied :class:`ZeroCurve`, so its internal day count
    does not need to agree with ACT/365.

    Day count is pinned to ACT/365 for the time axis, the standard equity
    quoting convention; this matches
    :class:`market_structures.volatility.forward.EquityForward`.

    The instance is callable, accepting either a :class:`datetime.date` or a
    year-fraction ``float``, mirroring ``EquityForward.__call__`` exactly so
    it duck-types as ``market_structures.volatility.surface.ForwardCallable``.

    Attributes
    ----------
    spot
        Underlying spot at the reference date.
    reference_date
        Anchor date; mirrors the supplied ``ZeroCurve.reference_date``.
    pillar_times
        Tuple of ACT/365 year fractions where dividend yields are anchored.
    pillar_yields
        Tuple of continuously-compounded dividend yields at the pillars.
    """

    def __init__(
        self,
        spot: float,
        zero_curve: ZeroCurve,
        pillar_times: Sequence[float],
        pillar_yields: Sequence[float],
        interpolation: DividendYieldInterpolation = DividendYieldInterpolation.FORWARD_YIELD_FLAT,
        discrete_dividends: Sequence[DiscreteDividend] = (),
        borrow_pillar_times: Sequence[float] = (),
        borrow_pillar_yields: Sequence[float] = (),
        borrow_interpolation: DividendYieldInterpolation | None = None,
    ) -> None:
        """Construct the curve from spot, a discount curve, and a yield term structure.

        Parameters
        ----------
        spot
            Underlying spot price at ``zero_curve.reference_date``; must be
            strictly positive.
        zero_curve
            Risk-free discount curve. Its ``reference_date`` defines ``t=0``
            for this curve.
        pillar_times
            Pillar year fractions in ACT/365, strictly positive and strictly
            increasing.
        pillar_yields
            Continuously-compounded dividend yields at each pillar; same
            length as ``pillar_times``.
        interpolation
            Interpolation policy between pillars. Defaults to
            :attr:`DividendYieldInterpolation.FORWARD_YIELD_FLAT` (piecewise
            constant instantaneous forward yield, the arbitrage-aware
            equity analogue of log-linear-in-DF).
        discrete_dividends
            Optional discrete-dividend schedule combined with the continuous
            yield as ``F(T) = (S0 * Π(1 - p_i) - Σ d_j * DF(ex_j)) * exp(-q(T)
            * T) / DF(T)`` (Hull convention). All ex-dates must be strictly
            after the curve's reference date; the sequence is sorted by
            ex-date internally and may contain multiple entries on the same
            date. Defaults to an empty schedule (continuous-only curve).
        borrow_pillar_times
            Optional second term structure for the borrow / repo yield in
            ACT/365 years. If non-empty, ``borrow_pillar_yields`` must be
            supplied with the same length. The borrow yield adds to the
            dividend yield to form the net carry: ``effective_yield(T) =
            dividend_yield(T) + borrow_yield(T)``. Positive borrow rates
            depress the forward, matching the empirical behaviour of
            hard-to-borrow names. Pillars are strictly positive and strictly
            increasing.
        borrow_pillar_yields
            Continuously-compounded borrow yields at each borrow pillar.
            May be negative. Must have the same length as
            ``borrow_pillar_times``.
        borrow_interpolation
            Interpolation policy for the borrow term structure. ``None``
            inherits the dividend ``interpolation``. Same semantics as
            :class:`DividendYieldInterpolation`.

        Raises
        ------
        ValueError
            If ``spot`` is non-positive, ``pillar_times`` is empty, the two
            lists disagree in length, any pillar is non-positive, the
            pillar grid is not strictly increasing, any discrete dividend
            has ``ex_date <= zero_curve.reference_date``, or the borrow
            term structure (when supplied) fails the same pillar
            constraints.
        """
        if spot <= 0.0:
            raise ValueError(f"spot must be positive, got {spot}")
        if len(pillar_times) == 0:
            raise ValueError("at least one pillar required")
        if len(pillar_times) != len(pillar_yields):
            raise ValueError(
                "pillar_times and pillar_yields must have the same length"
            )
        if any(t <= 0.0 for t in pillar_times):
            raise ValueError("pillar_times must be strictly positive")
        if any(b <= a for a, b in zip(pillar_times, pillar_times[1:])):
            raise ValueError("pillar_times must be strictly increasing")

        if len(borrow_pillar_times) != len(borrow_pillar_yields):
            raise ValueError(
                "borrow_pillar_times and borrow_pillar_yields must have the same length"
            )
        if len(borrow_pillar_times) > 0:
            if any(t <= 0.0 for t in borrow_pillar_times):
                raise ValueError("borrow_pillar_times must be strictly positive")
            if any(b <= a for a, b in zip(borrow_pillar_times, borrow_pillar_times[1:])):
                raise ValueError("borrow_pillar_times must be strictly increasing")

        ref = zero_curve.reference_date
        for div in discrete_dividends:
            if div.ex_date <= ref:
                raise ValueError(
                    f"discrete dividend ex_date {div.ex_date} must be strictly "
                    f"after reference_date {ref}"
                )

        self._spot = float(spot)
        self._curve = zero_curve
        self._reference_date = ref
        self._pillar_times = tuple(float(t) for t in pillar_times)
        self._pillar_yields = tuple(float(q) for q in pillar_yields)
        self._interpolation = interpolation
        self._cumulative_yields = tuple(
            t * q for t, q in zip(self._pillar_times, self._pillar_yields)
        )
        self._borrow_pillar_times = tuple(float(t) for t in borrow_pillar_times)
        self._borrow_pillar_yields = tuple(float(b) for b in borrow_pillar_yields)
        self._borrow_interpolation = (
            borrow_interpolation if borrow_interpolation is not None else interpolation
        )
        self._borrow_cumulative_yields = tuple(
            t * b for t, b in zip(self._borrow_pillar_times, self._borrow_pillar_yields)
        )
        sorted_divs = sorted(discrete_dividends, key=lambda d: d.ex_date)
        self._discrete_dividends: tuple[DiscreteDividend, ...] = tuple(sorted_divs)
        self._div_ex_dates: tuple[date, ...] = tuple(d.ex_date for d in sorted_divs)
        self._div_pv_cash: tuple[float, ...] = tuple(
            d.amount * zero_curve.discount_factor(d.ex_date)
            if d.kind is DividendKind.CASH
            else 0.0
            for d in sorted_divs
        )
        self._div_log_prop: tuple[float, ...] = tuple(
            math.log1p(-d.amount) if d.kind is DividendKind.PROPORTIONAL else 0.0
            for d in sorted_divs
        )
        logger.info(
            "EquityForwardCurve built: spot=%.6g pillars=%d interp=%s "
            "borrow_pillars=%d discrete_divs=%d ref=%s",
            self._spot,
            len(self._pillar_times),
            interpolation.value,
            len(self._borrow_pillar_times),
            len(self._discrete_dividends),
            self._reference_date,
        )

    @classmethod
    def from_dividend_yield_quotes(
        cls,
        spot: float,
        zero_curve: ZeroCurve,
        quotes: Sequence[DividendYieldQuote],
        interpolation: DividendYieldInterpolation = DividendYieldInterpolation.FORWARD_YIELD_FLAT,
    ) -> EquityForwardCurve:
        """Build the curve from a list of dividend-yield market quotes.

        The quotes are sorted by maturity, validated against the discount
        curve's reference date, and converted to ACT/365 year fractions. The
        resulting ``(T_i, q_i)`` grid is handed to the standard constructor.

        Parameters
        ----------
        spot
            Underlying spot price; must be strictly positive.
        zero_curve
            Risk-free discount curve providing ``reference_date`` and
            ``discount_factor(date)``.
        quotes
            Dividend-yield quotes. Must contain at least one entry; all
            maturities must be strictly after ``zero_curve.reference_date``
            and pairwise distinct.
        interpolation
            Interpolation policy passed through to the constructor; defaults
            to :attr:`DividendYieldInterpolation.FORWARD_YIELD_FLAT`.

        Returns
        -------
        EquityForwardCurve
            Curve anchored at the discount curve's reference date.

        Raises
        ------
        ValueError
            If ``quotes`` is empty, contains a maturity on or before the
            reference date, or contains duplicate maturities.
        """
        if len(quotes) == 0:
            raise ValueError("at least one DividendYieldQuote required")
        ref = zero_curve.reference_date
        for quote in quotes:
            if quote.maturity_date <= ref:
                raise ValueError(
                    f"quote maturity {quote.maturity_date} must be strictly "
                    f"after reference_date {ref}"
                )
        sorted_quotes = sorted(quotes, key=lambda q: q.maturity_date)
        for prev, curr in zip(sorted_quotes, sorted_quotes[1:]):
            if prev.maturity_date == curr.maturity_date:
                raise ValueError(
                    f"duplicate quote maturity {curr.maturity_date}"
                )
        pillar_times = [
            day_count_fraction(ref, q.maturity_date, _EQUITY_DCC)
            for q in sorted_quotes
        ]
        pillar_yields = [q.continuous_yield for q in sorted_quotes]
        return cls(
            spot=spot,
            zero_curve=zero_curve,
            pillar_times=pillar_times,
            pillar_yields=pillar_yields,
            interpolation=interpolation,
        )

    @classmethod
    def from_dividend_and_borrow_quotes(
        cls,
        spot: float,
        zero_curve: ZeroCurve,
        dividend_quotes: Sequence[DividendYieldQuote],
        borrow_quotes: Sequence[BorrowRateQuote],
        interpolation: DividendYieldInterpolation = DividendYieldInterpolation.FORWARD_YIELD_FLAT,
        borrow_interpolation: DividendYieldInterpolation | None = None,
    ) -> EquityForwardCurve:
        """Build a curve with explicit dividend AND borrow term structures.

        Each input list is sorted independently and may have its own pillar
        grid; the two need not share maturities. Validation, duplicate
        rejection, and date-to-ACT/365 conversion mirror
        :meth:`from_dividend_yield_quotes`.

        Parameters
        ----------
        spot
            Underlying spot price; must be strictly positive.
        zero_curve
            Risk-free discount curve.
        dividend_quotes
            Dividend-yield quotes. Must contain at least one entry.
        borrow_quotes
            Borrow-rate quotes. Must contain at least one entry; pass an
            empty list and use :meth:`from_dividend_yield_quotes` instead if
            you don't need a borrow split.
        interpolation
            Interpolation policy for the dividend term structure. Defaults
            to :attr:`DividendYieldInterpolation.FORWARD_YIELD_FLAT`.
        borrow_interpolation
            Interpolation policy for the borrow term structure. ``None``
            inherits ``interpolation``.

        Returns
        -------
        EquityForwardCurve
            Curve such that ``effective_yield(T) = dividend_yield(T) +
            borrow_yield(T)`` at every queried ``T``, and the dividend /
            borrow components are exactly recoverable at their respective
            pillars.

        Raises
        ------
        ValueError
            If either quote list is empty, contains a maturity on or before
            the reference date, or contains duplicate maturities within its
            own list (cross-list duplicates are allowed — they simply yield
            coincident pillars in the two term structures).
        """
        if len(dividend_quotes) == 0:
            raise ValueError("at least one DividendYieldQuote required")
        if len(borrow_quotes) == 0:
            raise ValueError(
                "at least one BorrowRateQuote required; use "
                "from_dividend_yield_quotes for a borrow-free curve"
            )
        ref = zero_curve.reference_date

        def _to_pillars(
            quotes: Sequence,
            value_attr: str,
            quote_label: str,
        ) -> tuple[list[float], list[float]]:
            for q in quotes:
                if q.maturity_date <= ref:
                    raise ValueError(
                        f"{quote_label} maturity {q.maturity_date} must be strictly "
                        f"after reference_date {ref}"
                    )
            sorted_q = sorted(quotes, key=lambda x: x.maturity_date)
            for prev, curr in zip(sorted_q, sorted_q[1:]):
                if prev.maturity_date == curr.maturity_date:
                    raise ValueError(
                        f"duplicate {quote_label} maturity {curr.maturity_date}"
                    )
            return (
                [day_count_fraction(ref, q.maturity_date, _EQUITY_DCC) for q in sorted_q],
                [getattr(q, value_attr) for q in sorted_q],
            )

        div_times, div_yields = _to_pillars(
            dividend_quotes, "continuous_yield", "DividendYieldQuote"
        )
        bor_times, bor_yields = _to_pillars(
            borrow_quotes, "continuous_borrow_rate", "BorrowRateQuote"
        )
        return cls(
            spot=spot,
            zero_curve=zero_curve,
            pillar_times=div_times,
            pillar_yields=div_yields,
            interpolation=interpolation,
            borrow_pillar_times=bor_times,
            borrow_pillar_yields=bor_yields,
            borrow_interpolation=borrow_interpolation,
        )

    @classmethod
    def from_discrete_dividends(
        cls,
        spot: float,
        zero_curve: ZeroCurve,
        dividends: Sequence[DiscreteDividend],
        borrow_rate: float = 0.0,
    ) -> EquityForwardCurve:
        """Build a curve from a discrete dividend schedule and an optional flat borrow.

        The continuous yield component is set to a single flat pillar at
        ``q = borrow_rate``; the discrete dividends are applied on top per the
        Hull convention (see :meth:`__init__`). This is the natural entry
        point for single-stock names where dividends are quoted as a
        schedule of cash amounts and proportional drops rather than a
        continuous yield strip.

        Parameters
        ----------
        spot
            Underlying spot price; must be strictly positive.
        zero_curve
            Risk-free discount curve providing ``reference_date`` and
            ``discount_factor(date)``.
        dividends
            Discrete dividend schedule; may be empty (which is equivalent to
            :meth:`flat` with ``dividend_yield=borrow_rate``).
        borrow_rate
            Flat continuous carry applied as ``exp(-borrow_rate * T)`` in the
            forward formula. Conventions match
            :class:`market_structures.volatility.forward.EquityForward`:
            positive ``borrow_rate`` reduces the forward, negative increases
            it. Defaults to zero (pure-cash-carry curve). A term structure of
            borrow / repo is deferred to a later PR.

        Returns
        -------
        EquityForwardCurve
            Curve combining the discrete schedule with the flat continuous
            carry.
        """
        return cls(
            spot=spot,
            zero_curve=zero_curve,
            pillar_times=[1.0],
            pillar_yields=[borrow_rate],
            discrete_dividends=dividends,
        )

    @classmethod
    def flat(
        cls,
        spot: float,
        zero_curve: ZeroCurve,
        dividend_yield: float,
    ) -> EquityForwardCurve:
        """Construct a degenerate single-pillar curve with a flat dividend yield.

        Numerically identical to
        :class:`market_structures.volatility.forward.EquityForward` constructed
        with the same arguments; this classmethod exists so that the new curve
        is a strict superset of the legacy flat-yield forward.

        Parameters
        ----------
        spot
            Underlying spot price; must be strictly positive.
        zero_curve
            Risk-free discount curve providing ``reference_date`` and
            ``discount_factor(date)``.
        dividend_yield
            Continuous dividend yield ``q`` in ACT/365, held constant across
            all maturities.

        Returns
        -------
        EquityForwardCurve
            Curve with a single pillar at ``T = 1.0`` and the supplied yield;
            because extrapolation is flat in ``q``, the constant ``q`` applies
            at every maturity.
        """
        return cls(
            spot=spot,
            zero_curve=zero_curve,
            pillar_times=[1.0],
            pillar_yields=[dividend_yield],
        )

    @property
    def spot(self) -> float:
        """Return the underlying spot at the reference date."""
        return self._spot

    @property
    def reference_date(self) -> date:
        """Return the curve's reference date (the discount curve's anchor)."""
        return self._reference_date

    @property
    def pillar_times(self) -> tuple[float, ...]:
        """Return the pillar grid in ACT/365 years."""
        return self._pillar_times

    @property
    def pillar_yields(self) -> tuple[float, ...]:
        """Return the continuously-compounded dividend yields at the pillars."""
        return self._pillar_yields

    @property
    def discrete_dividends(self) -> tuple[DiscreteDividend, ...]:
        """Return the discrete dividend schedule, sorted by ex-date."""
        return self._discrete_dividends

    @property
    def borrow_pillar_times(self) -> tuple[float, ...]:
        """Return the borrow term structure's pillar grid in ACT/365 years.

        Empty tuple if no borrow curve was supplied at construction.
        """
        return self._borrow_pillar_times

    @property
    def borrow_pillar_yields(self) -> tuple[float, ...]:
        """Return the continuously-compounded borrow yields at the borrow pillars.

        Empty tuple if no borrow curve was supplied at construction.
        """
        return self._borrow_pillar_yields

    @property
    def has_borrow_curve(self) -> bool:
        """Return ``True`` if a borrow term structure was supplied at construction."""
        return bool(self._borrow_pillar_times)

    def _discrete_adjustment(
        self,
        expiry: date,
    ) -> tuple[float, float]:
        """Return ``(prop_factor, pv_cash)`` aggregating dividends with ``ex_date <= expiry``.

        Parameters
        ----------
        expiry
            Forward maturity date.

        Returns
        -------
        prop_factor
            ``Π_{ex_i <= expiry} (1 - p_i)`` over proportional dividends.
        pv_cash
            ``Σ_{ex_j <= expiry} d_j * DF(ex_j)`` over cash dividends.
        """
        if not self._discrete_dividends:
            return 1.0, 0.0
        log_prop = 0.0
        pv_cash = 0.0
        for ex_date, pv_amount, log_factor in zip(
            self._div_ex_dates, self._div_pv_cash, self._div_log_prop
        ):
            if ex_date > expiry:
                break
            pv_cash += pv_amount
            log_prop += log_factor
        prop_factor = math.exp(log_prop) if log_prop != 0.0 else 1.0
        return prop_factor, pv_cash

    @staticmethod
    def _interpolate_yield(
        time_to_expiry: float,
        times: tuple[float, ...],
        yields: tuple[float, ...],
        cumulative_yields: tuple[float, ...],
        interpolation: DividendYieldInterpolation,
    ) -> float:
        """Interpolate a yield term structure under the given mode.

        Shared kernel for both :meth:`dividend_yield` and :meth:`borrow_yield`.
        Caller is responsible for validating ``time_to_expiry > 0`` and that
        the pillar grid is non-empty.

        Parameters
        ----------
        time_to_expiry
            Year fraction at which to evaluate the term structure.
        times
            Strictly increasing pillar grid in ACT/365 years.
        yields
            Pillar yields aligned with ``times``.
        cumulative_yields
            Pre-computed ``t_i * y_i`` per pillar; used only when
            ``interpolation`` is ``FORWARD_YIELD_FLAT``.
        interpolation
            Policy selecting forward-yield-flat or linear-in-yield.

        Returns
        -------
        float
            Interpolated yield at ``time_to_expiry``. Flat extrapolation in
            the yield value above the last pillar; in
            ``FORWARD_YIELD_FLAT`` mode below the first pillar the
            cumulative yield is linearly interpolated from the implicit
            ``(0, 0)`` anchor.
        """
        if time_to_expiry >= times[-1]:
            return yields[-1]
        if interpolation is DividendYieldInterpolation.FORWARD_YIELD_FLAT:
            if time_to_expiry <= times[0]:
                t_lo, q_lo_cum = 0.0, 0.0
                t_hi, q_hi_cum = times[0], cumulative_yields[0]
            else:
                idx = bisect_right(times, time_to_expiry)
                t_lo = times[idx - 1]
                t_hi = times[idx]
                q_lo_cum = cumulative_yields[idx - 1]
                q_hi_cum = cumulative_yields[idx]
            w = (time_to_expiry - t_lo) / (t_hi - t_lo)
            cumulative = q_lo_cum + w * (q_hi_cum - q_lo_cum)
            return cumulative / time_to_expiry
        if time_to_expiry <= times[0]:
            return yields[0]
        idx = bisect_right(times, time_to_expiry)
        t_lo, t_hi = times[idx - 1], times[idx]
        q_lo, q_hi = yields[idx - 1], yields[idx]
        w = (time_to_expiry - t_lo) / (t_hi - t_lo)
        return q_lo + w * (q_hi - q_lo)

    def dividend_yield(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return the interpolated continuous dividend yield at ``time_to_expiry``.

        Behaviour depends on the curve's :class:`DividendYieldInterpolation`
        mode:

        - ``FORWARD_YIELD_FLAT`` (default): cumulative yield ``Q(T) = q(T) *
          T`` is piecewise-linear in ``T`` between pillars, with the
          ``(T_0, Q_0) = (0, 0)`` anchor implied. ``q(T) = Q(T) / T``.
        - ``LINEAR_IN_YIELD``: ``q(T)`` itself is piecewise-linear in ``T``
          between pillars.

        Outside the pillar grid, both modes extrapolate **flat in q** (held
        constant at the boundary pillar's value). At a pillar both modes
        agree by construction. This method returns the dividend component
        only; if a borrow term structure is attached, use
        :meth:`effective_yield` for the net carry that feeds the forward
        formula.

        Parameters
        ----------
        time_to_expiry
            Year fraction from the reference date; must be strictly positive.

        Returns
        -------
        float
            Continuous dividend yield at ``time_to_expiry``.

        Raises
        ------
        ValueError
            If ``time_to_expiry`` is non-positive.
        """
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be positive, got {time_to_expiry}"
            )
        return self._interpolate_yield(
            time_to_expiry,
            self._pillar_times,
            self._pillar_yields,
            self._cumulative_yields,
            self._interpolation,
        )

    def borrow_yield(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return the interpolated continuous borrow yield at ``time_to_expiry``.

        Returns ``0.0`` when the curve was built without a borrow term
        structure (i.e. ``borrow_pillar_times`` was empty at construction),
        so callers can always sum ``dividend_yield`` and ``borrow_yield``
        without an extra branch. When a borrow term structure is present,
        interpolation follows the same scheme as :meth:`dividend_yield` but
        under the (possibly distinct) ``borrow_interpolation`` policy.

        Parameters
        ----------
        time_to_expiry
            Year fraction from the reference date; must be strictly positive.

        Returns
        -------
        float
            Continuous borrow yield at ``time_to_expiry``.

        Raises
        ------
        ValueError
            If ``time_to_expiry`` is non-positive.
        """
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be positive, got {time_to_expiry}"
            )
        if not self._borrow_pillar_times:
            return 0.0
        return self._interpolate_yield(
            time_to_expiry,
            self._borrow_pillar_times,
            self._borrow_pillar_yields,
            self._borrow_cumulative_yields,
            self._borrow_interpolation,
        )

    def effective_yield(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return the net carry yield consumed by the forward formula.

        ``effective_yield(T) = dividend_yield(T) + borrow_yield(T)``. This
        is the quantity that appears in the exponential carry factor
        ``exp(-effective_yield * T)`` of :meth:`at_date` and :meth:`at_time`.

        Parameters
        ----------
        time_to_expiry
            Year fraction from the reference date; must be strictly positive.

        Returns
        -------
        float
            Sum of the dividend and borrow yields at ``time_to_expiry``.
        """
        return self.dividend_yield(time_to_expiry) + self.borrow_yield(time_to_expiry)

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
            Forward price ``S0 * exp(-q(T) * T) / DF(expiry)``.

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
        q = self.effective_yield(t)
        df = self._curve.discount_factor(expiry)
        prop_factor, pv_cash = self._discrete_adjustment(expiry)
        adjusted_spot = self._spot * prop_factor - pv_cash
        if adjusted_spot <= 0.0:
            raise ValueError(
                f"discounted spot net of cash dividends is non-positive at expiry "
                f"{expiry}: spot * Π(1-p) = {self._spot * prop_factor:.6g}, "
                f"PV(cash) = {pv_cash:.6g}"
            )
        return adjusted_spot * math.exp(-q * t) / df

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
            Forward price ``S0 * exp(-q(T) * T) / DF(T)``.

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
        q = self.effective_yield(time_to_expiry)
        df = self._curve.discount_factor(expiry)
        prop_factor, pv_cash = self._discrete_adjustment(expiry)
        adjusted_spot = self._spot * prop_factor - pv_cash
        if adjusted_spot <= 0.0:
            raise ValueError(
                f"discounted spot net of cash dividends is non-positive at T={time_to_expiry}: "
                f"spot * Π(1-p) = {self._spot * prop_factor:.6g}, "
                f"PV(cash) = {pv_cash:.6g}"
            )
        return adjusted_spot * math.exp(-q * time_to_expiry) / df

    def __call__(
        self,
        when: float | date,
    ) -> float:
        """Return the forward at a maturity given as either a date or a year fraction.

        Mirrors :meth:`market_structures.volatility.forward.EquityForward.__call__`
        so that ``EquityForwardCurve`` duck-types as ``ForwardCallable``.

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
