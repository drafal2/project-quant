"""Constant-volatility model: a single scalar sigma, independent of time and spot."""

from __future__ import annotations

import logging

import numpy as np

from .model import VolModel

logger = logging.getLogger(__name__)


class ConstantVol(VolModel):
    """Flat lognormal volatility, the textbook Black-Scholes diffusion.

    Useful as a sanity model (closed-form vanilla prices match the MC output)
    and as a smoke-test fixture for the path engine. Time, spot, and any
    stochastic-vol state are ignored.

    Parameters
    ----------
    sigma
        Annualised lognormal volatility; must be strictly positive.
    """

    def __init__(
        self,
        sigma: float,
    ) -> None:
        if sigma <= 0.0:
            raise ValueError(f"sigma must be strictly positive, got {sigma!r}")
        self._sigma = float(sigma)
        logger.info("ConstantVol sigma=%.6f", self._sigma)

    @property
    def sigma(self) -> float:
        """Return the stored constant volatility."""
        return self._sigma

    def diffusion(
        self,
        time: float,
        spot: np.ndarray,
        state: dict | None = None,
    ) -> np.ndarray:
        """Return ``sigma`` broadcast to the shape of ``spot``.

        Parameters
        ----------
        time
            Year fraction; ignored.
        spot
            Per-path spot values; only the shape is consulted.
        state
            Ignored.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``np.shape(spot)`` filled with ``sigma``.
        """
        return np.full(np.shape(spot), self._sigma, dtype=np.float64)
