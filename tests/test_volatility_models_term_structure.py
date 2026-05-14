"""Tests for montecarlo.volatility.BlackTermStructureVol."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from market_structures.volatility.interpolated import InterpolatedVolSurface
from market_structures.volatility.surface import VolSurface
from montecarlo.volatility import BlackTermStructureVol


_REF = date(2026, 1, 1)


def _surface_from_atm_vols(
    expiries: list[float],
    atm_vols: list[float],
) -> InterpolatedVolSurface:
    """Build a flat-in-k surface whose ATM column matches ``atm_vols``."""
    k_grid = [-0.1, 0.0, 0.1]
    total_variances = [[v * v * t] * len(k_grid) for v, t in zip(atm_vols, expiries)]
    return InterpolatedVolSurface(
        reference_date=_REF,
        forward=lambda t: 100.0,
        expiries=expiries,
        log_moneynesses=[k_grid] * len(expiries),
        total_variances=total_variances,
    )


class _StubSurface(VolSurface):
    """Minimal VolSurface returning user-supplied ATM total variances."""

    def __init__(
        self,
        expiries: list[float],
        atm_w: list[float],
    ) -> None:
        self._expiries = expiries
        self._w = dict(zip(expiries, atm_w))

    @property
    def reference_date(self) -> date:
        return _REF

    @property
    def expiries(self) -> list[float]:
        return list(self._expiries)

    def forward(self, time_to_expiry: float) -> float:
        return 100.0

    def implied_vol(self, time_to_expiry: float, strike: float) -> float:
        return float(np.sqrt(self._w[time_to_expiry] / time_to_expiry))

    def total_variance(self, time_to_expiry: float, log_moneyness: float) -> float:
        return self._w[time_to_expiry]


def test_pillar_repricing_exact():
    expiries = [0.5, 1.0, 2.0]
    atm_vols = [0.20, 0.25, 0.30]
    surface = _surface_from_atm_vols(expiries, atm_vols)
    model = BlackTermStructureVol(surface)

    pillars = model.pillars
    sigma_inst = model.sigma_inst
    dt = np.diff(pillars, prepend=0.0)
    cumulative_variance = np.cumsum(sigma_inst**2 * dt)
    for i, T in enumerate(expiries):
        expected = atm_vols[i] ** 2 * T
        assert cumulative_variance[i] == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_diffusion_is_piecewise_constant_inside_a_segment():
    expiries = [0.5, 1.0, 2.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25, 0.30])
    model = BlackTermStructureVol(surface)
    spot = np.ones(4)

    s_a = model.diffusion(time=0.51, spot=spot)
    s_b = model.diffusion(time=0.75, spot=spot)
    s_c = model.diffusion(time=1.0, spot=spot)  # right-closed boundary
    np.testing.assert_array_equal(s_a, s_b)
    np.testing.assert_array_equal(s_b, s_c)

    s_next = model.diffusion(time=1.0 + 1e-12, spot=spot)
    assert not np.array_equal(s_c, s_next)


def test_diffusion_matches_segment_sigma_inst():
    expiries = [0.5, 1.0, 2.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25, 0.30])
    model = BlackTermStructureVol(surface)
    spot = np.ones(2)

    # Segment 0: (0, 0.5]; Segment 1: (0.5, 1.0]; Segment 2: (1.0, 2.0].
    np.testing.assert_allclose(
        model.diffusion(time=0.0, spot=spot), model.sigma_inst[0]
    )
    np.testing.assert_allclose(
        model.diffusion(time=0.5, spot=spot), model.sigma_inst[0]
    )
    np.testing.assert_allclose(
        model.diffusion(time=0.75, spot=spot), model.sigma_inst[1]
    )
    np.testing.assert_allclose(
        model.diffusion(time=1.5, spot=spot), model.sigma_inst[2]
    )


def test_flat_extrapolation_beyond_last_pillar():
    expiries = [0.5, 1.0, 2.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25, 0.30])
    model = BlackTermStructureVol(surface)
    spot = np.ones(3)

    last_segment = model.diffusion(time=1.9, spot=spot)
    extrapolated = model.diffusion(time=5.0, spot=spot)
    np.testing.assert_array_equal(last_segment, extrapolated)


def test_vectorisation_over_spot():
    expiries = [0.5, 1.0, 2.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25, 0.30])
    model = BlackTermStructureVol(surface)

    spot = np.array([100.0, 110.0, 120.0, 130.0])
    sigma = model.diffusion(time=0.7, spot=spot)
    assert sigma.shape == spot.shape
    assert sigma.dtype == np.float64
    assert np.all(sigma == sigma[0])


def test_state_kwarg_is_accepted_and_ignored():
    expiries = [0.5, 1.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25])
    model = BlackTermStructureVol(surface)
    spot = np.ones(3)
    sigma_no_state = model.diffusion(time=0.7, spot=spot)
    sigma_with_state = model.diffusion(
        time=0.7,
        spot=spot,
        state={"variance": np.zeros(3), "alpha": np.ones(3)},
    )
    np.testing.assert_array_equal(sigma_no_state, sigma_with_state)


def test_flat_vol_surface_recovers_constant_sigma():
    expiries = [0.5, 1.0, 2.0]
    sigma_flat = 0.22
    surface = _surface_from_atm_vols(expiries, [sigma_flat] * 3)
    model = BlackTermStructureVol(surface)
    assert np.allclose(model.sigma_inst, sigma_flat)
    spot = np.ones(2)
    for t in (0.01, 0.4, 0.9, 1.5, 5.0):
        np.testing.assert_allclose(model.diffusion(time=t, spot=spot), sigma_flat)


def test_calendar_arbitrage_rejected_at_construction():
    expiries = [0.5, 1.0, 2.0]
    # w must be non-decreasing; w1 < w0 is calendar arbitrage.
    w0 = 0.40**2 * 0.5   # 0.080
    w1 = 0.20**2 * 1.0   # 0.040  <-- decrease
    w2 = 0.30**2 * 2.0   # 0.180
    arb_surface = _StubSurface(expiries=expiries, atm_w=[w0, w1, w2])
    with pytest.raises(ValueError, match="calendar arbitrage"):
        BlackTermStructureVol(arb_surface)


def test_negative_time_rejected():
    expiries = [0.5, 1.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25])
    model = BlackTermStructureVol(surface)
    with pytest.raises(ValueError):
        model.diffusion(time=-0.01, spot=np.ones(3))


def test_empty_expiries_rejected():
    empty_surface = _StubSurface(expiries=[], atm_w=[])
    with pytest.raises(ValueError, match="no expiries"):
        BlackTermStructureVol(empty_surface)


def test_pillars_and_sigma_inst_are_defensive_copies():
    expiries = [0.5, 1.0]
    surface = _surface_from_atm_vols(expiries, [0.20, 0.25])
    model = BlackTermStructureVol(surface)
    pillars = model.pillars
    sigma_inst = model.sigma_inst
    pillars[0] = 999.0
    sigma_inst[0] = 999.0
    assert model.pillars[0] == 0.5
    assert model.sigma_inst[0] != 999.0
