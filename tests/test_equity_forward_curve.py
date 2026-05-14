"""Tests for market_structures.equity.forward_curve."""

import math
from datetime import date, timedelta

import pytest

from market_conventions import DayCountConvention
from market_structures.equity import (
    DividendYieldInterpolation,
    DividendYieldQuote,
    EquityForwardCurve,
)
from market_structures.rates.curve import ZeroCurve
from market_structures.volatility.forward import EquityForward


_REF = date(2026, 1, 1)


def _flat_curve(rate: float) -> ZeroCurve:
    pillars = [_REF + timedelta(days=d) for d in (30, 180, 365, 1825)]
    return ZeroCurve(
        reference_date=_REF,
        pillar_dates=pillars,
        rates=[rate] * len(pillars),
        day_count_convention=DayCountConvention.ACT_365_FIXED,
    )


def test_flat_parity_with_equity_forward_by_date():
    spot = 100.0
    curve = _flat_curve(0.04)
    q = 0.02
    legacy = EquityForward(spot, curve, q)
    new = EquityForwardCurve.flat(spot, curve, q)
    for days in (1, 30, 180, 365, 730, 1825):
        expiry = _REF + timedelta(days=days)
        assert math.isclose(new.at_date(expiry), legacy.at_date(expiry), rel_tol=0.0, abs_tol=0.0)


def test_flat_parity_with_equity_forward_by_time():
    spot = 100.0
    curve = _flat_curve(0.03)
    q = 0.015
    legacy = EquityForward(spot, curve, q)
    new = EquityForwardCurve.flat(spot, curve, q)
    for t in (0.01, 0.25, 0.5, 1.0, 2.0, 5.0):
        assert math.isclose(new.at_time(t), legacy.at_time(t), rel_tol=0.0, abs_tol=0.0)


def test_flat_parity_call_dispatch():
    spot = 75.0
    curve = _flat_curve(0.05)
    q = 0.03
    legacy = EquityForward(spot, curve, q)
    new = EquityForwardCurve.flat(spot, curve, q)
    expiry = _REF + timedelta(days=365)
    assert math.isclose(new(expiry), legacy(expiry), rel_tol=0.0, abs_tol=0.0)
    assert math.isclose(new(1.5), legacy(1.5), rel_tol=0.0, abs_tol=0.0)


def test_at_date_matches_textbook_formula_flat():
    spot = 100.0
    r = 0.05
    q = 0.02
    curve = _flat_curve(r)
    fwd = EquityForwardCurve.flat(spot, curve, q)
    expiry = _REF + timedelta(days=365)
    expected = spot * math.exp((r - q) * 1.0)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-10)


def test_zero_dividend_collapses_to_no_carry_forward():
    spot = 100.0
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve.flat(spot, curve, 0.0)
    expiry = _REF + timedelta(days=365)
    assert math.isclose(fwd.at_date(expiry), spot, rel_tol=1e-12)


def test_reference_date_propagates_from_curve():
    curve = _flat_curve(0.03)
    fwd = EquityForwardCurve.flat(100.0, curve, 0.01)
    assert fwd.reference_date == _REF


def test_pillar_properties_round_trip():
    curve = _flat_curve(0.03)
    times = [0.25, 1.0, 2.0]
    yields = [0.01, 0.02, 0.025]
    fwd = EquityForwardCurve(100.0, curve, times, yields)
    assert fwd.pillar_times == tuple(times)
    assert fwd.pillar_yields == tuple(yields)


def test_dividend_yield_interpolates_linearly_in_linear_mode():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(
        100.0,
        curve,
        [1.0, 2.0],
        [0.02, 0.04],
        interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD,
    )
    assert math.isclose(fwd.dividend_yield(1.0), 0.02, rel_tol=1e-12)
    assert math.isclose(fwd.dividend_yield(2.0), 0.04, rel_tol=1e-12)
    assert math.isclose(fwd.dividend_yield(1.5), 0.03, rel_tol=1e-12)


def test_dividend_yield_default_is_forward_yield_flat():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(100.0, curve, [1.0, 2.0], [0.02, 0.04])
    # Pillars are exact in both schemes.
    assert math.isclose(fwd.dividend_yield(1.0), 0.02, rel_tol=1e-12)
    assert math.isclose(fwd.dividend_yield(2.0), 0.04, rel_tol=1e-12)
    # Cumulative yield Q(T) = q(T)*T is piecewise linear from (0,0) -> (1,0.02) -> (2,0.08).
    # At T=1.5: Q = 0.02 + 0.5 * (0.08 - 0.02) = 0.05, q = 0.05/1.5 = 1/30.
    assert math.isclose(fwd.dividend_yield(1.5), 1.0 / 30.0, rel_tol=1e-12)


def test_forward_yield_flat_and_linear_in_yield_agree_at_pillars():
    curve = _flat_curve(0.0)
    times = [0.5, 1.0, 2.5]
    yields = [0.01, 0.03, 0.02]
    fyf = EquityForwardCurve(100.0, curve, times, yields)
    liy = EquityForwardCurve(
        100.0,
        curve,
        times,
        yields,
        interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD,
    )
    for t in times:
        assert math.isclose(fyf.dividend_yield(t), liy.dividend_yield(t), rel_tol=1e-12)


def test_forward_yield_flat_and_linear_in_yield_differ_between_pillars():
    curve = _flat_curve(0.0)
    fyf = EquityForwardCurve(100.0, curve, [1.0, 2.0], [0.02, 0.04])
    liy = EquityForwardCurve(
        100.0,
        curve,
        [1.0, 2.0],
        [0.02, 0.04],
        interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD,
    )
    assert not math.isclose(fyf.dividend_yield(1.5), liy.dividend_yield(1.5), rel_tol=1e-6)


def test_dividend_yield_flat_extrapolation_outside_grid():
    curve = _flat_curve(0.0)
    fwd = EquityForwardCurve(100.0, curve, [1.0, 2.0], [0.02, 0.04])
    assert math.isclose(fwd.dividend_yield(0.01), 0.02, rel_tol=1e-12)
    assert math.isclose(fwd.dividend_yield(10.0), 0.04, rel_tol=1e-12)


def test_term_structured_yield_changes_forward():
    spot = 100.0
    curve = _flat_curve(0.04)
    flat = EquityForwardCurve.flat(spot, curve, 0.02)
    sloped = EquityForwardCurve(spot, curve, [0.5, 5.0], [0.01, 0.05])
    expiry = _REF + timedelta(days=365)
    assert not math.isclose(sloped.at_date(expiry), flat.at_date(expiry), rel_tol=1e-6)


def test_duck_types_as_forward_callable():
    """EquityForwardCurve must be usable wherever EquityForward is."""
    spot = 100.0
    curve = _flat_curve(0.04)
    fwd_curve = EquityForwardCurve.flat(spot, curve, 0.02)

    def consume(forward_callable, t: float) -> float:
        return forward_callable(t)

    assert math.isclose(consume(fwd_curve, 1.0), fwd_curve.at_time(1.0), rel_tol=0.0)


def test_rejects_non_positive_spot():
    curve = _flat_curve(0.03)
    with pytest.raises(ValueError):
        EquityForwardCurve(0.0, curve, [1.0], [0.01])
    with pytest.raises(ValueError):
        EquityForwardCurve(-1.0, curve, [1.0], [0.01])


def test_rejects_empty_pillar_grid():
    curve = _flat_curve(0.03)
    with pytest.raises(ValueError):
        EquityForwardCurve(100.0, curve, [], [])


def test_rejects_length_mismatch():
    curve = _flat_curve(0.03)
    with pytest.raises(ValueError):
        EquityForwardCurve(100.0, curve, [1.0, 2.0], [0.01])


def test_rejects_non_positive_pillar_time():
    curve = _flat_curve(0.03)
    with pytest.raises(ValueError):
        EquityForwardCurve(100.0, curve, [0.0, 1.0], [0.01, 0.02])
    with pytest.raises(ValueError):
        EquityForwardCurve(100.0, curve, [-0.1, 1.0], [0.01, 0.02])


def test_rejects_non_monotone_pillars():
    curve = _flat_curve(0.03)
    with pytest.raises(ValueError):
        EquityForwardCurve(100.0, curve, [1.0, 1.0], [0.01, 0.02])
    with pytest.raises(ValueError):
        EquityForwardCurve(100.0, curve, [2.0, 1.0], [0.01, 0.02])


def test_at_date_rejects_past_expiry():
    curve = _flat_curve(0.03)
    fwd = EquityForwardCurve.flat(100.0, curve, 0.0)
    with pytest.raises(ValueError):
        fwd.at_date(_REF)
    with pytest.raises(ValueError):
        fwd.at_date(_REF - timedelta(days=1))


def test_at_time_rejects_non_positive_T():
    curve = _flat_curve(0.03)
    fwd = EquityForwardCurve.flat(100.0, curve, 0.0)
    with pytest.raises(ValueError):
        fwd.at_time(0.0)
    with pytest.raises(ValueError):
        fwd.at_time(-0.5)


def test_dividend_yield_rejects_non_positive_T():
    curve = _flat_curve(0.03)
    fwd = EquityForwardCurve.flat(100.0, curve, 0.02)
    with pytest.raises(ValueError):
        fwd.dividend_yield(0.0)
    with pytest.raises(ValueError):
        fwd.dividend_yield(-1.0)
