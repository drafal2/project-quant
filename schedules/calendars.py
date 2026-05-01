from datetime import date, timedelta

from .enums import BusinessDayConvention, CalendarType


class HolidayCalendar:
    def __init__(self, calendar_type: CalendarType, label: str = 'BASE') -> None:
        self._type = calendar_type
        self._label = label
        self._cache: dict[int, frozenset] = {}
        from database.holidays import HolidayRepository
        self._repo = HolidayRepository()

    def _holidays(self, year: int) -> frozenset:
        if year not in self._cache:
            self._cache[year] = self._repo.get_by_year(self._type.value, year, self._label)
        return self._cache[year]

    def is_holiday(self, d: date) -> bool:
        return d in self._holidays(d.year)

    def is_business_day(self, d: date) -> bool:
        
        return d.weekday() < 5 and not self.is_holiday(d)

    def adjust(self, d: date, convention: BusinessDayConvention) -> date:
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
