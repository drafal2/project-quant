"""Abstract base for all uniform samplers (pseudo-random and low-discrepancy)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Sampler(ABC):
    """Abstract base for uniform samplers on the open unit cube ``(0, 1)^d``.

    The contract is *dimension-aware* on purpose: every call to ``next_block``
    must specify how many independent uniforms each path needs. Pseudo-random
    samplers (``KnuthSampler``, ``MRG32k3aSampler``, ``MersenneTwisterSampler``)
    treat the dimension argument as a reshape; low-discrepancy samplers
    (``HaltonSampler``, ``SobolSampler``) treat it as the structural dimension
    of the Sobol/Halton point and *cannot* be made dimension-agnostic without
    breaking correctness.

    Concrete subclasses set the class attribute ``is_quasi`` to ``True`` if and
    only if they implement a low-discrepancy sequence; the normal-transform
    factory relies on this flag to enforce the QMC / inversion pairing rule.

    Attributes
    ----------
    is_quasi
        Class-level flag: ``True`` for Sobol / Halton, ``False`` for PRNGs.
    """

    is_quasi: bool = False

    @abstractmethod
    def next_block(
        self,
        n_paths: int,
        n_dimensions: int,
    ) -> np.ndarray:
        """Return a block of uniforms with shape ``(n_paths, n_dimensions)``.

        All entries lie strictly in the open interval ``(0, 1)``. The open
        interval matters for downstream inverse-cumulative transforms which
        would diverge at ``0`` or ``1``.

        Parameters
        ----------
        n_paths
            Number of Monte Carlo paths in this block (rows of the output).
        n_dimensions
            Number of independent uniforms each path needs (columns of the
            output). For low-discrepancy samplers this is the structural
            dimension of the sequence and is fixed for the lifetime of a single
            call sequence; mixing dimensions across calls produces an
            ill-defined sequence and is rejected.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)`` with values
            in ``(0, 1)``.
        """

    @abstractmethod
    def reset(self) -> None:
        """Restore the sampler to the state it had immediately after construction.

        For PRNGs this re-seeds; for low-discrepancy samplers this rewinds the
        sequence to point zero. After ``reset()``, replaying the same
        ``next_block`` calls must return bit-identical results.
        """

    @property
    @abstractmethod
    def state(self) -> dict:
        """Return a snapshot of the internal state, suitable for diagnostics.

        Subclasses should return a shallow dictionary that uniquely identifies
        the sampler's current position in its sequence.

        Returns
        -------
        dict
            Snapshot of internal state. The exact keys are implementation
            defined; consumers should treat this as opaque except for equality
            and printing.
        """
