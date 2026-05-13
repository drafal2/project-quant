"""Tests for market_structures.volatility.coordinates."""

import math

import pytest

from market_structures.volatility.coordinates import (
    delta_to_strike,
    log_moneyness_to_strike,
    strike_to_delta,
    strike_to_log_moneyness,
)


_FORWARD = 100.0
_T = 1.0
_DF = 0.95
_SIGMA = 0.2


@pytest.mark.parametrize("k_over_f", [0.5, 0.8, 1.0, 1.2, 2.0])
def test_strike_log_moneyness_round_trip(k_over_f):
    strike = _FORWARD * k_over_f
    k_log = strike_to_log_moneyness(strike, _FORWARD)
    recovered = log_moneyness_to_strike(k_log, _FORWARD)
    assert math.isclose(recovered, strike, rel_tol=1e-12)


def test_strike_to_log_moneyness_atm_zero():
    assert strike_to_log_moneyness(_FORWARD, _FORWARD) == 0.0


def test_strike_to_log_moneyness_rejects_non_positive():
    with pytest.raises(ValueError):
        strike_to_log_moneyness(0.0, _FORWARD)
    with pytest.raises(ValueError):
        strike_to_log_moneyness(_FORWARD, 0.0)


def test_call_delta_positive_in_admissible_range():
    delta = strike_to_delta(_FORWARD, _FORWARD, _T, _SIGMA, _DF, "C")
    assert 0.0 < delta < _DF


def test_put_delta_negative_in_admissible_range():
    delta = strike_to_delta(_FORWARD, _FORWARD, _T, _SIGMA, _DF, "P")
    assert -_DF < delta < 0.0


@pytest.mark.parametrize("k_over_f", [0.7, 0.9, 1.0, 1.1, 1.5])
@pytest.mark.parametrize("option_type", ["C", "P"])
def test_delta_strike_round_trip(k_over_f, option_type):
    strike = _FORWARD * k_over_f
    delta = strike_to_delta(strike, _FORWARD, _T, _SIGMA, _DF, option_type)
    recovered = delta_to_strike(delta, _FORWARD, _T, _SIGMA, _DF, option_type)
    assert math.isclose(recovered, strike, rel_tol=1e-10)


def test_delta_to_strike_rejects_out_of_range_call():
    with pytest.raises(ValueError):
        delta_to_strike(_DF + 0.01, _FORWARD, _T, _SIGMA, _DF, "C")
    with pytest.raises(ValueError):
        delta_to_strike(0.0, _FORWARD, _T, _SIGMA, _DF, "C")


def test_delta_to_strike_rejects_out_of_range_put():
    with pytest.raises(ValueError):
        delta_to_strike(-_DF - 0.01, _FORWARD, _T, _SIGMA, _DF, "P")
    with pytest.raises(ValueError):
        delta_to_strike(0.0, _FORWARD, _T, _SIGMA, _DF, "P")


def test_strike_to_delta_rejects_bad_option_type():
    with pytest.raises(ValueError):
        strike_to_delta(_FORWARD, _FORWARD, _T, _SIGMA, _DF, "X")
