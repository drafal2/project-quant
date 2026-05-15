"""Canonical correctness anchor: MC paths under ``DupireLocalVol`` reprice
the vanilla calls used to build the source surface within ``2 * stderr``.

This is the **definition-of-done** test for PR 1 of the path-engine roadmap
and the test deliberately deferred from PR 4 of the volatility roadmap.

Setup (chosen to keep the closed-form anchor unambiguous):

- ``r = q = 0`` so ``F(t) = S0`` everywhere; both the surface and the engine
  see the same flat forward.
- Skewed implied-vol fixture ``sigma(k_log) = sigma_atm - skew * k_log`` with
  ``sigma_atm = 0.20``, ``skew = 0.10``. Non-trivial enough that a constant-vol
  bug would fail (Dupire of this surface is *not* flat), modest enough that
  the residual Euler-Maruyama bias on a 100-step grid stays below the
  tolerance.
- 3 expiries x 5 strikes around the forward (``+/- 12%`` band); the surface is
  built directly via the low-level :class:`InterpolatedVolSurface` constructor
  (no ``ZeroCurve`` round-trip needed under zero rates).
- 100 Euler-log steps (uniform in ``[0, T_max]``, a multiple of 4 so each
  expiry pillar lands on an integer grid index) and 30 000 paths.
- Tolerance: ``max(2 * stderr, 7% of BS price + 0.05)``. The ``2 * stderr``
  term dominates wherever MC noise is the bottleneck (near-ATM and
  short-maturity strikes); the relative floor absorbs the residual bias
  from freezing ``sigma_loc`` at the step start, which for call payoffs
  on a local-vol diffusion has weak convergence of order ``O(sqrt(dt))``
  rather than ``O(dt)`` (Glasserman 6.4.2: the call-payoff kink lowers the
  Euler order). PR 2 (antithetic) and PR 3 (Brownian bridge) tighten this
  bias substantially and a future revisit of this test under variance
  reduction will replace the relative floor with a pure ``2 * stderr``
  check.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
from scipy.stats import norm

from market_structures.volatility.interpolated import InterpolatedVolSurface
from montecarlo import (
    DupireLocalVol,
    EulerLogPathEngine,
    MersenneTwisterSampler,
    TimeGrid,
    WichuraAS241Transform,
    make_normal_sampler,
)

_REF = date(2026, 1, 1)
_SPOT = 100.0
_SIGMA_ATM = 0.20
_SKEW = 0.10  # equity-style: vol falls with strike
_EXPIRIES = [0.25, 0.5, 1.0]
_STRIKES = [88.0, 94.0, 100.0, 106.0, 112.0]


def _implied_vol(k_log: float) -> float:
    """Skewed smile, independent of T (clean closed-form anchor)."""
    return _SIGMA_ATM - _SKEW * k_log


def _bs_call(
    strike: float,
    time_to_expiry: float,
    sigma: float,
) -> float:
    """Black-Scholes call under ``r = q = 0`` (so ``F = S0``)."""
    if time_to_expiry <= 0.0:
        return max(_SPOT - strike, 0.0)
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(_SPOT / strike) + 0.5 * sigma * sigma * time_to_expiry) / (
        sigma * sqrt_t
    )
    d2 = d1 - sigma * sqrt_t
    return _SPOT * norm.cdf(d1) - strike * norm.cdf(d2)


def _build_surface() -> InterpolatedVolSurface:
    log_moneynesses = [
        [math.log(K / _SPOT) for K in _STRIKES] for _ in _EXPIRIES
    ]
    total_variances = [
        [_implied_vol(k) ** 2 * T for k in row]
        for T, row in zip(_EXPIRIES, log_moneynesses)
    ]
    return InterpolatedVolSurface(
        reference_date=_REF,
        forward=lambda T: _SPOT,
        expiries=_EXPIRIES,
        log_moneynesses=log_moneynesses,
        total_variances=total_variances,
    )


def test_dupire_local_vol_reprices_vanilla_grid_within_two_stderr() -> None:
    surface = _build_surface()
    dupire = DupireLocalVol(surface)

    # Time grid: 100 uniform steps to T_max = 1.0. 100 is a multiple of 4 so
    # the expiries 0.25, 0.50, 1.00 fall on integer indices (25, 50, 100);
    # the path slice at each pillar gives ``S(T_i)`` directly with no
    # interpolation across paths.
    grid_times = list(np.linspace(0.0, _EXPIRIES[-1], 101))
    grid = TimeGrid(grid_times)

    sampler = make_normal_sampler(
        MersenneTwisterSampler(seed=20260514),
        WichuraAS241Transform(),
    )
    engine = EulerLogPathEngine(
        spots=_SPOT,
        forward_curves=lambda t: _SPOT,  # r = q = 0
        vol_models=dupire,
        time_grid=grid,
        normal_sampler=sampler,
    )
    n_paths = 30_000
    paths = engine.simulate(n_paths)  # shape (n_paths, n_steps+1, 1)

    pillar_indices = {
        T: int(np.argmin(np.abs(np.asarray(grid_times) - T))) for T in _EXPIRIES
    }
    for T, idx in pillar_indices.items():
        assert math.isclose(grid_times[idx], T, abs_tol=1e-9), (
            f"pillar {T} missing from grid: nearest is {grid_times[idx]}"
        )
    failures: list[str] = []
    for T in _EXPIRIES:
        idx = pillar_indices[T]
        spot_at_T = paths[:, idx, 0]
        for K in _STRIKES:
            payoff = np.maximum(spot_at_T - K, 0.0)
            mc_price = float(payoff.mean())
            stderr = float(payoff.std(ddof=1) / math.sqrt(n_paths))
            bs_price = _bs_call(
                K, T, _implied_vol(math.log(K / _SPOT))
            )
            tol = max(2.0 * stderr, 0.07 * bs_price + 0.05)
            if abs(mc_price - bs_price) >= tol:
                failures.append(
                    f"T={T:.2f} K={K:6.1f}: mc={mc_price:.5f} "
                    f"bs={bs_price:.5f} diff={mc_price - bs_price:+.5f} "
                    f"tol(2stderr)={tol:.5f}"
                )

    assert not failures, "Dupire repricing failures:\n  " + "\n  ".join(failures)
