"""Tests for market_structures.volatility.parametric.ssvi and the SSVI calibrator."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from market_structures.volatility import (
    HestonLikePhi,
    PowerLawPhi,
    SSVISurface,
    fit_ssvi,
)
from market_structures.volatility.arbitrage import (
    check_butterfly,
    check_calendar,
)


_REF = date(2026, 1, 1)


# --- PhiFunction validation and accuracy --------------------------------------


def test_power_law_phi_rejects_bad_params():
    with pytest.raises(ValueError, match="eta"):
        PowerLawPhi(eta=0.0, gamma=0.5)
    with pytest.raises(ValueError, match="gamma"):
        PowerLawPhi(eta=1.0, gamma=0.0)
    with pytest.raises(ValueError, match="gamma"):
        PowerLawPhi(eta=1.0, gamma=1.0)


def test_heston_phi_rejects_bad_params():
    with pytest.raises(ValueError, match="lambda"):
        HestonLikePhi(lambda_=0.0)


def test_power_law_phi_derivative_matches_finite_difference():
    phi = PowerLawPhi(eta=1.2, gamma=0.4)
    h = 1e-7
    for theta in (0.01, 0.04, 0.1, 0.25, 1.0):
        analytic = phi.derivative(theta)
        numeric = (phi(theta + h) - phi(theta - h)) / (2.0 * h)
        assert analytic == pytest.approx(numeric, rel=1e-6, abs=1e-8)


def test_heston_phi_derivative_matches_finite_difference():
    phi = HestonLikePhi(lambda_=2.5)
    h = 1e-7
    for theta in (0.01, 0.04, 0.1, 0.25, 1.0):
        analytic = phi.derivative(theta)
        numeric = (phi(theta + h) - phi(theta - h)) / (2.0 * h)
        assert analytic == pytest.approx(numeric, rel=1e-5, abs=1e-8)


def test_heston_phi_small_x_taylor_matches_direct_at_threshold():
    """At the Taylor/direct branch threshold, the two formulas must agree.

    The threshold is chosen so the direct formula still has ~12 digits of
    floating-point precision; the Taylor branch has ~15 digits. Evaluated
    on the same x just below and just above the threshold, the *function
    value* differs only by the slope-times-step, while a Taylor evaluated
    at the boundary x and a direct evaluated at the boundary x must agree
    to machine precision. We probe the latter via a tiny step that keeps
    the slope contribution well below the tolerance.
    """
    phi = HestonLikePhi(lambda_=2.0)
    boundary_x = HestonLikePhi._TAYLOR_THRESHOLD
    # Use a step so small the slope contribution is < 1e-14.
    step = 1e-13
    theta_below = (boundary_x - step) / phi.lambda_
    theta_above = (boundary_x + step) / phi.lambda_
    assert phi(theta_below) == pytest.approx(phi(theta_above), abs=1e-12)


def test_heston_phi_atm_limit_is_one_half():
    phi = HestonLikePhi(lambda_=2.5)
    # As theta -> 0, phi -> 1/2.
    assert phi(1e-6) == pytest.approx(0.5, abs=1e-4)


# --- SSVISurface evaluation and derivatives -----------------------------------


def _build_ssvi(rho: float = -0.5) -> SSVISurface:
    return SSVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=[0.25, 0.5, 1.0, 2.0],
        theta_atm=[0.02, 0.045, 0.10, 0.22],
        rho=rho,
        phi=PowerLawPhi(eta=1.2, gamma=0.4),
    )


def test_ssvi_atm_identity():
    """w(T, 0) == theta(T) by construction."""
    surf = _build_ssvi()
    for T, theta in zip(surf.expiries, surf.theta_atm):
        assert surf.total_variance(T, 0.0) == pytest.approx(theta, rel=1e-14)


def test_ssvi_implied_vol_matches_total_variance():
    surf = _build_ssvi()
    T = 1.0
    K = 110.0
    k = math.log(K / surf.forward(T))
    w = surf.total_variance(T, k)
    assert surf.implied_vol(T, K) == pytest.approx(math.sqrt(w / T), rel=1e-14)


def test_ssvi_rejects_non_monotone_theta():
    with pytest.raises(ValueError, match="strictly increasing"):
        SSVISurface(
            reference_date=_REF,
            forward=lambda T: 100.0,
            expiries=[0.5, 1.0],
            theta_atm=[0.05, 0.04],
            rho=-0.5,
            phi=PowerLawPhi(eta=1.0, gamma=0.5),
        )


def test_ssvi_rejects_rho_out_of_range():
    with pytest.raises(ValueError, match="rho"):
        SSVISurface(
            reference_date=_REF,
            forward=lambda T: 100.0,
            expiries=[0.5],
            theta_atm=[0.04],
            rho=1.5,
            phi=PowerLawPhi(eta=1.0, gamma=0.5),
        )


def test_ssvi_dw_dk_matches_finite_difference():
    surf = _build_ssvi(rho=-0.5)
    h = 1e-7
    for T in (0.4, 1.0, 1.5):
        for k in (-0.3, -0.1, 0.0, 0.1, 0.3):
            analytic = surf.dw_dk(T, k)
            numeric = (
                surf.total_variance(T, k + h) - surf.total_variance(T, k - h)
            ) / (2.0 * h)
            assert analytic == pytest.approx(numeric, rel=1e-6, abs=1e-8)


def test_ssvi_d2w_dk2_matches_finite_difference():
    surf = _build_ssvi(rho=-0.5)
    h = 1e-4
    for T in (0.4, 1.0, 1.5):
        for k in (-0.3, -0.1, 0.0, 0.1, 0.3):
            analytic = surf.d2w_dk2(T, k)
            numeric = (
                surf.total_variance(T, k + h)
                - 2.0 * surf.total_variance(T, k)
                + surf.total_variance(T, k - h)
            ) / (h * h)
            assert analytic == pytest.approx(numeric, rel=1e-5, abs=1e-6)


def test_ssvi_dw_dT_matches_finite_difference():
    surf = _build_ssvi(rho=-0.5)
    h = 1e-7
    # Inside a segment (theta is piecewise linear, theta' is constant).
    for T in (0.4, 0.7, 1.5):
        for k in (-0.3, 0.0, 0.3):
            analytic = surf.dw_dT(T, k)
            numeric = (
                surf.total_variance(T + h, k) - surf.total_variance(T - h, k)
            ) / (2.0 * h)
            assert analytic == pytest.approx(numeric, rel=1e-6, abs=1e-8)


# --- SSVI calibration ---------------------------------------------------------


def test_fit_ssvi_power_law_recovers_synthetic_params():
    ref = _REF
    fwd = lambda T: 100.0
    expiries = [0.25, 0.5, 1.0, 2.0]
    theta_atm = [0.02, 0.045, 0.10, 0.22]
    true_rho = -0.55
    true_phi = PowerLawPhi(eta=1.2, gamma=0.4)
    true_surf = SSVISurface(ref, fwd, expiries, theta_atm, true_rho, true_phi)
    k_grid = np.linspace(-0.5, 0.5, 11)
    w_by_slice = [
        [true_surf.total_variance(T, float(k)) for k in k_grid] for T in expiries
    ]
    ks_by_slice = [list(k_grid)] * len(expiries)

    fit = fit_ssvi(ref, fwd, expiries, ks_by_slice, w_by_slice, phi_kind="power_law")
    assert fit.rho == pytest.approx(true_rho, abs=1e-5)
    assert fit.phi.params[0] == pytest.approx(true_phi.eta, abs=1e-5)
    assert fit.phi.params[1] == pytest.approx(true_phi.gamma, abs=1e-5)
    np.testing.assert_allclose(fit.theta_atm, theta_atm, rtol=1e-14)


def test_fit_ssvi_heston_like_recovers_synthetic_params():
    ref = _REF
    fwd = lambda T: 100.0
    expiries = [0.25, 0.5, 1.0, 2.0]
    theta_atm = [0.02, 0.045, 0.10, 0.22]
    true_rho = -0.55
    true_phi = HestonLikePhi(lambda_=2.5)
    true_surf = SSVISurface(ref, fwd, expiries, theta_atm, true_rho, true_phi)
    k_grid = np.linspace(-0.5, 0.5, 11)
    w_by_slice = [
        [true_surf.total_variance(T, float(k)) for k in k_grid] for T in expiries
    ]
    ks_by_slice = [list(k_grid)] * len(expiries)

    fit = fit_ssvi(
        ref, fwd, expiries, ks_by_slice, w_by_slice, phi_kind="heston_like"
    )
    assert fit.rho == pytest.approx(true_rho, abs=1e-5)
    assert fit.phi.params[0] == pytest.approx(true_phi.lambda_, abs=1e-5)


def test_fit_ssvi_rejects_unknown_phi_kind():
    with pytest.raises(ValueError, match="phi_kind"):
        fit_ssvi(
            _REF,
            lambda T: 100.0,
            [0.5, 1.0],
            [[-0.1, 0.0, 0.1], [-0.1, 0.0, 0.1]],
            [[0.04, 0.04, 0.04], [0.05, 0.05, 0.05]],
            phi_kind="banana",
        )


def test_fit_ssvi_rejects_non_monotone_atm_term_structure():
    with pytest.raises(ValueError, match="strictly increasing"):
        fit_ssvi(
            _REF,
            lambda T: 100.0,
            [0.5, 1.0],
            [[-0.1, 0.0, 0.1], [-0.1, 0.0, 0.1]],
            # ATM column decreases: theta(0.5) > theta(1.0).
            [[0.08, 0.08, 0.08], [0.05, 0.05, 0.05]],
            phi_kind="power_law",
        )


# --- Arbitrage checks on a calibrated SSVI ------------------------------------


def test_calibrated_ssvi_passes_calendar_and_butterfly():
    """Arb-free SSVI (rho moderate, theta strictly increasing) passes both checks."""
    surf = _build_ssvi(rho=-0.5)
    T_grid = np.linspace(0.1, 2.5, 12)
    k_grid = np.linspace(-1.5, 1.5, 41)
    cal = check_calendar(surf, T_grid, k_grid)
    assert cal.is_arb_free, f"calendar failed: {cal}"
    for T in T_grid:
        butt = check_butterfly(surf, float(T), k_grid)
        assert butt.is_arb_free, f"butterfly failed at T={T}: {butt}"
