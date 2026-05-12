"""Knuth subtractive pseudo-random generator (TAOCP Vol 2 §3.2.2 / ``ran3``).

Implements the additive/subtractive lagged-Fibonacci generator that Knuth
discusses in *The Art of Computer Programming* Vol 2 and that appears as
``ran3`` in *Numerical Recipes in C*. It is included in this library for
pedagogical contrast — it is **not** a generator to use for production Monte
Carlo. Modern alternatives (MRG32k3a, MT19937, PCG64, Philox) outperform it on
every dimension of statistical quality.

The recurrence is

.. math::

    X_n = (X_{n - 24} - X_{n - 55}) \\bmod 2^{30}

operating on a 55-element ring buffer of 30-bit integers, initialised from a
single 32-bit seed by the procedure on TAOCP page 283.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler

logger = logging.getLogger(__name__)

_MBIG = 1_000_000_000
_MSEED = 161_803_398
_MZ = 0
_FAC = 1.0 / (_MBIG + 1)


class KnuthSampler(Sampler):
    """Knuth's subtractive method (``ran3``); period roughly :math:`2^{55}`.

    Notes
    -----
    Pros
        Simple, deterministic from a single seed, and a useful reference point
        when discussing why modern generators are better.
    Cons
        Outclassed on every statistical test by MRG32k3a and MT19937; not
        recommended for any real-world Monte Carlo.
    Use when
        Teaching or comparing generators. Never for pricing.
    """

    is_quasi = False

    def __init__(
        self,
        seed: int = 1,
    ) -> None:
        """Initialise the generator with a 32-bit seed.

        Parameters
        ----------
        seed
            Any non-negative integer; mapped to the internal state by Knuth's
            initialisation procedure.
        """
        self._seed = int(seed)
        self.reset()

    def reset(self) -> None:
        """Re-initialise the internal ring buffer from the original seed."""
        ma = [0] * 56
        mj = (_MSEED - abs(self._seed)) % _MBIG
        ma[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            ma[ii] = mk
            mk = mj - mk
            if mk < _MZ:
                mk += _MBIG
            mj = ma[ii]
        for _ in range(4):
            for i in range(1, 56):
                ma[i] -= ma[1 + (i + 30) % 55]
                if ma[i] < _MZ:
                    ma[i] += _MBIG
        self._ma = ma
        self._inext = 0
        self._inextp = 31

    def _next_raw(self) -> int:
        """Advance the generator by one step and return the raw integer.

        Returns
        -------
        int
            Integer uniformly distributed on ``[0, _MBIG - 1]``.
        """
        self._inext += 1
        if self._inext == 56:
            self._inext = 1
        self._inextp += 1
        if self._inextp == 56:
            self._inextp = 1
        mj = self._ma[self._inext] - self._ma[self._inextp]
        if mj < _MZ:
            mj += _MBIG
        self._ma[self._inext] = mj
        return mj

    def next_block(
        self,
        n_paths: int,
        n_dimensions: int,
    ) -> np.ndarray:
        """Draw ``n_paths * n_dimensions`` uniforms and reshape.

        Parameters
        ----------
        n_paths
            Number of rows in the returned array.
        n_dimensions
            Number of columns in the returned array.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)`` with values
            strictly in ``(0, 1)``.
        """
        n_total = n_paths * n_dimensions
        out = np.empty(n_total, dtype=np.float64)
        for i in range(n_total):
            out[i] = (self._next_raw() + 0.5) * _FAC
        return out.reshape(n_paths, n_dimensions)

    @property
    def state(self) -> dict:
        """Return a snapshot of the ring buffer and read/write cursors.

        Returns
        -------
        dict
            Keys: ``seed``, ``inext``, ``inextp``, ``ring`` (the 55-element
            ring buffer copied out of internal storage).
        """
        return {
            "seed": self._seed,
            "inext": self._inext,
            "inextp": self._inextp,
            "ring": list(self._ma[1:]),
        }
