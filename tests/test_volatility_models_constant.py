"""Tests for montecarlo.volatility.ConstantVol."""

from __future__ import annotations

import numpy as np
import pytest

from montecarlo.volatility import ConstantVol


def test_diffusion_returns_sigma_for_vector_spot():
    model = ConstantVol(sigma=0.25)
    spot = np.array([90.0, 100.0, 110.0, 120.0])
    sigma = model.diffusion(time=0.5, spot=spot)
    assert sigma.shape == spot.shape
    assert sigma.dtype == np.float64
    assert np.all(sigma == 0.25)


def test_diffusion_for_zero_dim_spot():
    model = ConstantVol(sigma=0.3)
    spot = np.float64(100.0)
    sigma = model.diffusion(time=1.0, spot=spot)
    assert sigma.shape == ()
    assert float(sigma) == 0.3


def test_diffusion_is_independent_of_time():
    model = ConstantVol(sigma=0.2)
    spot = np.ones(5)
    s_short = model.diffusion(time=1e-6, spot=spot)
    s_long = model.diffusion(time=10.0, spot=spot)
    np.testing.assert_array_equal(s_short, s_long)


def test_state_is_accepted_and_ignored():
    model = ConstantVol(sigma=0.15)
    spot = np.ones(3)
    sigma = model.diffusion(time=0.5, spot=spot, state={"variance": np.zeros(3)})
    assert np.all(sigma == 0.15)


def test_rejects_non_positive_sigma():
    with pytest.raises(ValueError):
        ConstantVol(sigma=0.0)
    with pytest.raises(ValueError):
        ConstantVol(sigma=-0.1)


def test_sigma_property_exposes_input():
    model = ConstantVol(sigma=0.42)
    assert model.sigma == 0.42
