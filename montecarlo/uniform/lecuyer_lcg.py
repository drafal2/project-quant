"""L'Ecuyer (1988) combined-LCG generator with Bays-Durham shuffle.

Implements the generator from L'Ecuyer's 1988 paper "Efficient and portable
combined random number generators". Two linear congruential generators are
combined and routed through a 32-element Bays-Durham shuffle table; the
construction is also known as ``ran2`` in *Numerical Recipes in C*, 2nd edition.

This sampler is **bit-for-bit compatible with**
:class:`QuantLib.LecuyerUniformRng`. It exists as a peer to the project's own
:class:`~montecarlo.uniform.lecuyer.LecuyerMRG32k3a1999Sampler` (which implements the
later 1999 paper) so that cross-validation against QuantLib is possible
without changing the production-grade L'Ecuyer.

Algorithm constants (from QL's ``lecuyeruniformrng.cpp``):

- Stream 1: ``m1 = 2_147_483_563``, ``a1 = 40_014``, Schrage split
  ``q1 = 53_668``, ``r1 = 12_211``.
- Stream 2: ``m2 = 2_147_483_399``, ``a2 = 40_692``, Schrage split
  ``q2 = 52_774``, ``r2 = 3_791``.
- Shuffle buffer size 32; warm-up of 8 iterations beyond the buffer fill.

Period ``~ 2.3 × 10^18`` (product of the two LCG periods, minus structure).
This is roughly ``2^61``, far shorter than MRG32k3a's ``2^191``. For the
basket autocall path engine the project uses ``LecuyerMRG32k3a1999Sampler``;
``LecuyerLCG1988Sampler`` is the right choice only for QL cross-validation
or pedagogical contrast.

Bit-parity is enforced by ``validation/quantlib_xref/test_uniform_distributional.py``.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler

logger = logging.getLogger(__name__)

_M1 = 2_147_483_563
_A1 = 40_014
_Q1 = 53_668
_R1 = 12_211

_M2 = 2_147_483_399
_A2 = 40_692
_Q2 = 52_774
_R2 = 3_791

_BUFFER_SIZE = 32
# int(1 + (m1 - 1) / bufferSize); matches QL's bufferNormalizer constant.
_BUFFER_NORMALIZER = 67_108_862

# (1 - QL_EPSILON); doubles bigger than this are clamped down. Matches QL clamp.
_MAX_RANDOM = 1.0 - 2.220446049250313e-16


class LecuyerLCG1988Sampler(Sampler):
    """L'Ecuyer (1988) combined-LCG + Bays-Durham shuffle; period ``~ 2^61``.

    Notes
    -----
    Pros
        Bit-for-bit match with ``ql.LecuyerUniformRng`` (Numerical Recipes
        ``ran2``); good statistical quality for its period; reference
        algorithm in many older textbooks.
    Cons
        Period only ``~ 2.3e18`` — a basket autocall with
        ``10^5`` paths × 250 steps × 5 assets uses ``~ 1.3e8`` uniforms per
        run, which is comfortable headroom for one run but exhausts the
        period within minutes if reused naively across many runs of a
        sensitivity study. No leap-ahead / substream support.
    Use when
        Cross-validation against QuantLib is required, or as a contrast
        point in the demo notebook. For production path generation use
        :class:`~montecarlo.uniform.lecuyer.LecuyerMRG32k3a1999Sampler` instead.
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
            Non-negative integer. Unlike ``ql.LecuyerUniformRng``,
            ``seed = 0`` is **not** remapped to a clock-based random seed —
            it is used literally. Pass a non-zero seed to compare against
            QuantLib.
        """
        self._seed = int(seed)
        self.reset()

    def reset(self) -> None:
        """Re-initialise both LCG states and warm up the shuffle table.

        Follows QL's constructor exactly: starting from ``temp1 = temp2 =
        seed``, advance the first LCG for ``buffer_size + 8`` warm-up
        steps, capturing the last ``buffer_size`` outputs into the shuffle
        table.
        """
        self._temp1 = self._seed
        self._temp2 = self._seed
        self._buffer = [0] * _BUFFER_SIZE
        for j in range(_BUFFER_SIZE + 7, -1, -1):
            k = self._temp1 // _Q1
            self._temp1 = _A1 * (self._temp1 - k * _Q1) - k * _R1
            if self._temp1 < 0:
                self._temp1 += _M1
            if j < _BUFFER_SIZE:
                self._buffer[j] = self._temp1
        self._y = self._buffer[0]

    def _next_one(self) -> float:
        """Return one uniform draw via the combined-LCG + shuffle scheme.

        Returns
        -------
        float
            Value in ``(0, 1)``; the upper bound ``1 - epsilon`` is enforced
            by an explicit clamp, matching QL's ``maxRandom`` ceiling.
        """
        # Advance LCG 1 (Schrage's method to avoid overflow)
        k = self._temp1 // _Q1
        self._temp1 = _A1 * (self._temp1 - k * _Q1) - k * _R1
        if self._temp1 < 0:
            self._temp1 += _M1
        # Advance LCG 2
        k = self._temp2 // _Q2
        self._temp2 = _A2 * (self._temp2 - k * _Q2) - k * _R2
        if self._temp2 < 0:
            self._temp2 += _M2
        # Bays-Durham shuffle
        j = self._y // _BUFFER_NORMALIZER
        self._y = self._buffer[j] - self._temp2
        self._buffer[j] = self._temp1
        if self._y < 1:
            self._y += _M1 - 1
        result = self._y / _M1
        if result > _MAX_RANDOM:
            result = _MAX_RANDOM
        return result

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
            ``float64`` array of shape ``(n_paths, n_dimensions)`` with
            values in ``(0, 1)``.
        """
        n_total = n_paths * n_dimensions
        out = np.empty(n_total, dtype=np.float64)
        for i in range(n_total):
            out[i] = self._next_one()
        return out.reshape(n_paths, n_dimensions)

    @property
    def state(self) -> dict:
        """Return a compact snapshot of the generator state.

        Returns
        -------
        dict
            Keys: ``seed``, ``temp1``, ``temp2``, ``y``, ``buffer`` (the
            32-element shuffle table copied out).
        """
        return {
            "seed": self._seed,
            "temp1": self._temp1,
            "temp2": self._temp2,
            "y": self._y,
            "buffer": list(self._buffer),
        }
