"""Tests for the uniform samplers in ``montecarlo.uniform``."""

from __future__ import annotations

import numpy as np
import pytest

from montecarlo import (
    HaltonSampler,
    KnuthSampler,
    MRG32k3aSampler,
    MersenneTwisterSampler,
    SobolSampler,
)
from montecarlo.diagnostics import ks_uniform, l2_discrepancy


_PRNG_FACTORIES = [
    pytest.param(lambda: KnuthSampler(seed=42), id="knuth"),
    pytest.param(lambda: MRG32k3aSampler(seed=42), id="mrg32k3a"),
    pytest.param(lambda: MersenneTwisterSampler(seed=42), id="mt19937"),
]

_QMC_FACTORIES = [
    pytest.param(lambda: HaltonSampler(max_dimensions=8), id="halton"),
    pytest.param(lambda: SobolSampler(max_dimensions=8), id="sobol"),
]


@pytest.mark.parametrize("factory", _PRNG_FACTORIES + _QMC_FACTORIES)
def test_shape_and_range(factory):
    block = factory().next_block(50, 4)
    assert block.shape == (50, 4)
    assert ((block > 0.0) & (block < 1.0)).all()


@pytest.mark.parametrize("factory", _PRNG_FACTORIES + _QMC_FACTORIES)
def test_reproducibility_after_reset(factory):
    sampler = factory()
    first = sampler.next_block(20, 3)
    sampler.reset()
    second = sampler.next_block(20, 3)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("factory", _PRNG_FACTORIES)
def test_prng_passes_ks(factory):
    samples = factory().next_block(100_000, 1).ravel()
    res = ks_uniform(samples)
    assert res.p_value > 0.01, f"KS p-value too low: {res.p_value:.4f}"


def test_sobol_gray_code_reference_values():
    s = SobolSampler(max_dimensions=2)
    points = s.next_block(4, 2)
    expected = np.array(
        [
            [0.5, 0.5],
            [0.75, 0.25],
            [0.25, 0.75],
            [0.375, 0.375],
        ]
    )
    assert np.allclose(points, expected, atol=1e-9)


def test_sobol_beats_prng_on_discrepancy():
    sobol = SobolSampler(max_dimensions=4)
    prng = MRG32k3aSampler(seed=7)
    n = 1024
    d_sobol = l2_discrepancy(sobol.next_block(n, 4))
    d_prng = l2_discrepancy(prng.next_block(n, 4))
    assert d_sobol < 0.1 * d_prng


def test_halton_l2_degrades_relative_to_sobol_in_high_dim():
    n = 1024
    d = 40
    halton_points = HaltonSampler(max_dimensions=d).next_block(n, d)
    sobol_points = SobolSampler(max_dimensions=d).next_block(n, d)
    halton_l2 = l2_discrepancy(halton_points)
    sobol_l2 = l2_discrepancy(sobol_points)
    assert halton_l2 > 3.0 * sobol_l2, (
        f"Halton L2 ({halton_l2:.3e}) did not degrade relative to Sobol "
        f"({sobol_l2:.3e}) at d={d}, n={n}"
    )


def test_sobol_max_dimension_guard():
    s = SobolSampler(max_dimensions=4)
    with pytest.raises(ValueError):
        s.next_block(10, 5)


def test_halton_max_dimension_guard():
    s = HaltonSampler(max_dimensions=4)
    with pytest.raises(ValueError):
        s.next_block(10, 5)


def test_sobol_rejects_oversize_construction():
    with pytest.raises(ValueError):
        SobolSampler(max_dimensions=10_000_000)


def test_mrg32k3a_substream_stub():
    s = MRG32k3aSampler(seed=1)
    with pytest.raises(NotImplementedError):
        s.substream(3)
