"""Tests for market_structures.equity.bootstrapper.EquityForwardCurveBootstrapper
and market_structures.equity.quotes.ForwardQuote.
"""

import math
from datetime import date, timedelta

import pytest

from market_conventions import DayCountConvention
from market_structures.equity import (
    DividendYieldInterpolation,
    DividendYieldQuote,
    EquityForwardCurve,
    EquityForwardCurveBootstrapper,
    ForwardQuote,
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


# ForwardQuote validation


def test_forward_quote_stores_fields():
    q = ForwardQuote(maturity_date=date(2027, 1, 1), forward_price=105.0)
    assert q.maturity_date == date(2027, 1, 1)
    assert q.forward_price == 105.0


def test_forward_quote_is_frozen():
    q = ForwardQuote(maturity_date=date(2027, 1, 1), forward_price=105.0)
    with pytest.raises(Exception):
        q.forward_price = 110.0  # type: ignore[misc]


def test_forward_quote_rejects_non_positive_price():
    with pytest.raises(ValueError):
        ForwardQuote(maturity_date=date(2027, 1, 1), forward_price=0.0)
    with pytest.raises(ValueError):
        ForwardQuote(maturity_date=date(2027, 1, 1), forward_price=-1.0)


def test_forward_quote_rejects_non_finite_price():
    with pytest.raises(ValueError):
        ForwardQuote(maturity_date=date(2027, 1, 1), forward_price=float("nan"))
    with pytest.raises(ValueError):
        ForwardQuote(maturity_date=date(2027, 1, 1), forward_price=float("inf"))


# Bootstrapper construction


def test_bootstrapper_rejects_non_positive_spot():
    curve = _flat_curve(0.04)
    with pytest.raises(ValueError):
        EquityForwardCurveBootstrapper(0.0, curve)
    with pytest.raises(ValueError):
        EquityForwardCurveBootstrapper(-1.0, curve)


# Round-trip: ForwardQuote -> bootstrap -> at_date recovers F


def test_single_forward_quote_round_trip():
    spot = 100.0
    curve = _flat_curve(0.04)
    expiry = _REF + timedelta(days=365)
    f_market = 102.0
    bs = EquityForwardCurveBootstrapper(spot, curve)
    fwd = bs.bootstrap([ForwardQuote(expiry, f_market)])
    assert math.isclose(fwd.at_date(expiry), f_market, rel_tol=1e-12)


def test_multiple_forward_quotes_round_trip():
    spot = 100.0
    curve = _flat_curve(0.04)
    quotes = [
        ForwardQuote(_REF + timedelta(days=90), 100.5),
        ForwardQuote(_REF + timedelta(days=180), 101.2),
        ForwardQuote(_REF + timedelta(days=365), 102.4),
        ForwardQuote(_REF + timedelta(days=730), 105.0),
    ]
    bs = EquityForwardCurveBootstrapper(spot, curve)
    fwd = bs.bootstrap(quotes)
    for quote in quotes:
        assert math.isclose(
            fwd.at_date(quote.maturity_date), quote.forward_price, rel_tol=1e-12
        )


def test_unsorted_input_is_handled():
    spot = 100.0
    curve = _flat_curve(0.04)
    bs = EquityForwardCurveBootstrapper(spot, curve)
    quotes_unsorted = [
        ForwardQuote(_REF + timedelta(days=365), 103.0),
        ForwardQuote(_REF + timedelta(days=90), 100.5),
        ForwardQuote(_REF + timedelta(days=730), 106.0),
    ]
    fwd = bs.bootstrap(quotes_unsorted)
    for quote in quotes_unsorted:
        assert math.isclose(
            fwd.at_date(quote.maturity_date), quote.forward_price, rel_tol=1e-12
        )
    assert list(fwd.pillar_times) == sorted(fwd.pillar_times)


# Round-trip via a known curve


def test_bootstrap_recovers_original_curve_yields():
    """Build a curve, sample its forwards at the pillars, bootstrap from those
    samples, and verify the recovered yields match the original to ~1e-12."""
    spot = 100.0
    curve = _flat_curve(0.04)
    original = EquityForwardCurve.from_dividend_yield_quotes(
        spot,
        curve,
        [
            DividendYieldQuote(_REF + timedelta(days=180), 0.01),
            DividendYieldQuote(_REF + timedelta(days=365), 0.02),
            DividendYieldQuote(_REF + timedelta(days=1825), 0.035),
        ],
    )
    sampled = [
        ForwardQuote(_REF + timedelta(days=180), original.at_date(_REF + timedelta(days=180))),
        ForwardQuote(_REF + timedelta(days=365), original.at_date(_REF + timedelta(days=365))),
        ForwardQuote(_REF + timedelta(days=1825), original.at_date(_REF + timedelta(days=1825))),
    ]
    bs = EquityForwardCurveBootstrapper(spot, curve)
    recovered = bs.bootstrap(sampled)
    for t_orig, q_orig, t_rec, q_rec in zip(
        original.pillar_times,
        original.pillar_yields,
        recovered.pillar_times,
        recovered.pillar_yields,
    ):
        assert math.isclose(t_orig, t_rec, rel_tol=1e-12)
        assert math.isclose(q_orig, q_rec, rel_tol=1e-12)


# Mixed input


def test_mixed_forward_and_dividend_yield_quotes():
    spot = 100.0
    curve = _flat_curve(0.04)
    fwd_quote = ForwardQuote(_REF + timedelta(days=365), 102.0)
    div_quote = DividendYieldQuote(_REF + timedelta(days=730), 0.015)
    bs = EquityForwardCurveBootstrapper(spot, curve)
    fwd = bs.bootstrap([fwd_quote, div_quote])
    # Forward quote pillar must reprice exactly.
    assert math.isclose(fwd.at_date(fwd_quote.maturity_date), fwd_quote.forward_price, rel_tol=1e-12)
    # Dividend yield quote pillar must store the quoted q.
    t_div = (div_quote.maturity_date - _REF).days / 365.0
    assert math.isclose(fwd.dividend_yield(t_div), div_quote.continuous_yield, rel_tol=1e-12)


# Validation


def test_bootstrap_rejects_empty_list():
    bs = EquityForwardCurveBootstrapper(100.0, _flat_curve(0.04))
    with pytest.raises(ValueError):
        bs.bootstrap([])


def test_bootstrap_rejects_quote_on_or_before_reference_date():
    bs = EquityForwardCurveBootstrapper(100.0, _flat_curve(0.04))
    with pytest.raises(ValueError):
        bs.bootstrap([ForwardQuote(_REF, 100.0)])
    with pytest.raises(ValueError):
        bs.bootstrap([ForwardQuote(_REF - timedelta(days=1), 100.0)])


def test_bootstrap_rejects_duplicate_maturities_same_type():
    bs = EquityForwardCurveBootstrapper(100.0, _flat_curve(0.04))
    with pytest.raises(ValueError):
        bs.bootstrap([
            ForwardQuote(_REF + timedelta(days=365), 101.0),
            ForwardQuote(_REF + timedelta(days=365), 102.0),
        ])


def test_bootstrap_rejects_duplicate_maturities_cross_type():
    bs = EquityForwardCurveBootstrapper(100.0, _flat_curve(0.04))
    with pytest.raises(ValueError):
        bs.bootstrap([
            ForwardQuote(_REF + timedelta(days=365), 101.0),
            DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        ])


def test_bootstrap_propagates_interpolation_choice():
    spot = 100.0
    curve = _flat_curve(0.0)
    quotes = [
        DividendYieldQuote(_REF + timedelta(days=365), 0.02),
        DividendYieldQuote(_REF + timedelta(days=730), 0.04),
    ]
    bs = EquityForwardCurveBootstrapper(spot, curve)
    fyf = bs.bootstrap(quotes)
    liy = bs.bootstrap(quotes, interpolation=DividendYieldInterpolation.LINEAR_IN_YIELD)
    t_mid = 0.5 * (fyf.pillar_times[0] + fyf.pillar_times[1])
    assert not math.isclose(fyf.dividend_yield(t_mid), liy.dividend_yield(t_mid), rel_tol=1e-6)


def test_bootstrapped_curve_is_forward_callable():
    """Sanity: bootstrap output duck-types as the volatility ForwardCallable."""
    spot = 100.0
    curve = _flat_curve(0.04)
    bs = EquityForwardCurveBootstrapper(spot, curve)
    fwd = bs.bootstrap([ForwardQuote(_REF + timedelta(days=365), 102.0)])
    # Both float and date dispatch must work.
    assert math.isclose(fwd(_REF + timedelta(days=365)), 102.0, rel_tol=1e-12)
    assert isinstance(fwd(1.0), float)
