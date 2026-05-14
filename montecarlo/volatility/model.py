"""Abstract base class for diffusion-side volatility models."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class VolModel(ABC):
    """Diffusion coefficient consumed by the Monte Carlo path engine.

    A concrete :class:`VolModel` returns the instantaneous lognormal
    volatility ``sigma(t, S; state)`` per path for one time step. The path
    engine integrates ``dS_t = (r - q) S_t dt + sigma(t, S_t) S_t dW_t``
    using whatever scheme it chooses (Euler-log, Milstein, etc.); the model
    itself is stateless from the engine's perspective — any path-dependent
    state lives in the ``state`` dictionary owned by the engine.

    The ``state`` channel is plumbed from day one even though the models in
    this PR (``ConstantVol``, ``BlackTermStructureVol``) ignore it. Future
    stochastic-vol models (Heston, SABR) will read keys such as
    ``state["variance"]`` or ``state["alpha"]``; keeping the signature stable
    means adding those models will not churn the path-engine call site.
    """

    @abstractmethod
    def diffusion(
        self,
        time: float,
        spot: np.ndarray,
        state: dict | None = None,
    ) -> np.ndarray:
        """Return per-path instantaneous volatility at ``(time, spot)``.

        Parameters
        ----------
        time
            Year fraction from the model's reference date; non-negative.
        spot
            Per-path spot values, shape ``(n_paths,)``. Scalars and 0-d
            arrays are accepted and broadcast.
        state
            Optional dict carrying path-dependent auxiliary state (variance
            for Heston, alpha for SABR, etc.). Stateless models ignore it.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``spot.shape`` with the per-path
            instantaneous volatility.
        """
