from enum import Enum


class DayCountConvention(Enum):
    ACT_360 = "ACT/360"
    ACT_365_FIXED = "ACT/365 Fixed"
    THIRTY_360_BOND = "30/360 Bond Basis"
    ACT_ACT_ISDA = "ACT/ACT ISDA"
