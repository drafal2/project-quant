"""Market quote type for CDS spread bootstrapping."""

from datetime import date

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from market_structures.rates.quotes import MaturityReference
from schedules import CalendarType, Frequency, Schedule
from schedules.calendars import HolidayCalendar
from schedules.date_utils import add_spot_lag, add_tenor


# TODO: it should be in common folder
def _resolve_calendar(calendar: CalendarType | HolidayCalendar) -> HolidayCalendar:
    """Return a HolidayCalendar, constructing one from a CalendarType if necessary."""
    return calendar if isinstance(calendar, HolidayCalendar) else HolidayCalendar(calendar)


class CdsQuote:
    """Single CDS spread quote bundling tenor, spread, and premium leg conventions.

    Each quote carries its own schedule conventions so different pillars can use
    different payment settings. ``maturity_date`` and ``start_date`` are resolved
    lazily from ``reference_date`` at bootstrap time.
    """

    def __init__(
        self,
        spread: float,
        tenor: str,
        spot_lag: int = 0,
        pay_frequency: Frequency = Frequency.QUARTERLY,
        calendar: CalendarType | HolidayCalendar = CalendarType.USD,
        business_day_convention: BusinessDayConvention = BusinessDayConvention.FOLLOWING,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_360,
        stub_type: StubType = StubType.SHORT_FRONT,
        payment_lag: int = 0,
        maturity_reference: MaturityReference = MaturityReference.ACCRUAL_END,
        maturity_date: date | None = None,
    ) -> None:
        """Initialise a CDS spread quote (spread in decimal, e.g. 0.01 = 100 bps).

        If ``maturity_date`` is provided it is used as the pillar date directly,
        bypassing tenor computation and ``maturity_reference`` logic.
        """
        if spread <= 0:
            raise ValueError(f"spread must be positive, got {spread}")
        self._spread = spread
        self.tenor = tenor
        self._spot_lag = spot_lag
        self._pay_frequency = pay_frequency
        self._cal = _resolve_calendar(calendar)
        self._bdc = business_day_convention
        self._dcc = day_count_convention
        self._stub_type = stub_type
        self._payment_lag = payment_lag
        self._maturity_reference = maturity_reference
        self._maturity_override = maturity_date

    def _spot(self, reference_date: date) -> date:
        """Return the accrual start date (reference_date + spot_lag business days)."""
        return add_spot_lag(reference_date, self._spot_lag, self._cal)

    def start_date(self, reference_date: date) -> date:
        """Return the CDS accrual start date."""
        return self._spot(reference_date)

    def maturity_date(self, reference_date: date) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        Returns the override date if one was supplied at construction. Otherwise,
        with ``MaturityReference.ACCRUAL_END`` (default) this is spot + tenor
        BDC-adjusted; with ``MaturityReference.PAYMENT_DATE`` it is the accrual
        end advanced by ``payment_lag`` business days.
        """
        if self._maturity_override is not None:
            return self._maturity_override
        accrual_end = add_tenor(self._spot(reference_date), self.tenor, self._cal, self._bdc)
        if self._maturity_reference is MaturityReference.PAYMENT_DATE:
            return self._cal.add_business_days(accrual_end, self._payment_lag)
        return accrual_end

    def quote_value(self) -> float:
        """Return the market CDS spread in decimal."""
        return self._spread

    def schedule(self, reference_date: date) -> Schedule:
        """Return the premium-leg ``Schedule`` for this quote rooted at ``reference_date``."""
        return Schedule(
            effective_date=self._spot(reference_date),
            termination_date=self.maturity_date(reference_date),
            frequency=self._pay_frequency,
            day_count_convention=self._dcc,
            business_day_convention=self._bdc,
            calendar=self._cal,
            stub_type=self._stub_type,
            payment_lag=self._payment_lag,
        )

    def bumped(self, delta: float) -> "CdsQuote":
        """Return a new ``CdsQuote`` with the spread shifted by ``delta``."""
        return CdsQuote(
            spread=self._spread + delta,
            tenor=self.tenor,
            spot_lag=self._spot_lag,
            pay_frequency=self._pay_frequency,
            calendar=self._cal,
            business_day_convention=self._bdc,
            day_count_convention=self._dcc,
            stub_type=self._stub_type,
            payment_lag=self._payment_lag,
            maturity_reference=self._maturity_reference,
            maturity_date=self._maturity_override,
        )
