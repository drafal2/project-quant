"""Stub type enum."""

from enum import Enum


class StubType(Enum):
    """Position and length of the irregular stub period in a schedule."""

    SHORT_FRONT = "SHORT_FRONT"
    LONG_FRONT = "LONG_FRONT"
    SHORT_BACK = "SHORT_BACK"
    LONG_BACK = "LONG_BACK"
