"""Arbitrage diagnostics for differentiable volatility surfaces.

Two checks live here, both anchored on the canonical-coordinate identities
spelled out in :mod:`market_structures.volatility.surface`:

- **Butterfly arbitrage** (Roper 2010, Gatheral-Jacquier 2014). For a single
  expiry slice ``w(k)``, the Durrleman function

      g(k) = (1 - k * w'(k) / (2 * w(k)))^2
             - (w'(k))^2 / 4 * (1 / w(k) + 1 / 4)
             + w''(k) / 2

  must satisfy ``g(k) >= 0`` everywhere for the slice to be free of butterfly
  arbitrage. A negative ``g(k)`` corresponds to a negative state-price density
  at strike ``F(T) * exp(k)``.
- **Calendar arbitrage**. For total variance ``w(T, k)``, the slice family is
  free of calendar arbitrage iff ``dw/dT >= 0`` for every ``(T, k)``. This is
  exactly the requirement that no fixed-strike vanilla is cheaper at a longer
  expiry than at a shorter one.

Both checks consume :class:`~market_structures.volatility.DifferentiableVolSurface`
instances so the derivatives in the formulas are evaluated analytically. For
plain :class:`~market_structures.volatility.VolSurface` instances the user
must first wrap the surface in something that exposes ``dw_dT`` / ``dw_dk`` /
``d2w_dk2``; this module does not approximate them numerically.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from .surface import DifferentiableVolSurface

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ButterflyReport:
    """Result of :func:`check_butterfly`.

    Attributes
    ----------
    is_arb_free
        ``True`` iff ``g(k) >= -tol`` on the queried grid.
    g_min
        Minimum of ``g(k)`` on the grid.
    k_at_min
        Log-moneyness at which the minimum was attained.
    expiry
        Time-to-expiry of the slice (echoed back for caller convenience).
    """

    is_arb_free: bool
    g_min: float
    k_at_min: float
    expiry: float


@dataclass(frozen=True)
class CalendarReport:
    """Result of :func:`check_calendar`.

    Attributes
    ----------
    is_arb_free
        ``True`` iff ``dw/dT >= -tol`` on the full ``(T, k)`` grid.
    min_dw_dT
        Minimum of ``dw/dT`` on the grid.
    T_at_min
        Time-to-expiry at which the minimum was attained.
    k_at_min
        Log-moneyness at which the minimum was attained.
    """

    is_arb_free: bool
    min_dw_dT: float
    T_at_min: float
    k_at_min: float


def durrleman_g(
    surface: DifferentiableVolSurface,
    time_to_expiry: float,
    log_moneyness: float,
) -> float:
    """Return the Durrleman function ``g(k)`` at ``(T, k_log)``.

    Parameters
    ----------
    surface
        Surface exposing ``total_variance``, ``dw_dk``, ``d2w_dk2``.
    time_to_expiry
        Year fraction from the surface's reference date; strictly positive.
    log_moneyness
        ``k_log = log(K / F(T))``.

    Returns
    -------
    float
        ``g(k) = (1 - k * w' / (2w))^2 - (w')^2 / 4 * (1/w + 1/4) + w'' / 2``.
        Must be non-negative for a butterfly-arbitrage-free slice.
    """
    w = surface.total_variance(time_to_expiry, log_moneyness)
    wp = surface.dw_dk(time_to_expiry, log_moneyness)
    wpp = surface.d2w_dk2(time_to_expiry, log_moneyness)
    term_skew = (1.0 - log_moneyness * wp / (2.0 * w)) ** 2
    term_smile = (wp * wp) / 4.0 * (1.0 / w + 0.25)
    return term_skew - term_smile + wpp / 2.0


def check_butterfly(
    surface: DifferentiableVolSurface,
    time_to_expiry: float,
    k_grid: Sequence[float],
    tol: float = 1e-10,
) -> ButterflyReport:
    """Evaluate :func:`durrleman_g` on a grid and report the minimum.

    Parameters
    ----------
    surface
        Surface to probe.
    time_to_expiry
        Expiry slice at which to check butterfly arbitrage.
    k_grid
        Log-moneyness grid on which to sample ``g(k)``. Should cover both
        wings (e.g. ``np.linspace(-3, 3, 401)`` is a common choice for
        equity).
    tol
        Negative slack tolerance. ``g_min >= -tol`` is treated as arb-free.

    Returns
    -------
    ButterflyReport
        Worst-case ``g`` on the grid and the corresponding ``k``.
    """
    if len(k_grid) == 0:
        raise ValueError("k_grid must be non-empty")
    k_iter = iter(k_grid)
    k0 = float(next(k_iter))
    g0 = durrleman_g(surface, time_to_expiry, k0)
    g_min = g0
    k_at_min = k0
    for k in k_iter:
        k = float(k)
        g = durrleman_g(surface, time_to_expiry, k)
        if g < g_min:
            g_min = g
            k_at_min = k
    is_arb_free = g_min >= -tol
    if not is_arb_free:
        logger.info(
            "butterfly arbitrage at T=%.4f: g_min=%.6e at k=%.4f",
            time_to_expiry,
            g_min,
            k_at_min,
        )
    return ButterflyReport(
        is_arb_free=is_arb_free,
        g_min=g_min,
        k_at_min=k_at_min,
        expiry=time_to_expiry,
    )


def check_calendar(
    surface: DifferentiableVolSurface,
    T_grid: Sequence[float],
    k_grid: Sequence[float],
    tol: float = 1e-10,
) -> CalendarReport:
    """Evaluate ``dw/dT`` on a ``(T, k)`` grid and report the minimum.

    Parameters
    ----------
    surface
        Surface exposing ``dw_dT``.
    T_grid
        Time-to-expiry samples; all strictly positive.
    k_grid
        Log-moneyness samples.
    tol
        Negative slack tolerance. ``min_dw_dT >= -tol`` is arb-free.

    Returns
    -------
    CalendarReport
        Worst-case ``dw/dT`` and the corresponding ``(T, k)``.
    """
    if len(T_grid) == 0 or len(k_grid) == 0:
        raise ValueError("T_grid and k_grid must both be non-empty")
    min_val = float("inf")
    T_at_min = 0.0
    k_at_min = 0.0
    for T in T_grid:
        T = float(T)
        for k in k_grid:
            k = float(k)
            val = surface.dw_dT(T, k)
            if val < min_val:
                min_val = val
                T_at_min = T
                k_at_min = k
    is_arb_free = min_val >= -tol
    if not is_arb_free:
        logger.info(
            "calendar arbitrage: min_dw_dT=%.6e at T=%.4f k=%.4f",
            min_val,
            T_at_min,
            k_at_min,
        )
    return CalendarReport(
        is_arb_free=is_arb_free,
        min_dw_dT=min_val,
        T_at_min=T_at_min,
        k_at_min=k_at_min,
    )
