"""Sobol low-discrepancy sequence with Joe-Kuo (2008) direction numbers.

Abbreviations used in this module:

- **QMC** — Quasi-Monte Carlo. A class of deterministic point sets
  (Sobol, Halton, lattice rules, ...) designed to fill the unit hypercube
  more uniformly than independent random samples — buying a faster
  convergence rate (``~ 1/N`` for smooth integrands, vs ``1/√N`` for any
  PRNG) at the cost of losing the standard-error CI.
- **Star discrepancy** — the supremum over axis-aligned anchored boxes of
  ``|empirical_measure(box) − Lebesgue(box)|``; the canonical quality
  measure for QMC point sets. Sobol attains the lowest known asymptotic
  star discrepancy in arbitrary dimension.
- **Direction numbers** — the per-dimension binary expansion of the
  Sobol point coordinate at each bit position; chosen to satisfy the
  ``(t, m, s)``-net property for the underlying primitive polynomial.
  The Joe-Kuo (2008) table improves the choice in high dimensions.
- **Gray code** — a binary encoding where consecutive integers differ in
  exactly one bit. Sobol's gray-code recurrence updates only one
  direction-number column per step, making sequential generation cheap.
- **van der Corput sequence** — the 1D Sobol sequence in base 2: write
  ``n`` in binary, reverse the digits, and interpret as a fraction below
  the binary point. Higher Sobol dimensions are van der Corput-like
  sequences over different primitive polynomials.

Generates the gray-code Sobol sequence in 32-bit integer arithmetic. Direction
numbers for dimensions 2 through 1024 come from the table compiled in
:mod:`_joe_kuo_data`; dimension 1 is handled inline as the trivial van der
Corput sequence in base 2.

The point at integer index 0 is the origin and is skipped (it would yield zero
in every coordinate, breaking the strict open-interval contract of
:meth:`Sampler.next_block`). The returned point at row ``k`` corresponds to
Sobol index ``index_at_construction + k + 1``.

Direction-integer set: which one we ship and what else exists
-------------------------------------------------------------

This module ships **one** direction-integer set: the **Joe-Kuo D6** table from
``new-joe-kuo-6.21201`` (Joe & Kuo, 2008). It is bit-for-bit equivalent to
QuantLib's ``ql.SobolRsg.JoeKuoD6`` direction set; see
``validation/quantlib_xref/test_joe_kuo_data.py`` for the parity proof. Several
alternative direction-integer sets exist in the QMC literature and are exposed
by other libraries (notably QuantLib via the ``ql.SobolRsg`` constructor flag);
**none of them are implemented here.** This block documents what is on offer
elsewhere and why we picked D6 — should a future caller need a different set,
this is the place to start.

The "D" parameter in the Joe-Kuo naming refers to the
*dimension-stratification depth* against which the construction is optimised:
larger ``D`` means the projection onto more coordinates simultaneously is
well-equidistributed (lower ``t``-value), at the cost of fewer total
dimensions supported.

==========================  ======================================  ============
QuantLib constant            Source                                  Status here
==========================  ======================================  ============
``Unit``                    trivial (all-ones direction integers)   not shipped
``Jaeckel``                 Jäckel (2002), *MC Methods in Finance*  not shipped
``SobolLevitan``            Levitan (1968), corrected by Joe-Kuo    not shipped
``SobolLevitanLemieux``     Lemieux modification of the above       not shipped
``JoeKuoD5``                Joe & Kuo (2003), ~1 111 dimensions     not shipped
**``JoeKuoD6``**            **Joe & Kuo (2008), 21 201 dimensions**  **shipped**
``JoeKuoD7``                Joe & Kuo (2010), stricter ``t``-value  not shipped
``Kuo``, ``Kuo2``, ``Kuo3`` F. Kuo (solo), alternative variants     not shipped
==========================  ======================================  ============

Why D6 is the right default for this library:

- Enough dimensions for any practical equity-basket payoff
  (a monthly autocall on 5 underlyings over 5 years needs ``5 × 60 = 300``
  dimensions; even daily over 5 years is only ``5 × 1260 = 6 300``, well below
  D6's 21 201).
- ``t``-value remains small in low and mid dimensions, so 2D and 3D
  projections — the regime where Sobol's *Brownian-bridge* / *PCA*
  re-ordering allocates the highest-variance time steps — are well
  equidistributed.
- This is the set used by NAG, Premia, and most finance papers from ~2010
  onward, so cross-checking against published benchmarks is straightforward.

Adding another set would mean: vendoring its primitive-polynomial + initial
direction-integer table in a new ``_<name>_data.py`` module, plumbing a
``direction_set`` constructor parameter through ``SobolSampler``, and adding a
matching cross-validation test. Nothing in the gray-code recurrence
(``_build_direction_table`` below) is set-specific — only the input table is.
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
