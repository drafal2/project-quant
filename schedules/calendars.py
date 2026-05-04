"""Holiday calendar and business day adjustment utilities."""

from datetime import date, timedelta
from enum import Enum

from market_conventions import BusinessDayConvention


class CalendarType(Enum):
    """Supported holiday calendar identifiers."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    PLN = "PLN"


class HolidayCalendar:
    """Holiday calendar with business day checking and date adjustment."""

    def __init__(self, calendar_type: CalendarType, label: str = 'BASE') -> None:
        """Initialise the calendar for the given calendar type and holiday label."""
        self._type = calendar_type
        self._label = label
        self._cache: dict[int, frozenset] = {}
        from database.holidays import HolidayRepository
        self._repo = HolidayRepository()

    def _holidays(self, year: int) -> frozenset:
        """Return holiday dates for a year, fetching from the DB and caching the result."""
        if year not in self._cache:
            self._cache[year] = self._repo.get_by_year(self._type.value, year, self._label)
        return self._cache[year]

    def is_holiday(self, d: date) -> bool:
        """Return True if the date is a holiday."""
        return d in self._holidays(d.year)

    def is_business_day(self, d: date) -> bool:
        """Return True if the date is a weekday and not a holiday."""
        return d.weekday() < 5 and not self.is_holiday(d)

    def add_holiday(self, d: date, description: str = "", persist: bool = False) -> None:
        """Add a holiday to the in-memory cache; optionally persist it to the database."""
        self._cache[d.year] = self._holidays(d.year) | {d}
        if persist:
            self._repo.add(self._type.value, d, description, self._label)

    def adjust(self, d: date, convention: BusinessDayConvention) -> date:
        """Adjust a date to a business day using the given convention."""
        if convention == BusinessDayConvention.UNADJUSTED:
            return d

        if convention == BusinessDayConvention.FOLLOWING:
            while not self.is_business_day(d):
                d += timedelta(days=1)
            return d

        if convention == BusinessDayConvention.PRECEDING:
            while not self.is_business_day(d):
                d -= timedelta(days=1)
            return d

        if convention == BusinessDayConvention.MODIFIED_FOLLOWING:
            original_month = d.month
            candidate = d
            while not self.is_business_day(candidate):
                candidate += timedelta(days=1)
            if candidate.month != original_month:
                candidate = d
                while not self.is_business_day(candidate):
                    candidate -= timedelta(days=1)
            return candidate

        raise ValueError(f"Unknown convention: {convention}")
