from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Period:
    accrual_start: date
    accrual_end: date
    pay_date: date
    dcf: float
