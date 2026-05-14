"""Dupire local volatility — the bridge from a quote-side surface to MC diffusion.

The local-vol diffusion coefficient ``sigma_loc(t, S)`` is the unique
Markov-state coefficient under which the SDE

    dS_t = (r - q) S_t dt + sigma_loc(t, S_t) S_t dW_t

reprices every vanilla call that defines the input volatility surface
(Dupire 1994). In the project's canonical coordinates
``w(T, k_log) = sigma_imp^2 * T`` with ``k_log = log(K / F(T))``, the
formula reads (Gatheral 2006, *The Volatility Surface*, ch. 1):

    sigma_loc^2(T, k_log)
        = (dw/dT)
          / [
              1 - (k_log / (2 w)) * dw_dk
                + (1/4) * (-1/4 - 1/w + k_log^2 / w^2) * (dw_dk)^2
                + (1/2) * d2w_dk2
            ]

This module ships ``DupireLocalVol(surface)``, a :class:`VolModel` sibling of
``ConstantVol`` and ``BlackTermStructureVol``. Two execution paths are
dispatched on the input surface type:

- :class:`~market_structures.volatility.DifferentiableVolSurface` (SVI, SSVI):
  the four canonical quantities are evaluated **analytically** on every call;
  no grid is built.
- Plain :class:`~market_structures.volatility.VolSurface`
  (``InterpolatedVolSurface`` and others without closed-form derivatives): the
  module pre-computes ``sigma_loc^2`` on a ``(t, k_log)`` grid using central
  finite differences against the surface, with clipping to a positive floor
  where the Dupire denominator goes non-positive (butterfly arbitrage in the
  source surface) or where ``dw/dT`` is negative (calendar arbitrage).
  Runtime evaluation is bilinear interpolation of the pre-computed grid.

Both paths expose two public queries:

- :meth:`DupireLocalVol.local_variance` — ``sigma_loc^2(T, k_log)`` in surface
  coordinates, used by closed-form identity tests and the QuantLib
  cross-check.
- :meth:`DupireLocalVol.diffusion` — per-path ``sigma_loc(t, S)`` with the
  ``(time, spot, state)`` signature of the path-engine contract.
"""

from __future__ import annotations

import logging
import math
import warnings
from collections.abc import Sequence

import numpy as np

from market_structures.volatility.surface import (
    DifferentiableVolSurface,
    VolSurface,
)

from .model import VolModel

logger = logging.getLogger(__name__)

_DENOM_EPS = 1e-8
_DEFAULT_SIGMA_FLOOR = 0.01
_DEFAULT_CLIP_WARN_THRESHOLD = 0.01  # 1% of grid points triggers the warning
_NUM_FD_H_T = 1e-4
_NUM_FD_H_K = 1e-3


class DupireLocalVol(VolModel):
    """Dupire local-vol diffusion coefficient from a quote-side surface.

    Parameters
    ----------
    surface
        Source :class:`VolSurface`. If the surface also subclasses
        :class:`DifferentiableVolSurface`, the analytical path is used and
        no grid is built. Otherwise a numerical-derivative grid is
        pre-computed.
    t_grid
        Optional time-axis override for the numerical grid (ignored for the
        analytical path). Sorted, strictly positive.
    k_grid
        Optional log-moneyness axis override for the numerical grid.
        Sorted, strictly increasing.
    sigma_floor
        Positive floor applied when the Dupire denominator collapses or the
        numerator goes negative. Default ``0.01``.
    clip_warning_threshold
        Fraction of grid points that, when clipped, triggers a
        :class:`UserWarning`. Only meaningful for the numerical path.

    Raises
    ------
    ValueError
        On non-positive ``sigma_floor`` or malformed override grids.
    """

    def __init__(
        self,
        surface: VolSurface,
        t_grid: Sequence[float] | None = None,
        k_grid: Sequence[float] | None = None,
        sigma_floor: float = _DEFAULT_SIGMA_FLOOR,
        clip_warning_threshold: float = _DEFAULT_CLIP_WARN_THRESHOLD,
    ) -> None:
        if sigma_floor <= 0.0:
            raise ValueError(
                f"sigma_floor must be strictly positive, got {sigma_floor!r}"
            )
        self._surface = surface
        self._sigma_floor = float(sigma_floor)
        self._sigma_floor_sq = self._sigma_floor * self._sigma_floor
        self._is_analytical = isinstance(surface, DifferentiableVolSurface)

        if self._is_analytical:
            if t_grid is not None or k_grid is not None:
                raise ValueError(
                    "t_grid / k_grid are only valid for the numerical path; "
                    "the analytical Dupire path uses no grid"
                )
            self._t_grid: np.ndarray | None = None
            self._k_grid: np.ndarray | None = None
            self._sigma_sq_grid: np.ndarray | None = None
            logger.info(
                "DupireLocalVol built: mode=analytical surface=%s",
                type(surface).__name__,
            )
            return

        # Numerical-grid path.
        ts, ks = self._build_grid(surface, t_grid, k_grid)
        sigma_sq, n_clipped, worst = self._compute_grid(surface, ts, ks)
        self._t_grid = ts
        self._k_grid = ks
        self._sigma_sq_grid = sigma_sq

        n_total = ts.size * ks.size
        clip_frac = n_clipped / n_total
        if clip_frac > clip_warning_threshold:
            worst_t, worst_k = worst
            warnings.warn(
                f"DupireLocalVol clipped {n_clipped}/{n_total} grid points "
                f"({clip_frac:.2%}); worst at t={worst_t:.4f} k_log={worst_k:.4f}. "
                f"Check the surface for butterfly or calendar arbitrage.",
                UserWarning,
                stacklevel=2,
            )
        logger.info(
            "DupireLocalVol built: mode=grid surface=%s n_t=%d n_k=%d n_clipped=%d",
            type(surface).__name__,
            ts.size,
            ks.size,
            n_clipped,
        )

    @property
    def surface(self) -> VolSurface:
        """Return the source surface (read-only reference)."""
        return self._surface

    @property
    def is_analytical(self) -> bool:
        """``True`` if dispatch uses the analytical Dupire formula."""
        return self._is_analytical

    @property
    def sigma_floor(self) -> float:
        """Return the positive floor applied on degenerate Dupire denominators."""
        return self._sigma_floor

    @property
    def t_grid(self) -> np.ndarray | None:
        """Return a copy of the numerical-grid time axis (``None`` if analytical)."""
        return None if self._t_grid is None else self._t_grid.copy()

    @property
    def k_grid(self) -> np.ndarray | None:
        """Return a copy of the numerical-grid log-moneyness axis."""
        return None if self._k_grid is None else self._k_grid.copy()

    def local_variance(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``sigma_loc^2(T, k_log)`` in surface coordinates.

        Parameters
        ----------
        time_to_expiry
            Year fraction from the surface's reference date; strictly positive.
        log_moneyness
            ``k_log = log(K / F(T))``.

        Returns
        -------
        float
            Local variance ``sigma_loc^2``, always at least ``sigma_floor^2``.
        """
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        if self._is_analytical:
            return self._analytical_local_variance(time_to_expiry, log_moneyness)
        assert self._t_grid is not None and self._k_grid is not None
        assert self._sigma_sq_grid is not None
        return self._bilinear_interp(
            time_to_expiry, log_moneyness, self._t_grid, self._k_grid, self._sigma_sq_grid
        )

    def diffusion(
        self,
        time: float,
        spot: np.ndarray,
        state: dict | None = None,
    ) -> np.ndarray:
        """Return per-path ``sigma_loc(t, S)`` with shape ``np.shape(spot)``.

        Parameters
        ----------
        time
            Year fraction from the surface's reference date; strictly positive
            (Dupire is singular at ``t = 0``).
        spot
            Per-path spot values; ``log_moneyness = log(spot / F(time))`` is
            computed pointwise.
        state
            Ignored (Dupire is Markov in ``(t, S)`` alone).

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``np.shape(spot)``.
        """
        if time <= 0.0:
            raise ValueError(f"time must be strictly positive, got {time!r}")
        spot_arr = np.asarray(spot, dtype=np.float64)
        if np.any(spot_arr <= 0.0):
            raise ValueError("all spot values must be strictly positive")
        fwd = float(self._surface.forward(time))
        k_log_arr = np.log(spot_arr / fwd)
        # Vectorise by mapping local_variance over the flattened k_log array.
        flat = k_log_arr.ravel()
        sigma_sq = np.empty_like(flat)
        for i, k in enumerate(flat):
            sigma_sq[i] = self.local_variance(time, float(k))
        return np.sqrt(sigma_sq).reshape(spot_arr.shape)

    # ---------- analytical path -------------------------------------------------

    def _analytical_local_variance(
        self,
        T: float,
        k: float,
    ) -> float:
        surf = self._surface
        # mypy: surface is DifferentiableVolSurface here.
        assert isinstance(surf, DifferentiableVolSurface)
        w = surf.total_variance(T, k)
        if w <= 0.0:
            return self._sigma_floor_sq
        dw_dT = surf.dw_dT(T, k)
        dw_dk = surf.dw_dk(T, k)
        d2w_dk2 = surf.d2w_dk2(T, k)
        return self._dupire_from_w(w, dw_dT, dw_dk, d2w_dk2, k)

    # ---------- numerical path --------------------------------------------------

    def _build_grid(
        self,
        surface: VolSurface,
        t_override: Sequence[float] | None,
        k_override: Sequence[float] | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        # Time axis.
        if t_override is not None:
            ts = np.asarray(t_override, dtype=np.float64)
            if ts.size < 2 or np.any(np.diff(ts) <= 0.0):
                raise ValueError("t_grid must be strictly increasing with >= 2 points")
            if np.any(ts <= 0.0):
                raise ValueError("t_grid entries must be strictly positive")
        else:
            expiries = list(surface.expiries)
            t_min = 0.5 * expiries[0]
            t_max = 1.5 * expiries[-1]
            ts = np.linspace(t_min, t_max, 50)
        # k axis.
        if k_override is not None:
            ks = np.asarray(k_override, dtype=np.float64)
            if ks.size < 2 or np.any(np.diff(ks) <= 0.0):
                raise ValueError("k_grid must be strictly increasing with >= 2 points")
        else:
            # sigma_max at k=0 across pillars.
            sigmas = [
                math.sqrt(max(surface.total_variance(T, 0.0), 0.0) / T)
                for T in surface.expiries
            ]
            sigma_max = max(sigmas) if sigmas else 0.4
            T_max = float(ts[-1])
            half_width = 3.0 * sigma_max * math.sqrt(T_max)
            ks = np.linspace(-half_width, half_width, 100)
        return ts, ks

    def _compute_grid(
        self,
        surface: VolSurface,
        ts: np.ndarray,
        ks: np.ndarray,
    ) -> tuple[np.ndarray, int, tuple[float, float]]:
        sigma_sq = np.empty((ts.size, ks.size), dtype=np.float64)
        n_clipped = 0
        worst_clip_t = float(ts[0])
        worst_clip_k = float(ks[0])
        for i, T in enumerate(ts):
            T = float(T)
            for j, k in enumerate(ks):
                k = float(k)
                w = surface.total_variance(T, k)
                if w <= 0.0:
                    sigma_sq[i, j] = self._sigma_floor_sq
                    n_clipped += 1
                    continue
                # Central finite differences against the surface.
                h_t = max(_NUM_FD_H_T, 1e-3 * T)
                h_k = _NUM_FD_H_K
                T_lo = max(T - h_t, 1e-12)
                T_hi = T + h_t
                w_T_lo = surface.total_variance(T_lo, k)
                w_T_hi = surface.total_variance(T_hi, k)
                dw_dT = (w_T_hi - w_T_lo) / (T_hi - T_lo)
                w_k_lo = surface.total_variance(T, k - h_k)
                w_k_hi = surface.total_variance(T, k + h_k)
                dw_dk = (w_k_hi - w_k_lo) / (2.0 * h_k)
                d2w_dk2 = (w_k_hi - 2.0 * w + w_k_lo) / (h_k * h_k)
                value = self._dupire_from_w(w, dw_dT, dw_dk, d2w_dk2, k)
                if value <= self._sigma_floor_sq:
                    n_clipped += 1
                    if value < sigma_sq[i, max(j - 1, 0)] - 1e-9:
                        worst_clip_t = T
                        worst_clip_k = k
                sigma_sq[i, j] = max(value, self._sigma_floor_sq)
        return sigma_sq, n_clipped, (worst_clip_t, worst_clip_k)

    def _dupire_from_w(
        self,
        w: float,
        dw_dT: float,
        dw_dk: float,
        d2w_dk2: float,
        k: float,
    ) -> float:
        """Dupire formula applied to pre-computed canonical-coordinate quantities."""
        if dw_dT < 0.0:
            return self._sigma_floor_sq
        denom = (
            1.0
            - (k / (2.0 * w)) * dw_dk
            + 0.25 * (-0.25 - 1.0 / w + (k * k) / (w * w)) * (dw_dk * dw_dk)
            + 0.5 * d2w_dk2
        )
        if denom <= _DENOM_EPS:
            return self._sigma_floor_sq
        return dw_dT / denom

    def _bilinear_interp(
        self,
        T: float,
        k: float,
        ts: np.ndarray,
        ks: np.ndarray,
        grid: np.ndarray,
    ) -> float:
        # Time-axis clip.
        if T <= ts[0]:
            T_idx_lo = 0
            T_alpha = 0.0
        elif T >= ts[-1]:
            T_idx_lo = ts.size - 2
            T_alpha = 1.0
        else:
            T_idx_lo = int(np.searchsorted(ts, T, side="right") - 1)
            T_idx_lo = min(T_idx_lo, ts.size - 2)
            T_alpha = (T - ts[T_idx_lo]) / (ts[T_idx_lo + 1] - ts[T_idx_lo])
        # k-axis clip.
        if k <= ks[0]:
            k_idx_lo = 0
            k_alpha = 0.0
        elif k >= ks[-1]:
            k_idx_lo = ks.size - 2
            k_alpha = 1.0
        else:
            k_idx_lo = int(np.searchsorted(ks, k, side="right") - 1)
            k_idx_lo = min(k_idx_lo, ks.size - 2)
            k_alpha = (k - ks[k_idx_lo]) / (ks[k_idx_lo + 1] - ks[k_idx_lo])
        # Bilinear blend.
        v00 = grid[T_idx_lo, k_idx_lo]
        v01 = grid[T_idx_lo, k_idx_lo + 1]
        v10 = grid[T_idx_lo + 1, k_idx_lo]
        v11 = grid[T_idx_lo + 1, k_idx_lo + 1]
        v_lo = v00 + k_alpha * (v01 - v00)
        v_hi = v10 + k_alpha * (v11 - v10)
        return float(v_lo + T_alpha * (v_hi - v_lo))
