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

    def __init__(
        self,
        calendar_type: CalendarType,
        label: str = 'BASE',
    ) -> None:
        """Initialise the calendar for the given calendar type and holiday label.

        Parameters
        ----------
        calendar_type
            Identifies which country/currency holiday set to load from the
            database.
        label
            Holiday set label within the calendar type. Defaults to
            ``'BASE'``.
        """
        self._type = calendar_type
        self._label = label
        self._cache: dict[int, frozenset] = {}
        from database.holidays import HolidayRepository
        self._repo = HolidayRepository()

    def _holidays(
        self,
        year: int,
    ) -> frozenset:
        """Return holiday dates for a year, fetching from the DB and caching the result.

        Parameters
        ----------
        year
            Calendar year whose holidays are requested.

        Returns
        -------
        frozenset
            Set of holiday ``date`` objects for the given year.
        """
        if year not in self._cache:
            self._cache[year] = self._repo.get_by_year(self._type.value, year, self._label)
        return self._cache[year]

    def is_holiday(
        self,
        d: date,
    ) -> bool:
        """Return True if the date is a holiday.

        Parameters
        ----------
        d
            Date to check.

        Returns
        -------
        bool
            True if d is a holiday in this calendar, False otherwise.
        """
        return d in self._holidays(d.year)

    def is_business_day(
        self,
        d: date,
    ) -> bool:
        """Return True if the date is a weekday and not a holiday.

        Parameters
        ----------
        d
            Date to check.

        Returns
        -------
        bool
            True if d is a business day (Monday–Friday and not a holiday).
        """
        return d.weekday() < 5 and not self.is_holiday(d)

    def add_holiday(
        self,
        d: date,
        description: str = "",
        persist: bool = False,
    ) -> None:
        """Add a holiday to the in-memory cache; optionally persist it to the database.

        Parameters
        ----------
        d
            Date to mark as a holiday.
        description
            Human-readable description of the holiday. Defaults to ``""``.
        persist
            If True, writes the holiday to the database via ``HolidayRepository``.
            Defaults to False.
        """
        self._cache[d.year] = self._holidays(d.year) | {d}
        if persist:
            self._repo.add(self._type.value, d, description, self._label)

    def add_business_days(
        self,
        d: date,
        n: int,
    ) -> date:
        """Return the date that is n business days after d.

        Parameters
        ----------
        d
            Starting date.
        n
            Number of business days to advance; zero returns d unchanged.

        Returns
        -------
        date
            Date that is n business days after d.
        """
        remaining = n
        while remaining > 0:
            d += timedelta(days=1)
            if self.is_business_day(d):
                remaining -= 1
        return d

    def adjust(
        self,
        d: date,
        convention: BusinessDayConvention,
    ) -> date:
        """Adjust a date to a business day using the given convention.

        Parameters
        ----------
        d
            Date to adjust.
        convention
            Business day convention determining the adjustment direction.

        Returns
        -------
        date
            Business-day-adjusted date.

        Raises
        ------
        ValueError
            If convention is not a recognised ``BusinessDayConvention`` value.
        """
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
