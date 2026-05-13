"""Tests for market_structures.volatility.interpolated."""

import math
import warnings
from datetime import date, timedelta

import pytest

from market_conventions import DayCountConvention
from market_structures.rates.curve import ZeroCurve
from market_structures.volatility.forward import EquityForward
from market_structures.volatility.interpolated import InterpolatedVolSurface
from market_structures.volatility.pricing import black_scholes_price


_REF = date(2026, 1, 1)
_SPOT = 100.0
_R = 0.03
_Q = 0.01


def _curve() -> ZeroCurve:
    pillars = [_REF + timedelta(days=d) for d in (30, 180, 365, 730, 1825)]
    return ZeroCurve(
        reference_date=_REF,
        pillar_dates=pillars,
        rates=[_R] * len(pillars),
        day_count_convention=DayCountConvention.ACT_365_FIXED,
    )


def _expiries_and_strikes():
    expiries = [_REF + timedelta(days=d) for d in (90, 365, 730)]
    strikes = [
        [80.0, 90.0, 100.0, 110.0, 120.0],
        [70.0, 90.0, 100.0, 110.0, 130.0],
        [60.0, 90.0, 100.0, 110.0, 140.0],
    ]
    return expiries, strikes


def test_init_rejects_empty_expiries():
    with pytest.raises(ValueError):
        InterpolatedVolSurface(
            reference_date=_REF,
            forward=lambda t: 100.0,
            expiries=[],
            log_moneynesses=[],
            total_variances=[],
        )


def test_init_rejects_non_monotone_expiries():
    with pytest.raises(ValueError):
        InterpolatedVolSurface(
            reference_date=_REF,
            forward=lambda t: 100.0,
            expiries=[1.0, 0.5],
            log_moneynesses=[[-0.1, 0.1], [-0.1, 0.1]],
            total_variances=[[0.04, 0.04], [0.04, 0.04]],
        )


def test_init_rejects_non_monotone_k_log():
    with pytest.raises(ValueError):
        InterpolatedVolSurface(
            reference_date=_REF,
            forward=lambda t: 100.0,
            expiries=[1.0],
            log_moneynesses=[[0.1, -0.1]],
            total_variances=[[0.04, 0.04]],
        )


def test_init_rejects_non_positive_variance():
    with pytest.raises(ValueError):
        InterpolatedVolSurface(
            reference_date=_REF,
            forward=lambda t: 100.0,
            expiries=[1.0],
            log_moneynesses=[[-0.1, 0.1]],
            total_variances=[[0.04, -0.01]],
        )


def test_flat_vol_grid_returns_constant_vol_everywhere():
    curve = _curve()
    expiries, strikes = _expiries_and_strikes()
    flat_sigma = 0.2
    vols = [[flat_sigma] * len(ks) for ks in strikes]
    surface = InterpolatedVolSurface.from_implied_vols(
        reference_date=_REF,
        spot=_SPOT,
        dividend_yield=_Q,
        zero_curve=curve,
        expiries=expiries,
        strikes=strikes,
        implied_vols=vols,
    )
    for t in (0.1, 0.5, 1.0, 1.5, 1.99):
        for k_over_f in (0.7, 0.9, 1.0, 1.1, 1.5):
            fwd = surface.forward(t)
            sigma = surface.implied_vol(t, fwd * k_over_f)
            assert math.isclose(sigma, flat_sigma, abs_tol=1e-10)


def test_from_implied_vols_recovers_inputs_at_nodes():
    curve = _curve()
    expiries, strikes = _expiries_and_strikes()
    vols = [
        [0.25, 0.22, 0.20, 0.22, 0.25],
        [0.24, 0.21, 0.19, 0.21, 0.24],
        [0.23, 0.20, 0.18, 0.20, 0.23],
    ]
    surface = InterpolatedVolSurface.from_implied_vols(
        reference_date=_REF,
        spot=_SPOT,
        dividend_yield=_Q,
        zero_curve=curve,
        expiries=expiries,
        strikes=strikes,
        implied_vols=vols,
    )
    for slice_idx, expiry in enumerate(expiries):
        t = (expiry - _REF).days / 365.0
        for k, expected_vol in zip(strikes[slice_idx], vols[slice_idx]):
            recovered = surface.implied_vol(t, k)
            assert math.isclose(recovered, expected_vol, abs_tol=1e-10)


def test_from_option_prices_inverts_synthetic_grid():
    curve = _curve()
    expiries, strikes = _expiries_and_strikes()
    target_vols = [
        [0.25, 0.22, 0.20, 0.22, 0.25],
        [0.24, 0.21, 0.19, 0.21, 0.24],
        [0.23, 0.20, 0.18, 0.20, 0.23],
    ]
    equity_fwd = EquityForward(_SPOT, curve, _Q)
    prices, types = [], []
    for slice_idx, expiry in enumerate(expiries):
        t = (expiry - _REF).days / 365.0
        f = equity_fwd.at_date(expiry)
        df = curve.discount_factor(expiry)
        slice_prices, slice_types = [], []
        for k, v in zip(strikes[slice_idx], target_vols[slice_idx]):
            ot = "C" if k >= f else "P"
            slice_prices.append(black_scholes_price(f, k, t, v, df, ot))
            slice_types.append(ot)
        prices.append(slice_prices)
        types.append(slice_types)

    surface = InterpolatedVolSurface.from_option_prices(
        reference_date=_REF,
        spot=_SPOT,
        dividend_yield=_Q,
        zero_curve=curve,
        expiries=expiries,
        strikes=strikes,
        prices=prices,
        option_types=types,
    )

    for slice_idx, expiry in enumerate(expiries):
        t = (expiry - _REF).days / 365.0
        for k, expected_vol in zip(strikes[slice_idx], target_vols[slice_idx]):
            recovered = surface.implied_vol(t, k)
            assert math.isclose(recovered, expected_vol, abs_tol=1e-7)


def test_time_clamping_outside_range():
    curve = _curve()
    expiries, strikes = _expiries_and_strikes()
    vols = [[0.2] * 5 for _ in range(3)]
    surface = InterpolatedVolSurface.from_implied_vols(
        reference_date=_REF,
        spot=_SPOT,
        dividend_yield=_Q,
        zero_curve=curve,
        expiries=expiries,
        strikes=strikes,
        implied_vols=vols,
    )
    f_short = surface.forward(0.01)
    sigma_short = surface.implied_vol(0.01, f_short)
    f_long = surface.forward(10.0)
    sigma_long = surface.implied_vol(10.0, f_long)
    assert math.isclose(sigma_short, 0.2, abs_tol=1e-10)
    assert math.isclose(sigma_long, 0.2, abs_tol=1e-10)


def test_from_option_prices_warns_and_skips_arb_violators():
    curve = _curve()
    expiries, strikes = _expiries_and_strikes()
    equity_fwd = EquityForward(_SPOT, curve, _Q)
    prices, types = [], []
    for slice_idx, expiry in enumerate(expiries):
        t = (expiry - _REF).days / 365.0
        f = equity_fwd.at_date(expiry)
        df = curve.discount_factor(expiry)
        slice_prices, slice_types = [], []
        for k in strikes[slice_idx]:
            ot = "C" if k >= f else "P"
            slice_prices.append(black_scholes_price(f, k, t, 0.2, df, ot))
            slice_types.append(ot)
        prices.append(slice_prices)
        types.append(slice_types)
    # Poison the middle slice's middle quote with an above-upper-bound price.
    bad_slice = 1
    bad_idx = 2
    f_bad = equity_fwd.at_date(expiries[bad_slice])
    df_bad = curve.discount_factor(expiries[bad_slice])
    prices[bad_slice][bad_idx] = df_bad * f_bad * 1.5  # above upper call bound

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        surface = InterpolatedVolSurface.from_option_prices(
            reference_date=_REF,
            spot=_SPOT,
            dividend_yield=_Q,
            zero_curve=curve,
            expiries=expiries,
            strikes=strikes,
            prices=prices,
            option_types=types,
        )
    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert any("outside no-arb bounds" in str(w.message) for w in user_warnings)
    # Remaining quotes on the affected slice still recover their input vol.
    for k_idx, k in enumerate(strikes[bad_slice]):
        if k_idx == bad_idx:
            continue
        t = (expiries[bad_slice] - _REF).days / 365.0
        recovered = surface.implied_vol(t, k)
        assert math.isclose(recovered, 0.2, abs_tol=1e-7)


def test_reference_date_mismatch_raises():
    curve = _curve()
    expiries, strikes = _expiries_and_strikes()
    vols = [[0.2] * 5 for _ in range(3)]
    other_ref = _REF + timedelta(days=1)
    with pytest.raises(ValueError):
        InterpolatedVolSurface.from_implied_vols(
            reference_date=other_ref,
            spot=_SPOT,
            dividend_yield=_Q,
            zero_curve=curve,
            expiries=expiries,
            strikes=strikes,
            implied_vols=vols,
        )


def test_calendar_arbitrage_warning_emitted():
    # Construct a grid where total variance decreases in T (vol drops too fast).
    expiries_dt = [_REF + timedelta(days=d) for d in (180, 365)]
    strikes = [[90.0, 100.0, 110.0], [90.0, 100.0, 110.0]]
    # T1 ~ 0.493y at sigma 0.5 -> w ~ 0.123; T2 = 1.0y at sigma 0.2 -> w ~ 0.04 (decreasing).
    vols = [[0.5, 0.5, 0.5], [0.2, 0.2, 0.2]]
    curve = _curve()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        InterpolatedVolSurface.from_implied_vols(
            reference_date=_REF,
            spot=_SPOT,
            dividend_yield=_Q,
            zero_curve=curve,
            expiries=expiries_dt,
            strikes=strikes,
            implied_vols=vols,
        )
    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert any("Calendar arbitrage" in str(w.message) for w in user_warnings)


def test_expiries_property_returns_copy():
    curve = _curve()
    expiries_dt, strikes = _expiries_and_strikes()
    vols = [[0.2] * 5 for _ in range(3)]
    surface = InterpolatedVolSurface.from_implied_vols(
        reference_date=_REF,
        spot=_SPOT,
        dividend_yield=_Q,
        zero_curve=curve,
        expiries=expiries_dt,
        strikes=strikes,
        implied_vols=vols,
    )
    ts_a = surface.expiries
    ts_a.append(99.0)
    ts_b = surface.expiries
    assert 99.0 not in ts_b
