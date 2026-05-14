"""Black-76 / Black-Scholes pricing and implied-volatility inversion.

The pricing routines are written in the Black-76 form ``df * (F * N(d1) -
K * N(d2))``: a single ``df_funding`` discount factor and the carry-adjusted
forward ``F``. For equities priced as ``dS = (r - q) S dt + sigma S dW``, this
means ``df_funding = exp(-r * T)`` and ``F = S0 * exp((r - q) * T)``. The
forward-domain convention keeps the formulas free of any class-specific carry
treatment, so the same pricing primitives work for FX (``q`` = foreign rate)
and futures (``q`` = ``r``, ``F`` quoted directly).

The implied-vol inverter uses Brent's method on the price residual
``BS_price(sigma) - target``, with an arbitrage-bound pre-check and a fixed
bracket ``[1e-8, 5.0]``. Newton-with-vega would be roughly three times faster
but Brent's guaranteed convergence on a bracket matters more than speed here:
the inverter runs once per market quote at construction time, never in a hot
loop.
"""

from __future__ import annotations

import logging
import math

from scipy.optimize import brentq
from scipy.stats import norm

logger = logging.getLogger(__name__)


_VOL_MIN = 1e-8
_VOL_MAX = 5.0


def black_scholes_price(
    forward: float,
    strike: float,
    time_to_expiry: float,
    sigma: float,
    df_funding: float,
    option_type: str,
) -> float:
    """Return the Black-76 / Black-Scholes price of a European option.

    Parameters
    ----------
    forward
        Forward price at the option's maturity; must be strictly positive.
    strike
        Option strike; must be strictly positive.
    time_to_expiry
        Time to expiry in years; must be strictly positive.
    sigma
        Lognormal (Black) implied volatility; must be non-negative.
    df_funding
        Risk-free discount factor ``exp(-r * time_to_expiry)`` under continuous
        compounding; must lie in ``(0, 1]``.
    option_type
        Either ``"C"`` (call) or ``"P"`` (put); case-insensitive.

    Returns
    -------
    float
        Undiscounted price multiplied by ``df_funding`` (so the result is the
        present-value premium). At ``sigma == 0`` returns the discounted
        intrinsic ``df_funding * max(F - K, 0)`` for a call and
        ``df_funding * max(K - F, 0)`` for a put.

    Raises
    ------
    ValueError
        If any positivity precondition fails, or if ``option_type`` is not
        ``"C"`` or ``"P"``.
    """
    if forward <= 0.0 or strike <= 0.0:
        raise ValueError("forward and strike must be positive")
    if time_to_expiry <= 0.0:
        raise ValueError("time_to_expiry must be positive")
    if sigma < 0.0:
        raise ValueError("sigma must be non-negative")
    if not 0.0 < df_funding <= 1.0:
        raise ValueError("df_funding must lie in (0, 1]")
    side = option_type.upper()
    if side not in ("C", "P"):
        raise ValueError(f"option_type must be 'C' or 'P', got {option_type!r}")
    if sigma == 0.0:
        intrinsic = max(forward - strike, 0.0) if side == "C" else max(strike - forward, 0.0)
        return df_funding * intrinsic
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * time_to_expiry) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if side == "C":
        undiscounted = forward * float(norm.cdf(d1)) - strike * float(norm.cdf(d2))
    else:
        undiscounted = strike * float(norm.cdf(-d2)) - forward * float(norm.cdf(-d1))
    return df_funding * undiscounted


def black_scholes_vega(
    forward: float,
    strike: float,
    time_to_expiry: float,
    sigma: float,
    df_funding: float,
) -> float:
    """Return the Black-76 vega ``dV / dsigma`` of a European option.

    Vega is the same for calls and puts by put-call parity.

    Parameters
    ----------
    forward
        Forward price at the option's maturity; must be strictly positive.
    strike
        Option strike; must be strictly positive.
    time_to_expiry
        Time to expiry in years; must be strictly positive.
    sigma
        Lognormal (Black) implied volatility; must be strictly positive.
    df_funding
        Risk-free discount factor in ``(0, 1]``.

    Returns
    -------
    float
        Vega ``df_funding * F * phi(d1) * sqrt(T)`` where ``phi`` is the
        standard-normal PDF. Always non-negative.

    Raises
    ------
    ValueError
        If any positivity precondition fails.
    """
    if forward <= 0.0 or strike <= 0.0:
        raise ValueError("forward and strike must be positive")
    if time_to_expiry <= 0.0:
        raise ValueError("time_to_expiry must be positive")
    if sigma <= 0.0:
        raise ValueError("sigma must be positive")
    if not 0.0 < df_funding <= 1.0:
        raise ValueError("df_funding must lie in (0, 1]")
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * time_to_expiry) / (sigma * sqrt_t)
    return df_funding * forward * float(norm.pdf(d1)) * sqrt_t


def no_arb_price_bounds(
    forward: float,
    strike: float,
    df_funding: float,
    option_type: str,
) -> tuple[float, float]:
    """Return the static no-arbitrage price bounds for a European option.

    These are the bounds implied by put-call parity and non-negative payoffs
    in the forward-domain Black-76 representation. Any quoted price outside
    the open interval ``(lower, upper)`` admits a model-free arbitrage and
    must be rejected before attempting implied-vol inversion.

    Parameters
    ----------
    forward
        Forward price at the option's maturity; must be strictly positive.
    strike
        Option strike; must be strictly positive.
    df_funding
        Risk-free discount factor in ``(0, 1]``.
    option_type
        Either ``"C"`` (call) or ``"P"`` (put); case-insensitive.

    Returns
    -------
    tuple[float, float]
        ``(lower, upper)`` discounted bounds:

        - call: ``(df * max(F - K, 0), df * F)``
        - put:  ``(df * max(K - F, 0), df * K)``

    Raises
    ------
    ValueError
        If preconditions fail or ``option_type`` is invalid.
    """
    if forward <= 0.0 or strike <= 0.0:
        raise ValueError("forward and strike must be positive")
    if not 0.0 < df_funding <= 1.0:
        raise ValueError("df_funding must lie in (0, 1]")
    side = option_type.upper()
    if side not in ("C", "P"):
        raise ValueError(f"option_type must be 'C' or 'P', got {option_type!r}")
    if side == "C":
        return df_funding * max(forward - strike, 0.0), df_funding * forward
    return df_funding * max(strike - forward, 0.0), df_funding * strike


def implied_vol_from_price(
    price: float,
    forward: float,
    strike: float,
    time_to_expiry: float,
    df_funding: float,
    option_type: str,
    vol_min: float = _VOL_MIN,
    vol_max: float = _VOL_MAX,
    tolerance: float = 1e-8,
) -> float:
    """Invert an option price to its Black-76 implied volatility via Brent's method.

    Performs a strict no-arbitrage pre-check, then solves ``BS_price(sigma) -
    price = 0`` on ``[vol_min, vol_max]``. The bracket is hard-coded for
    robustness; production option markets very rarely produce implied vols
    outside ``[0.5%, 500%]``.

    Parameters
    ----------
    price
        Market option price (present value); must lie strictly between the
        bounds returned by :func:`no_arb_price_bounds`.
    forward
        Forward price at the option's maturity; must be strictly positive.
    strike
        Option strike; must be strictly positive.
    time_to_expiry
        Time to expiry in years; must be strictly positive.
    df_funding
        Risk-free discount factor in ``(0, 1]``.
    option_type
        Either ``"C"`` (call) or ``"P"`` (put); case-insensitive.
    vol_min
        Lower bracket bound. Defaults to ``1e-8``.
    vol_max
        Upper bracket bound. Defaults to ``5.0``.
    tolerance
        Brent convergence tolerance on ``sigma``. Defaults to ``1e-8``.

    Returns
    -------
    float
        Implied volatility ``sigma`` such that ``black_scholes_price(...,
        sigma, ...)`` matches ``price`` to within ``tolerance``.

    Raises
    ------
    ValueError
        If ``price`` is outside the no-arbitrage bounds, or if standard
        preconditions fail.
    RuntimeError
        If Brent fails to bracket the root (e.g. the price is admissible by
        bounds but pricing at ``vol_min`` and ``vol_max`` straddles the wrong
        sign — should not happen for valid inputs).
    """
    lower, upper = no_arb_price_bounds(forward, strike, df_funding, option_type)
    if not lower < price < upper:
        raise ValueError(
            f"price {price:.8g} outside no-arbitrage bounds "
            f"({lower:.8g}, {upper:.8g}) for {option_type.upper()} "
            f"K={strike} F={forward} df={df_funding}"
        )

    def residual(sigma: float) -> float:
        return (
            black_scholes_price(forward, strike, time_to_expiry, sigma, df_funding, option_type)
            - price
        )

    r_lo = residual(vol_min)
    r_hi = residual(vol_max)
    if r_lo * r_hi > 0.0:
        logger.error(
            "Brent bracket failed: residual same sign at endpoints "
            "(r_lo=%.3e, r_hi=%.3e) for K=%.6g F=%.6g T=%.6g price=%.8g",
            r_lo,
            r_hi,
            strike,
            forward,
            time_to_expiry,
            price,
        )
        raise RuntimeError(
            f"Brent bracket failed to straddle root for K={strike} F={forward} "
            f"T={time_to_expiry} price={price}"
        )

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "Inverting: F=%.6g K=%.6g T=%.6g price=%.8g bounds=(%.6g, %.6g)",
            forward,
            strike,
            time_to_expiry,
            price,
            lower,
            upper,
        )
    return float(brentq(residual, vol_min, vol_max, xtol=tolerance))
