"""Market quote type for CDS spread bootstrapping."""

from datetime import date

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from market_structures.rates.quotes import MaturityReference
from schedules import CalendarType, Frequency, Schedule
from schedules.calendars import HolidayCalendar
from schedules.date_utils import add_spot_lag, add_tenor


class CdsQuote:
    """Single CDS spread quote bundling tenor, spread, and premium leg conventions.

    Passed as input to SurvivalCurve.from_cds_spreads(). Each quote carries its own
    schedule conventions so different pillars can use different payment settings.
    maturity_date and start_date are resolved lazily from reference_date at bootstrap time.
    """

    def __init__(
        self,
        spread: float,
        tenor: str,
        spot_lag: int = 0,
        pay_frequency: Frequency = Frequency.QUARTERLY,
        calendar: CalendarType = CalendarType.USD,
        business_day_convention: BusinessDayConvention = BusinessDayConvention.FOLLOWING,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_360,
        stub_type: StubType = StubType.SHORT_FRONT,
        payment_lag: int = 0,
        maturity_reference: MaturityReference = MaturityReference.ACCRUAL_END,
    ) -> None:
        """Initialise a CDS spread quote. spread must be positive (decimal, e.g. 0.01 = 100 bps)."""
        if spread <= 0:
            raise ValueError(f"spread must be positive, got {spread}")
        self._spread = spread
        self.tenor = tenor
        self._spot_lag = spot_lag
        self._pay_frequency = pay_frequency
        self._calendar = calendar
        self._bdc = business_day_convention
        self._dcc = day_count_convention
        self._stub_type = stub_type
        self._payment_lag = payment_lag
        self._maturity_reference = maturity_reference

    def _spot(self, reference_date: date) -> date:
        """Return the accrual start date (reference_date advanced by spot_lag business days)."""
        cal = HolidayCalendar(self._calendar)
        return add_spot_lag(reference_date, self._spot_lag, cal)

    def start_date(self, reference_date: date) -> date:
        """Return the CDS accrual start date."""
        return self._spot(reference_date)

    def maturity_date(self, reference_date: date) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        With MaturityReference.ACCRUAL_END (default) this is spot + tenor BDC-adjusted.
        With MaturityReference.PAYMENT_DATE it is the accrual end advanced by payment_lag
        business days.
        """
        cal = HolidayCalendar(self._calendar)
        accrual_end = add_tenor(self._spot(reference_date), self.tenor, cal, self._bdc)
        if self._maturity_reference is MaturityReference.PAYMENT_DATE:
            return cal.add_business_days(accrual_end, self._payment_lag)
        return accrual_end

    def quote_value(self) -> float:
        """Return the market CDS spread in decimal."""
        return self._spread

    def schedule(self, reference_date: date) -> list:
        """Return the list of accrual periods for the CDS premium leg."""
        return Schedule(
            effective_date=self._spot(reference_date),
            termination_date=self.maturity_date(reference_date),
            frequency=self._pay_frequency,
            day_count_convention=self._dcc,
            business_day_convention=self._bdc,
            calendar=self._calendar,
            stub_type=self._stub_type,
            payment_lag=self._payment_lag,
        ).generate()

    def bumped(self, delta: float) -> "CdsQuote":
        """Return a new CdsQuote with spread shifted by delta."""
        return CdsQuote(
            self._spread + delta,
            self.tenor,
            self._spot_lag,
            self._pay_frequency,
            self._calendar,
            self._bdc,
            self._dcc,
            self._stub_type,
            self._payment_lag,
            self._maturity_reference,
        )
