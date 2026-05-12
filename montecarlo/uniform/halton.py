"""Halton low-discrepancy sequence (van der Corput in distinct prime bases).

For dimension :math:`d` the sequence is the van der Corput sequence in base
:math:`p_d` (the :math:`d`-th prime). The sequence is deterministic, has
:math:`O((\\log N)^d / N)` star discrepancy, and is trivial to code — but its
canonical (unscrambled) form develops visible correlations between higher-prime
coordinates for :math:`d \\gtrsim 10`. The diagnostic that exposes this is the
2D projection grid on the (16, 17) pair, included in the demo notebook.

Halton is included here primarily as a pedagogical contrast to Sobol: the
former is what one writes by hand to "do QMC"; the latter is what one actually
uses for a basket autocall.
"""

from __future__ import annotations

import logging

import numpy as np

from ..sampler import Sampler

logger = logging.getLogger(__name__)


def _first_primes(n: int) -> list[int]:
    """Return the first ``n`` primes by trial division.

    Parameters
    ----------
    n
        Number of primes required.

    Returns
    -------
    list[int]
        First ``n`` primes in ascending order.
    """
    primes: list[int] = []
    candidate = 2
    while len(primes) < n:
        prime = True
        for p in primes:
            if p * p > candidate:
                break
            if candidate % p == 0:
                prime = False
                break
        if prime:
            primes.append(candidate)
        candidate += 1
    return primes


def _van_der_corput(
    indices: np.ndarray,
    base: int,
) -> np.ndarray:
    """Return the van der Corput sequence values for the given integer indices.

    Parameters
    ----------
    indices
        ``int64`` array of strictly positive indices.
    base
        Integer base (a prime number for Halton).

    Returns
    -------
    numpy.ndarray
        ``float64`` array of the same shape as ``indices`` with values in
        ``(0, 1)``.
    """
    working = indices.astype(np.int64).copy()
    result = np.zeros_like(working, dtype=np.float64)
    f = 1.0 / base
    while working.any():
        result += (working % base) * f
        working //= base
        f /= base
    return result


class HaltonSampler(Sampler):
    """Halton low-discrepancy sequence; deterministic, prime-base van der Corput.

    Notes
    -----
    Pros
        Trivial to implement, deterministic, exact reproducibility, decent
        convergence for low-dimensional integrals.
    Cons
        Visible coordinate-pair correlations for dimensions above roughly 10,
        worsening with each additional prime base. Unsuitable for basket
        payoffs without scrambling.
    Use when
        Low-dimensional integrals (``d`` up to about 6); pedagogical demos.
        Otherwise prefer :class:`SobolSampler`.
    """

    is_quasi = True

    def __init__(
        self,
        max_dimensions: int = 64,
        burn_in: int = 1,
    ) -> None:
        """Initialise the Halton sampler.

        Parameters
        ----------
        max_dimensions
            Maximum dimension supported by this instance. Pre-computes the
            first ``max_dimensions`` primes.
        burn_in
            Number of initial points to skip when the sequence is reset. The
            default of ``1`` skips the all-zero point at index zero so that
            every returned value lies strictly in ``(0, 1)``.

        Raises
        ------
        ValueError
            If ``max_dimensions < 1`` or ``burn_in < 0``.
        """
        if max_dimensions < 1:
            raise ValueError("max_dimensions must be >= 1")
        if burn_in < 0:
            raise ValueError("burn_in must be >= 0")
        self._primes = _first_primes(max_dimensions)
        self.dimensions = max_dimensions
        self._burn_in = burn_in
        self.reset()

    def reset(self) -> None:
        """Rewind the sequence to the start of the burn-in region."""
        self._index = self._burn_in

    def next_block(
        self,
        n_paths: int,
        n_dimensions: int,
    ) -> np.ndarray:
        """Draw ``n_paths`` consecutive Halton points in ``n_dimensions``.

        Parameters
        ----------
        n_paths
            Number of rows in the returned array.
        n_dimensions
            Structural dimension of the Halton sequence; must not exceed
            ``self.dimensions``.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_dimensions)`` with values
            strictly in ``(0, 1)``.

        Raises
        ------
        ValueError
            If ``n_dimensions`` exceeds the pre-computed prime table.
        """
        if n_dimensions > self.dimensions:
            raise ValueError(
                f"requested {n_dimensions} dimensions but sampler was built "
                f"with max_dimensions={self.dimensions}"
            )
        indices = np.arange(self._index, self._index + n_paths, dtype=np.int64)
        out = np.empty((n_paths, n_dimensions), dtype=np.float64)
        for d in range(n_dimensions):
            out[:, d] = _van_der_corput(indices, self._primes[d])
        self._index += n_paths
        return out

    @property
    def state(self) -> dict:
        """Return the current sequence cursor and dimensionality.

        Returns
        -------
        dict
            Keys: ``index``, ``burn_in``, ``max_dimensions``.
        """
        return {
            "index": self._index,
            "burn_in": self._burn_in,
            "max_dimensions": self.dimensions,
        }
