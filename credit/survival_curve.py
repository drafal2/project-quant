"""Survival curve with piecewise-constant hazard rates and bootstrap from market CDS spreads."""

import math
from bisect import bisect_left
from datetime import date

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from schedules import CalendarType, Frequency, Schedule
from schedules.day_count import day_count_fraction


def _par_spread_from_schedule(periods, discount_curve, survival_curve, recovery_rate):
    """Compute par CDS spread from a schedule, discount curve, and survival curve.

    Uses the midpoint discount factor approximation so that the protection leg
    correctly approaches zero as the hazard rate approaches zero.
    """
    prot = 0.0
    rpv01 = 0.0
    for p in periods:
        df_s = discount_curve.discount_factor(p.accrual_start)
        df_e = discount_curve.discount_factor(p.accrual_end)
        df_pay = discount_curve.discount_factor(p.pay_date)
        q_s = survival_curve.survival_probability(p.accrual_start)
        q_e = survival_curve.survival_probability(p.accrual_end)
        df_avg = (df_s + df_e) / 2.0
        dq = q_s - q_e
        prot += (1.0 - recovery_rate) * df_avg * dq
        rpv01 += p.dcf * df_pay * q_e + (p.dcf / 2.0) * df_avg * dq
    return prot / rpv01


class SurvivalCurve:
    """Piecewise-constant hazard rate survival curve, optionally bootstrapped from market CDS spreads."""

    def __init__(
        self,
        reference_date: date,
        pillar_dates: list[date],
        hazard_rates: list[float],
        day_count_convention: DayCountConvention = DayCountConvention.ACT_365_FIXED,
    ) -> None:
        """Construct a survival curve from pillar dates and per-segment hazard rates.

        Each hazard rate covers the segment [t_{i-1}, t_i] where t_0 = 0 (reference date).
        All hazard rates must be >= 0. All pillar dates must be after reference_date.
        """
        if len(pillar_dates) != len(hazard_rates):
            raise ValueError("pillar_dates and hazard_rates must have the same length")
        if len(pillar_dates) == 0:
            raise ValueError("at least one pillar required")
        if any(d <= reference_date for d in pillar_dates):
            raise ValueError("all pillar dates must be after reference_date")
        if any(h < 0 for h in hazard_rates):
            raise ValueError("all hazard_rates must be >= 0")

        self._reference_date = reference_date
        self._dcc = day_count_convention
        self._bootstrap_meta = None

        sorted_pairs = sorted(zip(pillar_dates, hazard_rates), key=lambda x: x[0])
        self._pillar_dates, self._hazard_rates = [list(x) for x in zip(*sorted_pairs)]
        self._recompute_cumulative_hazard()

    def _recompute_cumulative_hazard(self) -> None:
        """Recompute pillar times and cumulative hazard from current state."""
        self._pillar_times = [
            day_count_fraction(self._reference_date, d, self._dcc)
            for d in self._pillar_dates
        ]
        H = []
        for i, (h, t) in enumerate(zip(self._hazard_rates, self._pillar_times)):
            if i == 0:
                H.append(h * t)
            else:
                H.append(H[-1] + h * (t - self._pillar_times[i - 1]))
        self._cumulative_hazard = H

    def _t(self, d: date) -> float:
        """Return the year fraction from reference date to d."""
        return day_count_fraction(self._reference_date, d, self._dcc)

    def survival_probability(self, d: date) -> float:
        """Return the survival probability Q(d) = exp(-H(d)).

        Returns 1.0 for d <= reference_date. Flat-extrapolates beyond the last pillar.
        """
        if d <= self._reference_date:
            return 1.0
        t = self._t(d)
        n = len(self._pillar_times)
        idx = bisect_left(self._pillar_times, t)
        if idx == 0:
            H = self._hazard_rates[0] * t
        elif idx >= n:
            H = self._cumulative_hazard[-1] + self._hazard_rates[-1] * (t - self._pillar_times[-1])
        else:
            H = self._cumulative_hazard[idx - 1] + self._hazard_rates[idx] * (t - self._pillar_times[idx - 1])
        return math.exp(-H)

    def hazard_rate(self, d: date) -> float:
        """Return the piecewise-constant hazard rate at date d.

        Flat-extrapolates the last segment rate beyond the final pillar.
        """
        if d <= self._reference_date:
            return self._hazard_rates[0]
        t = self._t(d)
        idx = bisect_left(self._pillar_times, t)
        if idx >= len(self._hazard_rates):
            return self._hazard_rates[-1]
        return self._hazard_rates[idx]

    def add_pillar(self, d: date, h: float) -> None:
        """Add a pillar at date d with hazard rate h, inserting in sorted order."""
        if d <= self._reference_date:
            raise ValueError("pillar date must be after reference_date")
        if d in self._pillar_dates:
            raise ValueError(f"pillar {d} already exists")
        if h < 0:
            raise ValueError("hazard_rate must be >= 0")
        idx = bisect_left(self._pillar_dates, d)
        self._pillar_dates.insert(idx, d)
        self._hazard_rates.insert(idx, h)
        self._recompute_cumulative_hazard()
        self._bootstrap_meta = None

    def remove_pillar(self, d: date) -> None:
        """Remove the pillar at date d."""
        if d not in self._pillar_dates:
            raise ValueError(f"pillar {d} not found")
        if len(self._pillar_dates) == 1:
            raise ValueError("curve must have at least one pillar")
        idx = self._pillar_dates.index(d)
        self._pillar_dates.pop(idx)
        self._hazard_rates.pop(idx)
        self._recompute_cumulative_hazard()
        self._bootstrap_meta = None

    def bump(self, delta: float) -> "SurvivalCurve":
        """Return a new SurvivalCurve bootstrapped with market spreads shifted by delta.

        Raises ValueError if the curve was not created via from_spreads.
        """
        if self._bootstrap_meta is None:
            raise ValueError("bump requires a bootstrapped curve; use SurvivalCurve.from_spreads")
        meta = self._bootstrap_meta
        bumped_spreads = [s + delta for s in meta["spreads"]]
        return SurvivalCurve.from_spreads(
            meta["reference_date"],
            meta["pillar_dates"],
            bumped_spreads,
            meta["discount_curve"],
            meta["recovery_rate"],
            meta["pay_frequency"],
            meta["day_count_convention"],
            meta["business_day_convention"],
            meta["calendar"],
            meta["stub_type"],
            meta["curve_day_count_convention"],
        )

    @classmethod
    def from_spreads(
        cls,
        reference_date: date,
        pillar_dates: list[date],
        spreads: list[float],
        discount_curve,
        recovery_rate: float,
        pay_frequency: Frequency = Frequency.QUARTERLY,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_360,
        business_day_convention: BusinessDayConvention = BusinessDayConvention.FOLLOWING,
        calendar: CalendarType = CalendarType.USD,
        stub_type: StubType = StubType.SHORT_FRONT,
        curve_day_count_convention: DayCountConvention = DayCountConvention.ACT_365_FIXED,
    ) -> "SurvivalCurve":
        """Bootstrap a SurvivalCurve from market CDS spread quotes.

        Solves for piecewise-constant hazard rates using bisection per pillar so that
        the implied par spread at each pillar matches the given market spread.
        Spreads are in decimal (0.01 = 100 bps).
        """
        bootstrap_meta = {
            "reference_date": reference_date,
            "pillar_dates": list(pillar_dates),
            "spreads": list(spreads),
            "discount_curve": discount_curve,
            "recovery_rate": recovery_rate,
            "pay_frequency": pay_frequency,
            "day_count_convention": day_count_convention,
            "business_day_convention": business_day_convention,
            "calendar": calendar,
            "stub_type": stub_type,
            "curve_day_count_convention": curve_day_count_convention,
        }

        known_rates: list[float] = []
        for i, (d, s) in enumerate(zip(pillar_dates, spreads)):
            periods = Schedule(
                effective_date=reference_date,
                termination_date=d,
                frequency=pay_frequency,
                day_count_convention=day_count_convention,
                business_day_convention=business_day_convention,
                calendar=calendar,
                stub_type=stub_type,
            ).generate()

            lo, hi = 1e-9, 100.0

            def objective(lam):
                partial = cls(
                    reference_date,
                    list(pillar_dates[: i + 1]),
                    list(known_rates) + [lam],
                    curve_day_count_convention,
                )
                return _par_spread_from_schedule(periods, discount_curve, partial, recovery_rate) - s

            f_lo = objective(lo)
            f_hi = objective(hi)
            if f_lo > 0 or f_hi < 0:
                raise ValueError(
                    f"bootstrap bracket failed for pillar {d}: f_lo={f_lo:.8f}, f_hi={f_hi:.8f}"
                )

            mid = lo
            for _ in range(100):
                mid = (lo + hi) / 2.0
                f_mid = objective(mid)
                if abs(f_mid) < 1e-10:
                    break
                if f_lo * f_mid < 0:
                    hi = mid
                else:
                    lo = mid
                    f_lo = f_mid

            known_rates.append(mid)

        curve = cls(reference_date, list(pillar_dates), known_rates, curve_day_count_convention)
        curve._bootstrap_meta = bootstrap_meta
        return curve
