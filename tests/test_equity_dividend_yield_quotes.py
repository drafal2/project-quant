"""Tests for market_structures.equity.quotes.DividendYieldQuote and
EquityForwardCurve.from_dividend_yield_quotes.
"""

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


# DividendYieldQuote


def test_quote_stores_maturity_and_yield():
    quote = DividendYieldQuote(maturity_date=date(2027, 1, 1), continuous_yield=0.025)
    assert quote.maturity_date == date(2027, 1, 1)
    assert quote.continuous_yield == 0.025


def test_quote_is_frozen():
    quote = DividendYieldQuote(maturity_date=date(2027, 1, 1), continuous_yield=0.02)
    with pytest.raises(Exception):
        quote.continuous_yield = 0.03  # type: ignore[misc]


def test_quote_accepts_negative_yield():
    """Hard-to-borrow names can produce negative implied dividend yields."""
    quote = DividendYieldQuote(maturity_date=date(2027, 1, 1), continuous_yield=-0.03)
    assert quote.continuous_yield == -0.03


def test_quote_rejects_non_finite_yield():
    with pytest.raises(ValueError):
        DividendYieldQuote(maturity_date=date(2027, 1, 1), continuous_yield=float("nan"))
    with pytest.raises(ValueError):
        DividendYieldQuote(maturity_date=date(2027, 1, 1), continuous_yield=float("inf"))


# from_dividend_yield_quotes


def test_flat_quote_list_reproduces_equity_forward():
    """A constant-yield quote list must match EquityForward exactly at every expiry."""
    spot = 100.0
    curve = _flat_curve(0.04)
    q = 0.02
    quotes = [
        DividendYieldQuote(_REF + timedelta(days=180), q),
        DividendYieldQuote(_REF + timedelta(days=365), q),
        DividendYieldQuote(_REF + timedelta(days=1825), q),
    ]
    fwd_curve = EquityForwardCurve.from_dividend_yield_quotes(spot, curve, quotes)
    legacy = EquityForward(spot, curve, q)
    for days in (30, 180, 365, 730, 1825):
        expiry = _REF + timedelta(days=days)
        assert math.isclose(
            fwd_curve.at_date(expiry), legacy.at_date(expiry), rel_tol=1e-12
        )


def test_quotes_sorted_by_maturity():
    curve = _flat_curve(0.04)
    quotes_unsorted = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.03),
        DividendYieldQuote(_REF + timedelta(days=90), 0.01),
        DividendYieldQuote(_REF + timedelta(days=730), 0.04),
    ]
    fwd_curve = EquityForwardCurve.from_dividend_yield_quotes(100.0, curve, quotes_unsorted)
    assert list(fwd_curve.pillar_times) == sorted(fwd_curve.pillar_times)
    assert fwd_curve.pillar_yields[0] == 0.01
    assert fwd_curve.pillar_yields[-1] == 0.04


def test_pillar_yields_recovered_exactly_at_each_quote():
    """At each quote's pillar time, dividend_yield must return the quoted value."""
    curve = _flat_curve(0.04)
    quotes = [
        DividendYieldQuote(_REF + timedelta(days=180), 0.01),
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=1825), 0.035),
    ]
    fwd_curve = EquityForwardCurve.from_dividend_yield_quotes(100.0, curve, quotes)
    for t, q in zip(fwd_curve.pillar_times, fwd_curve.pillar_yields):
        assert math.isclose(fwd_curve.dividend_yield(t), q, rel_tol=1e-12)


def test_forward_yield_flat_default_gives_piecewise_linear_cumulative_yield():
    """Under FORWARD_YIELD_FLAT, Q(T) = q(T)*T is piecewise linear in T."""
    curve = _flat_curve(0.0)
    quotes = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=730), 0.04),
    ]
    fwd_curve = EquityForwardCurve.from_dividend_yield_quotes(100.0, curve, quotes)
    # Pillars at T~=1.0 and T~=2.0. Halfway between, cumulative yield should
    # be midway between the pillar cumulative yields.
    t_mid = 0.5 * (fwd_curve.pillar_times[0] + fwd_curve.pillar_times[1])
    cum_mid = fwd_curve.dividend_yield(t_mid) * t_mid
    cum_lo = fwd_curve.pillar_times[0] * fwd_curve.pillar_yields[0]
    cum_hi = fwd_curve.pillar_times[1] * fwd_curve.pillar_yields[1]
    assert math.isclose(cum_mid, 0.5 * (cum_lo + cum_hi), rel_tol=1e-12)


def test_pillar_bump_only_affects_forwards_past_that_pillar():
    """Shifting the second pillar's yield must not move F(T) for T <= first pillar."""
    spot = 100.0
    curve = _flat_curve(0.04)
    base = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=1825), 0.03),
    ]
    bumped = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=1825), 0.05),  # bumped
    ]
    fwd_base = EquityForwardCurve.from_dividend_yield_quotes(spot, curve, base)
    fwd_bump = EquityForwardCurve.from_dividend_yield_quotes(spot, curve, bumped)

    short = _REF + timedelta(days=180)
    pillar1 = _REF + timedelta(days=365)
    long = _REF + timedelta(days=1825)

    assert math.isclose(fwd_base.at_date(short), fwd_bump.at_date(short), rel_tol=1e-12)
    assert math.isclose(fwd_base.at_date(pillar1), fwd_bump.at_date(pillar1), rel_tol=1e-12)
    assert not math.isclose(fwd_base.at_date(long), fwd_bump.at_date(long), rel_tol=1e-6)


def test_linear_in_yield_mode_propagates_through_classmethod():
    """Passing interpolation=LINEAR_IN_YIELD must change the inter-pillar values."""
    curve = _flat_curve(0.0)
    quotes = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=730), 0.04),
    ]
    fyf = EquityForwardCurve.from_dividend_yield_quotes(100.0, curve, quotes)
    liy = EquityForwardCurve.from_dividend_yield_quotes(
        100.0,
        curve,
        quotes,
        interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD,
    )
    t_mid = 0.5 * (fyf.pillar_times[0] + fyf.pillar_times[1])
    assert not math.isclose(fyf.dividend_yield(t_mid), liy.dividend_yield(t_mid), rel_tol=1e-6)


def test_rejects_empty_quote_list():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_yield_quotes(100.0, curve, [])


def test_rejects_quote_on_reference_date():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_yield_quotes(
            100.0,
            curve,
            [DividendYieldQuote(_REF, 0.02)],
        )


def test_rejects_quote_before_reference_date():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_yield_quotes(
            100.0,
            curve,
            [DividendYieldQuote(_REF - timedelta(days=1), 0.02)],
        )


def test_rejects_duplicate_maturities():
    curve = _flat_curve(0.04)
    quotes = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=365), 0.03),
    ]
    with pytest.raises(ValueError):
        EquityForwardCurve.from_dividend_yield_quotes(100.0, curve, quotes)
