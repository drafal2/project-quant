"""Tests for the borrow / repo term structure on EquityForwardCurve and
the BorrowRateQuote / from_dividend_and_borrow_quotes pair.
"""

import math
from datetime import date, timedelta

import pytest

from market_conventions import DayCountConvention
from market_structures.equity import (
    BorrowRateQuote,
    DividendYieldInterpolation,
    DividendYieldQuote,
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


# BorrowRateQuote validation


def test_borrow_quote_stores_fields():
    q = BorrowRateQuote(date(2027, 1, 1), 0.015)
    assert q.maturity_date == date(2027, 1, 1)
    assert q.continuous_borrow_rate == 0.015


def test_borrow_quote_is_frozen():
    q = BorrowRateQuote(date(2027, 1, 1), 0.015)
    with pytest.raises(Exception):
        q.continuous_borrow_rate = 0.02  # type: ignore[misc]


def test_borrow_quote_accepts_negative_rate():
    """Some GC-priced names may carry a small negative borrow spread when
    modelled this way."""
    q = BorrowRateQuote(date(2027, 1, 1), -0.002)
    assert q.continuous_borrow_rate == -0.002


def test_borrow_quote_rejects_non_finite_rate():
    with pytest.raises(ValueError):
        BorrowRateQuote(date(2027, 1, 1), float("nan"))
    with pytest.raises(ValueError):
        BorrowRateQuote(date(2027, 1, 1), float("inf"))


# Backward compatibility: empty borrow curve preserves old numerics


def test_no_borrow_curve_preserves_backward_compat():
    spot = 100.0
    curve = _flat_curve(0.04)
    legacy = EquityForwardCurve(spot, curve, [1.0], [0.02])
    same = EquityForwardCurve(
        spot, curve, [1.0], [0.02],
        borrow_pillar_times=(),
        borrow_pillar_yields=(),
    )
    expiry = _REF + timedelta(days=365)
    assert math.isclose(legacy.at_date(expiry), same.at_date(expiry), rel_tol=0.0)
    assert not same.has_borrow_curve
    assert same.borrow_yield(1.0) == 0.0


def test_effective_yield_equals_dividend_yield_without_borrow():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(100.0, curve, [1.0, 2.0], [0.02, 0.04])
    for t in (0.1, 0.5, 1.0, 1.5, 2.0, 3.0):
        assert math.isclose(fwd.effective_yield(t), fwd.dividend_yield(t), rel_tol=0.0)


# Forward formula with borrow


def test_forward_formula_with_flat_dividend_and_borrow():
    """F(T) = S0 * exp(-(d + b) * T) / DF(T) for flat both."""
    spot = 100.0
    r = 0.04
    d = 0.015
    b = 0.008
    curve = _flat_curve(r)
    fwd = EquityForwardCurve(
        spot, curve, [1.0], [d],
        borrow_pillar_times=[1.0],
        borrow_pillar_yields=[b],
    )
    expiry = _REF + timedelta(days=365)
    expected = spot * math.exp((r - d - b) * 1.0)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-10)


def test_high_borrow_depresses_forward():
    """Hard-to-borrow names (positive borrow yield) must produce a lower forward."""
    spot = 100.0
    curve = _flat_curve(0.04)
    base = EquityForwardCurve(spot, curve, [1.0], [0.02])
    hard_to_borrow = EquityForwardCurve(
        spot, curve, [1.0], [0.02],
        borrow_pillar_times=[1.0], borrow_pillar_yields=[0.05],
    )
    expiry = _REF + timedelta(days=365)
    assert hard_to_borrow.at_date(expiry) < base.at_date(expiry)


def test_zero_borrow_curve_collapses_to_no_borrow():
    spot = 100.0
    curve = _flat_curve(0.04)
    fwd_no_borrow = EquityForwardCurve(spot, curve, [1.0], [0.02])
    fwd_zero_borrow = EquityForwardCurve(
        spot, curve, [1.0], [0.02],
        borrow_pillar_times=[0.5, 5.0], borrow_pillar_yields=[0.0, 0.0],
    )
    expiry = _REF + timedelta(days=365)
    assert math.isclose(
        fwd_no_borrow.at_date(expiry), fwd_zero_borrow.at_date(expiry), rel_tol=1e-12
    )


def test_dividend_and_borrow_recoverable_independently_at_pillars():
    curve = _flat_curve(0.0)
    div_times = [0.5, 1.0, 2.0]
    div_yields = [0.01, 0.02, 0.03]
    bor_times = [0.5, 1.5]
    bor_yields = [0.005, 0.012]
    fwd = EquityForwardCurve(
        100.0, curve, div_times, div_yields,
        borrow_pillar_times=bor_times, borrow_pillar_yields=bor_yields,
    )
    for t, q in zip(div_times, div_yields):
        assert math.isclose(fwd.dividend_yield(t), q, rel_tol=1e-12)
    for t, b in zip(bor_times, bor_yields):
        assert math.isclose(fwd.borrow_yield(t), b, rel_tol=1e-12)


def test_dividend_and_borrow_can_have_distinct_pillar_grids():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(
        100.0, curve,
        pillar_times=[0.25, 1.0],
        pillar_yields=[0.01, 0.02],
        borrow_pillar_times=[0.5, 2.0, 5.0],
        borrow_pillar_yields=[0.005, 0.010, 0.015],
    )
    # At a borrow pillar that is NOT a dividend pillar, both should still be defined.
    assert math.isclose(fwd.borrow_yield(0.5), 0.005, rel_tol=1e-12)
    assert math.isclose(fwd.borrow_yield(5.0), 0.015, rel_tol=1e-12)


def test_borrow_interpolation_defaults_to_dividend_interpolation():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(
        100.0, curve,
        pillar_times=[1.0, 2.0], pillar_yields=[0.0, 0.0],
        borrow_pillar_times=[1.0, 2.0], borrow_pillar_yields=[0.01, 0.03],
        interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD,
    )
    # LINEAR_IN_YIELD on borrow: midpoint is the linear midpoint.
    assert math.isclose(fwd.borrow_yield(1.5), 0.02, rel_tol=1e-12)


def test_borrow_interpolation_can_override_dividend_interpolation():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(
        100.0, curve,
        pillar_times=[1.0, 2.0], pillar_yields=[0.0, 0.0],
        borrow_pillar_times=[1.0, 2.0], borrow_pillar_yields=[0.02, 0.04],
        interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD,
        borrow_interpolation=DividendYieldInterpolation.FORWARD_YIELD_FLAT,
    )
    # FORWARD_YIELD_FLAT at T=1.5: cumulative Q = 0.02 + 0.5*(0.08-0.02) = 0.05, q = 0.05/1.5.
    assert math.isclose(fwd.borrow_yield(1.5), 0.05 / 1.5, rel_tol=1e-12)


def test_borrow_validation_length_mismatch():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve(
            100.0, curve, [1.0], [0.02],
            borrow_pillar_times=[1.0, 2.0],
            borrow_pillar_yields=[0.01],
        )


def test_borrow_validation_non_monotone_pillars():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve(
            100.0, curve, [1.0], [0.02],
            borrow_pillar_times=[1.0, 1.0],
            borrow_pillar_yields=[0.01, 0.02],
        )
    with pytest.raises(ValueError):
        EquityForwardCurve(
            100.0, curve, [1.0], [0.02],
            borrow_pillar_times=[2.0, 1.0],
            borrow_pillar_yields=[0.01, 0.02],
        )


def test_borrow_validation_non_positive_pillar():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve(
            100.0, curve, [1.0], [0.02],
            borrow_pillar_times=[0.0, 1.0],
            borrow_pillar_yields=[0.01, 0.02],
        )


def test_borrow_yield_rejects_non_positive_T():
    curve = _flat_curve(0.04)
    fwd = EquityForwardCurve(
        100.0, curve, [1.0], [0.02],
        borrow_pillar_times=[1.0], borrow_pillar_yields=[0.01],
    )
    with pytest.raises(ValueError):
        fwd.borrow_yield(0.0)
    with pytest.raises(ValueError):
        fwd.borrow_yield(-0.5)


# from_dividend_and_borrow_quotes


def test_from_dividend_and_borrow_quotes_round_trip():
    spot = 100.0
    curve = _flat_curve(0.04)
    dividend_quotes = [
        DividendYieldQuote(_REF + timedelta(days=180), 0.010),
        DividendYieldQuote(_REF + timedelta(days=365), 0.020),
    ]
    borrow_quotes = [
        BorrowRateQuote(_REF + timedelta(days=90), 0.005),
        BorrowRateQuote(_REF + timedelta(days=365), 0.012),
        BorrowRateQuote(_REF + timedelta(days=1825), 0.018),
    ]
    fwd = EquityForwardCurve.from_dividend_and_borrow_quotes(
        spot, curve, dividend_quotes, borrow_quotes
    )
    for q in dividend_quotes:
        t = (q.maturity_date - _REF).days / 365.0
        assert math.isclose(fwd.dividend_yield(t), q.continuous_yield, rel_tol=1e-12)
    for q in borrow_quotes:
        t = (q.maturity_date - _REF).days / 365.0
        assert math.isclose(fwd.borrow_yield(t), q.continuous_borrow_rate, rel_tol=1e-12)
    assert fwd.has_borrow_curve


def test_from_dividend_and_borrow_quotes_sorts_independently():
    spot = 100.0
    curve = _flat_curve(0.04)
    dividend_quotes = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.020),
        DividendYieldQuote(_REF + timedelta(days=180), 0.010),
    ]
    borrow_quotes = [
        BorrowRateQuote(_REF + timedelta(days=1825), 0.018),
        BorrowRateQuote(_REF + timedelta(days=90), 0.005),
    ]
    fwd = EquityForwardCurve.from_dividend_and_borrow_quotes(
        spot, curve, dividend_quotes, borrow_quotes
    )
    assert list(fwd.pillar_times) == sorted(fwd.pillar_times)
    assert list(fwd.borrow_pillar_times) == sorted(fwd.borrow_pillar_times)


def test_from_dividend_and_borrow_quotes_rejects_empty_lists():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_and_borrow_quotes(
            100.0, curve,
            dividend_quotes=[],
            borrow_quotes=[BorrowRateQuote(_REF + timedelta(days=365), 0.01)],
        )
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_and_borrow_quotes(
            100.0, curve,
            dividend_quotes=[DividendYieldQuote(_REF + timedelta(days=365), 0.02)],
            borrow_quotes=[],
        )


def test_from_dividend_and_borrow_quotes_rejects_dates_on_or_before_reference():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_and_borrow_quotes(
            100.0, curve,
            dividend_quotes=[DividendYieldQuote(_REF + timedelta(days=365), 0.02)],
            borrow_quotes=[BorrowRateQuote(_REF, 0.01)],
        )


def test_from_dividend_and_borrow_quotes_rejects_within_list_duplicates():
    curve = _flat_curve(0.04)
    dup = _REF + timedelta(days=365)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_and_borrow_quotes(
            100.0, curve,
            dividend_quotes=[DividendYieldQuote(dup, 0.02)],
            borrow_quotes=[
                BorrowRateQuote(dup, 0.01),
                BorrowRateQuote(dup, 0.02),
            ],
        )


def test_cross_list_coincident_pillar_dates_allowed():
    """A pillar shared between the dividend and borrow lists is intentionally
    permitted — the two grids are independent."""
    spot = 100.0
    curve = _flat_curve(0.04)
    shared = _REF + timedelta(days=365)
    fwd = EquityForwardCurve.from_dividend_and_borrow_quotes(
        spot, curve,
        dividend_quotes=[DividendYieldQuote(shared, 0.02)],
        borrow_quotes=[BorrowRateQuote(shared, 0.01)],
    )
    t = 1.0
    assert math.isclose(fwd.dividend_yield(t), 0.02, rel_tol=1e-12)
    assert math.isclose(fwd.borrow_yield(t), 0.01, rel_tol=1e-12)
    assert math.isclose(fwd.effective_yield(t), 0.03, rel_tol=1e-12)
