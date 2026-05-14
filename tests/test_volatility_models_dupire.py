"""Tests for montecarlo.volatility.DupireLocalVol."""

from __future__ import annotations

import warnings
from datetime import date

import numpy as np
import pytest

from market_structures.volatility import (
    InterpolatedVolSurface,
    PowerLawPhi,
    SSVISurface,
    SVIParameters,
    SVISlice,
    SVISurface,
)
from montecarlo.volatility import (
    BlackTermStructureVol,
    DupireLocalVol,
)


_REF = date(2026, 1, 1)


def _flat_surface(
    sigma: float,
    expiries: list[float] | None = None,
) -> InterpolatedVolSurface:
    expiries = expiries or [0.5, 1.0, 2.0]
    k_grid = [-0.3, -0.1, 0.0, 0.1, 0.3]
    return InterpolatedVolSurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=expiries,
        log_moneynesses=[k_grid] * len(expiries),
        total_variances=[[sigma * sigma * t] * len(k_grid) for t in expiries],
    )


def _flat_in_k_surface(
    sigmas_by_expiry: list[tuple[float, float]],
) -> InterpolatedVolSurface:
    expiries = [t for t, _ in sigmas_by_expiry]
    sigmas = [s for _, s in sigmas_by_expiry]
    k_grid = [-0.3, -0.1, 0.0, 0.1, 0.3]
    return InterpolatedVolSurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=expiries,
        log_moneynesses=[k_grid] * len(expiries),
        total_variances=[[s * s * t] * len(k_grid) for t, s in zip(expiries, sigmas)],
    )


def _svi_surface() -> SVISurface:
    return SVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        slices=[
            SVISlice(0.5, SVIParameters(0.005, 0.08, -0.30, 0.0, 0.12)),
            SVISlice(1.0, SVIParameters(0.020, 0.10, -0.40, 0.0, 0.15)),
            SVISlice(2.0, SVIParameters(0.050, 0.12, -0.50, 0.0, 0.18)),
        ],
    )


def _ssvi_surface() -> SSVISurface:
    return SSVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=[0.25, 0.5, 1.0, 2.0],
        theta_atm=[0.02, 0.045, 0.10, 0.22],
        rho=-0.5,
        phi=PowerLawPhi(eta=1.2, gamma=0.4),
    )


# --- Identity: flat-vol surface ----------------------------------------------


def test_flat_vol_grid_returns_constant_sigma_loc():
    sigma = 0.20
    dup = DupireLocalVol(_flat_surface(sigma=sigma))
    for T in (0.4, 0.8, 1.2, 1.8):
        for k in (-0.2, -0.05, 0.0, 0.05, 0.2):
            assert dup.local_variance(T, k) == pytest.approx(sigma * sigma, abs=5e-6)


# --- Identity: pure-time-dependent surface agrees with BlackTermStructureVol --


def test_pure_time_dependent_matches_black_term_structure():
    sigmas = [(0.5, 0.18), (1.0, 0.24), (2.0, 0.30)]
    surface = _flat_in_k_surface(sigmas)
    dup = DupireLocalVol(surface)
    bts = BlackTermStructureVol(surface)
    # Pick interior points of each segment so we hit the piecewise-constant
    # sigma_inst of BlackTermStructureVol cleanly.
    for T in (0.4, 0.7, 1.5):
        spot_vec = np.array([100.0, 110.0, 90.0])
        sigma_dup = dup.diffusion(T, spot_vec)
        sigma_bts = bts.diffusion(T, spot_vec)
        np.testing.assert_allclose(sigma_dup, sigma_bts, rtol=5e-3)


# --- Analytical Dupire on SVI matches numerical FD on the same surface --------


def _fd_dupire(surface, T, k, h_T=1e-5, h_k=1e-4):
    """Numerical Dupire applied directly to a (potentially analytical) surface."""
    w = surface.total_variance(T, k)
    dw_dT = (surface.total_variance(T + h_T, k) - surface.total_variance(T - h_T, k)) / (
        2 * h_T
    )
    dw_dk = (
        surface.total_variance(T, k + h_k) - surface.total_variance(T, k - h_k)
    ) / (2 * h_k)
    d2w_dk2 = (
        surface.total_variance(T, k + h_k)
        - 2 * w
        + surface.total_variance(T, k - h_k)
    ) / (h_k * h_k)
    denom = (
        1.0
        - (k / (2.0 * w)) * dw_dk
        + 0.25 * (-0.25 - 1.0 / w + (k * k) / (w * w)) * (dw_dk * dw_dk)
        + 0.5 * d2w_dk2
    )
    return dw_dT / denom


def test_analytical_dupire_on_svi_matches_finite_difference():
    """Analytical and FD must agree at any *interior* of a cross-T segment.

    SVISurface has a kink in dw/dT at slice pillars (the slope is piecewise
    constant between adjacent slices), so the FD across a pillar samples two
    different segments. We avoid that by picking T strictly inside each
    segment.
    """
    surf = _svi_surface()
    dup = DupireLocalVol(surf)
    assert dup.is_analytical
    interior_Ts = (0.7, 1.5)  # inside (0.5, 1.0) and (1.0, 2.0) respectively
    for T in interior_Ts:
        for k in (-0.3, -0.1, 0.0, 0.1, 0.3):
            analytic = dup.local_variance(T, k)
            numeric = _fd_dupire(surf, T, k)
            assert analytic == pytest.approx(numeric, rel=1e-5, abs=1e-8), (
                f"T={T} k={k}: analytic={analytic} numeric={numeric}"
            )


def test_analytical_dupire_on_ssvi_matches_finite_difference():
    """SSVI's dw/dT is also segment-piecewise-constant; avoid pillars."""
    surf = _ssvi_surface()
    dup = DupireLocalVol(surf)
    assert dup.is_analytical
    interior_Ts = (0.4, 0.8, 1.5)  # inside (0.25, 0.5), (0.5, 1.0), (1.0, 2.0)
    for T in interior_Ts:
        for k in (-0.3, -0.1, 0.0, 0.1, 0.3):
            analytic = dup.local_variance(T, k)
            numeric = _fd_dupire(surf, T, k)
            assert analytic == pytest.approx(numeric, rel=1e-5, abs=1e-8), (
                f"T={T} k={k}: analytic={analytic} numeric={numeric}"
            )


# --- Grid path on InterpolatedVolSurface -------------------------------------


def test_grid_path_constructed_with_expected_default_sizes():
    surf = _flat_surface(sigma=0.20)
    dup = DupireLocalVol(surf)
    assert not dup.is_analytical
    assert dup.t_grid is not None
    assert dup.k_grid is not None
    assert dup.t_grid.size == 50
    assert dup.k_grid.size == 100


def test_grid_path_accepts_override_grids():
    surf = _flat_surface(sigma=0.20)
    custom_t = np.linspace(0.1, 3.0, 30)
    custom_k = np.linspace(-2.0, 2.0, 60)
    dup = DupireLocalVol(surf, t_grid=custom_t, k_grid=custom_k)
    assert dup.t_grid is not None
    assert dup.k_grid is not None
    assert dup.t_grid.size == 30
    assert dup.k_grid.size == 60


def test_grid_override_rejected_on_analytical_path():
    surf = _svi_surface()
    with pytest.raises(ValueError, match="t_grid"):
        DupireLocalVol(surf, t_grid=[0.1, 1.0, 2.0])


# --- Diffusion vectorisation and state-ignored -------------------------------


def test_diffusion_shape_matches_spot_vector():
    dup = DupireLocalVol(_svi_surface())
    spot = np.array([80.0, 100.0, 120.0, 140.0])
    sigma = dup.diffusion(time=1.0, spot=spot)
    assert sigma.shape == spot.shape
    assert sigma.dtype == np.float64
    # Different spots produce different local vols on a skewed surface.
    assert not np.allclose(sigma, sigma[0])


def test_diffusion_for_zero_dim_spot():
    dup = DupireLocalVol(_svi_surface())
    spot = np.float64(100.0)
    sigma = dup.diffusion(1.0, spot)
    assert sigma.shape == ()


def test_state_kwarg_is_accepted_and_ignored():
    dup = DupireLocalVol(_svi_surface())
    spot = np.ones(3) * 100.0
    sigma_no_state = dup.diffusion(1.0, spot)
    sigma_with_state = dup.diffusion(
        1.0, spot, state={"variance": np.zeros(3), "alpha": np.ones(3)}
    )
    np.testing.assert_array_equal(sigma_no_state, sigma_with_state)


def test_diffusion_rejects_non_positive_time_or_spot():
    dup = DupireLocalVol(_svi_surface())
    with pytest.raises(ValueError):
        dup.diffusion(-0.1, np.array([100.0]))
    with pytest.raises(ValueError):
        dup.diffusion(1.0, np.array([100.0, 0.0, 90.0]))


# --- Sigma floor and clipping -------------------------------------------------


def test_sigma_floor_property_exposed():
    dup = DupireLocalVol(_flat_surface(0.2), sigma_floor=0.05)
    assert dup.sigma_floor == 0.05


def test_rejects_non_positive_sigma_floor():
    with pytest.raises(ValueError, match="sigma_floor"):
        DupireLocalVol(_flat_surface(0.2), sigma_floor=0.0)


def test_clipping_warning_on_arb_violating_grid():
    """Build a surface with calendar arb so the Dupire numerator goes negative.

    We hand-build an InterpolatedVolSurface whose ATM total variance
    *decreases* between adjacent expiries on the union grid — this triggers
    the surface's own calendar-arb warning AND makes Dupire clip nearly
    every grid point.
    """
    k_grid = [-0.3, 0.0, 0.3]
    # Slice at T=1.0 has higher w than slice at T=2.0 -> calendar arb.
    arb_surface = InterpolatedVolSurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=[1.0, 2.0],
        log_moneynesses=[k_grid, k_grid],
        total_variances=[[0.20, 0.20, 0.20], [0.10, 0.10, 0.10]],
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dup = DupireLocalVol(arb_surface)
        # Two warnings expected: one from the surface itself on construction,
        # plus the DupireLocalVol clipping warning. We only assert the latter.
        clip_warnings = [
            w for w in caught if "clipped" in str(w.message).lower()
        ]
        assert len(clip_warnings) >= 1
    # Floor is applied on the clipped region.
    assert dup.local_variance(1.5, 0.0) == pytest.approx(
        dup.sigma_floor * dup.sigma_floor, abs=1e-12
    )


def test_local_variance_rejects_non_positive_time():
    dup = DupireLocalVol(_svi_surface())
    with pytest.raises(ValueError, match="time_to_expiry"):
        dup.local_variance(0.0, 0.0)
    with pytest.raises(ValueError, match="time_to_expiry"):
        dup.local_variance(-1.0, 0.0)
