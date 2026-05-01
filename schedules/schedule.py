import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional

from .calendars import CalendarType, HolidayCalendar
from .conventions import BusinessDayConvention, DayCountConvention, StubType
from .day_count import day_count_fraction


@dataclass(frozen=True)
class Period:
    accrual_start: date
    accrual_end: date
    pay_date: date
    dcf: float


class Frequency(Enum):
    DAILY = 0
    MONTHLY = 1
    QUARTERLY = 3
    SEMI_ANNUAL = 6
    ANNUAL = 12


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _is_last_day_of_month(d: date) -> bool:
    return d.day == _days_in_month(d.year, d.month)


class Schedule:
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
    ) -> None:
        if effective_date >= termination_date:
            raise ValueError("effective_date must be before termination_date")
        self._effective = effective_date
        self._termination = termination_date
        self._frequency = frequency
        self._dcc = day_count_convention
        self._bdc = business_day_convention
        self._calendar = HolidayCalendar(calendar)
        self._eom = end_of_month
        self._stub_type = stub_type
        self._periods: Optional[List[Period]] = None

    def generate(self) -> List[Period]:
        if self._periods is None:
            unadj = self._generate_unadjusted_dates()
            self._periods = self._build_periods(unadj)
        return self._periods

    def __iter__(self):
        return iter(self.generate())

    def __len__(self):
        return len(self.generate())

    def _add_months(self, d: date, n: int) -> date:
        total_months = d.year * 12 + (d.month - 1) + n
        year = total_months // 12
        month = total_months % 12 + 1
        if self._eom and _is_last_day_of_month(d):
            day = _days_in_month(year, month)
        else:
            day = min(d.day, _days_in_month(year, month))
        return date(year, month, day)

    def _generate_unadjusted_dates(self) -> List[date]:
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
        periods = []
        for i in range(len(dates) - 1):
            start = dates[i]
            end = dates[i + 1]
            pay = self._calendar.adjust(end, self._bdc)
            dcf = day_count_fraction(start, end, self._dcc)
            periods.append(Period(
                accrual_start=start,
                accrual_end=end,
                pay_date=pay,
                dcf=dcf,
            ))
        return periods
