from enum import Enum


class Frequency(Enum):
    DAILY = 0
    MONTHLY = 1
    QUARTERLY = 3
    SEMI_ANNUAL = 6
    ANNUAL = 12


class DayCountConvention(Enum):
    ACT_360 = "ACT/360"
    ACT_365_FIXED = "ACT/365 Fixed"
    THIRTY_360_BOND = "30/360 Bond Basis"
    ACT_ACT_ISDA = "ACT/ACT ISDA"


class BusinessDayConvention(Enum):
    UNADJUSTED = "UNADJUSTED"
    FOLLOWING = "FOLLOWING"
    PRECEDING = "PRECEDING"
    MODIFIED_FOLLOWING = "MODIFIED_FOLLOWING"


class CalendarType(Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    PLN = "PLN"


class StubType(Enum):
    SHORT_FRONT = "SHORT_FRONT"
    LONG_FRONT = "LONG_FRONT"
    SHORT_BACK = "SHORT_BACK"
    LONG_BACK = "LONG_BACK"
