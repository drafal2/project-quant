"""Day count fraction calculations for ACT/360, ACT/365, 30/360, and ACT/ACT ISDA."""

from datetime import date

from market_conventions import DayCountConvention


def _is_leap(year: int) -> bool:
    """Return True if the year is a leap year."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def day_count_fraction(
    start: date,
    end: date,
    convention: DayCountConvention,
) -> float:
    """Compute the day count fraction between two dates under the given convention."""
    if convention == DayCountConvention.ACT_360:
        return (end - start).days / 360

    if convention == DayCountConvention.ACT_365_FIXED:
        return (end - start).days / 365

    if convention == DayCountConvention.THIRTY_360_BOND:
        d1 = min(start.day, 30)
        d2 = 30 if end.day == 31 and d1 >= 30 else end.day
        days_360 = (
            360 * (end.year - start.year)
            + 30 * (end.month - start.month)
            + (d2 - d1)
        )
        return days_360 / 360

    if convention == DayCountConvention.ACT_ACT_ISDA:
        if start == end:
            return 0.0
        dcf = 0.0
        for y in range(start.year, end.year + 1):
            year_start = date(y, 1, 1)
            year_end = date(y + 1, 1, 1)
            overlap_start = max(start, year_start)
            overlap_end = min(end, year_end)
            if overlap_end > overlap_start:
                days_in_year = 366 if _is_leap(y) else 365
                dcf += (overlap_end - overlap_start).days / days_in_year
        return dcf

    raise ValueError(f"Unknown convention: {convention}")
