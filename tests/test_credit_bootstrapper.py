"""Tests for the CreditCurveBootstrapper across modes and interpolation variables."""

from datetime import date

import pytest

from credit.bootstrapper import BootstrapMode, CreditCurveBootstrapper
from credit.curve import InterpolationVariable
from credit.pricing import SingleNameCDS
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
RECOVERY = 0.4


def _zero_curve(rate: float = 0.03) -> ZeroCurve:
    return ZeroCurve(
        reference_date=REF,
        pillar_dates=[date(2034, 1, 2)],
        rates=[rate],
        day_count_convention=ACT365,
    )


def _quote(spread: float, tenor: str) -> CdsQuote:
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


def _quotes() -> list[CdsQuote]:
    return [
        _quote(0.0080, "1Y"),
        _quote(0.0110, "3Y"),
        _quote(0.0130, "5Y"),
        _quote(0.0145, "7Y"),
        _quote(0.0155, "10Y"),
    ]


@pytest.fixture
def quotes():
    return _quotes()


@pytest.fixture
def zero_curve():
    return _zero_curve(0.03)


def _round_trip_residuals(curve, zero_curve, quotes):
    return [
        SingleNameCDS.from_quote(q, REF, RECOVERY, zero_curve, curve).npv()
        for q in quotes
    ]


@pytest.mark.parametrize(
    "variable",
    [
        InterpolationVariable.FORWARD_DEFAULT_SPREAD,
        InterpolationVariable.DEFAULT_SPREAD,
        InterpolationVariable.SURVIVAL_PROBABILITY,
    ],
)
class TestSequentialMode:
    def test_round_trip(self, variable, quotes, zero_curve):
        bs = CreditCurveBootstrapper(
            REF,
            quotes,
            zero_curve,
            RECOVERY,
            interpolation_variable=variable,
            mode=BootstrapMode.SEQUENTIAL,
        )
        curve = bs.bootstrap()
        residuals = _round_trip_residuals(curve, zero_curve, quotes)
        assert max(abs(r) for r in residuals) < 1e-9


@pytest.mark.parametrize(
    "variable",
    [
        InterpolationVariable.FORWARD_DEFAULT_SPREAD,
        InterpolationVariable.DEFAULT_SPREAD,
        InterpolationVariable.SURVIVAL_PROBABILITY,
    ],
)
class TestGlobalMode:
    def test_round_trip(self, variable, quotes, zero_curve):
        bs = CreditCurveBootstrapper(
            REF,
            quotes,
            zero_curve,
            RECOVERY,
            interpolation_variable=variable,
            mode=BootstrapMode.GLOBAL,
        )
        curve = bs.bootstrap()
        residuals = _round_trip_residuals(curve, zero_curve, quotes)
        assert max(abs(r) for r in residuals) < 1e-9


class TestModeAgreement:
    def test_sequential_and_global_agree(self, quotes, zero_curve):
        seq = CreditCurveBootstrapper(
            REF, quotes, zero_curve, RECOVERY,
            interpolation_variable=InterpolationVariable.FORWARD_DEFAULT_SPREAD,
            mode=BootstrapMode.SEQUENTIAL,
        ).bootstrap()
        glob = CreditCurveBootstrapper(
            REF, quotes, zero_curve, RECOVERY,
            interpolation_variable=InterpolationVariable.FORWARD_DEFAULT_SPREAD,
            mode=BootstrapMode.GLOBAL,
        ).bootstrap()
        for d in seq.pillar_dates:
            assert seq.non_default_probability(d) == pytest.approx(
                glob.non_default_probability(d), abs=1e-8
            )


class TestSurvivalIsMonotone:
    def test_q_decreases(self, quotes, zero_curve):
        curve = CreditCurveBootstrapper(
            REF, quotes, zero_curve, RECOVERY,
            interpolation_variable=InterpolationVariable.FORWARD_DEFAULT_SPREAD,
        ).bootstrap()
        prev = 1.0
        d = REF
        for _ in range(10):
            d = date(d.year + 1, d.month, d.day)
            q = curve.non_default_probability(d)
            assert q <= prev + 1e-12
            prev = q


class TestValidation:
    def test_recovery_out_of_range(self, quotes, zero_curve):
        with pytest.raises(ValueError):
            CreditCurveBootstrapper(REF, quotes, zero_curve, recovery_rate=1.0)

    def test_empty_quotes(self, zero_curve):
        with pytest.raises(ValueError):
            CreditCurveBootstrapper(REF, [], zero_curve, RECOVERY)
