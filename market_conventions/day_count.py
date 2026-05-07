"""Day count convention enum."""

from enum import Enum


class DayCountConvention(Enum):
    """Convention for computing the day count fraction between two dates.

    Attributes
    ----------
    ACT_360
        Actual days divided by 360. Common for money market instruments.
    ACT_365_FIXED
        Actual days divided by 365. Common for GBP and some other markets.
    THIRTY_360_BOND
        30/360 Bond Basis: each month is treated as 30 days, year as 360.
        Widely used for USD and EUR fixed-coupon bonds.
    ACT_ACT_ISDA
        Actual days divided by the actual number of days in each calendar
        year, split at year boundaries. ISDA standard for interest rate swaps.
    """

    ACT_360 = "ACT/360"
    ACT_365_FIXED = "ACT/365 Fixed"
    THIRTY_360_BOND = "30/360 Bond Basis"
    ACT_ACT_ISDA = "ACT/ACT ISDA"
