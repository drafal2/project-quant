"""Box-Muller normal transform (Box and Muller, 1958).

Maps pairs of independent uniforms :math:`(U_1, U_2)` to pairs of independent
normals via

.. math::

    Z_1 = \\sqrt{-2 \\ln U_1} \\cos(2 \\pi U_2),
    \\qquad
    Z_2 = \\sqrt{-2 \\ln U_1} \\sin(2 \\pi U_2).

The transform is exact (the resulting normals are *truly* :math:`N(0, 1)`
without rational approximation) and fast with PRNG input. It is **not** QMC
safe: the wrap from :math:`U_2` through trigonometric functions is
non-monotonic and destroys the low-discrepancy structure of Sobol or Halton
points (Boyle, Broadie, Glasserman, 1997, *Monte Carlo Methods for Security
Pricing*). The factory rejects this pairing.
"""

from __future__ import annotations

import logging

import numpy as np

from .transform import NormalTransform

logger = logging.getLogger(__name__)


class BoxMullerTransform(NormalTransform):
    """Trigonometric Box-Muller transform; PRNG-only.

    Notes
    -----
    Pros
        Exact (not a rational approximation), simple, two normals per two
        uniforms.
    Cons
        Not QMC-safe — must not be paired with Sobol or Halton.
    Use when
        Pairing with a PRNG (Knuth, MRG32k3a, MT19937) and exactness in the
        tails matters more than QMC compatibility.
    """

    qmc_safe = False
    uniforms_per_normal = 1

    def transform(
        self,
        uniforms: np.ndarray,
    ) -> np.ndarray:
        """Pair consecutive uniforms in the flattened block and convert.

        Parameters
        ----------
        uniforms
            ``float64`` array of any shape ``(n_paths, n_dim)`` whose total
            element count is even.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of the same shape, distributed as ``N(0, 1)``.

        Raises
        ------
        ValueError
            If the total number of elements is odd.
        """
        flat = uniforms.ravel()
        n = flat.size
        if n % 2 != 0:
            raise ValueError(
                f"BoxMullerTransform requires an even total uniform count; got {n}"
            )
        u1 = flat[0::2]
        u2 = flat[1::2]
        r = np.sqrt(-2.0 * np.log(u1))
        theta = 2.0 * np.pi * u2
        z = np.empty_like(flat)
        z[0::2] = r * np.cos(theta)
        z[1::2] = r * np.sin(theta)
        return z.reshape(uniforms.shape)
