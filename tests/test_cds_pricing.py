"""Tests for SingleNameCDS pricing."""

import math
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


def _flat_zero_curve(rate: float = 0.03) -> ZeroCurve:
    return ZeroCurve(
        reference_date=REF,
        pillar_dates=[date(2034, 1, 2)],
        rates=[rate],
        day_count_convention=ACT365,
    )


def _flat_credit_curve(lam: float = 0.02) -> CreditCurve:
    return CreditCurve(
        REF,
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


class TestSingleNameCDS:
    def test_par_spread_credit_triangle(self):
        """At small lambda the par spread is close to lambda * (1 - R) (continuous-time limit).

        The discrete schedule and ACT/360 day count introduce a small (~1-2%) correction,
        so we use a loose tolerance here.
        """
        lam = 0.01
        recovery = 0.4
        zero = _flat_zero_curve(0.0)
        credit = _flat_credit_curve(lam)
        cds = SingleNameCDS.from_quote(
            _quote(spread=lam * (1 - recovery)),
            REF,
            recovery_rate=recovery,
            zero_curve=zero,
            credit_curve=credit,
        )
        par = cds.par_spread()
        assert par == pytest.approx(lam * (1 - recovery), rel=2e-2)

    def test_npv_zero_when_spread_equals_par(self):
        zero = _flat_zero_curve(0.03)
        credit = _flat_credit_curve(0.02)
        q = _quote(spread=0.0125)
        cds = SingleNameCDS.from_quote(q, REF, 0.4, zero, credit)
        par = cds.par_spread()
        cds_at_par = SingleNameCDS(
            reference_date=REF,
            periods=q.schedule(REF),
            spread=par,
            recovery_rate=0.4,
            zero_curve=zero,
            credit_curve=credit,
        )
        assert cds_at_par.npv() == pytest.approx(0.0, abs=1e-12)

    def test_buyer_seller_npv_opposite(self):
        zero = _flat_zero_curve(0.03)
        credit = _flat_credit_curve(0.02)
        q = _quote(spread=0.005)  # off-par to make NPV non-zero
        buyer = SingleNameCDS.from_quote(q, REF, 0.4, zero, credit, side=CdsSide.BUYER)
        seller = SingleNameCDS.from_quote(q, REF, 0.4, zero, credit, side=CdsSide.SELLER)
        assert buyer.npv() == pytest.approx(-seller.npv(), abs=1e-15)

    def test_protection_leg_decomposition(self):
        zero = _flat_zero_curve(0.03)
        credit = _flat_credit_curve(0.02)
        q = _quote(spread=0.0125)
        cds = SingleNameCDS.from_quote(q, REF, 0.4, zero, credit)
        npv = cds.npv()
        prot = cds.protection_leg_pv()
        prem = cds.premium_leg_pv()
        assert npv == pytest.approx(prot - prem, abs=1e-15)

    def test_recovery_validation(self):
        zero = _flat_zero_curve(0.03)
        credit = _flat_credit_curve(0.02)
        with pytest.raises(ValueError):
            SingleNameCDS.from_quote(_quote(), REF, recovery_rate=1.0, zero_curve=zero, credit_curve=credit)
