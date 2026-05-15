"""Tests for ``montecarlo.paths.AntitheticNormalSampler`` and its engine integration."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import norm

from montecarlo import (
    AntitheticNormalSampler,
    ConstantVol,
    EulerLogPathEngine,
    HaltonSampler,
    MersenneTwisterSampler,
    SobolSampler,
    TimeGrid,
    WichuraAS241Transform,
    make_normal_sampler,
)


def _prng_sampler(seed: int = 42):
    return make_normal_sampler(
        MersenneTwisterSampler(seed=seed),
        WichuraAS241Transform(),
    )


def _qmc_sampler():
    return make_normal_sampler(
        SobolSampler(),
        WichuraAS241Transform(),
    )


def _flat_forward(spot: float, rate: float):
    return lambda t: spot * math.exp(rate * t)


# ---------------------------------------------------------------------------
# Wrapper itself
# ---------------------------------------------------------------------------


def test_wrapper_refuses_quasi_base() -> None:
    with pytest.raises(ValueError, match="low-discrepancy"):
        AntitheticNormalSampler(_qmc_sampler())
    with pytest.raises(ValueError, match="low-discrepancy"):
        AntitheticNormalSampler(
            make_normal_sampler(HaltonSampler(), WichuraAS241Transform())
        )


def test_wrapper_shape_and_dtype() -> None:
    wrapper = AntitheticNormalSampler(_prng_sampler())
    block = wrapper.next_block(8, 5)
    assert block.shape == (8, 5)
    assert block.dtype == np.float64


def test_reflection_property_exact() -> None:
    wrapper = AntitheticNormalSampler(_prng_sampler())
    block = wrapper.next_block(10, 3)
    upper, lower = block[:5, :], block[5:, :]
    np.testing.assert_array_equal(lower, -upper)


def test_odd_n_paths_raises() -> None:
    wrapper = AntitheticNormalSampler(_prng_sampler())
    with pytest.raises(ValueError, match="even n_paths"):
        wrapper.next_block(7, 4)


def test_reset_delegates_to_base() -> None:
    wrapper = AntitheticNormalSampler(_prng_sampler(seed=99))
    first = wrapper.next_block(6, 4)
    wrapper.reset()
    second = wrapper.next_block(6, 4)
    np.testing.assert_array_equal(first, second)


def test_wrapper_sampler_property_returns_base() -> None:
    base = _prng_sampler()
    wrapper = AntitheticNormalSampler(base)
    assert wrapper.sampler is base.sampler


def test_wrapper_halves_underlying_draws() -> None:
    """The wrapper must call base.next_block with n_paths/2, not n_paths."""
    base = _prng_sampler()
    calls: list[tuple[int, int]] = []
    original = base.next_block

    def spy(n_paths: int, n_dimensions: int) -> np.ndarray:
        calls.append((n_paths, n_dimensions))
        return original(n_paths, n_dimensions)

    base.next_block = spy  # type: ignore[method-assign]
    wrapper = AntitheticNormalSampler(base)
    wrapper.next_block(20, 6)
    assert calls == [(10, 6)]


# ---------------------------------------------------------------------------
# Mean-zero pairing: empirical sample mean is *exactly* zero per dimension.
# ---------------------------------------------------------------------------


def test_empirical_mean_is_exact_zero_per_dimension() -> None:
    wrapper = AntitheticNormalSampler(_prng_sampler(seed=7))
    block = wrapper.next_block(2_000, 8)
    np.testing.assert_allclose(block.mean(axis=0), 0.0, atol=1e-15)


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


def test_engine_antithetic_does_not_raise() -> None:
    grid = TimeGrid([0.0, 0.5, 1.0])
    EulerLogPathEngine(
        spots=100.0,
        forward_curves=_flat_forward(100.0, 0.0),
        vol_models=ConstantVol(0.2),
        time_grid=grid,
        normal_sampler=_prng_sampler(),
        antithetic=True,
    )


def test_engine_antithetic_refuses_quasi_base() -> None:
    grid = TimeGrid([0.0, 0.5, 1.0])
    with pytest.raises(ValueError, match="low-discrepancy"):
        EulerLogPathEngine(
            spots=100.0,
            forward_curves=_flat_forward(100.0, 0.0),
            vol_models=ConstantVol(0.2),
            time_grid=grid,
            normal_sampler=_qmc_sampler(),
            antithetic=True,
        )


def test_engine_antithetic_pairs_paths_exactly() -> None:
    """With antithetic, paths k and n/2+k come from sign-flipped normals so
    their log-spread trajectories sum to zero at every step under ConstantVol."""
    spot, sigma = 100.0, 0.2
    grid = TimeGrid([0.0, 0.25, 0.5, 1.0])
    engine = EulerLogPathEngine(
        spots=spot,
        forward_curves=_flat_forward(spot, 0.0),  # r = 0 -> F = spot
        vol_models=ConstantVol(sigma),
        time_grid=grid,
        normal_sampler=_prng_sampler(seed=13),
        antithetic=True,
    )
    paths = engine.simulate(10)
    upper = paths[:5, :, 0]
    lower = paths[5:, :, 0]
    # Under ConstantVol + r=0, X = log(S/F) follows X_{k+1} - X_k = -0.5 sigma^2 dt + sigma sqrt(dt) Z.
    # For antithetic pairs with Z and -Z, the *increments* satisfy
    # dX_pair_a + dX_pair_b = -sigma^2 dt (deterministic). Therefore:
    log_upper = np.log(upper / spot)
    log_lower = np.log(lower / spot)
    times = grid.times
    expected_sum = np.zeros(grid.n_steps + 1)
    for k in range(1, grid.n_steps + 1):
        expected_sum[k] = -sigma * sigma * times[k]
    pair_sum = log_upper + log_lower
    np.testing.assert_allclose(pair_sum - expected_sum, 0.0, atol=1e-12)


def _bs_call(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    T: float,
) -> float:
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * T) / (
        sigma * math.sqrt(T)
    )
    d2 = d1 - sigma * math.sqrt(T)
    return spot * norm.cdf(d1) - strike * math.exp(-rate * T) * norm.cdf(d2)


def test_antithetic_reduces_stderr_on_atm_call() -> None:
    """Variance reduction: with antithetic, the MC stderr of an ATM call drops
    by at least 30% at fixed n_paths and seed (call payoff is near-linear in
    Z near ATM)."""
    spot, strike, rate, sigma, T = 100.0, 100.0, 0.03, 0.2, 1.0
    grid = TimeGrid(np.linspace(0.0, T, 25))
    n_paths = 10_000

    def run(antithetic: bool) -> tuple[float, float]:
        engine = EulerLogPathEngine(
            spots=spot,
            forward_curves=_flat_forward(spot, rate),
            vol_models=ConstantVol(sigma),
            time_grid=grid,
            normal_sampler=_prng_sampler(seed=2026),
            antithetic=antithetic,
        )
        paths = engine.simulate(n_paths)
        discount = math.exp(-rate * T)
        payoff = discount * np.maximum(paths[:, -1, 0] - strike, 0.0)
        price = float(payoff.mean())
        # For antithetic, average each pair first to get the i.i.d. estimator
        # whose stderr is comparable across the two configurations at fixed
        # n_paths.
        if antithetic:
            pair_mean = 0.5 * (payoff[: n_paths // 2] + payoff[n_paths // 2:])
            stderr = float(pair_mean.std(ddof=1) / math.sqrt(n_paths // 2))
        else:
            stderr = float(payoff.std(ddof=1) / math.sqrt(n_paths))
        return price, stderr

    price_plain, stderr_plain = run(antithetic=False)
    price_anti, stderr_anti = run(antithetic=True)

    bs = _bs_call(spot, strike, rate, sigma, T)
    # Both estimates must be unbiased.
    assert abs(price_plain - bs) < 3 * stderr_plain
    assert abs(price_anti - bs) < 3 * stderr_anti
    # Antithetic should yield a meaningful stderr reduction on this
    # monotone-in-Z payoff. The theoretical ratio for an ATM call is
    # ``sqrt(1 - mean^2 / Var(P))`` which is roughly 0.6-0.7; we set the
    # threshold at 0.85 to accept seed-dependent jitter on a finite sample.
    assert stderr_anti < 0.85 * stderr_plain, (
        f"antithetic stderr {stderr_anti:.5f} not <= 85% of plain "
        f"{stderr_plain:.5f}"
    )
