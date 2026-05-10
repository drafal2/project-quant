"""Credit curve with three interpolation parameterisations."""

from __future__ import annotations

import math
from bisect import bisect_left
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

from market_conventions import DayCountConvention
from schedules.day_count import day_count_fraction

if TYPE_CHECKING:
    from .quotes import CdsQuote


class InterpolationVariable(Enum):
    """Pillar variable that is linearly interpolated between pillars.

    Attributes
    ----------
    SURVIVAL_PROBABILITY
        Pillar values are Q(t_i); linear interpolation in Q(t), flat
        extrapolation beyond the last pillar.
    DEFAULT_SPREAD
        Pillar values are s_i with Q(t_i) = exp(-s_i * t_i); linear
        interpolation in s(t), flat extrapolation.
    FORWARD_DEFAULT_SPREAD
        Pillar values are forward hazard rates lambda_i, one per segment
        (t_{i-1}, t_i]; piecewise-constant in lambda, flat extrapolation
        of the last segment rate.
    """

    SURVIVAL_PROBABILITY = "survival_probability"
    DEFAULT_SPREAD = "default_spread"
    FORWARD_DEFAULT_SPREAD = "forward_default_spread"


class CreditCurve:
    """Credit curve under the deterministic-intensity model.

    Survival probability Q(t) = P(tau > t), where tau is the first jump time of a
    Poisson process with deterministic intensity lambda(t). The curve stores pillar
    values of one of three interpolation variables and exposes Q(t), the cumulative
    default spread, and forward default spreads at arbitrary dates.
    """

    def __init__(
        self,
        reference_date: date,
        pillar_dates: list[date],
        pillar_values: list[float],
        interpolation_variable: InterpolationVariable = InterpolationVariable.FORWARD_DEFAULT_SPREAD,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_365_FIXED,
        quotes: list[CdsQuote] | None = None,
    ) -> None:
        """Construct a credit curve from pillar dates and values of the chosen variable.

        Parameters
        ----------
        reference_date
            Curve anchor date (t=0); all pillar dates must lie strictly after.
        pillar_dates
            Pillar dates, one per pillar value. Sorted internally.
        pillar_values
            Pillar values for the configured ``interpolation_variable``:
            survival probabilities Q(t_i), cumulative default spreads s_i, or
            piecewise forward hazard rates lambda_i.
        interpolation_variable
            Variable that is interpolated between pillars. Defaults to
            ``FORWARD_DEFAULT_SPREAD``.
        day_count_convention
            Day count used for converting dates to year fractions. Defaults to
            ``ACT_365_FIXED``.
        quotes
            Optional list of CDS quotes that calibrated this curve, retained
            for downstream inspection (e.g. ``summary``).

        Raises
        ------
        ValueError
            If ``pillar_dates`` and ``pillar_values`` differ in length, if no
            pillars are supplied, if any pillar date is at or before
            ``reference_date``, or if pillar values violate the interpolation
            variable's invariants (survival in (0, 1] and non-increasing;
            spreads and hazard rates non-negative).
        """
        if len(pillar_dates) != len(pillar_values):
            raise ValueError("pillar_dates and pillar_values must have the same length")
        if len(pillar_dates) == 0:
            raise ValueError("at least one pillar required")
        if any(d <= reference_date for d in pillar_dates):
            raise ValueError("all pillar dates must be after reference_date")

        self._reference_date = reference_date
        self._dcc = day_count_convention
        self._variable = interpolation_variable
        self._quotes: list[CdsQuote] = list(quotes) if quotes is not None else []

        sorted_pairs = sorted(zip(pillar_dates, pillar_values), key=lambda x: x[0])
        self._pillar_dates = [p[0] for p in sorted_pairs]
        self._pillar_values = [p[1] for p in sorted_pairs]
        self._pillar_times = [self._t(d) for d in self._pillar_dates]

        self._validate_values()
        self._survival_at_pillars = self._compute_pillar_survivals()

    @property
    def reference_date(self) -> date:
        """Curve reference date (t=0)."""
        return self._reference_date

    @property
    def interpolation_variable(self) -> InterpolationVariable:
        """Variable that is interpolated between pillars."""
        return self._variable

    @property
    def pillar_dates(self) -> list[date]:
        """Pillar dates in chronological order."""
        return list(self._pillar_dates)

    @property
    def pillar_values(self) -> list[float]:
        """Pillar values in the configured interpolation variable."""
        return list(self._pillar_values)

    def _t(self, d: date) -> float:
        """Return the day-count fraction from the reference date to d."""
        return day_count_fraction(self._reference_date, d, self._dcc)

    def _validate_values(self) -> None:
        """Validate pillar values against the interpolation-variable invariants.

        Raises
        ------
        ValueError
            For ``SURVIVAL_PROBABILITY``: if any value is outside (0, 1] or
            the sequence is not non-increasing. For ``DEFAULT_SPREAD`` and
            ``FORWARD_DEFAULT_SPREAD``: if any value is negative.
        """
        v = self._pillar_values
        if self._variable is InterpolationVariable.SURVIVAL_PROBABILITY:
            if any(q <= 0.0 or q > 1.0 for q in v):
                raise ValueError("survival probabilities must lie in (0, 1]")
            if any(v[i] > v[i - 1] for i in range(1, len(v))):
                raise ValueError("survival probabilities must be non-increasing")
        else:
            if any(x < 0.0 for x in v):
                raise ValueError(f"{self._variable.value} values must be >= 0")

    def _compute_pillar_survivals(self) -> list[float]:
        """Compute Q(t_i) at each pillar from the configured pillar values.

        Returns
        -------
        list[float]
            Survival probability at each pillar, in the same order as
            ``self._pillar_dates``.
        """
        v = self._pillar_values
        ts = self._pillar_times
        if self._variable is InterpolationVariable.SURVIVAL_PROBABILITY:
            return list(v)
        if self._variable is InterpolationVariable.DEFAULT_SPREAD:
            return [math.exp(-s * ti) for s, ti in zip(v, ts)]
        survivals: list[float] = []
        prev_q = 1.0
        prev_t = 0.0
        for lam, ti in zip(v, ts):
            prev_q *= math.exp(-lam * (ti - prev_t))
            survivals.append(prev_q)
            prev_t = ti
        return survivals

    def non_default_probability(self, d: date) -> float:
        """Return the survival probability Q(d) = P(tau > d).

        Parameters
        ----------
        d
            Query date.

        Returns
        -------
        float
            Survival probability at ``d``; ``1.0`` for any ``d`` at or before
            the reference date.
        """
        if d <= self._reference_date:
            return 1.0
        return self._survival_at_time(self._t(d))

    def survival_probability(self, d: date) -> float:
        """Alias for :meth:`non_default_probability`.

        Parameters
        ----------
        d
            Query date.

        Returns
        -------
        float
            Survival probability at ``d``.
        """
        return self.non_default_probability(d)

    def default_probability(self, d: date) -> float:
        """Return the cumulative default probability ``1 - Q(d)``.

        Parameters
        ----------
        d
            Query date.

        Returns
        -------
        float
            Probability of default by ``d``.
        """
        return 1.0 - self.non_default_probability(d)

    def _survival_at_time(self, t: float) -> float:
        """Return Q(t) given a year-fraction time t > 0 from the reference date."""
        ts = self._pillar_times
        qs = self._survival_at_pillars

        if self._variable is InterpolationVariable.SURVIVAL_PROBABILITY:
            if t <= ts[0]:
                return 1.0 + (qs[0] - 1.0) * (t / ts[0])
            if t >= ts[-1]:
                return qs[-1]
            i = bisect_left(ts, t)
            t0, t1 = ts[i - 1], ts[i]
            q0, q1 = qs[i - 1], qs[i]
            w = (t - t0) / (t1 - t0)
            return q0 + w * (q1 - q0)

        if self._variable is InterpolationVariable.DEFAULT_SPREAD:
            v = self._pillar_values
            if t <= ts[0]:
                s = v[0]
            elif t >= ts[-1]:
                s = v[-1]
            else:
                i = bisect_left(ts, t)
                t0, t1 = ts[i - 1], ts[i]
                s0, s1 = v[i - 1], v[i]
                w = (t - t0) / (t1 - t0)
                s = s0 + w * (s1 - s0)
            return math.exp(-s * t)

        v = self._pillar_values
        if t <= ts[0]:
            return math.exp(-v[0] * t)
        if t >= ts[-1]:
            return qs[-1] * math.exp(-v[-1] * (t - ts[-1]))
        i = bisect_left(ts, t)
        return qs[i - 1] * math.exp(-v[i] * (t - ts[i - 1]))

    def default_spread(self, d: date) -> float:
        """Return the cumulative-equivalent default spread s with Q(d) = exp(-s * t(d)).

        Parameters
        ----------
        d
            Query date; must lie strictly after the reference date.

        Returns
        -------
        float
            Continuously compounded default spread implied by the curve at
            ``d``.

        Raises
        ------
        ValueError
            If ``d`` is at or before the reference date, or if the implied
            survival probability is non-positive.
        """
        if d <= self._reference_date:
            raise ValueError("default_spread undefined at or before reference_date")
        q = self.non_default_probability(d)
        if q <= 0.0:
            raise ValueError(f"non-positive survival probability at {d}")
        return -math.log(q) / self._t(d)

    def forward_default_spread(
        self,
        start: date,
        end: date,
    ) -> float:
        """Return the forward hazard rate between two dates.

        Computes ``-ln(Q(end) / Q(start)) / (t(end) - t(start))``.

        Parameters
        ----------
        start
            Period start date.
        end
            Period end date; must lie strictly after ``start``.

        Returns
        -------
        float
            Forward hazard rate over the interval.

        Raises
        ------
        ValueError
            If ``start`` is not strictly before ``end``, or if either
            endpoint's survival probability is non-positive.
        """
        if start >= end:
            raise ValueError("start must be before end")
        q_start = self.non_default_probability(start)
        q_end = self.non_default_probability(end)
        if q_start <= 0.0 or q_end <= 0.0:
            raise ValueError("non-positive survival probability in interval")
        dt = self._t(end) - self._t(start)
        return -math.log(q_end / q_start) / dt

    def summary(self) -> str:
        """Return a formatted table of pillars with Q, cumulative spread, and forward hazard.

        Returns
        -------
        str
            Multi-line table prefixed with the configured
            ``InterpolationVariable``. Columns:

            - ``Pillar`` — pillar date.
            - ``Tenor`` — year fraction ``t_i`` from the reference date,
              under the curve's day-count convention.
            - ``Q`` — survival probability ``Q(t_i) = P(tau > t_i)``.
            - ``DefSpread`` — cumulative-equivalent default spread
              ``s(t_i) = -ln Q(t_i) / t_i``, anchored at the reference
              date. Equivalently, the time-average of the hazard rate from
              ``0`` to ``t_i``.
            - ``FwdHazard (lambda(t))`` — segment-local forward hazard
              ``-ln(Q_i / Q_{i-1}) / (t_i - t_{i-1})`` from the previous
              pillar (or reference date for the first pillar). Under
              ``FORWARD_DEFAULT_SPREAD`` interpolation this is the
              piecewise-constant ``lambda`` on the segment exactly; under
              the other parameterisations it is the segment-average of a
              continuously varying ``lambda(t)``.

            For pillar 1, ``DefSpread`` and ``FwdHazard`` coincide; further
            out they diverge whenever the term structure of hazards is
            non-flat.
        """
        if not self._pillar_dates:
            return ""
        header = (
            f"{'Pillar':>12} {'Tenor':>10} {'Q':>10} "
            f"{'DefSpread':>12} {'FwdHazard (lambda(t))':>12}"
        )
        sep = "-" * len(header)
        rows = [f"InterpolationVariable: {self._variable.value}", header, sep]
        prev_d = self._reference_date
        for d, q, t in zip(self._pillar_dates, self._survival_at_pillars, self._pillar_times):
            cum_spread = -math.log(q) / t if q > 0 else float("nan")
            fwd = self.forward_default_spread(prev_d, d)
            rows.append(
                f"{str(d):>12} {t:>10.4f} {q:>10.6f} "
                f"{cum_spread:>12.6%} {fwd:>12.6%}"
            )
            prev_d = d
        return "\n".join(rows)
