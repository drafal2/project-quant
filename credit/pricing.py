"""Single-name CDS pricer under the deterministic-intensity model."""

from __future__ import annotations

from datetime import date
from enum import Enum

from market_structures.rates.curve import ZeroCurve
from schedules.schedule import Period

from .curve import CreditCurve
from .quotes import CdsQuote


class CdsSide(Enum):
    """Trade side for CDS NPV reporting."""

    BUYER = "buyer"
    SELLER = "seller"

# TODO: docstrings should include parameters descriptions, notes and info what is returned

class SingleNameCDS:
    """Single-name CDS pricer under the deterministic-intensity (first-jump) model.

    Survival is taken from a ``CreditCurve`` and discounting from a ``ZeroCurve``.
    The accrual-on-default integral and the protection-leg integral are both
    approximated period-by-period using the midpoint discount factor — exact in
    the limit of vanishing accrual length and consistent with standard market
    practice. Recovery is paid at the default time and a constant recovery rate
    is assumed across the life of the trade.
    """

    def __init__(
        self,
        reference_date: date,
        periods: list[Period],
        spread: float,
        recovery_rate: float,
        zero_curve: ZeroCurve,
        credit_curve: CreditCurve,
        notional: float = 1.0,
        side: CdsSide = CdsSide.BUYER,
    ) -> None:
        """Initialise a CDS pricer with a fully-resolved premium-leg schedule."""
        if not periods:
            raise ValueError("at least one accrual period required")
        if spread < 0:
            raise ValueError("spread must be non-negative")
        if not 0.0 <= recovery_rate < 1.0:
            raise ValueError("recovery_rate must lie in [0, 1)")
        self._reference_date = reference_date
        self._periods = list(periods)
        self._spread = spread
        self._recovery_rate = recovery_rate
        self._zero_curve = zero_curve
        self._credit_curve = credit_curve
        self._notional = notional
        self._side = side

    @classmethod
    def from_quote(
        cls,  # TODO: what is the difference between @classmethod and @staticmethod? when to use which? why is cls used instead of self?
        quote: CdsQuote,
        reference_date: date,
        recovery_rate: float,
        zero_curve: ZeroCurve,
        credit_curve: CreditCurve,
        notional: float = 1.0,
        side: CdsSide = CdsSide.BUYER,
    ) -> "SingleNameCDS":  # TODO: why is it in ""?
        """Construct a CDS pricer from a ``CdsQuote`` (spread and schedule taken from the quote)."""
        return cls(
            reference_date=reference_date,
            periods=quote.schedule(reference_date),
            spread=quote.quote_value(),
            recovery_rate=recovery_rate,
            zero_curve=zero_curve,
            credit_curve=credit_curve,
            notional=notional,
            side=side,
        )

    def _df_mid(self, p: Period) -> float:
        """Return the midpoint discount factor over a period's accrual interval."""
        df_s = self._zero_curve.discount_factor(p.accrual_start)
        df_e = self._zero_curve.discount_factor(p.accrual_end)
        return 0.5 * (df_s + df_e)

    def _delta_q(self, p: Period) -> float:
        """Return the period default probability Q(start) - Q(end)."""
        q_s = self._credit_curve.non_default_probability(p.accrual_start)
        q_e = self._credit_curve.non_default_probability(p.accrual_end)
        return q_s - q_e

    def protection_leg_pv(self) -> float:
        """Return the protection leg PV: (1 - R) * sum_i DF_mid_i * (Q_{i-1} - Q_i)."""
        loss = 1.0 - self._recovery_rate
        total = 0.0
        for p in self._periods:
            total += self._df_mid(p) * self._delta_q(p)
        return self._notional * loss * total

    def premium_leg_running_pv(self) -> float:
        """Return the running coupon PV: s * sum_i alpha_i * DF(pay_i) * Q(accrual_end_i)."""
        total = 0.0
        for p in self._periods:
            df_pay = self._zero_curve.discount_factor(p.pay_date)
            q_e = self._credit_curve.non_default_probability(p.accrual_end)
            total += p.dcf * df_pay * q_e
        return self._notional * self._spread * total

    def accrual_on_default_pv(self) -> float:
        """Return PV of premium accrued to default: s * sum_i (alpha_i/2) * DF_mid_i * dQ_i."""
        total = 0.0
        for p in self._periods:
            total += 0.5 * p.dcf * self._df_mid(p) * self._delta_q(p)
        return self._notional * self._spread * total

    def premium_leg_pv(self) -> float:
        """Return the full premium leg PV (running coupons plus accrued-on-default)."""
        return self.premium_leg_running_pv() + self.accrual_on_default_pv()

    def rpv01(self) -> float:
        """Return the risky annuity (premium leg PV per unit spread, per unit notional)."""
        total = 0.0
        for p in self._periods:
            df_pay = self._zero_curve.discount_factor(p.pay_date)
            q_e = self._credit_curve.non_default_probability(p.accrual_end)
            total += p.dcf * df_pay * q_e + 0.5 * p.dcf * self._df_mid(p) * self._delta_q(p)
        return self._notional * total

    def par_spread(self) -> float:
        """Return the spread that makes NPV zero: protection_leg_pv / rpv01."""
        rpv01 = self.rpv01()
        if rpv01 == 0.0:
            raise ZeroDivisionError("RPV01 is zero; par spread undefined")
        return self.protection_leg_pv() / rpv01

    def npv(self) -> float:
        """Return the trade NPV from the configured side's perspective.

        Buyer of protection receives the protection leg and pays the premium leg.
        Seller is the negative of buyer.
        """
        buyer_npv = self.protection_leg_pv() - self.premium_leg_pv()
        return buyer_npv if self._side is CdsSide.BUYER else -buyer_npv
