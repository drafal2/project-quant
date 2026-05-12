"""Central-limit-theorem normal transform: sum of 12 uniforms minus 6.

Abbreviations used in this module:

- **CLT** — Central Limit Theorem. The sum of a large number of
  independent identically-distributed finite-variance random variables
  is approximately normal after centring and rescaling. Here we sum 12
  uniforms, which has mean 6 and variance 1, so subtracting 6 gives an
  approximately ``N(0, 1)`` draw.
- **QMC** — Quasi-Monte Carlo (see ``montecarlo/uniform/sobol.py``).
  CLT is non-monotonic in each component uniform and therefore destroys
  the low-discrepancy structure of a QMC sampler — it is rejected by
  the factory in that pairing.

Included for pedagogical contrast. The sum :math:`\\sum_{i=1}^{12} U_i - 6` has
mean zero and variance one but is hard-bounded in ``[-6, +6]``, so the tails
beyond :math:`\\pm 6\\sigma` are *exactly* missing — not merely under-sampled.
For any tail-sensitive payoff (barrier, autocall, deep-OTM option) this biases
the price toward zero risk. The transform issues a ``UserWarning`` on
construction to make the misuse explicit.

This transform is not QMC-safe (it is also non-monotonic in each component
uniform) and the factory refuses to pair it with a low-discrepancy sampler.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np

from .transform import NormalTransform

logger = logging.getLogger(__name__)


class CLTTransform(NormalTransform):
    """Sum of 12 uniforms minus 6. Pedagogy only — never use for pricing.

    Notes
    -----
    Pros
        Trivially cheap, no transcendental functions, easy to explain.
    Cons
        Tails truncated at :math:`\\pm 6\\sigma` exactly. Excess kurtosis is
        :math:`-2/(5 \\cdot 12) \\approx -0.033`, i.e., the distribution is
        platykurtic relative to the true normal — barrier and autocall payoffs
        will be systematically underpriced.
    Use when
        Teaching the central limit theorem. **Never** for pricing.
    """

    qmc_safe = False
    uniforms_per_normal = 12

    def __init__(self) -> None:
        """Initialise the transform and issue the misuse warning."""
        warnings.warn(
            "CLTTransform truncates tails at +/- 6 sigma; never use for pricing.",
            UserWarning,
            stacklevel=2,
        )

    def transform(
        self,
        uniforms: np.ndarray,
    ) -> np.ndarray:
        """Sum each block of 12 uniforms and subtract 6.

        Parameters
        ----------
        uniforms
            ``float64`` array of shape ``(n_paths, 12 * n_dim)``.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dim)``.

        Raises
        ------
        ValueError
            If the second axis is not a multiple of 12.
        """
        n_paths, total = uniforms.shape
        if total % 12 != 0:
            raise ValueError(
                f"CLTTransform requires a multiple of 12 columns; got {total}"
            )
        n_dim = total // 12
        return uniforms.reshape(n_paths, n_dim, 12).sum(axis=2) - 6.0
