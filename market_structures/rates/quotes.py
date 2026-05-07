"""Market quote types for zero-coupon curve bootstrapping."""

from abc import ABC, abstractmethod
from datetime import date
from enum import Enum

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from schedules.calendars import CalendarType, HolidayCalendar
from schedules.date_utils import add_spot_lag, add_tenor, imm_date
from schedules.day_count import day_count_fraction
from schedules.schedule import Frequency, Schedule

from .curve import ZeroCurve


def _resolve_calendar(
    calendar: CalendarType | HolidayCalendar,
) -> HolidayCalendar:
    """Return a HolidayCalendar, constructing one from a CalendarType if necessary.

    Parameters
    ----------
    calendar
        Either an existing ``HolidayCalendar`` instance or a ``CalendarType``
        enum value from which one will be constructed.

    Returns
    -------
    HolidayCalendar
        Ready-to-use holiday calendar.
    """
    return calendar if isinstance(calendar, HolidayCalendar) else HolidayCalendar(calendar)


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


class MarketQuote(ABC):
    """Abstract base for all instrument types used in curve bootstrapping."""

    @abstractmethod
    def maturity_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the instrument's maturity date; used to sort and place the pillar.

        Parameters
        ----------
        reference_date
            Curve anchor date used to resolve tenor-based maturities.

        Returns
        -------
        date
            Maturity date for this instrument.
        """

    @abstractmethod
    def start_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the accrual start date (spot date for deposits/swaps, IMM date for futures).

        Parameters
        ----------
        reference_date
            Curve anchor date used to compute the spot date.

        Returns
        -------
        date
            Accrual start date.
        """

    @abstractmethod
    def quote_value(self) -> float:
        """Return the raw market observable (rate for deposits/OIS/swaps, price for futures).

        Returns
        -------
        float
            Market observable in its native units (decimal rate or exchange price).
        """

    @abstractmethod
    def initial_guess(self) -> float:
        """Return the Newton-Raphson seed for the zero rate at this pillar.

        Returns
        -------
        float
            Initial zero rate guess in decimal form.
        """

    @abstractmethod
    def npv(
        self,
        reference_date: date,
        curve: ZeroCurve,
    ) -> float:
        """Return instrument NPV given a (partial) bootstrapped curve; 0.0 at par.

        Parameters
        ----------
        reference_date
            Curve anchor date.
        curve
            Partially bootstrapped zero curve covering at least this instrument's
            maturity.

        Returns
        -------
        float
            Net present value; zero when the curve exactly prices this instrument.
        """


class DepositQuote(MarketQuote):
    """Money-market deposit quote."""

    def __init__(
        self,
        rate: float,
        tenor: str,
        spot_lag: int,
        calendar: CalendarType | HolidayCalendar,
        business_day_convention: BusinessDayConvention,
        day_count_convention: DayCountConvention,
        maturity_date: date | None = None,
    ) -> None:
        """Initialise a deposit quote.

        Parameters
        ----------
        rate
            Deposit rate in decimal form.
        tenor
            Tenor string (e.g. ``"3M"``, ``"1Y"``).
        spot_lag
            Number of business days from reference_date to the deposit start date.
        calendar
            Holiday calendar used for date adjustments.
        business_day_convention
            Business day convention applied to the maturity date.
        day_count_convention
            Day count convention for accrual fraction computation.
        maturity_date
            If provided, used as the pillar date directly, bypassing
            tenor-based computation.
        """
        self.rate = rate
        self.tenor = tenor
        self.spot_lag = spot_lag
        self._cal = _resolve_calendar(calendar)
        self.bdc = business_day_convention
        self.dcc = day_count_convention
        self._maturity_override = maturity_date

    def _spot(
        self,
        reference_date: date,
    ) -> date:
        """Return the deposit start date (spot date).

        Parameters
        ----------
        reference_date
            Curve anchor date.

        Returns
        -------
        date
            Spot date, advanced by spot_lag business days from reference_date.
        """
        return add_spot_lag(reference_date, self.spot_lag, self._cal)

    def maturity_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the deposit maturity date.

        Returns the override date if one was supplied at construction; otherwise
        computes spot + tenor BDC-adjusted.

        Parameters
        ----------
        reference_date
            Curve anchor date used to compute the spot date.

        Returns
        -------
        date
            BDC-adjusted maturity date.
        """
        if self._maturity_override is not None:
            return self._maturity_override
        return add_tenor(self._spot(reference_date), self.tenor, self._cal, self.bdc)

    def start_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the deposit start date (spot date).

        Parameters
        ----------
        reference_date
            Curve anchor date.

        Returns
        -------
        date
            Spot date.
        """
        return self._spot(reference_date)

    def quote_value(self) -> float:
        """Return the deposit rate.

        Returns
        -------
        float
            Deposit rate in decimal form.
        """
        return self.rate

    def initial_guess(self) -> float:
        """Return the deposit rate as the NR seed.

        Returns
        -------
        float
            Initial zero rate guess equal to the deposit rate.
        """
        return self.rate

    def npv(
        self,
        reference_date: date,
        curve: ZeroCurve,
    ) -> float:
        """Return NPV: (1 + rate * dcf) * DF(mat) - DF(spot).

        Parameters
        ----------
        reference_date
            Curve anchor date.
        curve
            Partially bootstrapped zero curve.

        Returns
        -------
        float
            Net present value; zero when the curve prices the deposit at par.
        """
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
        calendar: CalendarType | HolidayCalendar,
        business_day_convention: BusinessDayConvention,
        day_count_convention: DayCountConvention,
        convexity_adjustment: float = 0.0,
        maturity_date: date | None = None,
    ) -> None:
        """Initialise a futures quote.

        Parameters
        ----------
        price
            Exchange price (e.g. ``94.5``); the implied rate is ``(100 - price) / 100``.
        imm_code
            IMM contract code identifying the start month (e.g. ``"H26"`` for
            March 2026).
        tenor
            Length of the contract period (e.g. ``"3M"``).
        calendar
            Holiday calendar used for date adjustments.
        business_day_convention
            Business day convention applied to the contract end date.
        day_count_convention
            Day count convention for accrual fraction computation.
        convexity_adjustment
            Rate adjustment (in decimal) applied to correct for the difference
            between futures and forward rates. Defaults to ``0.0``.
        maturity_date
            If provided, used as the pillar date directly, bypassing
            IMM start + tenor computation.
        """
        self.price = price
        self.imm_code = imm_code
        self.tenor = tenor
        self._cal = _resolve_calendar(calendar)
        self.bdc = business_day_convention
        self.dcc = day_count_convention
        self.convexity_adjustment = convexity_adjustment
        self._maturity_override = maturity_date

    def _start(self) -> date:
        """Return the IMM contract start date (3rd Wednesday of the contract month).

        Returns
        -------
        date
            IMM date derived from imm_code.
        """
        return imm_date(self.imm_code)

    def maturity_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the contract end date.

        Returns the override date if one was supplied at construction; otherwise
        computes IMM start + tenor BDC-adjusted.

        Parameters
        ----------
        reference_date
            Curve anchor date; not used in computation but required by the
            ``MarketQuote`` interface.

        Returns
        -------
        date
            BDC-adjusted contract end date.
        """
        if self._maturity_override is not None:
            return self._maturity_override
        return add_tenor(self._start(), self.tenor, self._cal, self.bdc)

    def start_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the IMM contract start date (3rd Wednesday of the contract month).

        Parameters
        ----------
        reference_date
            Curve anchor date; not used in computation but required by the
            ``MarketQuote`` interface.

        Returns
        -------
        date
            IMM start date.
        """
        return self._start()

    def quote_value(self) -> float:
        """Return the exchange price (e.g. 95.25).

        Returns
        -------
        float
            Futures exchange price.
        """
        return self.price

    def initial_guess(self) -> float:
        """Return the convexity-adjusted futures rate as the NR seed.

        Returns
        -------
        float
            Implied rate after convexity adjustment, in decimal form.
        """
        return (100.0 - self.price) / 100.0 - self.convexity_adjustment

    def npv(
        self,
        reference_date: date,
        curve: ZeroCurve,
    ) -> float:
        """Return NPV: (1 + adjusted_rate * dcf) * DF(end) - DF(start).

        Parameters
        ----------
        reference_date
            Curve anchor date.
        curve
            Partially bootstrapped zero curve.

        Returns
        -------
        float
            Net present value; zero when the curve prices the futures contract at par.
        """
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
        calendar: CalendarType | HolidayCalendar,
        business_day_convention: BusinessDayConvention,
        day_count_convention: DayCountConvention,
        stub_type: StubType = StubType.SHORT_BACK,
        payment_lag: int = 0,
        maturity_reference: MaturityReference = MaturityReference.ACCRUAL_END,
        maturity_date: date | None = None,
    ) -> None:
        """Initialise an OIS quote.

        Parameters
        ----------
        rate
            OIS fixed rate in decimal form.
        tenor
            Tenor string (e.g. ``"1Y"``, ``"2Y"``).
        spot_lag
            Number of business days from reference_date to the swap start date.
        frequency
            Payment frequency of the fixed leg.
        calendar
            Holiday calendar used for date adjustments.
        business_day_convention
            Business day convention applied to period end dates.
        day_count_convention
            Day count convention for accrual fraction computation.
        stub_type
            Stub placement when the tenor does not divide evenly into periods.
            Defaults to ``StubType.SHORT_BACK``.
        payment_lag
            Number of business days after accrual end to the payment date.
            Defaults to ``0``.
        maturity_reference
            Controls which date is used as the bootstrapping pillar:
            ``ACCRUAL_END`` (default) or ``PAYMENT_DATE``.
        maturity_date
            If provided, used as the pillar date directly, bypassing tenor
            computation and maturity_reference logic.
        """
        self.rate = rate
        self.tenor = tenor
        self.spot_lag = spot_lag
        self.frequency = frequency
        self._cal = _resolve_calendar(calendar)
        self.bdc = business_day_convention
        self.dcc = day_count_convention
        self.stub_type = stub_type
        self.payment_lag = payment_lag
        self.maturity_reference = maturity_reference
        self._maturity_override = maturity_date

    def _spot(
        self,
        reference_date: date,
    ) -> date:
        """Return the swap start date (spot date).

        Parameters
        ----------
        reference_date
            Curve anchor date.

        Returns
        -------
        date
            Spot date, advanced by spot_lag business days from reference_date.
        """
        return add_spot_lag(reference_date, self.spot_lag, self._cal)

    def maturity_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        Returns the override date if one was supplied at construction. Otherwise,
        with ``MaturityReference.ACCRUAL_END`` (default) this is spot + tenor
        BDC-adjusted; with ``MaturityReference.PAYMENT_DATE`` it is the accrual
        end advanced by ``payment_lag`` business days.

        Parameters
        ----------
        reference_date
            Curve anchor date used to compute the spot date.

        Returns
        -------
        date
            Bootstrapping pillar date.
        """
        if self._maturity_override is not None:
            return self._maturity_override
        accrual_end = add_tenor(self._spot(reference_date), self.tenor, self._cal, self.bdc)
        if self.maturity_reference is MaturityReference.PAYMENT_DATE:
            return self._cal.add_business_days(accrual_end, self.payment_lag)
        return accrual_end

    def start_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the OIS start date (spot date).

        Parameters
        ----------
        reference_date
            Curve anchor date.

        Returns
        -------
        date
            Spot date.
        """
        return self._spot(reference_date)

    def quote_value(self) -> float:
        """Return the OIS fixed rate.

        Returns
        -------
        float
            OIS fixed rate in decimal form.
        """
        return self.rate

    def initial_guess(self) -> float:
        """Return the OIS rate as the NR seed.

        Returns
        -------
        float
            Initial zero rate guess equal to the OIS fixed rate.
        """
        return self.rate

    def npv(
        self,
        reference_date: date,
        curve: ZeroCurve,
    ) -> float:
        """Return NPV: floating_pv - fixed_pv using continuous approximation for floating leg.

        Floating leg PV is approximated as DF(spot) - DF(maturity), which is exact in the
        continuous-rate limit. Both legs are discounted on the same curve (self-discounting).

        Parameters
        ----------
        reference_date
            Curve anchor date.
        curve
            Partially bootstrapped zero curve (used as both projection and discount curve).

        Returns
        -------
        float
            Net present value; zero when the curve prices the OIS at par.

        Notes
        -----
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
            calendar=self._cal,
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
        calendar: CalendarType | HolidayCalendar,
        business_day_convention: BusinessDayConvention,
        discount_curve: ZeroCurve,
        stub_type: StubType = StubType.SHORT_BACK,
        payment_lag: int = 0,
        maturity_reference: MaturityReference = MaturityReference.ACCRUAL_END,
        maturity_date: date | None = None,
    ) -> None:
        """Initialise a swap quote with an external discount curve for multi-curve pricing.

        Parameters
        ----------
        rate
            Swap fixed rate in decimal form.
        tenor
            Tenor string (e.g. ``"5Y"``, ``"10Y"``).
        spot_lag
            Number of business days from reference_date to the swap start date.
        fixed_frequency
            Payment frequency of the fixed leg.
        fixed_day_count
            Day count convention for the fixed leg accrual fraction.
        floating_frequency
            Payment frequency of the floating leg.
        floating_day_count
            Day count convention for the floating leg accrual fraction.
        calendar
            Holiday calendar used for date adjustments.
        business_day_convention
            Business day convention applied to period end dates.
        discount_curve
            External zero curve used to discount both legs (multi-curve setup).
        stub_type
            Stub placement when the tenor does not divide evenly into periods.
            Defaults to ``StubType.SHORT_BACK``.
        payment_lag
            Number of business days after accrual end to the payment date.
            Defaults to ``0``.
        maturity_reference
            Controls which date is used as the bootstrapping pillar:
            ``ACCRUAL_END`` (default) or ``PAYMENT_DATE``.
        maturity_date
            If provided, used as the pillar date directly, bypassing tenor
            computation and maturity_reference logic.
        """
        self.rate = rate
        self.tenor = tenor
        self.spot_lag = spot_lag
        self.fixed_frequency = fixed_frequency
        self.fixed_day_count = fixed_day_count
        self.floating_frequency = floating_frequency
        self.floating_day_count = floating_day_count
        self._cal = _resolve_calendar(calendar)
        self.bdc = business_day_convention
        self.discount_curve = discount_curve
        self.stub_type = stub_type
        self.payment_lag = payment_lag
        self.maturity_reference = maturity_reference
        self._maturity_override = maturity_date

    def _spot(
        self,
        reference_date: date,
    ) -> date:
        """Return the swap start date (spot date).

        Parameters
        ----------
        reference_date
            Curve anchor date.

        Returns
        -------
        date
            Spot date, advanced by spot_lag business days from reference_date.
        """
        return add_spot_lag(reference_date, self.spot_lag, self._cal)

    def maturity_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        Returns the override date if one was supplied at construction. Otherwise,
        with ``MaturityReference.ACCRUAL_END`` (default) this is spot + tenor
        BDC-adjusted; with ``MaturityReference.PAYMENT_DATE`` it is the accrual
        end advanced by ``payment_lag`` business days.

        Parameters
        ----------
        reference_date
            Curve anchor date used to compute the spot date.

        Returns
        -------
        date
            Bootstrapping pillar date.
        """
        if self._maturity_override is not None:
            return self._maturity_override
        accrual_end = add_tenor(self._spot(reference_date), self.tenor, self._cal, self.bdc)
        if self.maturity_reference is MaturityReference.PAYMENT_DATE:
            return self._cal.add_business_days(accrual_end, self.payment_lag)
        return accrual_end

    def start_date(
        self,
        reference_date: date,
    ) -> date:
        """Return the swap start date (spot date).

        Parameters
        ----------
        reference_date
            Curve anchor date.

        Returns
        -------
        date
            Spot date.
        """
        return self._spot(reference_date)

    def quote_value(self) -> float:
        """Return the swap fixed rate.

        Returns
        -------
        float
            Swap fixed rate in decimal form.
        """
        return self.rate

    def initial_guess(self) -> float:
        """Return the swap rate as the NR seed.

        Returns
        -------
        float
            Initial zero rate guess equal to the swap fixed rate.
        """
        return self.rate

    def npv(
        self,
        reference_date: date,
        curve: ZeroCurve,
    ) -> float:
        """Return NPV: floating_pv - fixed_pv under multi-curve pricing.

        curve is the projection curve (being bootstrapped); self.discount_curve is the
        external discount curve used for both leg present values.

        Parameters
        ----------
        reference_date
            Curve anchor date.
        curve
            Projection curve being bootstrapped; used to compute forward rates
            on the floating leg.

        Returns
        -------
        float
            Net present value; zero when the projection curve prices the swap at par.
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
            calendar=self._cal,
            stub_type=self.stub_type,
            payment_lag=self.payment_lag,
        ).generate()

        float_periods = Schedule(
            effective_date=spot,
            termination_date=mat,
            frequency=self.floating_frequency,
            day_count_convention=self.floating_day_count,
            business_day_convention=self.bdc,
            calendar=self._cal,
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
