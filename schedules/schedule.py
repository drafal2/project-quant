"""Schedule class and Period dataclass for generating fixed income accrual schedules."""

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

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


def _days_in_month(
    year: int,
    month: int,
) -> int:
    """Return the number of days in the given month.

    Parameters
    ----------
    year
        Calendar year.
    month
        Calendar month (1–12).

    Returns
    -------
    int
        Number of days in the specified month.
    """
    return calendar.monthrange(year, month)[1]


def _is_last_day_of_month(
    d: date,
) -> bool:
    """Return True if the date falls on the last calendar day of its month.

    Parameters
    ----------
    d
        Date to check.

    Returns
    -------
    bool
        True if d is the last day of its month.
    """
    return d.day == _days_in_month(d.year, d.month)


class Schedule:  # TODO: you need to be able to generate a schedule from start_date, not just from effective and termination dates. for example, for cds bootstrapping you need to generate a schedule for each pillar from the quote's start_date and maturity_date. maybe you can add an alternate constructor that takes start_date and end_date instead of effective and termination dates?
    """Generates accrual schedules for fixed income instruments."""

    def __init__(
        self,
        effective_date: date,
        termination_date: date,
        frequency: Frequency,
        day_count_convention: DayCountConvention,
        business_day_convention: BusinessDayConvention,
        calendar: CalendarType | HolidayCalendar,
        end_of_month: bool = False,
        stub_type: StubType = StubType.SHORT_BACK,
        payment_lag: int = 0,
    ) -> None:
        """Initialise a schedule with effective/termination dates, frequency, and adjustment rules.

        Parameters
        ----------
        effective_date
            Schedule start date (first accrual period begins here).
        termination_date
            Schedule end date (last accrual period ends here); must be strictly
            after effective_date.
        frequency
            Payment frequency determining the length of regular periods.
        day_count_convention
            Day count convention used to compute accrual fractions.
        business_day_convention
            Business day convention applied to period end and pay dates.
        calendar
            Holiday calendar used for business day adjustments. Accepts either
            a ``CalendarType`` enum value or an existing ``HolidayCalendar``
            instance.
        end_of_month
            If True and the effective date falls on the last day of a month,
            each subsequent date is rolled to the last day of its month.
            Defaults to False.
        stub_type
            Placement of the irregular stub period when the tenor does not
            divide evenly. Defaults to ``StubType.SHORT_BACK``.
        payment_lag
            Number of business days after accrual end to the payment date.
            Defaults to ``0``.

        Raises
        ------
        ValueError
            If effective_date is on or after termination_date, or if
            payment_lag is negative.
        """
        if effective_date >= termination_date:
            raise ValueError("effective_date must be before termination_date")
        if payment_lag < 0:
            raise ValueError(f"payment_lag must be non-negative, got {payment_lag}.")
        self._effective = effective_date
        self._termination = termination_date
        self._frequency = frequency
        self._dcc = day_count_convention
        self._bdc = business_day_convention
        self._calendar = calendar if isinstance(calendar, HolidayCalendar) else HolidayCalendar(calendar)
        self._calendar_type = self._calendar._type
        self._eom = end_of_month
        self._stub_type = stub_type
        self._payment_lag = payment_lag
        self._periods: list[Period] | None = None

    def generate(self) -> list[Period]:
        """Build and return the list of accrual periods, computing on first call.

        Returns
        -------
        list[Period]
            Ordered list of accrual periods from effective to termination date.
        """
        if self._periods is None:
            unadj = self._generate_unadjusted_dates()
            self._periods = self._build_periods(unadj)
        return self._periods

    def __iter__(self) -> Iterator[Period]:
        """Iterate over the generated periods.

        Returns
        -------
        Iterator[Period]
            Iterator over the accrual periods in chronological order.
        """
        return iter(self.generate())

    def __len__(self) -> int:
        """Return the number of periods in the schedule.

        Returns
        -------
        int
            Total number of accrual periods.
        """
        return len(self.generate())

    def summary(self) -> str:
        """Return a formatted summary with a parameter header block and a per-period table.

        Returns
        -------
        str
            Multi-line string with schedule metadata followed by one row per
            accrual period.
        """
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

    def _add_months(
        self,
        d: date,
        n: int,
    ) -> date:
        """Add n months to a date, respecting the end-of-month convention.

        Parameters
        ----------
        d
            Base date.
        n
            Number of months to add; may be negative to subtract months.

        Returns
        -------
        date
            Resulting date after adding n months, clamped to the last day of
            the target month if necessary.
        """
        total_months = d.year * 12 + (d.month - 1) + n
        year = total_months // 12
        month = total_months % 12 + 1
        if self._eom and _is_last_day_of_month(d):
            day = _days_in_month(year, month)
        else:
            day = min(d.day, _days_in_month(year, month))
        return date(year, month, day)

    def _generate_unadjusted_dates(self) -> list[date]:
        """Generate raw schedule dates based on frequency and stub type, before BDC adjustment.

        Returns
        -------
        list[date]
            Unadjusted period boundary dates from effective to termination date.
        """
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
            has_back_stub = self._add_months(dates[-2], step) != dates[-1]
            if self._stub_type == StubType.LONG_BACK and len(dates) >= 3 and has_back_stub:
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
            has_front_stub = self._add_months(dates[0], step) != dates[1]
            if self._stub_type == StubType.LONG_FRONT and len(dates) >= 3 and has_front_stub:
                dates = [dates[0]] + dates[2:]

        return dates

    def _build_periods(
        self,
        dates: list[date],
    ) -> list[Period]:
        """Convert a list of dates into Period objects with adjusted pay dates and DCFs.

        Parameters
        ----------
        dates
            Ordered list of unadjusted period boundary dates; must contain at
            least two elements.

        Returns
        -------
        list[Period]
            One ``Period`` per consecutive pair of dates in the input list.
        """
        periods = []
        for i in range(len(dates) - 1):
            start = self._calendar.adjust(dates[i], self._bdc)
            end = self._calendar.adjust(dates[i + 1], self._bdc)
            pay = self._calendar.add_business_days(end, self._payment_lag) if self._payment_lag else end
            dcf = day_count_fraction(start, end, self._dcc)
            periods.append(Period(
                accrual_start=start,
                accrual_end=end,
                pay_date=pay,
                dcf=dcf,
            ))
        return periods
