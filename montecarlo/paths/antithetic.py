"""Antithetic variance reduction in the normal domain.

For payoffs that are monotone in the underlying Brownian increments, pairing
each path ``Z`` with its sign-flipped twin ``-Z`` produces two negatively
correlated estimates of the payoff. Averaging the pair has the same
expectation as a single i.i.d. draw but a strictly smaller variance, so the
stderr at fixed total path count is reduced. The reduction is largest for
near-linear payoffs (e.g. ATM vanilla calls) and tends to zero for payoffs
with no monotonic structure in the Brownian path (e.g. mid-strike straddles).

The wrapper is **strictly incompatible with quasi-random base samplers**:
appending ``-Z`` to a Sobol block produces a sequence with rank ``n / 2``
in normal space, destroying the low-discrepancy structure the Sobol /
Wichura pairing was chosen for. The construction refuses this combination
with a :class:`ValueError`, matching the existing Box-Muller + Sobol rule
enforced by :func:`montecarlo.normal.factory.make_normal_sampler`.
"""

from __future__ import annotations

import logging

import numpy as np

from ..normal.factory import NormalSampler
from ..sampler import Sampler

logger = logging.getLogger(__name__)


class AntitheticNormalSampler:
    """Wrap a :class:`NormalSampler` so each block pairs ``Z`` with ``-Z``.

    The wrapper draws ``n_paths // 2`` independent normals from the base
    sampler and stacks them on top of their negation to produce a
    ``(n_paths, n_dimensions)`` block. The first half is the underlying
    sequence; the second half is its reflection.

    Path count must be even — the antithetic pairing is a hard structural
    constraint, not a convention. An odd ``n_paths`` raises rather than
    silently dropping or duplicating a path.

    Attributes
    ----------
    base
        The wrapped :class:`NormalSampler`.
    """

    def __init__(
        self,
        base: NormalSampler,
    ) -> None:
        """Wrap a normal sampler, refusing the construction on a quasi base.

        Parameters
        ----------
        base
            The :class:`NormalSampler` to wrap. Its underlying ``Sampler``
            must be pseudo-random (``is_quasi == False``).

        Raises
        ------
        ValueError
            If ``base.sampler.is_quasi`` is ``True``. Appending the
            reflection of a Sobol / Halton block to itself produces a
            rank-deficient sequence and destroys the low-discrepancy
            structure that QMC was chosen for.
        """
        if base.sampler.is_quasi:
            raise ValueError(
                f"antithetic sampling destroys the low-discrepancy structure of "
                f"{type(base.sampler).__name__}; pair antithetic=True with a "
                f"pseudo-random base (e.g. MersenneTwisterSampler, "
                f"LecuyerMRG32k3a1999Sampler) instead."
            )
        self.base = base
        logger.info(
            "AntitheticNormalSampler wrapping %s",
            type(base.sampler).__name__,
        )

    @property
    def sampler(self) -> Sampler:
        """Return the underlying uniform sampler of the wrapped normal sampler.

        Engines introspect this attribute to check the QMC pairing rule.
        """
        return self.base.sampler

    def next_block(
        self,
        n_paths: int,
        n_dimensions: int,
    ) -> np.ndarray:
        """Return a ``(n_paths, n_dimensions)`` block with antithetic pairs.

        Parameters
        ----------
        n_paths
            Number of paths in the block; must be even.
        n_dimensions
            Number of normals per path.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)``. Rows
            ``0..n_paths/2 - 1`` are independent standard normals drawn from
            the base sampler; rows ``n_paths/2..n_paths - 1`` equal the
            negation of the corresponding upper half.

        Raises
        ------
        ValueError
            If ``n_paths`` is odd. The antithetic pair is a hard structural
            constraint, not a soft heuristic.
        """
        if n_paths % 2 != 0:
            raise ValueError(
                f"AntitheticNormalSampler requires even n_paths, got {n_paths}"
            )
        half = n_paths // 2
        upper = self.base.next_block(half, n_dimensions)
        out = np.empty((n_paths, n_dimensions), dtype=np.float64)
        out[:half, :] = upper
        out[half:, :] = -upper
        return out

    def reset(self) -> None:
        """Reset the underlying base sampler to its post-construction state."""
        self.base.reset()
