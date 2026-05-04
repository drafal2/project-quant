"""Market quote types for zero-coupon curve bootstrapping."""

import calendar as _calendar
from abc import ABC, abstractmethod
from datetime import date, timedelta
from enum import Enum

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from schedules.calendars import CalendarType, HolidayCalendar
from schedules.day_count import day_count_fraction
from schedules.schedule import Frequency, Schedule

from .curve import ZeroCurve

IMM_MONTHS = {'H': 3, 'M': 6, 'U': 9, 'Z': 12}


class MaturityReference(Enum):
    """Determines which date is treated as the instrument maturity (bootstrapping pillar).

    ACCRUAL_END  — pillar is placed at the last accrual period end (standard).
    PAYMENT_DATE — pillar is placed at the last payment date (accrual end + payment_lag
                   business days); relevant when the payment lag is non-trivial.
    """

    ACCRUAL_END = "accrual_end"
    PAYMENT_DATE = "payment_date"
# TODO: implement pricing models for this types of instruments and use it in bootstrapping
# TODO: convexity adjustment calculated from FRAs also

def _parse_tenor(tenor: str) -> tuple[int, str]:
    """Parse a tenor string into (quantity, unit); unit is one of 'D', 'W', 'M', 'Y'."""
    tenor = tenor.strip().upper()
    unit = tenor[-1]
    if unit not in ('D', 'W', 'M', 'Y'):
        raise ValueError(f"Unrecognised tenor unit '{unit}' in '{tenor}'. Use D, W, M, or Y.")
    try:
        quantity = int(tenor[:-1])
    except ValueError:
        raise ValueError(f"Cannot parse quantity from tenor '{tenor}'.")
    if quantity <= 0:
        raise ValueError(f"Tenor quantity must be positive, got {quantity}.")
    return quantity, unit


def _add_spot_lag(reference_date: date, spot_lag: int, cal: HolidayCalendar) -> date:
    """Advance reference_date by spot_lag business days."""
    d = reference_date
    remaining = spot_lag
    while remaining > 0:
        d += timedelta(days=1)
        if cal.is_business_day(d):
            remaining -= 1
    return d


def _add_tenor(start: date, tenor: str, cal: HolidayCalendar, bdc: BusinessDayConvention) -> date:
    """Add a tenor string to a date and adjust to a business day."""
    quantity, unit = _parse_tenor(tenor)
    if unit == 'D':
        raw = start + timedelta(days=quantity)
    elif unit == 'W':
        raw = start + timedelta(weeks=quantity)
    else:
        months = quantity if unit == 'M' else quantity * 12
        total_months = start.year * 12 + (start.month - 1) + months
        year = total_months // 12
        month = total_months % 12 + 1
        day = min(start.day, _calendar.monthrange(year, month)[1])
        raw = date(year, month, day)
    return cal.adjust(raw, bdc)


def _imm_date(imm_code: str) -> date:
    """Return the 3rd Wednesday (unadjusted) of the IMM contract month.

    IMM code format: letter (H/M/U/Z) + two-digit year (e.g. 'H26' = March 2026).
    """
    imm_code = imm_code.strip().upper()
    letter = imm_code[0]
    if letter not in IMM_MONTHS:
        raise ValueError(f"Invalid IMM month letter '{letter}'. Expected one of H, M, U, Z.")
    month = IMM_MONTHS[letter]
    year = 2000 + int(imm_code[1:])
    first = date(year, month, 1)
    # weekday(): Monday=0, Wednesday=2
    days_to_first_wed = (2 - first.weekday()) % 7
    return first + timedelta(days=days_to_first_wed + 14)


class MarketQuote(ABC):
    """Abstract base for all instrument types used in curve bootstrapping."""

    @abstractmethod
    def maturity_date(self, reference_date: date) -> date:
        """Return the instrument's maturity date; used to sort and place the pillar."""

    @abstractmethod
    def start_date(self, reference_date: date) -> date:
        """Return the accrual start date (spot date for deposits/swaps, IMM date for futures)."""

    @abstractmethod
    def quote_value(self) -> float:
        """Return the raw market observable (rate for deposits/OIS/swaps, price for futures)."""

    @abstractmethod
    def initial_guess(self) -> float:
        """Return the Newton-Raphson seed for the zero rate at this pillar."""

    @abstractmethod
    def npv(self, reference_date: date, curve: ZeroCurve) -> float:
        """Return instrument NPV given a (partial) bootstrapped curve; 0.0 at par."""


class DepositQuote(MarketQuote):
    """Money-market deposit quote."""

    def __init__(
        self,
        rate: float,
        tenor: str,
        spot_lag: int,
        calendar: CalendarType,
        business_day_convention: BusinessDayConvention,
        day_count_convention: DayCountConvention,
    ) -> None:
        """Initialise a deposit quote."""
        self.rate = rate
        self.tenor = tenor
        self.spot_lag = spot_lag
        self.calendar = calendar
        self.bdc = business_day_convention
        self.dcc = day_count_convention

    def _spot(self, reference_date: date) -> date:
        cal = HolidayCalendar(self.calendar)
        return _add_spot_lag(reference_date, self.spot_lag, cal)

    def maturity_date(self, reference_date: date) -> date:
        """Return the deposit maturity date (spot + tenor, BDC-adjusted)."""
        cal = HolidayCalendar(self.calendar)
        return _add_tenor(self._spot(reference_date), self.tenor, cal, self.bdc)

    def start_date(self, reference_date: date) -> date:
        """Return the deposit start date (spot date)."""
        return self._spot(reference_date)

    def quote_value(self) -> float:
        """Return the deposit rate."""
        return self.rate

    def initial_guess(self) -> float:
        """Return the deposit rate as the NR seed."""
        return self.rate

    def npv(self, reference_date: date, curve: ZeroCurve) -> float:
        """Return NPV: (1 + rate * dcf) * DF(mat) - DF(spot)."""
        spot = self._spot(reference_date)
        mat = self.maturity_date(reference_date)
        dcf = day_count_fraction(spot, mat, self.dcc)
        return (1.0 + self.rate * dcf) * curve.discount_factor(mat) - curve.discount_factor(spot)


class FuturesQuote(MarketQuote):
    """IMM-dated interest rate futures quote."""

    def __init__(
        self,
        price: float,
        imm_code: str,
        tenor: str,
        calendar: CalendarType,
        business_day_convention: BusinessDayConvention,
        day_count_convention: DayCountConvention,
        convexity_adjustment: float = 0.0,
    ) -> None:
        """Initialise a futures quote; price is the exchange price (e.g. 94.5)."""
        self.price = price
        self.imm_code = imm_code
        self.tenor = tenor
        self.calendar = calendar
        self.bdc = business_day_convention
        self.dcc = day_count_convention
        self.convexity_adjustment = convexity_adjustment

    def _start(self) -> date:
        return _imm_date(self.imm_code)

    def maturity_date(self, reference_date: date) -> date:
        """Return the contract end date (IMM start + tenor, BDC-adjusted)."""
        cal = HolidayCalendar(self.calendar)
        return _add_tenor(self._start(), self.tenor, cal, self.bdc)

    def start_date(self, reference_date: date) -> date:
        """Return the IMM contract start date (3rd Wednesday of the contract month)."""
        return self._start()

    def quote_value(self) -> float:
        """Return the exchange price (e.g. 95.25)."""
        return self.price

    def initial_guess(self) -> float:
        """Return the convexity-adjusted futures rate as the NR seed."""
        return (100.0 - self.price) / 100.0 - self.convexity_adjustment

    def npv(self, reference_date: date, curve: ZeroCurve) -> float:
        """Return NPV: (1 + adjusted_rate * dcf) * DF(end) - DF(start)."""
        adjusted_rate = self.initial_guess()
        start = self._start()
        end = self.maturity_date(reference_date)
        dcf = day_count_fraction(start, end, self.dcc)
        return (1.0 + adjusted_rate * dcf) * curve.discount_factor(end) - curve.discount_factor(start)


class OISQuote(MarketQuote):
    """Overnight Index Swap quote (self-discounting; continuous approximation for floating leg)."""

    def __init__(
        self,
        rate: float,
        tenor: str,
        spot_lag: int,
        frequency: Frequency,
        calendar: CalendarType,
        business_day_convention: BusinessDayConvention,
        day_count_convention: DayCountConvention,
        stub_type: StubType = StubType.SHORT_BACK,
        payment_lag: int = 0,
        maturity_reference: MaturityReference = MaturityReference.ACCRUAL_END,
    ) -> None:
        """Initialise an OIS quote."""
        self.rate = rate
        self.tenor = tenor
        self.spot_lag = spot_lag
        self.frequency = frequency
        self.calendar = calendar
        self.bdc = business_day_convention
        self.dcc = day_count_convention
        self.stub_type = stub_type
        self.payment_lag = payment_lag
        self.maturity_reference = maturity_reference

    def _spot(self, reference_date: date) -> date:
        cal = HolidayCalendar(self.calendar)
        return _add_spot_lag(reference_date, self.spot_lag, cal)

    def maturity_date(self, reference_date: date) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        With MaturityReference.ACCRUAL_END (default) this is spot + tenor BDC-adjusted.
        With MaturityReference.PAYMENT_DATE it is the accrual end advanced by payment_lag
        business days — placing the pillar at the last actual cash flow date.
        """
        cal = HolidayCalendar(self.calendar)
        accrual_end = _add_tenor(self._spot(reference_date), self.tenor, cal, self.bdc)
        if self.maturity_reference is MaturityReference.PAYMENT_DATE:
            return cal.add_business_days(accrual_end, self.payment_lag)
        return accrual_end

    def start_date(self, reference_date: date) -> date:
        """Return the OIS start date (spot date)."""
        return self._spot(reference_date)

    def quote_value(self) -> float:
        """Return the OIS fixed rate."""
        return self.rate

    def initial_guess(self) -> float:
        """Return the OIS rate as the NR seed."""
        return self.rate

    def npv(self, reference_date: date, curve: ZeroCurve) -> float:
        """Return NPV: floating_pv - fixed_pv using continuous approximation for floating leg.

        Floating leg PV is approximated as DF(spot) - DF(maturity), which is exact in the
        continuous-rate limit. Both legs are discounted on the same curve (self-discounting).
        # TODO: implement exact daily compounding for the floating leg
        """
        spot = self._spot(reference_date)
        mat = self.maturity_date(reference_date)
        periods = Schedule(
            effective_date=spot,
            termination_date=mat,
            frequency=self.frequency,
            day_count_convention=self.dcc,
            business_day_convention=self.bdc,
            calendar=self.calendar,
            stub_type=self.stub_type,
            payment_lag=self.payment_lag,
        ).generate()
        floating_pv = curve.discount_factor(spot) - curve.discount_factor(mat)
        fixed_pv = sum(self.rate * p.dcf * curve.discount_factor(p.pay_date) for p in periods)
        return floating_pv - fixed_pv


class SwapQuote(MarketQuote):
    """Vanilla interest rate swap quote (multi-curve: separate projection and discount curves)."""

    def __init__(
        self,
        rate: float,
        tenor: str,
        spot_lag: int,
        fixed_frequency: Frequency,
        fixed_day_count: DayCountConvention,
        floating_frequency: Frequency,
        floating_day_count: DayCountConvention,
        calendar: CalendarType,
        business_day_convention: BusinessDayConvention,
        discount_curve: ZeroCurve,
        stub_type: StubType = StubType.SHORT_BACK,
        payment_lag: int = 0,
        maturity_reference: MaturityReference = MaturityReference.ACCRUAL_END,
    ) -> None:
        """Initialise a swap quote with an external discount curve for multi-curve pricing."""
        self.rate = rate
        self.tenor = tenor
        self.spot_lag = spot_lag
        self.fixed_frequency = fixed_frequency
        self.fixed_day_count = fixed_day_count
        self.floating_frequency = floating_frequency
        self.floating_day_count = floating_day_count
        self.calendar = calendar
        self.bdc = business_day_convention
        self.discount_curve = discount_curve
        self.stub_type = stub_type
        self.payment_lag = payment_lag
        self.maturity_reference = maturity_reference

    def _spot(self, reference_date: date) -> date:
        cal = HolidayCalendar(self.calendar)
        return _add_spot_lag(reference_date, self.spot_lag, cal)

    def maturity_date(self, reference_date: date) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        With MaturityReference.ACCRUAL_END (default) this is spot + tenor BDC-adjusted.
        With MaturityReference.PAYMENT_DATE it is the accrual end advanced by payment_lag
        business days — placing the pillar at the last actual cash flow date.
        """
        cal = HolidayCalendar(self.calendar)
        accrual_end = _add_tenor(self._spot(reference_date), self.tenor, cal, self.bdc)
        if self.maturity_reference is MaturityReference.PAYMENT_DATE:
            return cal.add_business_days(accrual_end, self.payment_lag)
        return accrual_end

    def start_date(self, reference_date: date) -> date:
        """Return the swap start date (spot date)."""
        return self._spot(reference_date)

    def quote_value(self) -> float:
        """Return the swap fixed rate."""
        return self.rate

    def initial_guess(self) -> float:
        """Return the swap rate as the NR seed."""
        return self.rate

    def npv(self, reference_date: date, curve: ZeroCurve) -> float:
        """Return NPV: floating_pv - fixed_pv under multi-curve pricing.

        curve is the projection curve (being bootstrapped); self.discount_curve is the
        external discount curve used for both leg present values.
        """
        spot = self._spot(reference_date)
        mat = self.maturity_date(reference_date)
        D = self.discount_curve
        P = curve

        fixed_periods = Schedule(
            effective_date=spot,
            termination_date=mat,
            frequency=self.fixed_frequency,
            day_count_convention=self.fixed_day_count,
            business_day_convention=self.bdc,
            calendar=self.calendar,
            stub_type=self.stub_type,
            payment_lag=self.payment_lag,
        ).generate()

        float_periods = Schedule(
            effective_date=spot,
            termination_date=mat,
            frequency=self.floating_frequency,
            day_count_convention=self.floating_day_count,
            business_day_convention=self.bdc,
            calendar=self.calendar,
            stub_type=self.stub_type,
            payment_lag=self.payment_lag,
        ).generate()

        floating_pv = sum(
            (P.discount_factor(p.accrual_start) / P.discount_factor(p.accrual_end) - 1.0)
            * D.discount_factor(p.pay_date)
            for p in float_periods
        )
        fixed_pv = sum(self.rate * p.dcf * D.discount_factor(p.pay_date) for p in fixed_periods)
        return floating_pv - fixed_pv
