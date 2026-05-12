"""Factory pairing a uniform ``Sampler`` with a ``NormalTransform``.

The factory enforces the QMC / inversion pairing rule documented in the
package docstring: low-discrepancy samplers must use an inverse-cumulative
transform; pairing them with a non-QMC-safe transform raises ``ValueError``.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler
from .transform import NormalTransform

logger = logging.getLogger(__name__)


class NormalSampler:
    """A uniform :class:`~montecarlo.Sampler` composed with a :class:`NormalTransform`.

    The constructor is normally not called directly — use
    :func:`make_normal_sampler` which performs the QMC / inversion compatibility
    check.

    Attributes
    ----------
    sampler
        Underlying uniform sampler.
    transform
        Inverse-cumulative or Box-Muller-style transform applied to each block.
    """

    def __init__(
        self,
        sampler: Sampler,
        transform: NormalTransform,
    ) -> None:
        """Initialise the composite sampler.

        Parameters
        ----------
        sampler
            A uniform sampler from :mod:`montecarlo.uniform`.
        transform
            A normal transform from :mod:`montecarlo.normal`.
        """
        self.sampler = sampler
        self.transform = transform

    def next_block(
        self,
        n_paths: int,
        n_dimensions: int,
    ) -> np.ndarray:
        """Draw a block of standard normals of shape ``(n_paths, n_dimensions)``.

        Parameters
        ----------
        n_paths
            Number of Monte Carlo paths in this block.
        n_dimensions
            Number of independent normals per path.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)`` distributed
            as ``N(0, 1)``.
        """
        u_dim = n_dimensions * self.transform.uniforms_per_normal
        uniforms = self.sampler.next_block(n_paths, u_dim)
        return self.transform.transform(uniforms)

    def reset(self) -> None:
        """Reset the underlying uniform sampler to its post-construction state."""
        self.sampler.reset()


def make_normal_sampler(
    sampler: Sampler,
    transform: NormalTransform,
) -> NormalSampler:
    """Pair a uniform sampler with a normal transform, enforcing QMC compatibility.

    Parameters
    ----------
    sampler
        Any concrete :class:`~montecarlo.Sampler`.
    transform
        Any concrete :class:`NormalTransform`.

    Returns
    -------
    NormalSampler
        Ready-to-use composite that yields standard normals via ``next_block``.

    Raises
    ------
    ValueError
        If ``sampler.is_quasi`` is ``True`` and ``transform.qmc_safe`` is
        ``False``. The Box-Muller transform and the central-limit transform
        both fail this check; pair Sobol or Halton with ``MoroTransform``,
        ``AcklamTransform``, or ``WichuraAS241Transform`` instead.
    """
    if sampler.is_quasi and not transform.qmc_safe:
        raise ValueError(
            f"{type(transform).__name__} is not QMC-safe and cannot be paired "
            f"with {type(sampler).__name__}. Use MoroTransform, AcklamTransform, "
            f"or WichuraAS241Transform with low-discrepancy samplers."
        )
    logger.info(
        "Built NormalSampler: %s + %s",
        type(sampler).__name__,
        type(transform).__name__,
    )
    return NormalSampler(sampler, transform)
