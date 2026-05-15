"""Abstract base for Monte Carlo path engines."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class PathEngine(ABC):
    """Abstract Monte Carlo path engine.

    Concrete engines simulate one or more correlated underlyings on a fixed
    :class:`~montecarlo.paths.TimeGrid` and return the path tensor

        ``S[path, step, asset]``

    of shape ``(n_paths, n_steps + 1, n_assets)`` where the leading time slice
    ``S[:, 0, :]`` holds the broadcast initial spots and subsequent slices
    follow the engine's discretisation scheme. ``n_assets == 1`` for a
    single-underlying engine; the trailing axis is preserved so consumers do not
    need to special-case basket vs single-name geometry.
    """

    @abstractmethod
    def simulate(
        self,
        n_paths: int,
    ) -> np.ndarray:
        """Return simulated spot paths.

        Parameters
        ----------
        n_paths
            Number of Monte Carlo paths.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_steps + 1, n_assets)``.
            ``out[:, 0, :]`` equals the engine's initial spots broadcast across
            paths.
        """
