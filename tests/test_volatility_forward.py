"""Tests for market_structures.volatility.forward."""

import math
from datetime import date, timedelta

import pytest

from market_conventions import DayCountConvention
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


def test_at_date_matches_formula():
    spot = 100.0
    r = 0.05
    q = 0.02
    curve = _flat_curve(r)
    fwd = EquityForward(spot, curve, q)
    expiry = _REF + timedelta(days=365)
    t = 365.0 / 365.0
    expected = spot * math.exp((r - q) * t)
    assert math.isclose(fwd.at_date(expiry), expected, rel_tol=1e-10)


def test_at_time_matches_at_date_for_grid_dates():
    spot = 100.0
    curve = _flat_curve(0.04)
    fwd = EquityForward(spot, curve, 0.01)
    for days in (30, 180, 365, 730):
        expiry = _REF + timedelta(days=days)
        t = days / 365.0
        assert math.isclose(fwd.at_date(expiry), fwd.at_time(t), rel_tol=1e-12)


def test_call_dispatches_on_type():
    spot = 100.0
    curve = _flat_curve(0.03)
    fwd = EquityForward(spot, curve, 0.0)
    expiry = _REF + timedelta(days=365)
    assert math.isclose(fwd(expiry), fwd.at_date(expiry), rel_tol=1e-12)
    assert math.isclose(fwd(1.0), fwd.at_time(1.0), rel_tol=1e-12)


def test_zero_dividend_collapses_to_no_carry_forward():
    spot = 100.0
    curve = _flat_curve(0.0)
    fwd = EquityForward(spot, curve, 0.0)
    expiry = _REF + timedelta(days=365)
    assert math.isclose(fwd.at_date(expiry), spot, rel_tol=1e-12)


def test_reference_date_propagates_from_curve():
    curve = _flat_curve(0.03)
    fwd = EquityForward(100.0, curve, 0.01)
    assert fwd.reference_date == _REF


def test_rejects_non_positive_spot():
    curve = _flat_curve(0.03)
    with pytest.raises(ValueError):
        EquityForward(0.0, curve, 0.01)
    with pytest.raises(ValueError):
        EquityForward(-1.0, curve, 0.01)


def test_at_date_rejects_past_expiry():
    curve = _flat_curve(0.03)
    fwd = EquityForward(100.0, curve, 0.0)
    with pytest.raises(ValueError):
        fwd.at_date(_REF)
    with pytest.raises(ValueError):
        fwd.at_date(_REF - timedelta(days=1))


def test_at_time_rejects_non_positive_T():
    curve = _flat_curve(0.03)
    fwd = EquityForward(100.0, curve, 0.0)
    with pytest.raises(ValueError):
        fwd.at_time(0.0)
    with pytest.raises(ValueError):
        fwd.at_time(-0.5)
