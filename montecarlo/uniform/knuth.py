"""Knuth's RANARRAY lagged-Fibonacci generator in IEEE doubles.

Abbreviations used in this module:

- **PRNG** — Pseudo-Random Number Generator.
- **RANARRAY** — Knuth's batched random-array procedure (``ran_array`` in
  the integer version, ``ranf_array`` in the floating-point version);
  generates a full block of output values from the current state in one
  pass rather than one value at a time.
- **Lagged-Fibonacci generator** — a recurrence of the form
  ``X_n = X_{n-j} ⊕ X_{n-k} (mod m)`` for two lags ``j < k`` and some
  binary operation ``⊕`` (here: floating-point subtraction modulo 1).
  The state is the trailing ``k`` outputs.
- **KK / LL / TT** — Knuth's notation: ``KK = 100`` is the long lag (size
  of the persistent state ring), ``LL = 37`` is the short lag, ``TT = 70``
  is the number of "squaring" iterations applied during seed expansion
  (a longer-than-strictly-necessary warm-up that breaks short-range
  correlations from the linear seed-fanout step).
- **QUALITY** — Knuth's term for the size of the regenerated output buffer
  (``1009`` here); only the first ``KK`` values are emitted, the rest are
  discarded. This *quality trick* (1009 / 100 ≈ 10× over-generation)
  empirically improves equidistribution over consuming the full buffer.

Implements Knuth's *ran_array* / *ranf_array* algorithm from
*The Art of Computer Programming*, Volume 2, Section 3.6 (the floating-point
variant of his lagged-Fibonacci subtractive generator). The state is a
``KK = 100`` element ring of IEEE doubles in ``[0, 1)``; the recurrence is

.. math::

    X_n = \\{X_{n - KK} - X_{n - LL}\\} \\bmod 1

with ``LL = 37``. The generator emits the first ``KK`` values of every
``QUALITY = 1009`` element block and discards the rest — Knuth's quality
trick that improves equidistribution.

This is **bit-for-bit compatible with** :class:`QuantLib.KnuthUniformRng`,
including the ``TT = 70`` initialisation schedule that processes the seed
through 70 squaring-and-multiplication steps before the first draw.

Bit-parity is enforced by ``validation/quantlib_xref/test_uniform_distributional.py``.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler

logger = logging.getLogger(__name__)

_KK = 100
_LL = 37
_TT = 70
_QUALITY = 1009
_ULP = (1.0 / (1 << 30)) / (1 << 22)  # 2 ** -52


def _mod_sum(
    x: float,
    y: float,
) -> float:
    """Return the fractional part of ``x + y``; matches QL ``mod_sum``.

    Parameters
    ----------
    x, y
        Non-negative floats in ``[0, 1)``.

    Returns
    -------
    float
        ``(x + y) - int(x + y)``.
    """
    s = x + y
    return s - int(s)


class KnuthSampler(Sampler):
    """Knuth RANARRAY lagged-Fibonacci generator; period ``~ 2^240``.

    Notes
    -----
    Pros
        Long period, good spectral properties, and the published reference
        algorithm in Knuth's TAOCP. Matches ``ql.KnuthUniformRng`` bit-exact
        for any non-zero seed.
    Cons
        Slow Python implementation (lagged-Fibonacci over IEEE doubles does
        not vectorise as cleanly as the bit-twiddling generators); not the
        modern default for production Monte Carlo.
    Use when
        Cross-validation against QuantLib or other RANARRAY ports is
        required, or when Knuth's quality trick (use 100 of every 1009
        values) is desired for pedagogical purposes.
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
            Non-negative integer; the low 30 bits drive the RANARRAY
            initialisation. Unlike ``ql.KnuthUniformRng``, ``seed = 0`` is
            **not** remapped to a clock-based random seed — it is used
            literally, yielding a deterministic state. Pass a non-zero
            seed to compare against QuantLib.
        """
        self._seed = int(seed)
        self.reset()

    def reset(self) -> None:
        """Re-initialise the internal state from the original seed.

        Runs Knuth's ``ranf_start`` procedure (KK-element bootstrap + TT
        squaring iterations + seed bit-wise multiplication) and primes the
        output buffer to an empty state so the first draw triggers a cycle.
        """
        self._ran_u = self._ranf_start(self._seed)
        self._ranf_arr_buf = [0.0] * _QUALITY
        # Match QL initial state: ranf_arr_ptr == ranf_arr_sentinel == buf size,
        # which forces the first call to next() into ranf_arr_cycle().
        self._ranf_arr_ptr = _QUALITY
        self._ranf_arr_sentinel = _QUALITY

    @staticmethod
    def _ranf_start(
        seed: int,
    ) -> list[float]:
        """Build the 100-element initial state from a 30-bit seed.

        Parameters
        ----------
        seed
            Non-negative integer; only the low 30 bits matter (the
            ``seed & 0x3FFFFFFF`` mask in the reference C++).

        Returns
        -------
        list[float]
            Length-100 list of IEEE doubles in ``[0, 1)``.
        """
        ulp = _ULP
        u = [0.0] * (_KK + _KK - 1)
        ul = [0.0] * (_KK + _KK - 1)
        ss = 2.0 * ulp * ((seed & 0x3FFFFFFF) + 2)
        for j in range(_KK):
            u[j] = ss
            ul[j] = 0.0
            ss += ss
            if ss >= 1.0:
                ss -= 1.0 - 2 * ulp
        u[1] += ulp
        ul[1] = ulp
        s = seed & 0x3FFFFFFF
        t = _TT - 1
        while t != 0:
            # "square"
            for j in range(_KK - 1, 0, -1):
                ul[j + j] = ul[j]
                u[j + j] = u[j]
            for j in range(_KK + _KK - 2, _KK - _LL, -2):
                ul[_KK + _KK - 1 - j] = 0.0
                u[_KK + _KK - 1 - j] = u[j] - ul[j]
            for j in range(_KK + _KK - 2, _KK - 1, -1):
                if ul[j] != 0.0:
                    ul[j - (_KK - _LL)] = ulp - ul[j - (_KK - _LL)]
                    u[j - (_KK - _LL)] = _mod_sum(u[j - (_KK - _LL)], u[j])
                    ul[j - _KK] = ulp - ul[j - _KK]
                    u[j - _KK] = _mod_sum(u[j - _KK], u[j])
            if s & 1:
                # "multiply by z"
                for j in range(_KK, 0, -1):
                    ul[j] = ul[j - 1]
                    u[j] = u[j - 1]
                ul[0] = ul[_KK]
                u[0] = u[_KK]
                if ul[_KK] != 0.0:
                    ul[_LL] = ulp - ul[_LL]
                    u[_LL] = _mod_sum(u[_LL], u[_KK])
            if s != 0:
                s >>= 1
            else:
                t -= 1
        ran_u = [0.0] * _KK
        for j in range(_LL):
            ran_u[j + _KK - _LL] = u[j]
        for j in range(_LL, _KK):
            ran_u[j - _LL] = u[j]
        return ran_u

    def _ranf_array(
        self,
        aa: list[float],
        n: int,
    ) -> None:
        """Fill ``aa[:n]`` with the next ``n`` lagged-Fibonacci outputs.

        Mutates the persistent ``self._ran_u`` state so that subsequent
        calls continue the sequence. Direct port of QL's ``ranf_array``.

        Parameters
        ----------
        aa
            Pre-allocated output buffer of length at least ``n``.
        n
            Number of values to produce; must be ``>= _KK``.
        """
        ran_u = self._ran_u
        for j in range(_KK):
            aa[j] = ran_u[j]
        for j in range(_KK, n):
            aa[j] = _mod_sum(aa[j - _KK], aa[j - _LL])
        j = n
        for i in range(_LL):
            ran_u[i] = _mod_sum(aa[j - _KK], aa[j - _LL])
            j += 1
        for i in range(_LL, _KK):
            ran_u[i] = _mod_sum(aa[j - _KK], ran_u[i - _LL])
            j += 1

    def _ranf_arr_cycle(self) -> float:
        """Regenerate the output buffer and return the first value.

        Returns
        -------
        float
            ``ranf_arr_buf[0]`` after regenerating the full QUALITY-sized
            buffer; subsequent calls to :meth:`_next_one` will then consume
            indices 1 through 99 before triggering another cycle.
        """
        self._ranf_array(self._ranf_arr_buf, _QUALITY)
        self._ranf_arr_ptr = 1
        self._ranf_arr_sentinel = _KK
        return self._ranf_arr_buf[0]

    def _next_one(self) -> float:
        """Return one uniform draw, regenerating the buffer if exhausted.

        Returns
        -------
        float
            Value in ``[0, 1)``.
        """
        if self._ranf_arr_ptr != self._ranf_arr_sentinel:
            val = self._ranf_arr_buf[self._ranf_arr_ptr]
            self._ranf_arr_ptr += 1
            return val
        return self._ranf_arr_cycle()

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
            values in ``[0, 1)``. Note that the underlying generator can
            yield 0.0 exactly when ``u[0] = 0`` from initialisation; this
            differs from the strict open-interval guarantee of the QMC
            samplers. Inverse-CDF consumers should pair with a transform
            that handles the boundary, or use this sampler with Box-Muller
            / CLT only.
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
            Keys: ``seed``, ``arr_ptr``, ``arr_sentinel``, ``ran_u`` (the
            100-element internal state copied out).
        """
        return {
            "seed": self._seed,
            "arr_ptr": self._ranf_arr_ptr,
            "arr_sentinel": self._ranf_arr_sentinel,
            "ran_u": list(self._ran_u),
        }
