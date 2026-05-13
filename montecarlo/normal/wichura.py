"""Wichura AS241 rational approximation of the inverse standard normal CDF.

Abbreviations used in this module:

- **CDF** — Cumulative Distribution Function. For the standard normal,
  ``Φ(z) = P(Z ≤ z)``; its inverse ``Φ⁻¹(u)`` is the quantile function
  that maps a uniform input ``u ∈ (0, 1)`` to the corresponding
  ``N(0, 1)`` quantile.
- **AS 241** — *Applied Statistics Algorithm 241*. The journal
  *Applied Statistics* (Series C of the *Journal of the Royal Statistical
  Society*) ran a numbered "AS" series of named, peer-reviewed numerical
  algorithms; AS 241 is Wichura's 1988 contribution implementing
  high-precision ``Φ⁻¹``. The "AS" is the series prefix, not an acronym.
- **Horner evaluation** — a numerically stable way to evaluate a
  polynomial ``a_0 + a_1·x + ... + a_n·x^n`` as nested multiplications
  ``((... (a_n · x + a_{n-1}) · x + ...) · x + a_0)``; used in all three
  regions to minimise rounding error.

Implements Algorithm AS 241 (Wichura, 1988, *Applied Statistics* 37, 477-484),
the algorithm used by R's ``qnorm``. Three regions are stitched together:

* :math:`|q| \\le 0.425` (central): rational polynomial in :math:`r = 0.180625 - q^2`.
* :math:`r \\le 5` (intermediate tail): rational polynomial in :math:`r - 1.6`.
* :math:`r > 5` (deep tail): rational polynomial in :math:`r - 5`.

Absolute accuracy in :math:`\\Phi^{-1}(u)` is at the double-precision floor
(roughly :math:`10^{-15}`) throughout the entire support, including the deep
tails out beyond :math:`\\Phi^{-1}(10^{-300}) \\approx -37`. This is the
industrial standard for autocall barriers, deep-OTM, and any product where
tail mispricing translates directly into mispriced risk.

QMC-safe.
"""

from __future__ import annotations

import logging

import numpy as np

from .transform import NormalTransform

logger = logging.getLogger(__name__)


_A = (
    2509.0809287301226727,
    33430.575583588128105,
    67265.770927008700853,
    45921.953931549871457,
    13731.693765509461125,
    1971.5909503065514427,
    133.14166789178437745,
    3.387132872796366608,
)
_B = (
    5226.495278852854561,
    28729.085735721942674,
    39307.89580009271061,
    21213.794301586595867,
    5394.1960214247511077,
    687.1870074920579083,
    42.313330701600911252,
)
_C = (
    7.7454501427834140764e-04,
    0.0227238449892691845833,
    0.24178072517745061177,
    1.27045825245236838258,
    3.64784832476320460504,
    5.7694972214606914055,
    4.6303378461565452959,
    1.42343711074968357734,
)
_D = (
    1.05075007164441684324e-09,
    5.475938084995344946e-04,
    0.0151986665636164571966,
    0.14810397642748007459,
    0.68976733498510000455,
    1.6763848301838038494,
    2.05319162663775882187,
)
_E = (
    2.01033439929228813265e-07,
    2.71155556874348757815e-05,
    0.0012426609473880784386,
    0.026532189526576123093,
    0.29656057182850489123,
    1.7848265399172913358,
    5.4637849111641143699,
    6.6579046435011037772,
)
_F = (
    2.04426310338993978564e-15,
    1.4215117583164458887e-07,
    1.8463183175100546818e-05,
    7.868691311456132591e-04,
    0.0148753612908506148525,
    0.13692988092273580531,
    0.59983220655588793769,
)


def _poly_horner_const1(
    coeffs: tuple,
    x: np.ndarray,
) -> np.ndarray:
    """Evaluate ``coeffs[0]*x^7 + ... + coeffs[6]*x + 1`` by Horner's method.

    Parameters
    ----------
    coeffs
        Seven coefficients of a degree-seven polynomial whose constant term is
        implicit ``1``.
    x
        ``float64`` array at which to evaluate the polynomial.

    Returns
    -------
    numpy.ndarray
        ``float64`` array of polynomial values.
    """
    y = coeffs[0]
    for c in coeffs[1:]:
        y = y * x + c
    return y * x + 1.0


def _poly_horner(
    coeffs: tuple,
    x: np.ndarray,
) -> np.ndarray:
    """Evaluate a degree-seven polynomial by Horner's method with all coefficients given.

    Parameters
    ----------
    coeffs
        Eight coefficients in order ``[c_7, c_6, ..., c_1, c_0]``.
    x
        ``float64`` array at which to evaluate the polynomial.

    Returns
    -------
    numpy.ndarray
        ``float64`` array of polynomial values.
    """
    y = coeffs[0]
    for c in coeffs[1:]:
        y = y * x + c
    return y


class WichuraAS241Transform(NormalTransform):
    """Wichura's AS241 rational approximation of :math:`\\Phi^{-1}`.

    Notes
    -----
    Pros
        Full machine precision across the entire support including deep tails;
        QMC-safe; the algorithm behind R's ``qnorm``.
    Cons
        Three regions, twenty-eight named coefficients — more code than Moro
        or Acklam.
    Use when
        Tail-sensitive products: barrier options, autocalls, deep-OTM
        derivatives, anything where the price depends materially on the
        accuracy of ``Phi^{-1}(u)`` at ``|u - 0.5| > 0.4995``.
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
        q = u - 0.5
        abs_q = np.abs(q)
        central = abs_q <= 0.425
        r_central = 0.180625 - q * q
        x_central = q * _poly_horner(_A, r_central) / _poly_horner_const1(_B, r_central)
        r_tail_input = np.where(q < 0, u, 1.0 - u)
        r_tail_input_safe = np.maximum(r_tail_input, 1e-300)
        r_log = np.sqrt(-np.log(r_tail_input_safe))
        small_tail = r_log <= 5.0
        r_small = r_log - 1.6
        x_small = _poly_horner(_C, r_small) / _poly_horner_const1(_D, r_small)
        r_big = r_log - 5.0
        x_big = _poly_horner(_E, r_big) / _poly_horner_const1(_F, r_big)
        x_tail_mag = np.where(small_tail, x_small, x_big)
        x_tail = np.where(q < 0, -x_tail_mag, x_tail_mag)
        return np.where(central, x_central, x_tail)
