"""Equity market-data quote types.

Mirror of the rates-side `MarketQuote` family, but the equity bootstrap
target (a forward curve solved per-pillar in closed form) does not need an
`npv()` residual contract — equity quotes are therefore plain frozen
dataclasses with construction-time validation, not subclasses of
`market_structures.rates.quotes.MarketQuote`.

PR 2 shipped `DividendYieldQuote`. PR 4 adds `ForwardQuote`; the bootstrapper
in :mod:`market_structures.equity.bootstrapper` consumes a heterogeneous list
of `ForwardQuote | DividendYieldQuote` and converts each to the underlying
``(T_i, q_i)`` pillar grid in closed form. PR 5 adds `BorrowRateQuote` so a
separate borrow / repo term structure can sit alongside the dividend yield
inside `EquityForwardCurve`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DividendYieldQuote:
    """Continuously-compounded dividend yield observed at a specific maturity.

    A point on the equity dividend-yield term structure. The yield is
    interpreted under ACT/365 — the standard equity quoting convention.
    Used as an input to
    :meth:`market_structures.equity.EquityForwardCurve.from_dividend_yield_quotes`,
    which sorts a list of quotes by maturity, converts dates to year
    fractions, and hands the resulting grid to the curve.

    Attributes
    ----------
    maturity_date
        Quote maturity. The bootstrapper enforces that this is strictly
        after the curve's reference date.
    continuous_yield
        Continuous dividend yield ``q`` at the maturity. May be negative
        (e.g. for hard-to-borrow names where the implied carry is dominated
        by a positive borrow rate); must be finite.
    """

    maturity_date: date
    continuous_yield: float

    def __post_init__(self) -> None:
        """Validate the yield is finite.

        Raises
        ------
        ValueError
            If ``continuous_yield`` is NaN or infinite.
        """
        if not math.isfinite(self.continuous_yield):
            raise ValueError(
                f"continuous_yield must be finite, got {self.continuous_yield}"
            )


@dataclass(frozen=True)
class ForwardQuote:
    """Market-observed equity forward at a specific maturity.

    A point on the equity forward curve sourced from a futures, EFP, or
    OTC forward quote. The bootstrapper inverts the textbook formula
    ``F = S0 * exp(-q * T) / DF(T)`` to solve ``q`` in closed form
    (``q = -ln(F * DF(T) / S0) / T``).

    Attributes
    ----------
    maturity_date
        Quote maturity. The bootstrapper enforces that this is strictly
        after the curve's reference date.
    forward_price
        Market-quoted forward price. Must be strictly positive and finite;
        no static no-arbitrage relationship against spot / DF is enforced
        here because that requires knowing the dividend / borrow
        assumptions, which is precisely what the bootstrapper solves for.
    """

    maturity_date: date
    forward_price: float

    def __post_init__(self) -> None:
        """Validate the forward price is positive and finite.

        Raises
        ------
        ValueError
            If ``forward_price`` is non-positive, NaN, or infinite.
        """
        if not math.isfinite(self.forward_price):
            raise ValueError(
                f"forward_price must be finite, got {self.forward_price}"
            )
        if self.forward_price <= 0.0:
            raise ValueError(
                f"forward_price must be strictly positive, got {self.forward_price}"
            )


@dataclass(frozen=True)
class BorrowRateQuote:
    """Continuously-compounded borrow / repo rate observed at a specific maturity.

    A point on the equity borrow term structure. The convention used here is
    that ``continuous_borrow_rate`` is the **additional yield earned by a
    long-stock holder who lends out the share** (equivalently the cost paid
    by a short borrower). It adds to the dividend yield to form the net
    carry: ``effective_yield(T) = dividend_yield(T) + borrow_rate(T)``. A
    positive value depresses the forward, matching the empirical behaviour
    of hard-to-borrow names.

    Negative borrow rates are accepted (some general-collateral names have
    a small negative spread to OIS when modelled this way); non-finite
    rates raise `ValueError` at construction.

    Attributes
    ----------
    maturity_date
        Quote maturity. The curve constructor enforces that this is
        strictly after the reference date.
    continuous_borrow_rate
        Continuous borrow rate ``b`` at the maturity. Must be finite.
    """

    maturity_date: date
    continuous_borrow_rate: float

    def __post_init__(self) -> None:
        """Validate the borrow rate is finite.

        Raises
        ------
        ValueError
            If ``continuous_borrow_rate`` is NaN or infinite.
        """
        if not math.isfinite(self.continuous_borrow_rate):
            raise ValueError(
                f"continuous_borrow_rate must be finite, got {self.continuous_borrow_rate}"
            )
