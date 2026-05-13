"""Statistical diagnostics for samples that should be standard normal.

The functions here are intentionally minimal: each one returns either a
scalar, a small mapping, or a dataclass instance. The notebook composes
them into a multi-row diagnostic table; tests assert on individual fields.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KSResult:
    """KS test result against ``N(0, 1)``.

    Attributes
    ----------
    statistic
        KS statistic against the standard normal CDF.
    p_value
        Asymptotic p-value.
    n
        Number of samples used.
    """

    statistic: float
    p_value: float
    n: int


@dataclass(frozen=True)
class ADResult:
    """Anderson-Darling test result against ``N(0, 1)``.

    Attributes
    ----------
    statistic
        The Anderson-Darling :math:`A^2` statistic.
    critical_values
        Critical values at the standard significance levels reported by
        ``scipy.stats.anderson``.
    significance_levels
        Significance levels (percentages) corresponding to
        ``critical_values``.
    """

    statistic: float
    critical_values: tuple[float, ...]
    significance_levels: tuple[float, ...]


def moments(
    samples: np.ndarray,
) -> dict[str, float]:
    """Return mean, variance, skewness, and excess kurtosis of ``samples``.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before computing moments.

    Returns
    -------
    dict
        Keys: ``mean``, ``variance``, ``skewness``, ``excess_kurtosis``.
        For a true ``N(0, 1)`` sample these converge to ``(0, 1, 0, 0)``.
    """
    flat = np.asarray(samples).ravel().astype(np.float64)
    return {
        "mean": float(flat.mean()),
        "variance": float(flat.var(ddof=1)),
        "skewness": float(stats.skew(flat)),
        "excess_kurtosis": float(stats.kurtosis(flat)),
    }


def ks_normal(
    samples: np.ndarray,
) -> KSResult:
    """One-sample KS test of ``samples`` against ``N(0, 1)``.

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
    res = stats.kstest(flat, "norm")
    return KSResult(statistic=float(res.statistic), p_value=float(res.pvalue), n=flat.size)


def anderson_darling(
    samples: np.ndarray,
) -> ADResult:
    """Anderson-Darling test of ``samples`` against ``N(0, 1)``.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before the test.

    Returns
    -------
    ADResult
        Statistic plus the critical values and significance levels reported by
        ``scipy.stats.anderson``.
    """
    flat = np.asarray(samples).ravel()
    res = stats.anderson(flat, dist="norm", method="interpolate")
    return ADResult(
        statistic=float(res.statistic),
        critical_values=tuple(float(c) for c in res.critical_values),
        significance_levels=tuple(float(s) for s in res.significance_level),
    )


def tail_fractions(
    samples: np.ndarray,
    sigmas: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0),
) -> dict[float, dict[str, float]]:
    """Empirical vs theoretical :math:`P(|X| > k \\sigma)` for each :math:`k`.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before counting.
    sigmas
        Threshold multiples of one standard deviation.

    Returns
    -------
    dict
        Keyed by :math:`k`; each value is a dictionary with ``empirical`` and
        ``theoretical`` tail probabilities.
    """
    flat = np.asarray(samples).ravel()
    out: dict[float, dict[str, float]] = {}
    for k in sigmas:
        empirical = float((np.abs(flat) > k).mean())
        theoretical = float(2.0 * (1.0 - stats.norm.cdf(k)))
        out[float(k)] = {"empirical": empirical, "theoretical": theoretical}
    return out
