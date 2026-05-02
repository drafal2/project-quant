"""Compounding type and frequency enums."""

from enum import Enum


class CompoundingType(Enum):
    """Method used to compound interest over time."""

    CONTINUOUS = "CONTINUOUS"
    SIMPLE = "SIMPLE"
    COMPOUNDED = "COMPOUNDED"


class CompoundingFrequency(Enum):
    """Number of compounding periods per year."""

    ANNUAL = 1
    SEMI_ANNUAL = 2
    QUARTERLY = 4
    MONTHLY = 12
