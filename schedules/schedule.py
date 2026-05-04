"""Schedule class and Period dataclass for generating fixed income accrual schedules."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional

from .calendars import CalendarType, HolidayCalendar
from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from .day_count import day_count_fraction


@dataclass(frozen=True)
class Period:
    """Immutable record of a single accrual period."""

    accrual_start: date
    accrual_end: date
    pay_date: date
    dcf: float


class Frequency(Enum):
    """Payment frequency expressed as months per period (0 = daily)."""

    DAILY = 0
    MONTHLY = 1
    QUARTERLY = 3
    SEMI_ANNUAL = 6
    ANNUAL = 12


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given month."""
    return calendar.monthrange(year, month)[1]


def _is_last_day_of_month(d: date) -> bool:
    """Return True if the date falls on the last calendar day of its month."""
    return d.day == _days_in_month(d.year, d.month)


class Schedule:
    """Generates accrual schedules for fixed income instruments."""

    def __init__(
        self,
        effective_date: date,
        termination_date: date,
        frequency: Frequency,
        day_count_convention: DayCountConvention,
        business_day_convention: BusinessDayConvention,
        calendar: CalendarType,
        end_of_month: bool = False,
        stub_type: StubType = StubType.SHORT_BACK,
        payment_lag: int = 0,
    ) -> None:
        """Initialise a schedule with effective/termination dates, frequency, and adjustment rules."""
        if effective_date >= termination_date:
            raise ValueError("effective_date must be before termination_date")
        if payment_lag < 0:
            raise ValueError(f"payment_lag must be non-negative, got {payment_lag}.")
        self._effective = effective_date
        self._termination = termination_date
        self._frequency = frequency
        self._dcc = day_count_convention
        self._bdc = business_day_convention
        self._calendar_type = calendar
        self._calendar = HolidayCalendar(calendar)
        self._eom = end_of_month
        self._stub_type = stub_type
        self._payment_lag = payment_lag
        self._periods: Optional[List[Period]] = None

    def generate(self) -> List[Period]:
        """Build and return the list of accrual periods, computing on first call."""
        if self._periods is None:
            unadj = self._generate_unadjusted_dates()
            self._periods = self._build_periods(unadj)
        return self._periods

    def __iter__(self):
        """Iterate over the generated periods."""
        return iter(self.generate())

    def __len__(self):
        """Return the number of periods in the schedule."""
        return len(self.generate())

    def summary(self) -> str:
        """Return a formatted summary with a parameter header block and a per-period table."""
        periods = self.generate()
        header = (
            f"{'#':>3}  {'Accrual Start':>13}  {'Accrual End':>11}"
            f"  {'Pay Date':>10}  {'Days':>4}  {'DCF':>8}"
        )
        width = len(header)
        label_w = 18
        lines = [
            "Schedule Summary",
            "=" * width,
            f"{'Effective Date':<{label_w}}: {self._effective}",
            f"{'Termination Date':<{label_w}}: {self._termination}",
            f"{'Frequency':<{label_w}}: {self._frequency.name}",
            f"{'Day Count':<{label_w}}: {self._dcc.name}",
            f"{'Business Day Conv':<{label_w}}: {self._bdc.name}",
            f"{'Calendar':<{label_w}}: {self._calendar_type.value}",
            f"{'Payment Lag':<{label_w}}: {self._payment_lag}",
            "",
            header,
            "-" * width,
        ]
        for i, p in enumerate(periods, 1):
            days = (p.accrual_end - p.accrual_start).days
            lines.append(
                f"{i:>3}  {str(p.accrual_start):>13}  {str(p.accrual_end):>11}"
                f"  {str(p.pay_date):>10}  {days:>4}  {p.dcf:>8.4f}"
            )
        return "\n".join(lines)

    def _add_months(self, d: date, n: int) -> date:
        """Add n months to a date, respecting the end-of-month convention."""
        total_months = d.year * 12 + (d.month - 1) + n
        year = total_months // 12
        month = total_months % 12 + 1
        if self._eom and _is_last_day_of_month(d):
            day = _days_in_month(year, month)
        else:
            day = min(d.day, _days_in_month(year, month))
        return date(year, month, day)

    def _generate_unadjusted_dates(self) -> List[date]:
        """Generate raw schedule dates based on frequency and stub type, before business day adjustment."""
        if self._frequency == Frequency.DAILY:
            dates = [self._effective]
            d = self._effective
            while True:
                next_d = d + timedelta(days=1)
                while not self._calendar.is_business_day(next_d):
                    next_d += timedelta(days=1)
                if next_d >= self._termination:
                    break
                dates.append(next_d)
                d = next_d
            dates.append(self._termination)
            return dates

        step = self._frequency.value

        if self._stub_type in (StubType.SHORT_BACK, StubType.LONG_BACK):
            dates = [self._effective]
            d = self._effective
            while True:
                d = self._add_months(d, step)
                if d >= self._termination:
                    break
                dates.append(d)
            dates.append(self._termination)
            if self._stub_type == StubType.LONG_BACK and len(dates) >= 3:
                dates = dates[:-2] + [dates[-1]]

        else:
            dates_rev = [self._termination]
            d = self._termination
            while True:
                d = self._add_months(d, -step)
                if d <= self._effective:
                    break
                dates_rev.append(d)
            dates_rev.append(self._effective)
            dates = list(reversed(dates_rev))
            if self._stub_type == StubType.LONG_FRONT and len(dates) >= 3:
                dates = [dates[0]] + dates[2:]

        return dates

    def _build_periods(self, dates: List[date]) -> List[Period]:
        """Convert a list of dates into Period objects with adjusted pay dates and DCFs."""
        periods = []
        for i in range(len(dates) - 1):
            start = dates[i]
            end = dates[i + 1]
            pay = self._calendar.adjust(end, self._bdc)
            if self._payment_lag:
                pay = self._calendar.add_business_days(pay, self._payment_lag)
            dcf = day_count_fraction(start, end, self._dcc)
            periods.append(Period(
                accrual_start=start,
                accrual_end=end,
                pay_date=pay,
                dcf=dcf,
            ))
        return periods
