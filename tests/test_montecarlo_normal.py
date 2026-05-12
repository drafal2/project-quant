"""Tests for the normal transforms in ``montecarlo.normal``."""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from scipy.special import ndtri

from montecarlo import (
    AcklamTransform,
    BoxMullerTransform,
    CLTTransform,
    HaltonSampler,
    MRG32k3aSampler,
    MoroTransform,
    SobolSampler,
    WichuraAS241Transform,
    make_normal_sampler,
)


_ALL_TRANSFORMS = [
    pytest.param(BoxMullerTransform(), id="box_muller"),
    pytest.param(MoroTransform(), id="moro"),
    pytest.param(AcklamTransform(), id="acklam"),
    pytest.param(WichuraAS241Transform(), id="wichura"),
]


@pytest.mark.parametrize(
    "transform, max_central_err",
    [
        (MoroTransform(), 5e-9),
        (AcklamTransform(), 3e-9),
        (WichuraAS241Transform(), 1e-13),
    ],
)
def test_inverse_cdf_accuracy_central(transform, max_central_err):
    grid = np.linspace(0.025, 0.975, 50_001)[None, :]
    got = transform.transform(grid)
    ref = ndtri(grid)
    assert np.abs(got - ref).max() < max_central_err


@pytest.mark.parametrize(
    "transform, max_tail_err",
    [
        (AcklamTransform(), 1e-8),
        (WichuraAS241Transform(), 1e-13),
    ],
)
def test_inverse_cdf_accuracy_deep_tail(transform, max_tail_err):
    grid = np.concatenate(
        [np.logspace(-15, -6, 1000), 1.0 - np.logspace(-15, -6, 1000)]
    )[None, :]
    got = transform.transform(grid)
    ref = ndtri(grid)
    assert np.abs(got - ref).max() < max_tail_err


@pytest.mark.parametrize("transform", _ALL_TRANSFORMS)
def test_normal_moments_match_via_prng(transform):
    sampler = MRG32k3aSampler(seed=13)
    ns = make_normal_sampler(sampler, transform)
    z = ns.next_block(200_000, 1).ravel()
    assert abs(z.mean()) < 0.02
    assert abs(z.var(ddof=1) - 1.0) < 0.02


def test_clt_warns_on_construction():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        CLTTransform()
    assert any(issubclass(w.category, UserWarning) for w in captured)


def test_clt_shape_and_uniforms_per_normal():
    clt = CLTTransform()
    assert clt.uniforms_per_normal == 12
    rng = np.random.default_rng(0)
    u = rng.random((100, 12 * 5))
    z = clt.transform(u)
    assert z.shape == (100, 5)
    assert clt.qmc_safe is False


def test_clt_rejects_non_multiple_of_12():
    clt = CLTTransform()
    rng = np.random.default_rng(0)
    u = rng.random((10, 7))
    with pytest.raises(ValueError):
        clt.transform(u)


def test_box_muller_rejects_odd_total():
    bm = BoxMullerTransform()
    rng = np.random.default_rng(0)
    u = rng.random((3, 5))
    with pytest.raises(ValueError):
        bm.transform(u)


@pytest.mark.parametrize(
    "qmc_sampler_factory",
    [lambda: SobolSampler(max_dimensions=4), lambda: HaltonSampler(max_dimensions=4)],
    ids=["sobol", "halton"],
)
@pytest.mark.parametrize(
    "bad_transform",
    [BoxMullerTransform(), CLTTransform()],
    ids=["box_muller", "clt"],
)
def test_factory_rejects_qmc_with_unsafe_transform(qmc_sampler_factory, bad_transform):
    with pytest.raises(ValueError, match="not QMC-safe"):
        make_normal_sampler(qmc_sampler_factory(), bad_transform)


@pytest.mark.parametrize(
    "qmc_sampler_factory",
    [lambda: SobolSampler(max_dimensions=4), lambda: HaltonSampler(max_dimensions=4)],
    ids=["sobol", "halton"],
)
@pytest.mark.parametrize(
    "good_transform",
    [MoroTransform(), AcklamTransform(), WichuraAS241Transform()],
    ids=["moro", "acklam", "wichura"],
)
def test_factory_accepts_qmc_with_safe_transform(qmc_sampler_factory, good_transform):
    ns = make_normal_sampler(qmc_sampler_factory(), good_transform)
    z = ns.next_block(2048, 4)
    assert z.shape == (2048, 4)
    assert abs(z.mean()) < 0.05
