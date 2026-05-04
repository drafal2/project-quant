"""Single-name CDS pricer: premium/protection leg PV, par spread, MTM, CS01, RR01."""

from datetime import date

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from schedules import CalendarType, Frequency, Schedule
from .survival_curve import SurvivalCurve


class SingleNameCDS:
    """Pricer for a single-name Credit Default Swap."""

    def __init__(
        self,
        effective_date: date,
        maturity_date: date,
        notional: float,
        coupon_spread: float,
        recovery_rate: float,
        pay_frequency: Frequency = Frequency.QUARTERLY,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_360,
        business_day_convention: BusinessDayConvention = BusinessDayConvention.FOLLOWING,
        calendar: CalendarType = CalendarType.USD,
        stub_type: StubType = StubType.SHORT_FRONT,
        is_protection_buyer: bool = True,
    ) -> None:
        """Construct a single-name CDS.

        coupon_spread and recovery_rate are in decimal (0.01 = 100 bps, 0.40 = 40%).
        is_protection_buyer=True means MTM > 0 when par_spread > coupon_spread.
        """
        if effective_date >= maturity_date:
            raise ValueError("effective_date must be before maturity_date")
        if not (0.0 <= recovery_rate < 1.0):
            raise ValueError("recovery_rate must be in [0, 1)")
        if notional <= 0:
            raise ValueError("notional must be positive")

        self._effective = effective_date
        self._maturity = maturity_date
        self._notional = notional
        self._coupon = coupon_spread
        self._recovery = recovery_rate
        self._pay_freq = pay_frequency
        self._dcc = day_count_convention
        self._bdc = business_day_convention
        self._calendar = calendar
        self._stub = stub_type
        self._is_buyer = is_protection_buyer
        self._schedule = None

    def _get_schedule(self):
        """Return cached accrual schedule, generating on first call."""
        if self._schedule is None:
            self._schedule = Schedule(
                effective_date=self._effective,
                termination_date=self._maturity,
                frequency=self._pay_freq,
                day_count_convention=self._dcc,
                business_day_convention=self._bdc,
                calendar=self._calendar,
                stub_type=self._stub,
            ).generate()
        return self._schedule

    def premium_leg_pv(self, discount_curve, survival_curve) -> float:
        """Return PV of the premium leg including survival-weighted coupon and accrued on default."""
        N = self._notional
        s = self._coupon
        pv = 0.0
        for p in self._get_schedule():
            df_s = discount_curve.discount_factor(p.accrual_start)
            df_e = discount_curve.discount_factor(p.accrual_end)
            df_pay = discount_curve.discount_factor(p.pay_date)
            q_s = survival_curve.survival_probability(p.accrual_start)
            q_e = survival_curve.survival_probability(p.accrual_end)
            df_avg = (df_s + df_e) / 2.0
            dq = q_s - q_e
            pv += s * N * p.dcf * df_pay * q_e
            pv += s * N * (p.dcf / 2.0) * df_avg * dq
        return pv

    def protection_leg_pv(self, discount_curve, survival_curve) -> float:
        """Return PV of the protection leg (LGD * expected default payment).

        Uses midpoint discount factor: prot_i = (1-R)*N * df_avg * (Q_s - Q_e).
        Goes to zero as hazard rate goes to zero.
        """
        N = self._notional
        R = self._recovery
        pv = 0.0
        for p in self._get_schedule():
            df_s = discount_curve.discount_factor(p.accrual_start)
            df_e = discount_curve.discount_factor(p.accrual_end)
            q_s = survival_curve.survival_probability(p.accrual_start)
            q_e = survival_curve.survival_probability(p.accrual_end)
            df_avg = (df_s + df_e) / 2.0
            pv += (1.0 - R) * N * df_avg * (q_s - q_e)
        return pv

    def rpv01(self, discount_curve, survival_curve) -> float:
        """Return the risky annuity (RPV01) per unit notional."""
        val = 0.0
        for p in self._get_schedule():
            df_s = discount_curve.discount_factor(p.accrual_start)
            df_e = discount_curve.discount_factor(p.accrual_end)
            df_pay = discount_curve.discount_factor(p.pay_date)
            q_s = survival_curve.survival_probability(p.accrual_start)
            q_e = survival_curve.survival_probability(p.accrual_end)
            df_avg = (df_s + df_e) / 2.0
            val += p.dcf * df_pay * q_e + (p.dcf / 2.0) * df_avg * (q_s - q_e)
        return val

    def par_spread(self, discount_curve, survival_curve) -> float:
        """Return the par spread — the coupon that makes MTM = 0."""
        return self.protection_leg_pv(discount_curve, survival_curve) / (
            self._notional * self.rpv01(discount_curve, survival_curve)
        )

    def mtm(self, discount_curve, survival_curve) -> float:
        """Return mark-to-market value.

        Positive for protection buyer when par_spread > coupon_spread.
        Sign is negated for protection seller.
        """
        value = self.protection_leg_pv(discount_curve, survival_curve) - self.premium_leg_pv(
            discount_curve, survival_curve
        )
        return value if self._is_buyer else -value

    def cs01(self, discount_curve, survival_curve) -> float:
        """Return CS01: MTM change for a 1 bp parallel spread bump (re-bootstrapped).

        Positive for protection buyer (spread widening increases protection value).
        """
        bumped_sc = survival_curve.bump(0.0001)
        return self.mtm(discount_curve, bumped_sc) - self.mtm(discount_curve, survival_curve)

    def rr01(self, discount_curve, survival_curve) -> float:
        """Return RR01: MTM change for a 1% increase in recovery rate (sticky hazard rates).

        Positive for protection buyer (higher recovery reduces protection payout).
        """
        base_mtm = self.mtm(discount_curve, survival_curve)
        bumped = SingleNameCDS(
            self._effective,
            self._maturity,
            self._notional,
            self._coupon,
            self._recovery + 0.01,
            self._pay_freq,
            self._dcc,
            self._bdc,
            self._calendar,
            self._stub,
            self._is_buyer,
        )
        return base_mtm - bumped.mtm(discount_curve, survival_curve)
