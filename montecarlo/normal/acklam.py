"""Acklam (2003) rational approximation of the inverse standard normal CDF.

Abbreviations used in this module:

- **CDF** — Cumulative Distribution Function;
  ``Φ⁻¹`` is the inverse of the standard-normal CDF.
- **QMC-safe** — see ``moro.py`` for the longer definition. Monotone and
  one-uniform-in / one-normal-out, so safe to pair with Sobol / Halton.

Implements the algorithm published by Peter John Acklam at
https://web.archive.org/web/20151030215612/home.online.no/~pjacklam/notes/invnorm/
using degree-5 rational polynomials in two regions: a central region for
:math:`u \\in [0.02425, 0.97575]` and a tail region elsewhere. Absolute
accuracy in :math:`\\Phi^{-1}(u)` is approximately :math:`1.15 \\times 10^{-9}`
in the central region; in the tails the relative error remains at machine
precision for the standard double-precision implementation.

QMC-safe.
"""

from __future__ import annotations

import logging

import numpy as np

from .transform import NormalTransform

logger = logging.getLogger(__name__)


_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)

_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


class AcklamTransform(NormalTransform):
    """Acklam's 2003 rational approximation of :math:`\\Phi^{-1}`.

    Notes
    -----
    Pros
        Compact (six + five + six + four coefficients), QMC-safe, machine
        precision in the central region.
    Cons
        Marginally slower than Moro (one extra branch); tail accuracy is good
        but the Wichura algorithm is preferable for the very deepest tails.
    Use when
        General-purpose inverse normal; a good default when both QMC safety
        and tail accuracy matter and you want a single-region implementation.
    """

    qmc_safe = True
    uniforms_per_normal = 1

    def transform(
        self,
        uniforms: np.ndarray,
    ) -> np.ndarray:
        """Apply :math:`\\Phi^{-1}` to each uniform element-wise.

        Parameters
        ----------
        uniforms
            ``float64`` array with values strictly in ``(0, 1)``.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of the same shape, distributed as ``N(0, 1)``.
        """
        u = uniforms
        central = (u >= _P_LOW) & (u <= _P_HIGH)
        q = u - 0.5
        r = q * q
        num_c = ((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]
        den_c = ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        x_central = num_c * q / den_c
        lower = u < _P_LOW
        u_tail = np.where(lower, u, 1.0 - u)
        u_tail_safe = np.maximum(u_tail, 1e-300)
        q_tail = np.sqrt(-2.0 * np.log(u_tail_safe))
        num_t = ((((_C[0] * q_tail + _C[1]) * q_tail + _C[2]) * q_tail + _C[3]) * q_tail + _C[4]) * q_tail + _C[5]
        den_t = (((_D[0] * q_tail + _D[1]) * q_tail + _D[2]) * q_tail + _D[3]) * q_tail + 1.0
        x_tail_mag = num_t / den_t
        x_tail = np.where(lower, x_tail_mag, -x_tail_mag)
        return np.where(central, x_central, x_tail)
