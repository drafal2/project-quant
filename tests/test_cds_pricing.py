"""Tests for SingleNameCDS pricing."""

from datetime import date

import pytest

from credit.curve import CreditCurve, InterpolationVariable
from credit.pricing import CdsSide, SingleNameCDS
from credit.quotes import CdsQuote
from market_conventions import (
    BusinessDayConvention,
    DayCountConvention,
    StubType,
)
from market_structures.rates.curve import ZeroCurve
from schedules import CalendarType, Frequency

REF = date(2024, 1, 2)
ACT365 = DayCountConvention.ACT_365_FIXED


def _flat_zero_curve(rate: float = 0.03, ref: date = REF) -> ZeroCurve:
    return ZeroCurve(
        reference_date=ref,
        pillar_dates=[date(2034, 1, 2)],
        rates=[rate],
        day_count_convention=ACT365,
    )


def _flat_credit_curve(lam: float = 0.02, ref: date = REF) -> CreditCurve:
    return CreditCurve(
        ref,
        [date(2034, 1, 2)],
        [lam],
        InterpolationVariable.FORWARD_DEFAULT_SPREAD,
        ACT365,
    )


def _quote(spread: float = 0.0125, tenor: str = "5Y") -> CdsQuote:
    return CdsQuote(
        spread=spread,
        tenor=tenor,
        spot_lag=0,
        pay_frequency=Frequency.QUARTERLY,
        calendar=CalendarType.USD,
        business_day_convention=BusinessDayConvention.FOLLOWING,
        day_count_convention=DayCountConvention.ACT_360,
        stub_type=StubType.SHORT_FRONT,
    )


def _cds(
    spread: float = 0.0125,
    tenor: str = "5Y",
    recovery: float = 0.4,
    zero_rate: float = 0.03,
    lam: float = 0.02,
    side: CdsSide = CdsSide.BUYER,
    pricing_date: date = REF,
) -> SingleNameCDS:
    q = _quote(spread=spread, tenor=tenor)
    return SingleNameCDS(
        schedule=q.schedule(pricing_date),
        spread=q.quote_value(),
        recovery_rate=recovery,
        zero_curve=_flat_zero_curve(zero_rate, pricing_date),
        credit_curve=_flat_credit_curve(lam, pricing_date),
        pricing_date=pricing_date,
        side=side,
    )


class TestSingleNameCDS:
    def test_par_spread_credit_triangle(self):
        """At small lambda the par spread is close to lambda * (1 - R) (continuous-time limit).

        The discrete schedule and ACT/360 day count introduce a small (~1-2%) correction,
        so we use a loose tolerance here.
        """
        lam = 0.01
        recovery = 0.4
        par = _cds(spread=lam * (1 - recovery), lam=lam, zero_rate=0.0, recovery=recovery).par_spread()
        assert par == pytest.approx(lam * (1 - recovery), rel=2e-2)

    def test_npv_zero_when_spread_equals_par(self):
        q = _quote(spread=0.0125)
        zero = _flat_zero_curve(0.03)
        credit = _flat_credit_curve(0.02)
        cds = SingleNameCDS(
            schedule=q.schedule(REF),
            spread=q.quote_value(),
            recovery_rate=0.4,
            zero_curve=zero,
            credit_curve=credit,
            pricing_date=REF,
        )
        par = cds.par_spread()
        cds_at_par = SingleNameCDS(
            schedule=q.schedule(REF),
            spread=par,
            recovery_rate=0.4,
            zero_curve=zero,
            credit_curve=credit,
            pricing_date=REF,
        )
        assert cds_at_par.npv() == pytest.approx(0.0, abs=1e-12)

    def test_buyer_seller_npv_opposite(self):
        buyer = _cds(spread=0.005, side=CdsSide.BUYER)
        seller = _cds(spread=0.005, side=CdsSide.SELLER)
        assert buyer.npv() == pytest.approx(-seller.npv(), abs=1e-15)

    def test_protection_leg_decomposition(self):
        cds = _cds()
        assert cds.npv() == pytest.approx(cds.protection_leg_pv() - cds.premium_leg_pv(), abs=1e-15)

    def test_recovery_validation(self):
        q = _quote()
        with pytest.raises(ValueError):
            SingleNameCDS(
                schedule=q.schedule(REF),
                spread=q.quote_value(),
                recovery_rate=1.0,
                zero_curve=_flat_zero_curve(),
                credit_curve=_flat_credit_curve(),
                pricing_date=REF,
            )

    def test_pricing_date_mismatch_zero_curve_raises(self):
        q = _quote()
        wrong_ref = date(2024, 1, 3)
        with pytest.raises(ValueError, match="zero_curve.reference_date"):
            SingleNameCDS(
                schedule=q.schedule(REF),
                spread=q.quote_value(),
                recovery_rate=0.4,
                zero_curve=_flat_zero_curve(ref=wrong_ref),
                credit_curve=_flat_credit_curve(),
                pricing_date=REF,
            )

    def test_pricing_date_mismatch_credit_curve_raises(self):
        q = _quote()
        wrong_ref = date(2024, 1, 3)
        with pytest.raises(ValueError, match="credit_curve.reference_date"):
            SingleNameCDS(
                schedule=q.schedule(REF),
                spread=q.quote_value(),
                recovery_rate=0.4,
                zero_curve=_flat_zero_curve(),
                credit_curve=_flat_credit_curve(ref=wrong_ref),
                pricing_date=REF,
            )

    def test_elapsed_periods_dropped(self):
        """Pricing mid-life drops periods whose accrual end is on or before pricing_date."""
        q = _quote(tenor="2Y")
        mid = date(2024, 4, 3)  # one day after the first quarterly coupon end (2024-04-02)
        cds_full = SingleNameCDS(
            schedule=q.schedule(REF),
            spread=q.quote_value(),
            recovery_rate=0.4,
            zero_curve=_flat_zero_curve(ref=REF),
            credit_curve=_flat_credit_curve(ref=REF),
            pricing_date=REF,
        )
        cds_mid = SingleNameCDS(
            schedule=q.schedule(REF),  # same original schedule
            spread=q.quote_value(),
            recovery_rate=0.4,
            zero_curve=_flat_zero_curve(ref=mid),
            credit_curve=_flat_credit_curve(ref=mid),
            pricing_date=mid,
        )
        assert len(cds_mid._periods) < len(cds_full._periods)

    def test_stub_period_full_dcf_preserved(self):
        """The stub period retains its original DCF: the coupon is fixed for the full period."""
        q = _quote(tenor="2Y")
        mid = date(2024, 2, 1)  # inside first coupon period (2024-01-02 to 2024-04-02)
        cds_full = SingleNameCDS(
            schedule=q.schedule(REF),
            spread=q.quote_value(),
            recovery_rate=0.4,
            zero_curve=_flat_zero_curve(ref=REF),
            credit_curve=_flat_credit_curve(ref=REF),
            pricing_date=REF,
        )
        cds_mid = SingleNameCDS(
            schedule=q.schedule(REF),  # same original schedule
            spread=q.quote_value(),
            recovery_rate=0.4,
            zero_curve=_flat_zero_curve(ref=mid),
            credit_curve=_flat_credit_curve(ref=mid),
            pricing_date=mid,
        )
        assert cds_mid._periods[0].dcf == pytest.approx(cds_full._periods[0].dcf)
