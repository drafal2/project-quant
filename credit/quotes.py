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

        Parameters
        ----------
        spread
            Market CDS spread in decimal form (0.01 = 100 bps). Must be strictly
            positive.
        tenor
            Tenor string used to derive the maturity from the accrual start
            (e.g. ``"5Y"``). Ignored when ``maturity_date`` is supplied.
        spot_lag
            Number of business days from ``reference_date`` to the accrual start
            (T+spot_lag). Defaults to ``0``.
        pay_frequency
            Premium-leg coupon frequency. Defaults to ``QUARTERLY``.
        calendar
            Holiday calendar (or ``CalendarType`` to construct one) used for
            spot lag, tenor advance, BDC adjustment, and payment lag.
        business_day_convention
            Adjustment applied to schedule dates that fall on non-business days.
            Defaults to ``FOLLOWING``.
        day_count_convention
            Day count used for premium-leg accrual fractions. Defaults to
            ``ACT_360``.
        stub_type
            Stub placement when the schedule does not divide evenly. Defaults
            to ``SHORT_FRONT``.
        payment_lag
            Business days from accrual end to the cash payment date; also used
            to derive the maturity when ``maturity_reference`` is
            ``PAYMENT_DATE``. Defaults to ``0``.
        maturity_reference
            Selects whether the bootstrapping pillar maturity is the BDC-
            adjusted accrual end (``ACCRUAL_END``, default) or the payment
            date (``PAYMENT_DATE``).
        maturity_date
            Optional explicit maturity date. When supplied it is used as the
            pillar date directly, bypassing tenor computation and
            ``maturity_reference`` logic.

        Raises
        ------
        ValueError
            If ``spread`` is not strictly positive.
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
        """Return the CDS accrual start date.

        Parameters
        ----------
        reference_date
            Anchor date from which the spot lag is applied.

        Returns
        -------
        date
            ``reference_date + spot_lag`` business days.
        """
        return self._spot(reference_date)

    def maturity_date(self, reference_date: date) -> date:
        """Return the maturity date used as the bootstrapping pillar.

        Returns the override date if one was supplied at construction. Otherwise,
        with ``MaturityReference.ACCRUAL_END`` (default) this is spot + tenor
        BDC-adjusted; with ``MaturityReference.PAYMENT_DATE`` it is the accrual
        end advanced by ``payment_lag`` business days.

        Parameters
        ----------
        reference_date
            Anchor date from which the accrual start (and hence maturity) is
            derived. Ignored when an explicit ``maturity_date`` was supplied
            at construction.

        Returns
        -------
        date
            Pillar maturity date for bootstrapping.
        """
        if self._maturity_override is not None:
            return self._maturity_override
        accrual_end = add_tenor(self._spot(reference_date), self.tenor, self._cal, self._bdc)
        if self._maturity_reference is MaturityReference.PAYMENT_DATE:
            return self._cal.add_business_days(accrual_end, self._payment_lag)
        return accrual_end

    def quote_value(self) -> float:
        """Return the market CDS spread in decimal.

        Returns
        -------
        float
            CDS spread in decimal form (0.01 = 100 bps).
        """
        return self._spread

    def schedule(self, reference_date: date) -> Schedule:
        """Return the premium-leg ``Schedule`` for this quote rooted at ``reference_date``.

        Parameters
        ----------
        reference_date
            Anchor date used to resolve the accrual start and maturity.

        Returns
        -------
        Schedule
            Premium-leg schedule built from this quote's conventions, running
            from ``start_date(reference_date)`` to ``maturity_date(reference_date)``.
        """
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
        """Return a new ``CdsQuote`` with the spread shifted by ``delta``.

        Parameters
        ----------
        delta
            Spread shift in decimal form (e.g. ``1e-4`` for a 1 bp bump).

        Returns
        -------
        CdsQuote
            New quote with ``spread + delta`` and all other conventions copied
            unchanged. Used for finite-difference CS01 via re-bootstrapping.
        """
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
