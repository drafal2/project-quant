"""Sobol low-discrepancy sequence with Joe-Kuo (2008) direction numbers.

Generates the gray-code Sobol sequence in 32-bit integer arithmetic. Direction
numbers for dimensions 2 through 1024 come from the table compiled in
:mod:`_joe_kuo_data`; dimension 1 is handled inline as the trivial van der
Corput sequence in base 2.

The point at integer index 0 is the origin and is skipped (it would yield zero
in every coordinate, breaking the strict open-interval contract of
:meth:`Sampler.next_block`). The returned point at row ``k`` corresponds to
Sobol index ``index_at_construction + k + 1``.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler
from ._joe_kuo_data import JOE_KUO_PARAMS, MAX_DIMENSION

logger = logging.getLogger(__name__)

_BITS = 32
_TWO_POW_BITS = float(1 << _BITS)
_FAC = 1.0 / _TWO_POW_BITS


def _build_direction_table(
    n_dimensions: int,
) -> np.ndarray:
    """Build the direction-number table for the first ``n_dimensions`` dimensions.

    Parameters
    ----------
    n_dimensions
        Number of dimensions to populate. Must be at least 1.

    Returns
    -------
    numpy.ndarray
        ``uint32`` array of shape ``(_BITS, n_dimensions)``. Entry ``[j - 1, d]``
        is the direction integer ``V_j`` for dimension ``d`` (1-indexed in the
        Sobol literature; here both axes are 0-indexed).
    """
    table = np.zeros((_BITS, n_dimensions), dtype=np.uint32)
    for j in range(1, _BITS + 1):
        table[j - 1, 0] = 1 << (_BITS - j)
    for d in range(1, n_dimensions):
        s, a, m_init = JOE_KUO_PARAMS[d - 1]
        m = [0] * (_BITS + 1)
        for i in range(1, s + 1):
            m[i] = m_init[i - 1]
        for j in range(s + 1, _BITS + 1):
            value = m[j - s] ^ (m[j - s] << s)
            for k in range(1, s):
                bit = (a >> (s - 1 - k)) & 1
                if bit:
                    value ^= m[j - k] << k
            m[j] = value
        for j in range(1, _BITS + 1):
            table[j - 1, d] = (m[j] << (_BITS - j)) & 0xFFFF_FFFF
    return table


class SobolSampler(Sampler):
    """Sobol low-discrepancy sequence with Joe-Kuo direction numbers.

    Notes
    -----
    Pros
        Near-optimal star discrepancy, ``~1/N`` convergence on smooth
        integrands (versus ``~1/sqrt(N)`` for any PRNG), and Joe-Kuo direction
        numbers extend the construction to thousands of dimensions while
        keeping the all-important two-dimensional projections well-distributed.
    Cons
        More complex implementation; requires a lookup table; the
        unscrambled form is deterministic (no built-in error estimate — use
        randomised Sobol if a standard error is needed).
    Use when
        Default QMC choice for the equity basket autocall and other smooth /
        moderately-rough payoffs.
    """

    is_quasi = True

    def __init__(
        self,
        max_dimensions: int = 256,
        skip: int = 0,
    ) -> None:
        """Initialise the Sobol sampler.

        Parameters
        ----------
        max_dimensions
            Maximum supported dimension; capped by ``MAX_DIMENSION`` of the
            shipped Joe-Kuo table (currently 1024). Pre-computes direction
            numbers for all ``max_dimensions`` columns.
        skip
            Number of Sobol points to discard from the start of the sequence
            after the mandatory origin skip. A common choice is the largest
            power of two below the target sample count, which empirically
            improves equidistribution for small ``N``.

        Raises
        ------
        ValueError
            If ``max_dimensions`` exceeds the shipped table or ``skip`` is
            negative.
        """
        if max_dimensions < 1 or max_dimensions > MAX_DIMENSION:
            raise ValueError(
                f"max_dimensions must be in [1, {MAX_DIMENSION}], got {max_dimensions}"
            )
        if skip < 0:
            raise ValueError("skip must be >= 0")
        self.dimensions = max_dimensions
        self._skip = skip
        self._V = _build_direction_table(max_dimensions)
        self.reset()

    def reset(self) -> None:
        """Rewind the sequence to its post-construction position (origin + skip)."""
        self._state = np.zeros(self.dimensions, dtype=np.uint32)
        self._counter = 0
        if self._skip > 0:
            self._advance(self._skip)

    def _advance(
        self,
        n: int,
    ) -> None:
        """Step the running XOR state forward by ``n`` Sobol points, discarding output.

        Parameters
        ----------
        n
            Number of Sobol points to skip.
        """
        if n <= 0:
            return
        c_arr = _trailing_zeros_plus_one(self._counter, n)
        cum = np.bitwise_xor.accumulate(self._V[c_arr - 1, :], axis=0)
        self._state = (self._state ^ cum[-1]).astype(np.uint32)
        self._counter += n

    def next_block(
        self,
        n_paths: int,
        n_dimensions: int,
    ) -> np.ndarray:
        """Return the next ``n_paths`` Sobol points in ``n_dimensions``.

        Parameters
        ----------
        n_paths
            Number of consecutive Sobol points to draw.
        n_dimensions
            Number of dimensions; must not exceed ``self.dimensions``.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)`` with values
            strictly in ``(0, 1)``.

        Raises
        ------
        ValueError
            If ``n_dimensions`` exceeds the pre-built direction table.
        """
        if n_dimensions > self.dimensions:
            raise ValueError(
                f"requested {n_dimensions} dimensions but sampler was built "
                f"with max_dimensions={self.dimensions}"
            )
        c_arr = _trailing_zeros_plus_one(self._counter, n_paths)
        step_v = self._V[c_arr - 1, :n_dimensions]
        cum = np.bitwise_xor.accumulate(step_v, axis=0)
        state_slice = self._state[:n_dimensions]
        out = (state_slice ^ cum).astype(np.uint32)
        self._state[:n_dimensions] = out[-1]
        self._counter += n_paths
        return (out.astype(np.float64) + 0.5) * _FAC

    @property
    def state(self) -> dict:
        """Return the sequence counter and dimensionality.

        Returns
        -------
        dict
            Keys: ``counter``, ``skip``, ``max_dimensions``.
        """
        return {
            "counter": int(self._counter),
            "skip": self._skip,
            "max_dimensions": self.dimensions,
        }


def _trailing_zeros_plus_one(
    start: int,
    n: int,
) -> np.ndarray:
    """Return the rightmost-zero bit position (1-indexed) of ``i`` for ``i`` in a range.

    The Sobol gray-code recurrence steps the running state ``X_n = X_{n-1}
    XOR V_{c(n - 1)}`` where ``c(k) = trailing_zeros(k + 1) + 1`` is the
    bit position of the rightmost zero of ``k``. This helper returns
    ``c(start), c(start + 1), ..., c(start + n - 1)`` as a numpy array,
    using the identity ``c(k) = ctz(k + 1) + 1``.

    Parameters
    ----------
    start
        First index in the range (inclusive).
    n
        Number of consecutive indices to evaluate.

    Returns
    -------
    numpy.ndarray
        ``int32`` array of length ``n`` with values in ``[1, _BITS]``.
    """
    indices_plus_one = np.arange(start + 1, start + 1 + n, dtype=np.int64)
    isolated_bit = indices_plus_one & (-indices_plus_one)
    return (np.log2(isolated_bit.astype(np.float64)).astype(np.int32) + 1)
