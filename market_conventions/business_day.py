from enum import Enum


class BusinessDayConvention(Enum):
    UNADJUSTED = "UNADJUSTED"
    FOLLOWING = "FOLLOWING"
    PRECEDING = "PRECEDING"
    MODIFIED_FOLLOWING = "MODIFIED_FOLLOWING"
