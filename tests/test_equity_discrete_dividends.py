"""Tests for market_structures.equity.dividends and the discrete-dividend
extension of EquityForwardCurve.
"""

import math
from datetime import date, timedelta

import pytest

from market_conventions import DayCountConvention
from market_structures.equity import (
    DiscreteDividend,
    DividendKind,
    EquityForwardCurve,
)
from market_structures.rates.curve import ZeroCurve


_REF = date(2026, 1, 1)


def _flat_curve(rate: float) -> ZeroCurve:
    pillars = [_REF + timedelta(days=d) for d in (30, 180, 365, 1825)]
    return ZeroCurve(
        reference_date=_REF,
        pillar_dates=pillars,
        rates=[rate] * len(pillars),
        day_count_convention=DayCountConvention.ACT_365_FIXED,
    )


# DiscreteDividend validation


def test_cash_dividend_construction():
    d = DiscreteDividend(date(2026, 6, 1), 1.25, DividendKind.CASH)
    assert d.amount == 1.25
    assert d.kind is DividendKind.CASH


def test_proportional_dividend_construction():
    d = DiscreteDividend(date(2026, 6, 1), 0.02, DividendKind.PROPORTIONAL)
    assert d.amount == 0.02
    assert d.kind is DividendKind.PROPORTIONAL


def test_rejects_non_finite_amount():
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), float("nan"), DividendKind.CASH)
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), float("inf"), DividendKind.PROPORTIONAL)


def test_rejects_non_positive_cash_amount():
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), 0.0, DividendKind.CASH)
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), -1.0, DividendKind.CASH)


def test_rejects_proportional_outside_unit_interval():
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), -0.01, DividendKind.PROPORTIONAL)
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), 1.0, DividendKind.PROPORTIONAL)
    with pytest.raises(ValueError):
        DiscreteDividend(date(2026, 6, 1), 1.5, DividendKind.PROPORTIONAL)


def test_proportional_zero_is_allowed():
    d = DiscreteDividend(date(2026, 6, 1), 0.0, DividendKind.PROPORTIONAL)
    assert d.amount == 0.0


# from_discrete_dividends — formula correctness


def test_empty_schedule_collapses_to_flat_zero_yield():
    spot = 100.0
    curve = _flat_curve(0.04)
    fwd = EquityForwardCurve.from_discrete_dividends(spot, curve, [])
    expiry = _REF + timedelta(days=365)
    expected = spot / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_single_cash_dividend_before_expiry():
    """F(T) = (S0 - d * DF(ex)) / DF(T)."""
    spot = 100.0
    curve = _flat_curve(0.04)
    ex = _REF + timedelta(days=90)
    d = 2.5
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [DiscreteDividend(ex, d, DividendKind.CASH)]
    )
    expected = (spot - d * curve.discount_factor(ex)) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_single_cash_dividend_after_expiry_does_not_affect_forward():
    spot = 100.0
    curve = _flat_curve(0.04)
    ex = _REF + timedelta(days=500)
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [DiscreteDividend(ex, 2.5, DividendKind.CASH)]
    )
    expected = spot / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_single_proportional_dividend_before_expiry():
    """F(T) = S0 * (1 - p) / DF(T)."""
    spot = 100.0
    curve = _flat_curve(0.04)
    ex = _REF + timedelta(days=90)
    p = 0.03
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [DiscreteDividend(ex, p, DividendKind.PROPORTIONAL)]
    )
    expected = spot * (1.0 - p) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_single_proportional_dividend_after_expiry_does_not_affect_forward():
    spot = 100.0
    curve = _flat_curve(0.04)
    ex = _REF + timedelta(days=500)
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [DiscreteDividend(ex, 0.03, DividendKind.PROPORTIONAL)]
    )
    expected = spot / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_cash_dividend_exactly_on_expiry_is_subtracted():
    """Convention: ex_date <= expiry means the forward is ex-div, so the
    dividend is subtracted."""
    spot = 100.0
    curve = _flat_curve(0.04)
    expiry = _REF + timedelta(days=365)
    d = 2.5
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [DiscreteDividend(expiry, d, DividendKind.CASH)]
    )
    expected = (spot - d * curve.discount_factor(expiry)) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_mixed_cash_and_proportional():
    """F(T) = (S0 * (1-p) - d * DF(ex_d)) / DF(T)."""
    spot = 100.0
    curve = _flat_curve(0.04)
    ex_cash = _REF + timedelta(days=90)
    ex_prop = _REF + timedelta(days=180)
    d = 1.5
    p = 0.02
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot,
        curve,
        [
            DiscreteDividend(ex_cash, d, DividendKind.CASH),
            DiscreteDividend(ex_prop, p, DividendKind.PROPORTIONAL),
        ],
    )
    expected = (spot * (1.0 - p) - d * curve.discount_factor(ex_cash)) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_multiple_proportional_dividends_compound_multiplicatively():
    spot = 100.0
    curve = _flat_curve(0.04)
    expiry = _REF + timedelta(days=365)
    p1, p2 = 0.02, 0.03
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot,
        curve,
        [
            DiscreteDividend(_REF + timedelta(days=90), p1, DividendKind.PROPORTIONAL),
            DiscreteDividend(_REF + timedelta(days=180), p2, DividendKind.PROPORTIONAL),
        ],
    )
    expected = spot * (1.0 - p1) * (1.0 - p2) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_borrow_rate_adds_exponential_carry():
    spot = 100.0
    curve = _flat_curve(0.04)
    b = 0.01
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_discrete_dividends(spot, curve, [], borrow_rate=b)
    t = 365.0 / 365.0
    expected = spot * math.exp(-b * t) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_dividends_sorted_internally_regardless_of_input_order():
    spot = 100.0
    curve = _flat_curve(0.04)
    div_late = DiscreteDividend(_REF + timedelta(days=180), 1.0, DividendKind.CASH)
    div_early = DiscreteDividend(_REF + timedelta(days=90), 2.0, DividendKind.CASH)
    fwd_unsorted = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [div_late, div_early]
    )
    fwd_sorted = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [div_early, div_late]
    )
    expiry = _REF + timedelta(days=365)
    assert math.isclose(fwd_unsorted.at_date(expiry), fwd_sorted.at_date(expiry), rel_tol=0.0)
    assert fwd_unsorted.discrete_dividends == fwd_sorted.discrete_dividends


def test_rejects_dividend_on_or_before_reference_date():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_discrete_dividends(
            100.0, curve, [DiscreteDividend(_REF, 1.0, DividendKind.CASH)]
        )
    with pytest.raises(ValueError):
        EquityForwardCurve.from_discrete_dividends(
            100.0,
            curve,
            [DiscreteDividend(_REF - timedelta(days=1), 1.0, DividendKind.CASH)],
        )


def test_raises_when_cash_pv_exceeds_spot_at_expiry():
    """A pathological schedule that consumes more than spot via PV should error."""
    spot = 10.0
    curve = _flat_curve(0.0)
    huge_cash = DiscreteDividend(_REF + timedelta(days=90), 100.0, DividendKind.CASH)
    fwd = EquityForwardCurve.from_discrete_dividends(spot, curve, [huge_cash])
    with pytest.raises(ValueError):
        fwd.at_date(_REF + timedelta(days=180))


def test_continuous_yield_and_discrete_dividends_compose():
    """Continuous q and discrete divs apply multiplicatively (Hull):
    F = (S0*Π(1-p) - PV_cash) * exp(-q*T) / DF(T).
    """
    spot = 100.0
    curve = _flat_curve(0.04)
    q = 0.01
    ex = _REF + timedelta(days=90)
    p = 0.02
    expiry = _REF + timedelta(days=365)
    fwd = EquityForwardCurve(
        spot=spot,
        zero_curve=curve,
        pillar_times=[1.0],
        pillar_yields=[q],
        discrete_dividends=[DiscreteDividend(ex, p, DividendKind.PROPORTIONAL)],
    )
    t = 365.0 / 365.0
    expected = spot * (1.0 - p) * math.exp(-q * t) / curve.discount_factor(expiry)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-12)


def test_at_time_matches_at_date_with_discrete_dividends():
    spot = 100.0
    curve = _flat_curve(0.04)
    ex = _REF + timedelta(days=90)
    fwd = EquityForwardCurve.from_discrete_dividends(
        spot, curve, [DiscreteDividend(ex, 1.5, DividendKind.CASH)]
    )
    days = 365
    expiry = _REF + timedelta(days=days)
    assert math.isclose(fwd.at_date(expiry), fwd.at_time(days / 365.0), rel_tol=1e-12)
