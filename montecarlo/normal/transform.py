"""Abstract base for transforms from ``U(0, 1)`` to ``N(0, 1)``."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class NormalTransform(ABC):
    """Abstract base for transforms mapping ``U(0, 1)`` samples to ``N(0, 1)``.

    Each concrete transform is paired with a uniform :class:`~montecarlo.Sampler`
    via :func:`~montecarlo.make_normal_sampler`. The class attribute
    ``qmc_safe`` declares whether the transform preserves the low-discrepancy
    property of a quasi-random input. Box-Muller and the central-limit
    transform are *not* QMC-safe and must not be paired with Sobol or Halton;
    the factory enforces this.

    Attributes
    ----------
    qmc_safe
        Class-level flag: ``True`` if the transform preserves low-discrepancy
        structure (the inverse-cumulative family — Moro, Acklam, Wichura
        AS241), ``False`` otherwise (Box-Muller, CLT).
    uniforms_per_normal
        Number of input uniforms required to produce a single output normal.
        ``1`` for the inverse-cumulative family and Box-Muller (which is
        ``2 \\to 2`` and consumes 1-to-1 over a full block); ``12`` for the
        central-limit transform. The composite :class:`NormalSampler` reads
        this flag to size the input uniform block correctly.
    """

    qmc_safe: bool = False
    uniforms_per_normal: int = 1

    @abstractmethod
    def transform(
        self,
        uniforms: np.ndarray,
    ) -> np.ndarray:
        """Map a block of uniforms to standard normals.

        Parameters
        ----------
        uniforms
            ``float64`` array of shape ``(n_paths, n_dimensions * uniforms_per_normal)``
            with values in ``(0, 1)``.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)`` distributed
            as ``N(0, 1)`` under repeated sampling.
        """
