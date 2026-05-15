"""Tests for ``montecarlo.paths.EulerLogPathEngine`` (non-anchor coverage)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import norm

from montecarlo import (
    BlackTermStructureVol,
    ConstantVol,
    EulerLogPathEngine,
    MersenneTwisterSampler,
    TimeGrid,
    WichuraAS241Transform,
    make_normal_sampler,
)
from montecarlo.normal.factory import NormalSampler


def _flat_forward(
    spot: float,
    rate: float,
    dividend_yield: float = 0.0,
):
    """Return a callable ``F(t) = spot * exp((r - q) t)``."""
    drift = rate - dividend_yield
    return lambda t: spot * math.exp(drift * t)


def _make_sampler(seed: int = 42) -> NormalSampler:
    return make_normal_sampler(
        MersenneTwisterSampler(seed=seed),
        WichuraAS241Transform(),
    )


# ---------------------------------------------------------------------------
# Shape / construction / validation
# ---------------------------------------------------------------------------


def test_simulate_shape_and_initial_slice() -> None:
    spot = 100.0
    grid = TimeGrid([0.0, 0.25, 0.5, 1.0])
    engine = EulerLogPathEngine(
        spots=spot,
        forward_curves=_flat_forward(spot, 0.03),
        vol_models=ConstantVol(0.2),
        time_grid=grid,
        normal_sampler=_make_sampler(),
    )
    paths = engine.simulate(7)
    assert paths.shape == (7, 4, 1)
    assert paths.dtype == np.float64
    np.testing.assert_allclose(paths[:, 0, 0], spot)
    assert np.all(np.isfinite(paths))
    assert np.all(paths > 0.0)


def test_scalar_inputs_coerced_to_n_assets_one() -> None:
    grid = TimeGrid([0.0, 0.5, 1.0])
    engine = EulerLogPathEngine(
        spots=42.0,
        forward_curves=_flat_forward(42.0, 0.0),
        vol_models=ConstantVol(0.15),
        time_grid=grid,
        normal_sampler=_make_sampler(),
    )
    assert engine.n_assets == 1
    out = engine.simulate(3)
    assert out.shape == (3, 3, 1)


def test_non_positive_spot_raises() -> None:
    grid = TimeGrid([0.0, 1.0])
    with pytest.raises(ValueError, match="strictly positive"):
        EulerLogPathEngine(
            spots=-1.0,
            forward_curves=lambda t: 1.0,
            vol_models=ConstantVol(0.2),
            time_grid=grid,
            normal_sampler=_make_sampler(),
        )


def test_length_mismatch_raises() -> None:
    grid = TimeGrid([0.0, 1.0])
    with pytest.raises(ValueError, match="matching length"):
        EulerLogPathEngine(
            spots=[100.0, 50.0],
            forward_curves=[_flat_forward(100.0, 0.03)],
            vol_models=[ConstantVol(0.2), ConstantVol(0.3)],
            time_grid=grid,
            normal_sampler=_make_sampler(),
        )


def test_non_positive_n_paths_raises() -> None:
    grid = TimeGrid([0.0, 1.0])
    engine = EulerLogPathEngine(
        spots=100.0,
        forward_curves=_flat_forward(100.0, 0.0),
        vol_models=ConstantVol(0.2),
        time_grid=grid,
        normal_sampler=_make_sampler(),
    )
    with pytest.raises(ValueError, match="strictly positive integer"):
        engine.simulate(0)
    with pytest.raises(ValueError, match="strictly positive integer"):
        engine.simulate(-5)
    with pytest.raises(ValueError, match="strictly positive integer"):
        engine.simulate(3.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Reserved kwargs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, expected_pr",
    [
        ({"antithetic": True}, "PR 2"),
        ({"brownian_bridge": True}, "PR 3"),
        ({"correlation": object()}, "PR 4"),
    ],
)
def test_reserved_kwargs_raise(kwargs: dict, expected_pr: str) -> None:
    grid = TimeGrid([0.0, 1.0])
    with pytest.raises(NotImplementedError, match=expected_pr):
        EulerLogPathEngine(
            spots=100.0,
            forward_curves=_flat_forward(100.0, 0.0),
            vol_models=ConstantVol(0.2),
            time_grid=grid,
            normal_sampler=_make_sampler(),
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Sampler dimension contract — locks the convention PR 3 will rely on.
# ---------------------------------------------------------------------------


class _CountingNormalSampler:
    """Counts ``next_block`` invocations and records dimension arguments."""

    def __init__(self, base: NormalSampler) -> None:
        self.base = base
        self.calls: list[tuple[int, int]] = []

    @property
    def sampler(self):
        return self.base.sampler

    def next_block(self, n_paths: int, n_dimensions: int) -> np.ndarray:
        self.calls.append((n_paths, n_dimensions))
        return self.base.next_block(n_paths, n_dimensions)

    def reset(self) -> None:
        self.base.reset()


def test_sampler_called_once_with_n_steps_times_n_assets_dim() -> None:
    grid = TimeGrid([0.0, 0.25, 0.5, 0.75, 1.0])  # n_steps=4
    counter = _CountingNormalSampler(_make_sampler())
    engine = EulerLogPathEngine(
        spots=100.0,
        forward_curves=_flat_forward(100.0, 0.0),
        vol_models=ConstantVol(0.2),
        time_grid=grid,
        normal_sampler=counter,  # type: ignore[arg-type]
    )
    engine.simulate(11)
    assert counter.calls == [(11, 4 * 1)]  # exactly one call


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_reset_then_simulate_is_bitwise_reproducible() -> None:
    grid = TimeGrid([0.0, 0.25, 0.5, 1.0])
    sampler = _make_sampler(seed=123)
    engine = EulerLogPathEngine(
        spots=100.0,
        forward_curves=_flat_forward(100.0, 0.0),
        vol_models=ConstantVol(0.2),
        time_grid=grid,
        normal_sampler=sampler,
    )
    first = engine.simulate(50)
    sampler.reset()
    second = engine.simulate(50)
    np.testing.assert_array_equal(first, second)


# ---------------------------------------------------------------------------
# Distributional and pricing correctness
# ---------------------------------------------------------------------------


def test_flat_vol_log_normal_moments() -> None:
    """Under ConstantVol + flat forward, log(S_T / S_0) ~ N((r-q-0.5 sigma^2) T, sigma^2 T)."""
    spot, rate, sigma, T = 100.0, 0.03, 0.2, 1.0
    grid = TimeGrid([0.0, T])
    engine = EulerLogPathEngine(
        spots=spot,
        forward_curves=_flat_forward(spot, rate),
        vol_models=ConstantVol(sigma),
        time_grid=grid,
        normal_sampler=_make_sampler(seed=7),
    )
    n = 200_000
    paths = engine.simulate(n)
    log_ret = np.log(paths[:, -1, 0] / spot)
    expected_mean = (rate - 0.5 * sigma * sigma) * T
    expected_std = sigma * math.sqrt(T)
    # Stderr on the mean is sigma * sqrt(T) / sqrt(n) ~ 0.000447; allow 4*stderr.
    assert abs(log_ret.mean() - expected_mean) < 4 * expected_std / math.sqrt(n)
    # Std deviation: relative tolerance ~ 1/sqrt(2 n) ~ 1.6e-3; allow factor 4.
    assert abs(log_ret.std(ddof=1) - expected_std) < 4 * expected_std / math.sqrt(2 * n)


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


def test_constant_vol_reprices_black_scholes_atm_call() -> None:
    spot, strike, rate, sigma, T = 100.0, 100.0, 0.03, 0.2, 1.0
    grid = TimeGrid(np.linspace(0.0, T, 25))
    engine = EulerLogPathEngine(
        spots=spot,
        forward_curves=_flat_forward(spot, rate),
        vol_models=ConstantVol(sigma),
        time_grid=grid,
        normal_sampler=_make_sampler(seed=2026),
    )
    n = 200_000
    paths = engine.simulate(n)
    payoff = np.maximum(paths[:, -1, 0] - strike, 0.0)
    discount = math.exp(-rate * T)
    mc_price = discount * payoff.mean()
    stderr = discount * payoff.std(ddof=1) / math.sqrt(n)
    bs = _bs_call(spot, strike, rate, sigma, T)
    # Allow 3 * stderr to keep the test deterministic across seeds.
    assert abs(mc_price - bs) < 3 * stderr
    # Sanity: stderr should be small enough that the test is meaningful.
    assert stderr < 0.05


# ---------------------------------------------------------------------------
# BlackTermStructureVol — ATM repricing end-to-end through the engine.
# ---------------------------------------------------------------------------


class _FlatATMSurface:
    """Minimal VolSurface with three ATM pillars at a constant vol."""

    def __init__(self, sigma: float) -> None:
        from datetime import date as _date

        self._sigma = sigma
        self._ref = _date(2025, 1, 1)
        self._expiries = [0.25, 0.5, 1.0]

    @property
    def reference_date(self):
        return self._ref

    @property
    def expiries(self) -> list[float]:
        return list(self._expiries)

    def forward(self, time_to_expiry: float) -> float:
        return 100.0  # unused by BlackTermStructureVol (only ATM column matters)

    def implied_vol(self, time_to_expiry: float, strike: float) -> float:
        return self._sigma

    def total_variance(self, time_to_expiry: float, log_moneyness: float) -> float:
        return self._sigma * self._sigma * time_to_expiry


def test_black_term_structure_vol_reprices_flat_atm_call() -> None:
    sigma = 0.25
    spot, strike, rate, T = 100.0, 100.0, 0.0, 1.0
    surface = _FlatATMSurface(sigma)
    grid = TimeGrid([0.0, 0.25, 0.5, 0.75, T])
    engine = EulerLogPathEngine(
        spots=spot,
        forward_curves=_flat_forward(spot, rate),
        vol_models=BlackTermStructureVol(surface),
        time_grid=grid,
        normal_sampler=_make_sampler(seed=99),
    )
    n = 100_000
    paths = engine.simulate(n)
    payoff = np.maximum(paths[:, -1, 0] - strike, 0.0)
    mc_price = payoff.mean()
    stderr = payoff.std(ddof=1) / math.sqrt(n)
    bs = _bs_call(spot, strike, rate, sigma, T)
    assert abs(mc_price - bs) < 3 * stderr
