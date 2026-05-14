"""Coordinate conversions on the implied-vol smile axis.

Three smile-axis representations are supported: strike ``K``, log-moneyness
``k_log = log(K / F(T))``, and Black-Scholes spot delta. Log-moneyness is the
canonical internal coordinate of :class:`VolSurface` (SVI lives here natively;
calendar arbitrage is monotone-in-T). Strike is the natural quote axis; delta
is convenient for FX-style surfaces and is included for forward compatibility.

The delta convention used here is the **unadjusted spot delta** for an option
priced on the forward via Black-76 (i.e. the equity-style spot delta with the
funding discount factor factored out): ``delta_call = df_funding * N(d1)``,
``delta_put = -df_funding * N(-d1)``. Premium-adjusted and forward-delta
conventions used in FX are out of scope here.
"""

from __future__ import annotations

import math

from scipy.stats import norm


def strike_to_log_moneyness(
    strike: float,
    forward: float,
) -> float:
    """Return the log-moneyness ``log(K / F)`` for a strike against a forward.

    Parameters
    ----------
    strike
        Option strike; must be strictly positive.
    forward
        Forward price at the relevant maturity; must be strictly positive.

    Returns
    -------
    float
        Log-moneyness ``log(strike / forward)``.

    Raises
    ------
    ValueError
        If ``strike`` or ``forward`` is non-positive.
    """
    if strike <= 0.0:
        raise ValueError(f"strike must be positive, got {strike}")
    if forward <= 0.0:
        raise ValueError(f"forward must be positive, got {forward}")
    return math.log(strike / forward)


def log_moneyness_to_strike(
    log_moneyness: float,
    forward: float,
) -> float:
    """Return the strike corresponding to a log-moneyness against a forward.

    Parameters
    ----------
    log_moneyness
        Log-moneyness ``log(K / F)``.
    forward
        Forward price at the relevant maturity; must be strictly positive.

    Returns
    -------
    float
        Strike ``forward * exp(log_moneyness)``.

    Raises
    ------
    ValueError
        If ``forward`` is non-positive.
    """
    if forward <= 0.0:
        raise ValueError(f"forward must be positive, got {forward}")
    return forward * math.exp(log_moneyness)


def strike_to_delta(
    strike: float,
    forward: float,
    time_to_expiry: float,
    sigma: float,
    df_funding: float,
    option_type: str,
) -> float:
    """Return the Black-Scholes spot delta of a European option at the given strike.

    Parameters
    ----------
    strike
        Option strike; must be strictly positive.
    forward
        Forward price at the option's maturity; must be strictly positive.
    time_to_expiry
        Time to expiry in years; must be strictly positive.
    sigma
        Lognormal (Black) implied volatility; must be strictly positive.
    df_funding
        Risk-free discount factor ``exp(-r * time_to_expiry)`` for spot-delta
        conversion under continuous compounding.
    option_type
        Either ``"C"`` (call) or ``"P"`` (put); case-insensitive.

    Returns
    -------
    float
        Unadjusted spot delta in (0, df_funding] for a call, in
        [-df_funding, 0) for a put.

    Raises
    ------
    ValueError
        If any positivity precondition fails, or if ``option_type`` is not
        ``"C"`` or ``"P"``.
    """
    if strike <= 0.0 or forward <= 0.0:
        raise ValueError("strike and forward must be positive")
    if time_to_expiry <= 0.0:
        raise ValueError("time_to_expiry must be positive")
    if sigma <= 0.0:
        raise ValueError("sigma must be positive")
    side = option_type.upper()
    if side not in ("C", "P"):
        raise ValueError(f"option_type must be 'C' or 'P', got {option_type!r}")
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * time_to_expiry) / (sigma * sqrt_t)
    if side == "C":
        return df_funding * float(norm.cdf(d1))
    return -df_funding * float(norm.cdf(-d1))


def delta_to_strike(
    delta: float,
    forward: float,
    time_to_expiry: float,
    sigma: float,
    df_funding: float,
    option_type: str,
) -> float:
    """Return the strike that produces a given Black-Scholes spot delta.

    Inverts :func:`strike_to_delta` analytically using the inverse normal CDF.

    Parameters
    ----------
    delta
        Target unadjusted spot delta; must lie in (0, df_funding) for a call,
        (-df_funding, 0) for a put.
    forward
        Forward price at the option's maturity; must be strictly positive.
    time_to_expiry
        Time to expiry in years; must be strictly positive.
    sigma
        Lognormal (Black) implied volatility; must be strictly positive.
    df_funding
        Risk-free discount factor ``exp(-r * time_to_expiry)``.
    option_type
        Either ``"C"`` (call) or ``"P"`` (put); case-insensitive.

    Returns
    -------
    float
        Strike ``K`` such that :func:`strike_to_delta` returns ``delta``.

    Raises
    ------
    ValueError
        If preconditions fail, or if ``delta`` is outside the admissible range
        implied by ``option_type`` and ``df_funding``.
    """
    if forward <= 0.0:
        raise ValueError("forward must be positive")
    if time_to_expiry <= 0.0:
        raise ValueError("time_to_expiry must be positive")
    if sigma <= 0.0:
        raise ValueError("sigma must be positive")
    side = option_type.upper()
    if side not in ("C", "P"):
        raise ValueError(f"option_type must be 'C' or 'P', got {option_type!r}")
    sqrt_t = math.sqrt(time_to_expiry)
    if side == "C":
        if not 0.0 < delta < df_funding:
            raise ValueError(
                f"call delta must lie in (0, {df_funding}), got {delta}"
            )
        d1 = float(norm.ppf(delta / df_funding))
    else:
        if not -df_funding < delta < 0.0:
            raise ValueError(
                f"put delta must lie in (-{df_funding}, 0), got {delta}"
            )
        d1 = -float(norm.ppf(-delta / df_funding))
    return forward * math.exp(-d1 * sigma * sqrt_t + 0.5 * sigma * sigma * time_to_expiry)
