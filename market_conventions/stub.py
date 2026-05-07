"""Stub type enum."""

from enum import Enum


class StubType(Enum):
    """Position and length of the irregular stub period in a schedule.

    Attributes
    ----------
    SHORT_FRONT
        Short stub at the start of the schedule; the first period is shorter
        than a regular period.
    LONG_FRONT
        Long stub at the start of the schedule; the first period is longer
        than a regular period, absorbing the remainder that cannot form a
        full period given the effective and termination dates.
    SHORT_BACK
        Short stub at the end of the schedule; the last period is shorter
        than a regular period.
    LONG_BACK
        Long stub at the end of the schedule; the last period is longer
        than a regular period, absorbing the remainder that cannot form a
        full period given the effective and termination dates.
    """

    SHORT_FRONT = "SHORT_FRONT"
    LONG_FRONT = "LONG_FRONT"
    SHORT_BACK = "SHORT_BACK"
    LONG_BACK = "LONG_BACK"
