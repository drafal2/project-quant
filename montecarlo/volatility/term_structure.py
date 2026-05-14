"""Black term-structure volatility built from the ATM column of a quote surface.

The instantaneous lognormal volatility ``sigma_inst(t)`` is recovered from the
surface's ATM total variance ``w_ATM(T) = sigma_imp(T, F(T))^2 * T`` at the
pillar grid by the standard market relation

    w_ATM(T) = integral_0^T sigma_inst(u)^2 du,

solved by piecewise-constant differentiation:

    sigma_inst^2 on (T_{i-1}, T_i]  =  (w_i - w_{i-1}) / (T_i - T_{i-1}),

with the anchor ``T_0 = 0``, ``w_0 = 0``. Under this construction the MC
diffusion ``dS = (r - q) S dt + sigma_inst(t) S dW`` reprices every pillar
ATM vanilla exactly, by construction of the total-variance integral.

Skew is ignored: the model is the QuantLib ``BlackVarianceCurve`` analog, not a
local-vol bridge. The full skew-aware bridge lands as ``DupireLocalVol`` in a
later PR.
"""

from __future__ import annotations

import logging

import numpy as np

from market_structures.volatility.surface import VolSurface

from .model import VolModel

logger = logging.getLogger(__name__)


class BlackTermStructureVol(VolModel):
    """Piecewise-constant instantaneous vol from the ATM column of a surface.

    Reads ``surface.total_variance(T_i, 0.0)`` at the surface's pillar grid,
    differentiates to instantaneous volatility, and returns a piecewise-constant
    sigma over the segments ``(T_{i-1}, T_i]``. Calendar arbitrage in the
    surface (non-monotone ATM total variance in ``T``) is rejected at
    construction time with :class:`ValueError` — the square root of a negative
    variance increment is undefined.

    Parameters
    ----------
    surface
        Any :class:`~market_structures.volatility.VolSurface` whose ``expiries``
        list and ATM column are well-defined. ``InterpolatedVolSurface`` is the
        primary concrete subclass today; SVI / SSVI parametric surfaces will
        slot in here without API change.

    Attributes
    ----------
    surface
        The injected :class:`VolSurface` (read-only reference).
    pillars
        Copy of the surface's expiry grid in ACT/365 years.
    sigma_inst
        Per-segment instantaneous volatility, length ``len(pillars)``. Entry
        ``i`` is constant over ``(T_{i-1}, T_i]`` with the convention
        ``T_{-1} = 0``.

    Raises
    ------
    ValueError
        If the surface exposes no expiries, or if the ATM total variance is
        non-monotone in ``T`` (calendar arbitrage).
    """

    def __init__(
        self,
        surface: VolSurface,
    ) -> None:
        expiries = list(surface.expiries)
        if not expiries:
            raise ValueError("surface exposes no expiries")
        pillars = np.asarray(expiries, dtype=np.float64)
        if pillars[0] <= 0.0:
            raise ValueError(
                f"first expiry must be strictly positive, got {pillars[0]!r}"
            )
        if np.any(np.diff(pillars) <= 0.0):
            raise ValueError("expiries must be strictly increasing")

        w_atm = np.array(
            [surface.total_variance(float(t), 0.0) for t in pillars],
            dtype=np.float64,
        )
        # Anchor at (T=0, w=0). dt has length N, dw has length N.
        dt = np.diff(pillars, prepend=0.0)
        dw = np.diff(w_atm, prepend=0.0)
        if np.any(dw < 0.0):
            raise ValueError(
                "calendar arbitrage: ATM total variance non-monotone in T"
            )
        sigma_inst = np.sqrt(dw / dt)

        self._surface = surface
        self._pillars = pillars
        self._sigma_inst = sigma_inst

        logger.info(
            "BlackTermStructureVol pillars=%d T_range=[%.4f, %.4f] sigma_range=[%.4f, %.4f]",
            pillars.size,
            float(pillars[0]),
            float(pillars[-1]),
            float(sigma_inst.min()),
            float(sigma_inst.max()),
        )

    @property
    def surface(self) -> VolSurface:
        """Return the injected vol surface."""
        return self._surface

    @property
    def pillars(self) -> np.ndarray:
        """Return a copy of the pillar grid."""
        return self._pillars.copy()

    @property
    def sigma_inst(self) -> np.ndarray:
        """Return a copy of the per-segment instantaneous vol."""
        return self._sigma_inst.copy()

    def diffusion(
        self,
        time: float,
        spot: np.ndarray,
        state: dict | None = None,
    ) -> np.ndarray:
        """Return the piecewise-constant ``sigma_inst(time)`` broadcast to ``spot``.

        Parameters
        ----------
        time
            Year fraction; must be non-negative. For ``time > T_N`` the last
            segment's vol is extended (flat extrapolation).
        spot
            Per-path spot values; only the shape is consulted.
        state
            Ignored.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``np.shape(spot)`` filled with the
            segment's instantaneous volatility.

        Raises
        ------
        ValueError
            If ``time < 0``.
        """
        if time < 0.0:
            raise ValueError(f"time must be non-negative, got {time!r}")
        # Segments are (T_{i-1}, T_i] with T_{-1}=0. searchsorted with
        # side='left' on the pillar array puts t == T_i into index i, which is
        # the right-closed convention.
        idx = int(np.searchsorted(self._pillars, time, side="left"))
        if idx >= self._sigma_inst.size:
            idx = self._sigma_inst.size - 1
        return np.full(np.shape(spot), self._sigma_inst[idx], dtype=np.float64)
