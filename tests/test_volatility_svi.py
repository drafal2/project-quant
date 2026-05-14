"""Tests for market_structures.volatility.parametric.svi and the SVI calibrator."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from market_structures.volatility import (
    SVIParameters,
    SVISlice,
    SVISurface,
    fit_svi_slice,
    fit_svi_surface,
)


_REF = date(2026, 1, 1)


# --- SVIParameters validation -------------------------------------------------


def test_svi_parameters_rejects_negative_b():
    with pytest.raises(ValueError, match="b must be non-negative"):
        SVIParameters(a=0.01, b=-0.01, rho=0.0, m=0.0, sigma=0.1)


def test_svi_parameters_rejects_rho_out_of_range():
    with pytest.raises(ValueError, match="rho"):
        SVIParameters(a=0.01, b=0.1, rho=1.5, m=0.0, sigma=0.1)
    with pytest.raises(ValueError, match="rho"):
        SVIParameters(a=0.01, b=0.1, rho=-1.5, m=0.0, sigma=0.1)


def test_svi_parameters_rejects_non_positive_sigma():
    with pytest.raises(ValueError, match="sigma"):
        SVIParameters(a=0.01, b=0.1, rho=0.0, m=0.0, sigma=0.0)


def test_svi_parameters_rejects_no_neg_variance_violation():
    # a + b*sigma*sqrt(1-rho^2) = -0.05 + 0.1 * 0.1 * 1 = -0.04 < 0 -> reject
    with pytest.raises(ValueError, match="no-negative-variance"):
        SVIParameters(a=-0.05, b=0.1, rho=0.0, m=0.0, sigma=0.1)


# --- SVISlice closed-forms ----------------------------------------------------


def test_svi_slice_total_variance_at_vertex():
    p = SVIParameters(a=0.02, b=0.15, rho=-0.3, m=0.05, sigma=0.12)
    s = SVISlice(expiry=1.0, params=p)
    # w(m) = a + b * sigma  (since the sqrt term equals sigma at k = m)
    expected = p.a + p.b * p.sigma
    assert s.total_variance(p.m) == pytest.approx(expected, rel=1e-14)


def test_svi_slice_dw_dk_at_vertex():
    p = SVIParameters(a=0.02, b=0.15, rho=-0.3, m=0.05, sigma=0.12)
    s = SVISlice(expiry=1.0, params=p)
    # w'(m) = b * rho  (since (k - m) / sqrt(...) = 0 at k = m)
    expected = p.b * p.rho
    assert s.dw_dk(p.m) == pytest.approx(expected, rel=1e-14)


def test_svi_slice_d2w_dk2_at_vertex_is_b_over_sigma():
    p = SVIParameters(a=0.02, b=0.15, rho=-0.3, m=0.05, sigma=0.12)
    s = SVISlice(expiry=1.0, params=p)
    # w''(m) = b * sigma^2 / sigma^3 = b / sigma
    expected = p.b / p.sigma
    assert s.d2w_dk2(p.m) == pytest.approx(expected, rel=1e-14)


def test_svi_slice_analytical_dw_dk_matches_finite_difference():
    p = SVIParameters(a=0.03, b=0.18, rho=-0.5, m=-0.02, sigma=0.2)
    s = SVISlice(expiry=1.0, params=p)
    h = 1e-6
    for k in np.linspace(-1.0, 1.0, 21):
        analytic = s.dw_dk(float(k))
        numeric = (s.total_variance(k + h) - s.total_variance(k - h)) / (2.0 * h)
        assert analytic == pytest.approx(numeric, rel=1e-7, abs=1e-10)


def test_svi_slice_analytical_d2w_dk2_matches_finite_difference():
    p = SVIParameters(a=0.03, b=0.18, rho=-0.5, m=-0.02, sigma=0.2)
    s = SVISlice(expiry=1.0, params=p)
    h = 1e-4
    for k in np.linspace(-1.0, 1.0, 21):
        analytic = s.d2w_dk2(float(k))
        numeric = (
            s.total_variance(k + h) - 2.0 * s.total_variance(k) + s.total_variance(k - h)
        ) / (h * h)
        assert analytic == pytest.approx(numeric, rel=1e-5, abs=1e-8)


def test_svi_slice_rejects_non_positive_expiry():
    p = SVIParameters(a=0.02, b=0.1, rho=0.0, m=0.0, sigma=0.1)
    with pytest.raises(ValueError, match="expiry"):
        SVISlice(expiry=0.0, params=p)


# --- SVISurface ---------------------------------------------------------------


def _build_three_slice_surface() -> SVISurface:
    return SVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        slices=[
            SVISlice(0.5, SVIParameters(0.01, 0.08, -0.3, 0.0, 0.1)),
            SVISlice(1.0, SVIParameters(0.02, 0.10, -0.3, 0.0, 0.1)),
            SVISlice(2.0, SVIParameters(0.05, 0.12, -0.3, 0.0, 0.1)),
        ],
    )


def test_svi_surface_rejects_empty_slices():
    with pytest.raises(ValueError, match="at least one"):
        SVISurface(reference_date=_REF, forward=lambda T: 100.0, slices=[])


def test_svi_surface_rejects_non_increasing_expiries():
    with pytest.raises(ValueError, match="strictly increasing"):
        SVISurface(
            reference_date=_REF,
            forward=lambda T: 100.0,
            slices=[
                SVISlice(1.0, SVIParameters(0.01, 0.08, -0.3, 0.0, 0.1)),
                SVISlice(0.5, SVIParameters(0.02, 0.10, -0.3, 0.0, 0.1)),
            ],
        )


def test_svi_surface_at_pillar_returns_slice_closed_form():
    surf = _build_three_slice_surface()
    slc = surf.slices[1]
    for k in (-0.3, -0.1, 0.0, 0.1, 0.3):
        assert surf.total_variance(1.0, k) == pytest.approx(
            slc.total_variance(k), rel=1e-14
        )


def test_svi_surface_cross_T_is_linear_in_w():
    surf = _build_three_slice_surface()
    s_lo, s_hi = surf.slices[1], surf.slices[2]
    T = 1.5  # midpoint between 1.0 and 2.0
    for k in (-0.2, 0.0, 0.2):
        expected = 0.5 * (s_lo.total_variance(k) + s_hi.total_variance(k))
        assert surf.total_variance(T, k) == pytest.approx(expected, rel=1e-14)


def test_svi_surface_short_extrapolation_holds_sigma_flat():
    surf = _build_three_slice_surface()
    boundary = surf.slices[0]
    # At T = T_boundary / 2, w should be w_boundary / 2 (so sigma is unchanged).
    for k in (-0.2, 0.0, 0.2):
        assert surf.total_variance(0.25, k) == pytest.approx(
            0.5 * boundary.total_variance(k), rel=1e-14
        )


def test_svi_surface_dw_dT_segment_slope():
    surf = _build_three_slice_surface()
    s_lo, s_hi = surf.slices[1], surf.slices[2]
    # Interior point in [1.0, 2.0] segment.
    for k in (-0.2, 0.0, 0.2):
        expected = (s_hi.total_variance(k) - s_lo.total_variance(k)) / (2.0 - 1.0)
        assert surf.dw_dT(1.5, k) == pytest.approx(expected, rel=1e-14)


def test_svi_surface_dw_dT_matches_finite_difference():
    surf = _build_three_slice_surface()
    h = 1e-6
    for T in (0.7, 1.5):
        for k in (-0.2, 0.0, 0.2):
            analytic = surf.dw_dT(T, k)
            numeric = (
                surf.total_variance(T + h, k) - surf.total_variance(T - h, k)
            ) / (2.0 * h)
            assert analytic == pytest.approx(numeric, rel=1e-6, abs=1e-9)


def test_svi_surface_implied_vol_matches_total_variance():
    surf = _build_three_slice_surface()
    T = 1.0
    K = 110.0
    k = math.log(K / surf.forward(T))
    w = surf.total_variance(T, k)
    sigma_expected = math.sqrt(w / T)
    assert surf.implied_vol(T, K) == pytest.approx(sigma_expected, rel=1e-14)


# --- SVI calibration ----------------------------------------------------------


def test_fit_svi_slice_synthetic_recovery():
    true_p = SVIParameters(a=0.02, b=0.12, rho=-0.4, m=0.05, sigma=0.15)
    true_s = SVISlice(expiry=1.0, params=true_p)
    k_grid = np.linspace(-0.5, 0.5, 11)
    w_grid = np.array([true_s.total_variance(float(k)) for k in k_grid])

    fit = fit_svi_slice(k_grid, w_grid)
    assert fit.a == pytest.approx(true_p.a, abs=1e-5)
    assert fit.b == pytest.approx(true_p.b, abs=1e-5)
    assert fit.rho == pytest.approx(true_p.rho, abs=1e-5)
    assert fit.m == pytest.approx(true_p.m, abs=1e-5)
    assert fit.sigma == pytest.approx(true_p.sigma, abs=1e-5)

    fit_slice = SVISlice(expiry=1.0, params=fit)
    w_fit = np.array([fit_slice.total_variance(float(k)) for k in k_grid])
    assert np.max(np.abs(w_fit - w_grid)) < 1e-8


def test_fit_svi_slice_with_weights_is_different_from_uniform():
    rng = np.random.default_rng(42)
    true_p = SVIParameters(a=0.02, b=0.12, rho=-0.4, m=0.05, sigma=0.15)
    true_s = SVISlice(expiry=1.0, params=true_p)
    k_grid = np.linspace(-0.5, 0.5, 11)
    noise = rng.normal(scale=1e-3, size=k_grid.size)
    w_grid = np.array([true_s.total_variance(float(k)) for k in k_grid]) + noise

    uniform_fit = fit_svi_slice(k_grid, w_grid)
    # Strongly emphasise the ATM region — vega is largest there.
    vega_like = np.exp(-0.5 * (k_grid / 0.1) ** 2)
    weighted_fit = fit_svi_slice(k_grid, w_grid, weights=vega_like)
    # Distinct fits, both within sane bounds.
    assert weighted_fit.a != uniform_fit.a or weighted_fit.b != uniform_fit.b


def test_fit_svi_slice_requires_minimum_points():
    with pytest.raises(ValueError, match="at least 5"):
        fit_svi_slice([0.0, 0.1, 0.2, 0.3], [0.04, 0.04, 0.05, 0.05])


def test_fit_svi_slice_rejects_non_positive_variance():
    with pytest.raises(ValueError, match="strictly positive"):
        fit_svi_slice([-0.2, -0.1, 0.0, 0.1, 0.2], [0.04, 0.0, 0.04, 0.04, 0.04])


def test_fit_svi_surface_synthetic_recovery():
    true_slices = [
        SVISlice(0.5, SVIParameters(0.005, 0.08, -0.3, 0.02, 0.10)),
        SVISlice(1.0, SVIParameters(0.020, 0.10, -0.4, 0.04, 0.12)),
        SVISlice(2.0, SVIParameters(0.050, 0.12, -0.5, 0.05, 0.15)),
    ]
    k_grid = np.linspace(-0.5, 0.5, 11)
    ws_by_slice = [
        [s.total_variance(float(k)) for k in k_grid] for s in true_slices
    ]
    ks_by_slice = [list(k_grid)] * len(true_slices)

    surf = fit_svi_surface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=[s.expiry for s in true_slices],
        log_moneynesses_by_slice=ks_by_slice,
        total_variances_by_slice=ws_by_slice,
    )
    for s_true, s_fit in zip(true_slices, surf.slices):
        assert s_fit.params.a == pytest.approx(s_true.params.a, abs=1e-4)
        assert s_fit.params.b == pytest.approx(s_true.params.b, abs=1e-4)
        assert s_fit.params.rho == pytest.approx(s_true.params.rho, abs=1e-4)
        assert s_fit.params.m == pytest.approx(s_true.params.m, abs=1e-4)
        assert s_fit.params.sigma == pytest.approx(s_true.params.sigma, abs=1e-4)


# --- Gatheral-Jacquier 2014 literature anchor ---------------------------------
#
# Representative SVI parameter set for SPX 2011-09-15 in the style of
# Gatheral-Jacquier (2014). These values match the qualitative shape reported
# in the paper (low a, moderate b, strongly negative rho, near-zero m, small
# sigma) but are not verbatim from Table 4 — they serve as a literature-anchored
# self-consistency check. Swap in exact paper values when the dataset is
# available.

_SPX_LITERATURE_SLICES = [
    (0.119, SVIParameters(a=0.0012, b=0.0410, rho=-0.6800, m=-0.0020, sigma=0.0625)),
    (0.197, SVIParameters(a=0.0028, b=0.0532, rho=-0.6750, m=-0.0030, sigma=0.0830)),
    (0.444, SVIParameters(a=0.0080, b=0.0731, rho=-0.6600, m=-0.0090, sigma=0.1010)),
    (0.692, SVIParameters(a=0.0125, b=0.0852, rho=-0.6450, m=-0.0150, sigma=0.1180)),
    (0.945, SVIParameters(a=0.0162, b=0.0951, rho=-0.6300, m=-0.0210, sigma=0.1330)),
]


@pytest.mark.parametrize(
    "expiry,true_params",
    _SPX_LITERATURE_SLICES,
    ids=[f"T={t:.3f}" for t, _ in _SPX_LITERATURE_SLICES],
)
def test_fit_svi_slice_recovers_spx_literature_params(expiry, true_params):
    true_s = SVISlice(expiry=expiry, params=true_params)
    # Paper-style log-moneyness range: deep wings on both sides.
    k_grid = np.linspace(-0.4, 0.3, 15)
    w_grid = np.array([true_s.total_variance(float(k)) for k in k_grid])
    fit = fit_svi_slice(k_grid, w_grid)
    assert fit.a == pytest.approx(true_params.a, abs=1e-4)
    assert fit.b == pytest.approx(true_params.b, abs=1e-4)
    assert fit.rho == pytest.approx(true_params.rho, abs=1e-4)
    assert fit.m == pytest.approx(true_params.m, abs=1e-4)
    assert fit.sigma == pytest.approx(true_params.sigma, abs=1e-4)
