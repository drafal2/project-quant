from enum import Enum


class CompoundingType(Enum):
    CONTINUOUS = "CONTINUOUS"
    SIMPLE = "SIMPLE"
    COMPOUNDED = "COMPOUNDED"


class CompoundingFrequency(Enum):
    ANNUAL = 1
    SEMI_ANNUAL = 2
    QUARTERLY = 4
    MONTHLY = 12
