"""L'Ecuyer MRG32k3a combined multiple-recursive generator.

Implements the combined MRG of L'Ecuyer (1999), "Good Parameters and
Implementations for Combined Multiple Recursive Random Number Generators",
*Operations Research* 47(1), 159-164. Period is approximately
:math:`2^{191}`. This is the production-quality choice on the PRNG side of
this library: it has substream / leap-ahead support (not implemented in this
PR — the autocall path engine will wire it up), passes BigCrush, and is the
generator used by MATLAB and ``rstream`` in R.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler

logger = logging.getLogger(__name__)

_M1 = 4_294_967_087
_M2 = 4_294_944_443
_A12 = 1_403_580
_A13 = 810_728
_A21 = 527_612
_A23 = 1_370_589
_NORM = 1.0 / (_M1 + 1)


class LecuyerMRG32k3a1999Sampler(Sampler):
    """L'Ecuyer's MRG32k3a; period :math:`\\approx 2^{191}`.

    Notes
    -----
    Pros
        Excellent statistical quality (passes BigCrush), long period, supports
        substream / leap-ahead by matrix-power skip (used by the autocall basket
        path engine in subsequent PRs).
    Cons
        Slower than Mersenne Twister; the two combined MRGs require six integer
        state values and modular arithmetic per draw.
    Use when
        Production Monte Carlo, especially when reproducible parallel paths or
        bias-free long simulations matter.
    """

    is_quasi = False

    def __init__(
        self,
        seed: int = 12_345,
    ) -> None:
        """Initialise the generator with a 32-bit seed.

        Parameters
        ----------
        seed
            Any non-negative integer. A small linear-congruential expansion is
            used to fan the seed into the six MRG state values, avoiding the
            zero state in either component.
        """
        self._seed = int(seed)
        self.reset()

    def reset(self) -> None:
        """Re-initialise the six MRG state values from the original seed."""
        s = self._seed if self._seed != 0 else 12_345
        values = []
        for _ in range(6):
            s = (1_103_515_245 * s + 12_345) & 0x7FFF_FFFF
            values.append(s % (_M1 - 1) + 1)
        self._s10, self._s11, self._s12 = values[:3]
        self._s20, self._s21, self._s22 = values[3:]

    def substream(
        self,
        index: int,
    ) -> "LecuyerMRG32k3a1999Sampler":
        """Return an independent stream positioned at substream ``index``.

        Reserved for the path engine in a later PR. The interface is fixed
        here so callers can be wired up without churn; the implementation is
        deferred because leap-ahead matrix exponentiation is non-trivial and
        is not required by Step 1.

        Parameters
        ----------
        index
            Substream index.

        Returns
        -------
        LecuyerMRG32k3a1999Sampler
            An LecuyerMRG32k3a1999Sampler positioned ``index * 2**76`` steps ahead.

        Raises
        ------
        NotImplementedError
            Always, in this PR.
        """
        raise NotImplementedError(
            "MRG32k3a substream leap-ahead is implemented in the path-engine PR."
        )

    def _next_raw(self) -> float:
        """Advance the generator by one step and return a single uniform.

        Returns
        -------
        float
            Uniform on ``(0, 1)``.
        """
        p1 = (_A12 * self._s11 - _A13 * self._s10) % _M1
        self._s10 = self._s11
        self._s11 = self._s12
        self._s12 = p1
        p2 = (_A21 * self._s22 - _A23 * self._s20) % _M2
        self._s20 = self._s21
        self._s21 = self._s22
        self._s22 = p2
        z = (p1 - p2) % _M1
        return (z + 1) * _NORM

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
            out[i] = self._next_raw()
        return out.reshape(n_paths, n_dimensions)

    @property
    def state(self) -> dict:
        """Return the six MRG state values plus the seed.

        Returns
        -------
        dict
            Keys: ``seed``, ``s10``, ``s11``, ``s12``, ``s20``, ``s21``, ``s22``.
        """
        return {
            "seed": self._seed,
            "s10": self._s10,
            "s11": self._s11,
            "s12": self._s12,
            "s20": self._s20,
            "s21": self._s21,
            "s22": self._s22,
        }
