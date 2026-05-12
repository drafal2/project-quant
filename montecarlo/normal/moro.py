"""Moro (1995) rational approximation of the inverse standard normal CDF.

Abbreviations used in this module:

- **CDF** — Cumulative Distribution Function;
  ``Φ⁻¹`` is the inverse of the standard-normal CDF.
- **QMC-safe** — a normal transform is *QMC-safe* if it is monotone and
  consumes exactly one uniform per output normal, so that a low-discrepancy
  uniform sampler retains its low-discrepancy structure through the
  transform. See ``montecarlo/CLAUDE.md`` for the full pairing rule.

The approximation uses two polynomials joined at :math:`v = 0.92` after
folding to the upper half. For the central region a rational polynomial of
degree 4 in :math:`(v - 0.5)^2` is applied; for the tail a polynomial of
degree 8 in :math:`y = \\ln(-\\ln(1 - v))` is applied. Maximum absolute error
in :math:`\\Phi^{-1}(u)` is roughly :math:`3 \\times 10^{-9}` from the centre
out to about :math:`\\Phi^{-1}(1 - 10^{-6}) \\approx 4.75\\sigma`, then
degrades into the deep tail (roughly :math:`5 \\times 10^{-3}` at
:math:`\\Phi^{-1}(1 - 10^{-15}) \\approx 7.94\\sigma`). For autocall barriers
and other tail-sensitive products prefer
:class:`~montecarlo.normal.wichura.WichuraAS241Transform`.

QMC-safe (monotone, single uniform in / single normal out).
"""

from __future__ import annotations

import logging

import numpy as np

from .transform import NormalTransform

logger = logging.getLogger(__name__)


_A = (
    2.50662823884,
    -18.61500062529,
    41.39119773534,
    -25.44106049637,
)
_B = (
    -8.47351093090,
    23.08336743743,
    -21.06224101826,
    3.13082909833,
)
_C = (
    0.3374754822726147,
    0.9761690190917186,
    0.1607979714918209,
    0.0276438810333863,
    0.0038405729373609,
    0.0003951896511919,
    0.0000321767881768,
    0.0000002888167364,
    0.0000003960315187,
)

_TAIL_CUTOFF = 0.92


class MoroTransform(NormalTransform):
    """Moro's 1995 rational approximation of :math:`\\Phi^{-1}`.

    Notes
    -----
    Pros
        Fast, smooth, QMC-safe; widely used in production risk and pricing
        systems where modest tail accuracy is acceptable.
    Cons
        Tail accuracy degrades beyond roughly the 7-sigma quantile. For
        autocall barriers with deep memory features prefer
        :class:`~montecarlo.normal.wichura.WichuraAS241Transform`.
    Use when
        Standard Monte Carlo, light-to-medium tail sensitivity, large path
        counts where rational evaluation cost matters.
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
        v = np.where(u < 0.5, 1.0 - u, u)
        sign = np.where(u < 0.5, -1.0, 1.0)
        q = v - 0.5
        r = q * q
        num = ((_A[3] * r + _A[2]) * r + _A[1]) * r + _A[0]
        den = (((_B[3] * r + _B[2]) * r + _B[1]) * r + _B[0]) * r + 1.0
        x_central = q * num / den
        y = np.log(-np.log(1.0 - v))
        x_tail = _C[8]
        for coeff in reversed(_C[:-1]):
            x_tail = x_tail * y + coeff
        x = np.where(v <= _TAIL_CUTOFF, x_central, x_tail)
        return sign * x
