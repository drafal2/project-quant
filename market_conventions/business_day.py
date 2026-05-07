"""Business day convention enum."""

from enum import Enum


class BusinessDayConvention(Enum):
    """Convention for adjusting dates that fall on non-business days.

    Attributes
    ----------
    UNADJUSTED
        Date is used as-is with no adjustment.
    FOLLOWING
        Roll to the next business day.
    PRECEDING
        Roll to the previous business day.
    MODIFIED_FOLLOWING
        Roll to the next business day unless it crosses a month boundary,
        in which case roll to the previous business day instead.
    """

    UNADJUSTED = "UNADJUSTED"
    FOLLOWING = "FOLLOWING"
    PRECEDING = "PRECEDING"
    MODIFIED_FOLLOWING = "MODIFIED_FOLLOWING"
