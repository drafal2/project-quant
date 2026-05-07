"""Compounding type and frequency enums."""

from enum import Enum


class CompoundingType(Enum):
    """Method used to compound interest over time.

    Attributes
    ----------
    CONTINUOUS
        Continuous compounding: discount factor is ``exp(-r * t)``.
    SIMPLE
        Simple (linear) compounding: discount factor is ``1 / (1 + r * t)``.
    COMPOUNDED
        Periodic compounding at a fixed frequency: discount factor is
        ``(1 + r / n) ** (-n * t)``. Requires a ``CompoundingFrequency``.
    """

    CONTINUOUS = "CONTINUOUS"
    SIMPLE = "SIMPLE"
    COMPOUNDED = "COMPOUNDED"


class CompoundingFrequency(Enum):
    """Number of compounding periods per year; used with ``CompoundingType.COMPOUNDED``.

    Attributes
    ----------
    ANNUAL
        One compounding period per year (n = 1).
    SEMI_ANNUAL
        Two compounding periods per year (n = 2).
    QUARTERLY
        Four compounding periods per year (n = 4).
    MONTHLY
        Twelve compounding periods per year (n = 12).
    """

    ANNUAL = 1
    SEMI_ANNUAL = 2
    QUARTERLY = 4
    MONTHLY = 12
