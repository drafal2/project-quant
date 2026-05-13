"""End-to-end integration smoke tests for the full ``(sampler, transform)`` stack.

These two utilities are the only diagnostics that exercise the composite
``NormalSampler`` end-to-end against a closed-form benchmark. The unit-level
diagnostics in ``uniform_tests`` and ``normal_tests`` validate one layer at a
time, so it is possible for each to pass while a composition is broken
(e.g. Sobol + Box-Muller); a Black-Scholes call price gone wrong is the cheap
way to surface that.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from ..normal.factory import NormalSampler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationResult:
    """Result of an MC integration check against a closed-form benchmark.

    Attributes
    ----------
    estimate
        Monte Carlo estimate.
    benchmark
        Closed-form (or otherwise exact) reference value.
    error
        ``estimate - benchmark``.
    std_error
        Estimated standard error of ``estimate`` (path standard deviation /
        :math:`\\sqrt{N}`). For QMC this is **not** a valid confidence
        interval and should be interpreted as a noise scale only.
    n_paths
        Number of Monte Carlo paths used.
    """

    estimate: float
    benchmark: float
    error: float
    std_error: float
    n_paths: int


def integrate_gaussian_moment(
    normal_sampler: NormalSampler,
    moment: int,
    n_paths: int,
) -> IntegrationResult:
    """Estimate :math:`E[X^{k}]` for :math:`X \\sim N(0, 1)` and compare to closed form.

    Parameters
    ----------
    normal_sampler
        A composite :class:`~montecarlo.normal.factory.NormalSampler`.
    moment
        The moment order :math:`k`. Closed form: ``0`` if ``k`` odd,
        ``(k - 1)!!`` if ``k`` even.
    n_paths
        Number of Monte Carlo paths.

    Returns
    -------
    IntegrationResult
        Estimate, closed-form value, error, standard error, and sample size.
    """
    z = normal_sampler.next_block(n_paths, 1).ravel()
    powers = z ** moment
    estimate = float(powers.mean())
    benchmark = 0.0 if moment % 2 else float(_double_factorial(moment - 1))
    std_error = float(powers.std(ddof=1) / math.sqrt(n_paths))
    return IntegrationResult(
        estimate=estimate,
        benchmark=benchmark,
        error=estimate - benchmark,
        std_error=std_error,
        n_paths=n_paths,
    )


def bs_call_price_mc(
    normal_sampler: NormalSampler,
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    maturity: float,
    n_paths: int,
) -> IntegrationResult:
    """Price a European call by Monte Carlo and compare to Black-Scholes.

    Parameters
    ----------
    normal_sampler
        A composite :class:`~montecarlo.normal.factory.NormalSampler`.
    spot
        Spot price :math:`S_0`.
    strike
        Strike :math:`K`.
    rate
        Continuously compounded risk-free rate :math:`r`.
    sigma
        Lognormal volatility :math:`\\sigma`.
    maturity
        Time to maturity in years :math:`T`.
    n_paths
        Number of Monte Carlo paths.

    Returns
    -------
    IntegrationResult
        MC price, Black-Scholes price, error, standard error, and path count.
    """
    z = normal_sampler.next_block(n_paths, 1).ravel()
    drift = (rate - 0.5 * sigma * sigma) * maturity
    diffusion = sigma * math.sqrt(maturity)
    s_t = spot * np.exp(drift + diffusion * z)
    payoff = np.maximum(s_t - strike, 0.0) * math.exp(-rate * maturity)
    estimate = float(payoff.mean())
    std_error = float(payoff.std(ddof=1) / math.sqrt(n_paths))
    benchmark = _bs_call_closed_form(spot, strike, rate, sigma, maturity)
    return IntegrationResult(
        estimate=estimate,
        benchmark=benchmark,
        error=estimate - benchmark,
        std_error=std_error,
        n_paths=n_paths,
    )


def _double_factorial(
    n: int,
) -> int:
    """Return :math:`n!!` for non-negative integer ``n``.

    Parameters
    ----------
    n
        Non-negative integer.

    Returns
    -------
    int
        Double factorial; ``1`` for ``n <= 0``.
    """
    if n <= 0:
        return 1
    result = 1
    while n > 1:
        result *= n
        n -= 2
    return result


def _bs_call_closed_form(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    maturity: float,
) -> float:
    """Return the Black-Scholes European call price.

    Parameters
    ----------
    spot
        Spot price.
    strike
        Strike.
    rate
        Continuously compounded risk-free rate.
    sigma
        Lognormal volatility.
    maturity
        Time to maturity in years.

    Returns
    -------
    float
        Black-Scholes call price.
    """
    sqrt_t = math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * maturity) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return float(spot * stats.norm.cdf(d1) - strike * math.exp(-rate * maturity) * stats.norm.cdf(d2))
