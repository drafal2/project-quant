"""Mersenne Twister MT19937 (Matsumoto and Nishimura, 1998).

Implements the 32-bit MT19937 word-recurrence with period :math:`2^{19937} - 1`.
The state is a 624-element buffer of 32-bit integers; a Python-loop refill
runs once per 624 outputs, and the per-output tempering is vectorised through
NumPy. Performance is adequate for unit tests but is dominated by Python
overhead — production code should fall back to ``numpy.random.MT19937`` if
needed.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler

logger = logging.getLogger(__name__)

_N = 624
_M = 397
_MATRIX_A = 0x9908_B0DF
_UPPER_MASK = 0x8000_0000
_LOWER_MASK = 0x7FFF_FFFF
_FAC = 1.0 / 4_294_967_296.0


class MersenneTwisterSampler(Sampler):
    """Mersenne Twister MT19937; period :math:`2^{19937} - 1`.

    Notes
    -----
    Pros
        Astronomical period, fast bulk generation in vectorised code,
        ubiquitous and well-understood reference generator.
    Cons
        Large 2.5 kB state, expensive seeding, fails some BigCrush
        equidistribution tests, recovers poorly from zero-rich initial states.
    Use when
        A serial PRNG default is needed and legacy compatibility (NumPy,
        SciPy, Boost) matters more than the strictest statistical quality.
    """

    is_quasi = False

    def __init__(
        self,
        seed: int = 5_489,
    ) -> None:
        """Initialise the generator with a 32-bit seed.

        Parameters
        ----------
        seed
            Any non-negative integer; mapped to the 624-word state by Knuth's
            initialisation recurrence from MT19937's reference implementation.
        """
        self._seed = int(seed)
        self.reset()

    def reset(self) -> None:
        """Re-initialise the 624-word state from the original seed."""
        seed = self._seed & 0xFFFF_FFFF
        mt = [seed]
        for i in range(1, _N):
            prev = mt[i - 1]
            mt.append((1_812_433_253 * (prev ^ (prev >> 30)) + i) & 0xFFFF_FFFF)
        self._mt = mt
        self._idx = _N

    def _refill(self) -> None:
        """Advance the state buffer by one full block of ``N`` words.

        Implements the canonical sequential update verbatim. The cost is
        amortised over 624 outputs per refill.
        """
        mt = self._mt
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("MT19937 refill at idx=%d", self._idx)
        for kk in range(_N - _M):
            y = (mt[kk] & _UPPER_MASK) | (mt[kk + 1] & _LOWER_MASK)
            mt[kk] = mt[kk + _M] ^ (y >> 1) ^ (_MATRIX_A if (y & 1) else 0)
        for kk in range(_N - _M, _N - 1):
            y = (mt[kk] & _UPPER_MASK) | (mt[kk + 1] & _LOWER_MASK)
            mt[kk] = mt[kk + (_M - _N)] ^ (y >> 1) ^ (_MATRIX_A if (y & 1) else 0)
        y = (mt[_N - 1] & _UPPER_MASK) | (mt[0] & _LOWER_MASK)
        mt[_N - 1] = mt[_M - 1] ^ (y >> 1) ^ (_MATRIX_A if (y & 1) else 0)
        self._idx = 0

    def next_int32_block(
        self,
        n: int,
    ) -> np.ndarray:
        """Draw ``n`` raw tempered 32-bit integers, matching ``ql.MersenneTwisterUniformRng::nextInt32``.

        Parameters
        ----------
        n
            Number of integers to draw.

        Returns
        -------
        numpy.ndarray
            ``uint32`` array of length ``n``. Useful when callers need the
            raw tempered output — e.g. seeding randomStart offsets for the
            Halton sampler in a manner compatible with QuantLib.
        """
        raw = np.empty(n, dtype=np.uint32)
        pos = 0
        while pos < n:
            if self._idx >= _N:
                self._refill()
            take = min(_N - self._idx, n - pos)
            raw[pos:pos + take] = self._mt[self._idx:self._idx + take]
            self._idx += take
            pos += take
        y = raw
        y = y ^ (y >> np.uint32(11))
        y = y ^ ((y << np.uint32(7)) & np.uint32(0x9D2C_5680))
        y = y ^ ((y << np.uint32(15)) & np.uint32(0xEFC6_0000))
        y = y ^ (y >> np.uint32(18))
        return y

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
        y = self.next_int32_block(n_total)
        out = (y.astype(np.float64) + 0.5) * _FAC
        return out.reshape(n_paths, n_dimensions)

    @property
    def state(self) -> dict:
        """Return the seed and read cursor; the 624-word buffer is omitted.

        Returns
        -------
        dict
            Keys: ``seed``, ``idx``. The full state buffer is intentionally
            *not* returned by value because it is large and intended to be
            opaque to consumers.
        """
        return {"seed": self._seed, "idx": self._idx}
