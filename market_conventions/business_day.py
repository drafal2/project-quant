"""Business day convention enum."""

from enum import Enum


class BusinessDayConvention(Enum):
    """Convention for adjusting dates that fall on non-business days."""

    UNADJUSTED = "UNADJUSTED"
    FOLLOWING = "FOLLOWING"
    PRECEDING = "PRECEDING"
    MODIFIED_FOLLOWING = "MODIFIED_FOLLOWING"
