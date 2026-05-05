"""Market quote type for CDS spread bootstrapping."""

from datetime import date

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from schedules import CalendarType, Frequency, Schedule


class CdsQuote:
    """Single CDS spread quote bundling maturity, spread, and premium leg conventions.

    Passed as input to SurvivalCurve.from_cds_spreads(). Each quote carries its own
    schedule conventions so different pillars can use different payment settings.
    """

    def __init__(
        self,
        spread: float,
        maturity_date: date,
        pay_frequency: Frequency = Frequency.QUARTERLY,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_360,
        business_day_convention: BusinessDayConvention = BusinessDayConvention.FOLLOWING,
        calendar: CalendarType = CalendarType.USD,
        stub_type: StubType = StubType.SHORT_FRONT,
    ) -> None:
        """Initialise a CDS spread quote. spread must be positive (decimal, e.g. 0.01 = 100 bps)."""
        if spread <= 0:
            raise ValueError(f"spread must be positive, got {spread}")
        self._spread = spread
        self._maturity_date = maturity_date
        self._pay_frequency = pay_frequency
        self._dcc = day_count_convention
        self._bdc = business_day_convention
        self._calendar = calendar
        self._stub_type = stub_type

    def maturity_date(self) -> date:
        """Return the maturity (pillar) date."""
        return self._maturity_date

    def quote_value(self) -> float:
        """Return the market CDS spread in decimal."""
        return self._spread

    def schedule(self, reference_date: date) -> list:
        """Return the list of accrual periods for the CDS premium leg."""
        return Schedule(
            effective_date=reference_date,
            termination_date=self._maturity_date,
            frequency=self._pay_frequency,
            day_count_convention=self._dcc,
            business_day_convention=self._bdc,
            calendar=self._calendar,
            stub_type=self._stub_type,
        ).generate()

    def bumped(self, delta: float) -> "CdsQuote":
        """Return a new CdsQuote with spread shifted by delta."""
        return CdsQuote(
            self._spread + delta,
            self._maturity_date,
            self._pay_frequency,
            self._dcc,
            self._bdc,
            self._calendar,
            self._stub_type,
        )
