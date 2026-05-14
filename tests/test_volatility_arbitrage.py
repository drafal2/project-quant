"""Tests for market_structures.volatility.arbitrage."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from market_structures.volatility import (
    PowerLawPhi,
    SSVISurface,
    SVIParameters,
    SVISlice,
    SVISurface,
    check_butterfly,
    check_calendar,
    durrleman_g,
)


_REF = date(2026, 1, 1)


def _flat_slice_surface(a: float, expiry: float) -> SVISurface:
    """Build a degenerate SVI surface with b = 0 -> w(k) = a everywhere."""
    return SVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        slices=[SVISlice(expiry, SVIParameters(a=a, b=0.0, rho=0.0, m=0.0, sigma=0.1))],
    )


def test_durrleman_g_on_flat_slice_equals_one():
    """For b = 0: w = a, w' = 0, w'' = 0, so g(k) = 1 for all k."""
    surf = _flat_slice_surface(a=0.04, expiry=1.0)
    for k in (-1.0, -0.5, 0.0, 0.5, 1.0):
        assert durrleman_g(surf, 1.0, k) == pytest.approx(1.0, rel=1e-12)


def test_check_butterfly_passes_on_arb_free_svi_slice():
    surf = SVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        slices=[
            SVISlice(
                1.0,
                SVIParameters(a=0.02, b=0.10, rho=-0.4, m=0.0, sigma=0.20),
            )
        ],
    )
    k_grid = np.linspace(-1.5, 1.5, 121)
    report = check_butterfly(surf, time_to_expiry=1.0, k_grid=k_grid)
    assert report.is_arb_free
    assert report.g_min > 0.0
    assert report.expiry == 1.0


def test_check_butterfly_flags_violating_slice():
    """Extreme SVI parameters produce a negative-density wing.

    Large b, sharp sigma, |rho| near 1 push the Durrleman function below
    zero in one wing. The exact threshold depends on parameter choice; the
    set below was chosen to violate at a deep negative k.
    """
    bad = SVIParameters(a=0.001, b=0.60, rho=-0.95, m=0.0, sigma=0.02)
    surf = SVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        slices=[SVISlice(1.0, bad)],
    )
    k_grid = np.linspace(-1.5, 1.5, 401)
    report = check_butterfly(surf, time_to_expiry=1.0, k_grid=k_grid)
    assert not report.is_arb_free, f"expected violation, got {report}"
    assert report.g_min < 0.0


def test_check_calendar_passes_on_monotone_theta_ssvi():
    surf = SSVISurface(
        reference_date=_REF,
        forward=lambda T: 100.0,
        expiries=[0.25, 0.5, 1.0, 2.0],
        theta_atm=[0.02, 0.045, 0.10, 0.22],
        rho=-0.5,
        phi=PowerLawPhi(eta=1.2, gamma=0.4),
    )
    T_grid = np.linspace(0.1, 2.5, 13)
    k_grid = np.linspace(-1.0, 1.0, 41)
    report = check_calendar(surf, T_grid, k_grid)
    assert report.is_arb_free
    assert report.min_dw_dT >= 0.0


def test_check_calendar_flags_decreasing_w_in_surface():
    """Construct a hand-built SVISurface whose adjacent slices cross in w."""
    # Two slices: at T=0.5 the slice has higher w at k=0 than the T=1.0 slice
    # (calendar arbitrage). Build with adjacent params and bypass the
    # SVISurface auto-warning by using slices that only cross at a chosen k.
    slc_lo = SVISlice(0.5, SVIParameters(a=0.10, b=0.0, rho=0.0, m=0.0, sigma=0.1))
    slc_hi = SVISlice(1.0, SVIParameters(a=0.05, b=0.0, rho=0.0, m=0.0, sigma=0.1))
    with pytest.warns(UserWarning, match="calendar arbitrage"):
        surf = SVISurface(
            reference_date=_REF,
            forward=lambda T: 100.0,
            slices=[slc_lo, slc_hi],
        )
    T_grid = np.linspace(0.5, 1.0, 6)
    k_grid = np.linspace(-0.5, 0.5, 11)
    report = check_calendar(surf, T_grid, k_grid)
    assert not report.is_arb_free
    assert report.min_dw_dT < 0.0


def test_check_butterfly_requires_non_empty_grid():
    surf = _flat_slice_surface(a=0.04, expiry=1.0)
    with pytest.raises(ValueError, match="non-empty"):
        check_butterfly(surf, 1.0, [])


def test_check_calendar_requires_non_empty_grids():
    surf = _flat_slice_surface(a=0.04, expiry=1.0)
    with pytest.raises(ValueError, match="non-empty"):
        check_calendar(surf, [], [0.0, 0.1])
    with pytest.raises(ValueError, match="non-empty"):
        check_calendar(surf, [0.5, 1.0], [])
