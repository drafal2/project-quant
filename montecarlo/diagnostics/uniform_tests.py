"""Statistical and discrepancy diagnostics for uniform samples.

All functions take an ``ndarray`` of samples and return either a scalar, a
``dict``, or a small named result object. ``scipy.stats`` is the ground truth
for distributional tests; the L2 discrepancy is hand-coded because it is the
single diagnostic that distinguishes good QMC from bad QMC (and from PRNG).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KSResult:
    """One-sample Kolmogorov-Smirnov test result.

    Attributes
    ----------
    statistic
        The KS statistic :math:`\\sup_x |F_n(x) - F(x)|`.
    p_value
        Asymptotic p-value.
    n
        Number of samples used.
    """

    statistic: float
    p_value: float
    n: int


@dataclass(frozen=True)
class Chi2Result:
    """Chi-square goodness-of-fit result for binned uniform samples.

    Attributes
    ----------
    statistic
        The chi-square statistic.
    p_value
        Asymptotic p-value with ``bins - 1`` degrees of freedom.
    bins
        Number of equal-width bins used.
    n
        Number of samples binned.
    """

    statistic: float
    p_value: float
    bins: int
    n: int


def ks_uniform(
    samples: np.ndarray,
) -> KSResult:
    """One-sample KS test of ``samples`` against :math:`U(0, 1)`.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before the test.

    Returns
    -------
    KSResult
        Statistic, p-value, and sample size.
    """
    flat = np.asarray(samples).ravel()
    res = stats.kstest(flat, "uniform")
    return KSResult(statistic=float(res.statistic), p_value=float(res.pvalue), n=flat.size)


def chi_square_uniform(
    samples: np.ndarray,
    bins: int = 100,
) -> Chi2Result:
    """Chi-square goodness-of-fit of ``samples`` against equal-width bins on ``(0, 1)``.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before binning.
    bins
        Number of equal-width bins. Each bin has expected count ``n / bins``.

    Returns
    -------
    Chi2Result
        Statistic, p-value, bins, and sample size.
    """
    flat = np.asarray(samples).ravel()
    counts, _ = np.histogram(flat, bins=bins, range=(0.0, 1.0))
    expected = np.full(bins, flat.size / bins)
    res = stats.chisquare(counts, expected)
    return Chi2Result(
        statistic=float(res.statistic),
        p_value=float(res.pvalue),
        bins=bins,
        n=flat.size,
    )


def serial_correlation(
    samples: np.ndarray,
    max_lag: int = 10,
) -> np.ndarray:
    """Return Pearson serial correlations at lags ``1, 2, ..., max_lag``.

    Parameters
    ----------
    samples
        ``float64`` 1-D array (or higher-dim array which is flattened).
    max_lag
        Maximum lag at which to compute the correlation.

    Returns
    -------
    numpy.ndarray
        ``float64`` array of length ``max_lag`` with the correlation at each lag.
    """
    flat = np.asarray(samples).ravel().astype(np.float64)
    centred = flat - flat.mean()
    var = centred.var()
    if var == 0.0:
        return np.zeros(max_lag)
    out = np.empty(max_lag)
    for lag in range(1, max_lag + 1):
        out[lag - 1] = (centred[:-lag] * centred[lag:]).mean() / var
    return out


def l2_discrepancy(
    points: np.ndarray,
) -> float:
    """Centred L2 star-discrepancy (Warnock formula) of points in ``[0, 1]^d``.

    Smaller is better. For a PRNG it scales as :math:`O(N^{-1/2})`; for a
    well-constructed QMC sequence it scales as :math:`O(N^{-1} (\\log N)^d)`.

    Parameters
    ----------
    points
        ``float64`` array of shape ``(n_points, n_dim)``.

    Returns
    -------
    float
        The centred L2 discrepancy.
    """
    pts = np.asarray(points, dtype=np.float64)
    n, d = pts.shape
    abs_shift = np.abs(pts - 0.5)
    term1 = (13.0 / 12.0) ** d
    term2 = -(2.0 / n) * np.prod(1.0 + 0.5 * abs_shift - 0.5 * abs_shift ** 2, axis=1).sum()
    accum = 0.0
    for i in range(n):
        diff = np.abs(pts[i] - pts)
        factor = 1.0 + 0.5 * (abs_shift[i] + abs_shift) - 0.5 * diff
        accum += np.prod(factor, axis=1).sum()
    term3 = accum / (n * n)
    return float(term1 + term2 + term3)


def effective_dimension_2d(
    points: np.ndarray,
) -> np.ndarray:
    """Return the absolute Pearson correlation between every pair of columns.

    A large off-diagonal entry signals visible coordinate-pair correlation,
    which is the canonical failure mode of unscrambled Halton in high
    dimensions. Used by the demo notebook to display the Halton-failure grid.

    Parameters
    ----------
    points
        ``float64`` array of shape ``(n_points, n_dim)``.

    Returns
    -------
    numpy.ndarray
        ``float64`` array of shape ``(n_dim, n_dim)``; the diagonal is ``1``.
    """
    pts = np.asarray(points, dtype=np.float64)
    return np.abs(np.corrcoef(pts, rowvar=False))
