"""Single-name CDS pricer under the deterministic-intensity model."""

from __future__ import annotations

from datetime import date
from enum import Enum

from market_structures.rates.curve import ZeroCurve
from schedules.schedule import Period, Schedule

from .curve import CreditCurve


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

    For a new trade pass ``quote.schedule(reference_date)`` as the schedule.
    For a mid-life trade construct a ``Schedule`` from the last coupon date to
    maturity and pass that instead; the pricer is agnostic to trade age.

    ``pricing_date`` must equal the reference date of both curves. Periods fully
    before ``pricing_date`` are dropped; the first live period retains its full DCF
    because the premium coupon is contractually fixed for the whole accrual period.
    Only the protection-leg and accrual-on-default integrals are clipped to begin at
    ``pricing_date`` via ``_integration_start``.
    """

    def __init__(
        self,
        pricing_date: date,
        schedule: Schedule,
        spread: float,
        recovery_rate: float,
        zero_curve: ZeroCurve,
        credit_curve: CreditCurve,
        notional: float = 1.0,
        side: CdsSide = CdsSide.BUYER,
    ) -> None:
        """Initialise a CDS pricer from a ``Schedule`` and market/model inputs."""
        if zero_curve.reference_date != pricing_date:
            raise ValueError(
                f"zero_curve.reference_date {zero_curve.reference_date} "
                f"does not match pricing_date {pricing_date}"
            )
        if credit_curve.reference_date != pricing_date:
            raise ValueError(
                f"credit_curve.reference_date {credit_curve.reference_date} "
                f"does not match pricing_date {pricing_date}"
            )
        if spread < 0:
            raise ValueError("spread must be non-negative")
        if not 0.0 <= recovery_rate < 1.0:
            raise ValueError("recovery_rate must lie in [0, 1)")

        periods = self._clip_periods(schedule.generate(), pricing_date)
        if not periods:
            raise ValueError("no accrual periods remain after the pricing date")

        self._pricing_date = pricing_date
        self._periods = periods
        self._spread = spread
        self._recovery_rate = recovery_rate
        self._zero_curve = zero_curve
        self._credit_curve = credit_curve
        self._notional = notional
        self._side = side

    @staticmethod
    def _clip_periods(periods: list[Period], pricing_date: date) -> list[Period]:
        """Drop fully elapsed periods; live periods retain their original DCF.

        The premium coupon is fixed as spread * full_dcf * N regardless of when
        the trade is priced mid-period, so the DCF is never rescaled here.
        """
        return [p for p in periods if p.accrual_end > pricing_date]

    def _integration_start(self, p: Period) -> date:
        """Return the effective start for protection/AoD integration.

        For the stub period this is pricing_date (default before today is impossible);
        for all subsequent periods it is the stored accrual_start.
        """
        return max(p.accrual_start, self._pricing_date)

    def _df_mid(self, p: Period) -> float:
        """Return the midpoint discount factor over the live portion of a period."""
        start = self._integration_start(p)
        return 0.5 * (
            self._zero_curve.discount_factor(start)
            + self._zero_curve.discount_factor(p.accrual_end)
        )

    def _delta_q(self, p: Period) -> float:
        """Return Q(integration_start) - Q(accrual_end) for the live portion of a period."""
        start = self._integration_start(p)
        return (
            self._credit_curve.non_default_probability(start)
            - self._credit_curve.non_default_probability(p.accrual_end)
        )

    def protection_leg_pv(self) -> float:
        """Return the protection leg PV: (1 - R) * sum_i DF_mid_i * (Q_{i-1} - Q_i)."""
        loss = 1.0 - self._recovery_rate
        total = sum(self._df_mid(p) * self._delta_q(p) for p in self._periods)
        return self._notional * loss * total

    def premium_leg_running_pv(self) -> float:
        """Return the running coupon PV: s * sum_i alpha_i * DF(pay_i) * Q(accrual_end_i)."""
        total = sum(
            p.dcf * self._zero_curve.discount_factor(p.pay_date)
            * self._credit_curve.non_default_probability(p.accrual_end)
            for p in self._periods
        )
        return self._notional * self._spread * total

    def accrual_on_default_pv(self) -> float:
        """Return PV of premium accrued to default: s * sum_i (alpha_i/2) * DF_mid_i * dQ_i."""
        total = sum(
            0.5 * p.dcf * self._df_mid(p) * self._delta_q(p)
            for p in self._periods
        )
        return self._notional * self._spread * total

    def premium_leg_pv(self) -> float:
        """Return the full premium leg PV (running coupons plus accrued-on-default)."""
        return self.premium_leg_running_pv() + self.accrual_on_default_pv()

    def rpv01(self) -> float:
        """Return the risky annuity (premium leg PV per unit spread, per unit notional)."""
        total = sum(
            p.dcf * self._zero_curve.discount_factor(p.pay_date)
            * self._credit_curve.non_default_probability(p.accrual_end)
            + 0.5 * p.dcf * self._df_mid(p) * self._delta_q(p)
            for p in self._periods
        )
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

    def premium_leg_summary(self) -> str:
        """Return a formatted per-period breakdown of the premium leg.

        Columns: period index, accrual start, accrual end, pay date, DCF,
        survival probability at accrual end, discount factor at pay date,
        undiscounted cash flow, running coupon PV, and accrual-on-default PV.
        """
        header = (
            f"{'#':>3}  {'Accrual Start':>13}  {'Accrual End':>11}  {'Pay Date':>10}"
            f"  {'DCF':>7}  {'Q(end)':>8}  {'DF(pay)':>8}"
            f"  {'Cash Flow':>12}  {'Running PV':>11}  {'AoD PV':>10}"
        )
        width = len(header)
        rows = [
            f"Premium Leg  |  spread={self._spread:.6f}  notional={self._notional:,.2f}"
            f"  pricing_date={self._pricing_date}",
            "=" * width,
            header,
            "-" * width,
        ]
        run_total = aod_total = 0.0
        for i, p in enumerate(self._periods, 1):
            q_end = self._credit_curve.non_default_probability(p.accrual_end)
            df_pay = self._zero_curve.discount_factor(p.pay_date)
            df_mid = self._df_mid(p)
            dq = self._delta_q(p)
            cf = self._spread * p.dcf * self._notional
            run_pv = self._spread * p.dcf * df_pay * q_end * self._notional
            aod_pv = self._spread * 0.5 * p.dcf * df_mid * dq * self._notional
            run_total += run_pv
            aod_total += aod_pv
            rows.append(
                f"{i:>3}  {str(p.accrual_start):>13}  {str(p.accrual_end):>11}"
                f"  {str(p.pay_date):>10}  {p.dcf:>7.4f}  {q_end:>8.6f}  {df_pay:>8.6f}"
                f"  {cf:>12,.4f}  {run_pv:>11,.4f}  {aod_pv:>10,.4f}"
            )
        rows.append("-" * width)
        rows.append(
            f"Running PV: {run_total:>12,.4f}  |  "
            f"AoD PV: {aod_total:>10,.4f}  |  "
            f"Total Premium PV: {run_total + aod_total:>12,.4f}"
        )
        return "\n".join(rows)

    def protection_leg_summary(self) -> str:
        """Return a formatted per-period breakdown of the protection leg.

        Columns: period index, accrual start, accrual end, survival probability
        at start and end, period default probability ΔQ, midpoint discount factor,
        and protection PV contribution.
        """
        header = (
            f"{'#':>3}  {'Accrual Start':>13}  {'Accrual End':>11}"
            f"  {'Q(start)':>9}  {'Q(end)':>8}  {'ΔQ':>9}"
            f"  {'DF_mid':>8}  {'Protection PV':>14}"
        )
        width = len(header)
        loss = 1.0 - self._recovery_rate
        rows = [
            f"Protection Leg  |  recovery={self._recovery_rate:.2%}  notional={self._notional:,.2f}"
            f"  pricing_date={self._pricing_date}",
            "=" * width,
            header,
            "-" * width,
        ]
        total = 0.0
        for i, p in enumerate(self._periods, 1):
            int_start = self._integration_start(p)
            q_start = self._credit_curve.non_default_probability(int_start)
            q_end = self._credit_curve.non_default_probability(p.accrual_end)
            dq = q_start - q_end
            df_mid = self._df_mid(p)
            pv = self._notional * loss * df_mid * dq
            total += pv
            rows.append(
                f"{i:>3}  {str(int_start):>13}  {str(p.accrual_end):>11}"
                f"  {q_start:>9.6f}  {q_end:>8.6f}  {dq:>9.6f}"
                f"  {df_mid:>8.6f}  {pv:>14,.4f}"
            )
        rows.append("-" * width)
        rows.append(f"Total Protection PV: {total:>14,.4f}")
        return "\n".join(rows)
