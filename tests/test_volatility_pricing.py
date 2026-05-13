"""Tests for market_structures.volatility.pricing."""

import math

import pytest

from market_structures.volatility.pricing import (
    black_scholes_price,
    black_scholes_vega,
    implied_vol_from_price,
    no_arb_price_bounds,
)


_F = 100.0
_T = 1.0
_DF = math.exp(-0.03 * _T)


@pytest.mark.parametrize("strike", [50.0, 80.0, 100.0, 120.0, 200.0])
@pytest.mark.parametrize("sigma", [0.05, 0.2, 0.6])
def test_put_call_parity(strike, sigma):
    call = black_scholes_price(_F, strike, _T, sigma, _DF, "C")
    put = black_scholes_price(_F, strike, _T, sigma, _DF, "P")
    parity_residual = call - put - _DF * (_F - strike)
    assert abs(parity_residual) < 1e-12


def test_zero_sigma_returns_discounted_intrinsic():
    itm_call = black_scholes_price(_F, 80.0, _T, 0.0, _DF, "C")
    assert math.isclose(itm_call, _DF * 20.0, rel_tol=1e-12)
    otm_call = black_scholes_price(_F, 120.0, _T, 0.0, _DF, "C")
    assert otm_call == 0.0
    itm_put = black_scholes_price(_F, 120.0, _T, 0.0, _DF, "P")
    assert math.isclose(itm_put, _DF * 20.0, rel_tol=1e-12)
    otm_put = black_scholes_price(_F, 80.0, _T, 0.0, _DF, "P")
    assert otm_put == 0.0


def test_atm_call_value_matches_closed_form():
    # ATM call (F = K) reduces to df * F * (2 N(sigma sqrt(T) / 2) - 1).
    sigma = 0.2
    expected = _DF * _F * (2.0 * 0.5398278372770290 - 1.0)  # N(0.1)
    got = black_scholes_price(_F, _F, _T, sigma, _DF, "C")
    assert math.isclose(got, expected, rel_tol=1e-10)


@pytest.mark.parametrize("strike", [60.0, 100.0, 150.0])
@pytest.mark.parametrize("sigma", [0.1, 0.3, 0.8])
def test_vega_non_negative_and_same_for_call_put(strike, sigma):
    vega = black_scholes_vega(_F, strike, _T, sigma, _DF)
    assert vega >= 0.0
    # Numerical derivative against the price (call vs put should agree).
    bump = 1e-6
    call_plus = black_scholes_price(_F, strike, _T, sigma + bump, _DF, "C")
    call_minus = black_scholes_price(_F, strike, _T, sigma - bump, _DF, "C")
    put_plus = black_scholes_price(_F, strike, _T, sigma + bump, _DF, "P")
    put_minus = black_scholes_price(_F, strike, _T, sigma - bump, _DF, "P")
    fd_call = (call_plus - call_minus) / (2.0 * bump)
    fd_put = (put_plus - put_minus) / (2.0 * bump)
    assert math.isclose(fd_call, vega, rel_tol=1e-4)
    assert math.isclose(fd_put, vega, rel_tol=1e-4)


def test_no_arb_bounds_call():
    lower, upper = no_arb_price_bounds(_F, 80.0, _DF, "C")
    assert math.isclose(lower, _DF * 20.0, rel_tol=1e-12)
    assert math.isclose(upper, _DF * _F, rel_tol=1e-12)


def test_no_arb_bounds_put():
    lower, upper = no_arb_price_bounds(_F, 120.0, _DF, "P")
    assert math.isclose(lower, _DF * 20.0, rel_tol=1e-12)
    assert math.isclose(upper, _DF * 120.0, rel_tol=1e-12)


@pytest.mark.parametrize("sigma", [0.05, 0.15, 0.5, 1.0])
@pytest.mark.parametrize("expiry", [0.05, 0.5, 5.0])
@pytest.mark.parametrize("k_over_f", [0.5, 0.8, 1.0, 1.2, 2.0])
@pytest.mark.parametrize("option_type", ["C", "P"])
def test_inversion_round_trip(sigma, expiry, k_over_f, option_type):
    # In deep ITM/OTM regions where |d1| is large, the option price collapses
    # to intrinsic (or zero) at machine precision and the implied vol is not
    # identifiable from the price. Skip those degenerate corners.
    d_magnitude = abs(math.log(k_over_f)) / (sigma * math.sqrt(expiry))
    if d_magnitude > 6.0:
        pytest.skip("vol not identifiable from price in this region")
    strike = _F * k_over_f
    df = math.exp(-0.03 * expiry)
    price = black_scholes_price(_F, strike, expiry, sigma, df, option_type)
    sigma_recovered = implied_vol_from_price(
        price=price,
        forward=_F,
        strike=strike,
        time_to_expiry=expiry,
        df_funding=df,
        option_type=option_type,
        tolerance=1e-10,
    )
    assert math.isclose(sigma_recovered, sigma, abs_tol=1e-6)


def test_inversion_rejects_price_above_upper_bound():
    _, upper = no_arb_price_bounds(_F, 100.0, _DF, "C")
    with pytest.raises(ValueError):
        implied_vol_from_price(upper * 1.01, _F, 100.0, _T, _DF, "C")


def test_inversion_rejects_price_below_lower_bound():
    lower, _ = no_arb_price_bounds(_F, 80.0, _DF, "C")
    with pytest.raises(ValueError):
        implied_vol_from_price(max(lower * 0.99, -1.0), _F, 80.0, _T, _DF, "C")


def test_price_rejects_bad_inputs():
    with pytest.raises(ValueError):
        black_scholes_price(0.0, 100.0, _T, 0.2, _DF, "C")
    with pytest.raises(ValueError):
        black_scholes_price(_F, 100.0, 0.0, 0.2, _DF, "C")
    with pytest.raises(ValueError):
        black_scholes_price(_F, 100.0, _T, -0.1, _DF, "C")
    with pytest.raises(ValueError):
        black_scholes_price(_F, 100.0, _T, 0.2, _DF, "X")
