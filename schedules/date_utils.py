"""Calendar-based date arithmetic utilities shared across quote types."""

import calendar as _calendar
from datetime import date, timedelta

from market_conventions import BusinessDayConvention
from schedules.calendars import HolidayCalendar

_IMM_MONTHS = {'H': 3, 'M': 6, 'U': 9, 'Z': 12}


def parse_tenor(
    tenor: str,
) -> tuple[int, str]:
    """Parse a tenor string into (quantity, unit).

    Parameters
    ----------
    tenor
        Tenor string such as ``"3M"``, ``"1Y"``, ``"2W"``, ``"5D"``.
        Case-insensitive; leading/trailing whitespace is stripped.

    Returns
    -------
    tuple[int, str]
        ``(quantity, unit)`` where unit is one of ``'D'``, ``'W'``, ``'M'``,
        ``'Y'``.

    Raises
    ------
    ValueError
        If the unit is not recognised, the quantity is not a positive integer,
        or the string cannot be parsed.
    """
    tenor = tenor.strip().upper()
    unit = tenor[-1]
    if unit not in ('D', 'W', 'M', 'Y'):
        raise ValueError(f"Unrecognised tenor unit '{unit}' in '{tenor}'. Use D, W, M, or Y.")
    try:
        quantity = int(tenor[:-1])
    except ValueError:
        raise ValueError(f"Cannot parse quantity from tenor '{tenor}'.")
    if quantity <= 0:
        raise ValueError(f"Tenor quantity must be positive, got {quantity}.")
    return quantity, unit


def add_spot_lag(
    reference_date: date,
    spot_lag: int,
    cal: HolidayCalendar,
) -> date:
    """Advance reference_date by spot_lag business days.

    Parameters
    ----------
    reference_date
        Starting date from which business days are counted.
    spot_lag
        Number of business days to advance; zero returns reference_date unchanged.
    cal
        Holiday calendar used to identify non-business days.

    Returns
    -------
    date
        Date that is spot_lag business days after reference_date.
    """
    d = reference_date
    remaining = spot_lag
    while remaining > 0:
        d += timedelta(days=1)
        if cal.is_business_day(d):
            remaining -= 1
    return d


def add_tenor(
    start: date,
    tenor: str,
    cal: HolidayCalendar,
    bdc: BusinessDayConvention,
) -> date:
    """Add a tenor string to a date and adjust to a business day.

    Parameters
    ----------
    start
        Base date to which the tenor is added.
    tenor
        Tenor string such as ``"3M"``, ``"1Y"``; parsed by ``parse_tenor``.
    cal
        Holiday calendar used for business day adjustment.
    bdc
        Business day convention applied to the resulting date.

    Returns
    -------
    date
        BDC-adjusted date after adding the tenor to start.
    """
    quantity, unit = parse_tenor(tenor)

    if unit == 'D':
        raw = start + timedelta(days=quantity)
    elif unit == 'W':
        raw = start + timedelta(weeks=quantity)
    else:
        months = quantity if unit == 'M' else quantity * 12
        total_months = start.year * 12 + (start.month - 1) + months
        year = total_months // 12
        month = total_months % 12 + 1
        day = min(start.day, _calendar.monthrange(year, month)[1])
        raw = date(year, month, day)

    return cal.adjust(raw, bdc)


def imm_date(
    imm_code: str,
) -> date:
    """Return the 3rd Wednesday (unadjusted) of the IMM contract month.

    Parameters
    ----------
    imm_code
        IMM contract code in the format ``<letter><2-digit-year>``, where the
        letter is one of ``H`` (March), ``M`` (June), ``U`` (September),
        ``Z`` (December). For example, ``"H26"`` resolves to March 2026.

    Returns
    -------
    date
        Unadjusted 3rd Wednesday of the contract month.

    Raises
    ------
    ValueError
        If the month letter is not one of ``H``, ``M``, ``U``, ``Z``.
    """
    imm_code = imm_code.strip().upper()
    letter = imm_code[0]
    if letter not in _IMM_MONTHS:
        raise ValueError(f"Invalid IMM month letter '{letter}'. Expected one of H, M, U, Z.")
    month = _IMM_MONTHS[letter]
    year = 2000 + int(imm_code[1:])
    first = date(year, month, 1)
    days_to_first_wed = (2 - first.weekday()) % 7
    return first + timedelta(days=days_to_first_wed + 14)
