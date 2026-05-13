"""End-to-end smoke tests for the ``(sampler, transform)`` composite stack."""

from __future__ import annotations

import pytest

from montecarlo import (
    AcklamTransform,
    BoxMullerTransform,
    LecuyerMRG32k3a1999Sampler,
    MersenneTwisterSampler,
    MoroTransform,
    SobolSampler,
    WichuraAS241Transform,
    make_normal_sampler,
)
from montecarlo.diagnostics.integration import (
    bs_call_price_mc,
    integrate_gaussian_moment,
)


_BS_PARAMS = dict(spot=100.0, strike=100.0, rate=0.05, sigma=0.2, maturity=1.0)


@pytest.mark.parametrize(
    "sampler_factory, transform, label",
    [
        (lambda: LecuyerMRG32k3a1999Sampler(seed=1), MoroTransform(), "mrg+moro"),
        (lambda: LecuyerMRG32k3a1999Sampler(seed=1), AcklamTransform(), "mrg+acklam"),
        (lambda: LecuyerMRG32k3a1999Sampler(seed=1), WichuraAS241Transform(), "mrg+wichura"),
        (lambda: LecuyerMRG32k3a1999Sampler(seed=1), BoxMullerTransform(), "mrg+box_muller"),
        (lambda: MersenneTwisterSampler(seed=1), MoroTransform(), "mt+moro"),
        (lambda: SobolSampler(max_dimensions=2, skip=1024), MoroTransform(), "sobol+moro"),
        (lambda: SobolSampler(max_dimensions=2, skip=1024), AcklamTransform(), "sobol+acklam"),
        (
            lambda: SobolSampler(max_dimensions=2, skip=1024),
            WichuraAS241Transform(),
            "sobol+wichura",
        ),
    ],
)
def test_bs_call_within_three_std_errors(sampler_factory, transform, label):
    ns = make_normal_sampler(sampler_factory(), transform)
    res = bs_call_price_mc(ns, n_paths=50_000, **_BS_PARAMS)
    band = max(3.0 * res.std_error, 0.05)
    assert abs(res.error) < band, f"{label}: error {res.error:.4f} std_err {res.std_error:.4f}"


def test_gaussian_second_moment():
    ns = make_normal_sampler(LecuyerMRG32k3a1999Sampler(seed=99), AcklamTransform())
    res = integrate_gaussian_moment(ns, moment=2, n_paths=200_000)
    assert abs(res.error) < 4.0 * res.std_error


def test_qmc_beats_prng_on_bs_call():
    paths = 4096
    ns_prng = make_normal_sampler(MersenneTwisterSampler(seed=11), BoxMullerTransform())
    err_prng = abs(bs_call_price_mc(ns_prng, n_paths=paths, **_BS_PARAMS).error)
    ns_qmc = make_normal_sampler(
        SobolSampler(max_dimensions=2, skip=paths), WichuraAS241Transform()
    )
    err_qmc = abs(bs_call_price_mc(ns_qmc, n_paths=paths, **_BS_PARAMS).error)
    assert err_qmc < err_prng, (
        f"QMC error {err_qmc:.4f} did not beat PRNG error {err_prng:.4f}"
    )
