"""Holiday date generators for USD, EUR, GBP, and PLN calendars."""

from datetime import date, timedelta


def _easter(year: int) -> date:
    """Compute Easter Sunday for a given year using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday (0=Mon) in the given month and year."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday (0=Mon) in the given month and year."""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _observed(d: date) -> date:
    """Return the observed date when a holiday falls on a weekend (Fri if Sat, Mon if Sun)."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _usd_holidays(year: int) -> dict:
    """Return US public holiday dates and names for the given year."""
    h = {}
    h[_observed(date(year, 1, 1))]          = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)]          = "MLK Day"
    h[_nth_weekday(year, 2, 0, 3)]          = "Presidents' Day"
    h[_last_weekday(year, 5, 0)]            = "Memorial Day"
    if year >= 2021:
        h[_observed(date(year, 6, 19))]     = "Juneteenth"
    h[_observed(date(year, 7, 4))]          = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)]          = "Labor Day"
    h[_nth_weekday(year, 10, 0, 2)]         = "Columbus Day"
    h[_observed(date(year, 11, 11))]        = "Veterans Day"
    h[_nth_weekday(year, 11, 3, 4)]         = "Thanksgiving"
    h[_observed(date(year, 12, 25))]        = "Christmas Day"
    return h


def _eur_holidays(year: int) -> dict:
    """Return ECB TARGET holiday dates and names for the given year."""
    easter = _easter(year)
    return {
        date(year, 1, 1):               "New Year's Day",
        easter - timedelta(days=2):     "Good Friday",
        easter + timedelta(days=1):     "Easter Monday",
        date(year, 5, 1):               "Labour Day",
        date(year, 12, 25):             "Christmas Day",
        date(year, 12, 26):             "Boxing Day",
    }


def _pln_holidays(year: int) -> dict:
    """Return Polish public holiday dates and names for the given year."""
    easter = _easter(year)
    h = {
        date(year, 1, 1):               "New Year's Day",
        easter:                         "Easter Sunday",
        easter + timedelta(days=1):     "Easter Monday",
        date(year, 5, 1):               "Labour Day",
        date(year, 5, 3):               "Constitution Day",
        easter + timedelta(days=49):    "Pentecost Sunday",
        easter + timedelta(days=60):    "Corpus Christi",
        date(year, 8, 15):              "Assumption of Mary",
        date(year, 11, 1):              "All Saints' Day",
        date(year, 11, 11):             "Independence Day",
        date(year, 12, 25):             "Christmas Day",
        date(year, 12, 26):             "Second Day of Christmas",
    }
    if year >= 2011:
        h[date(year, 1, 6)] = "Epiphany"
    if year >= 2025:
        h[date(year, 12, 24)] = "Christmas Eve"
    return h


def _gbp_holidays(year: int) -> dict:
    """Return UK public holiday dates and names for the given year."""
    easter = _easter(year)
    h = {}

    ny = date(year, 1, 1)
    if ny.weekday() == 5:
        h[date(year, 1, 3)] = "New Year's Day (substitute)"
    elif ny.weekday() == 6:
        h[date(year, 1, 2)] = "New Year's Day (substitute)"
    else:
        h[ny] = "New Year's Day"

    h[easter - timedelta(days=2)] = "Good Friday"
    h[easter + timedelta(days=1)] = "Easter Monday"
    h[_nth_weekday(year, 5, 0, 1)] = "Early May Bank Holiday"
    h[_last_weekday(year, 5, 0)]   = "Spring Bank Holiday"
    h[_last_weekday(year, 8, 0)]   = "Summer Bank Holiday"

    xmas = date(year, 12, 25)
    boxing = date(year, 12, 26)
    if xmas.weekday() == 5:
        h[date(year, 12, 27)] = "Christmas Day (substitute)"
        h[date(year, 12, 28)] = "Boxing Day (substitute)"
    elif xmas.weekday() == 6:
        h[date(year, 12, 26)] = "Boxing Day"
        h[date(year, 12, 27)] = "Christmas Day (substitute)"
    else:
        h[xmas] = "Christmas Day"
        if boxing.weekday() == 6:
            h[date(year, 12, 28)] = "Boxing Day (substitute)"
        else:
            h[boxing] = "Boxing Day"

    return h
