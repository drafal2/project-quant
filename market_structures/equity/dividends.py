"""Discrete dividend types for the equity forward curve.

Cash and proportional dividends are modelled as separate frozen-dataclass
``DiscreteDividend`` instances tagged by a :class:`DividendKind` enum. The
forward formula consumed by :class:`market_structures.equity.EquityForwardCurve`
is the Hull / Haug convention:

``F(T) = (S0 * Π_{ex_i <= T} (1 - p_i) - Σ_{ex_j <= T} d_j * DF(ex_j))
       * exp(-q(T) * T) / DF(T)``

where ``p_i`` are proportional drops, ``d_j`` are cash amounts, ``DF`` is the
risk-free discount factor, and ``q(T)`` is the curve's continuous component.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import Enum


class DividendKind(Enum):
    """Tag distinguishing cash from proportional discrete dividends.

    Attributes
    ----------
    CASH
        A fixed cash amount paid per share on the ex-date. Reduces the
        forward by ``amount * DF(ex_date)`` for every expiry ``T >= ex_date``.
    PROPORTIONAL
        A multiplicative drop of ``amount`` (e.g. ``0.02`` for a 2% drop).
        Reduces the forward by a factor ``(1 - amount)`` for every expiry
        ``T >= ex_date``.
    """

    CASH = "cash"
    PROPORTIONAL = "proportional"


@dataclass(frozen=True)
class DiscreteDividend:
    """A single discrete dividend on a known ex-date.

    Attributes
    ----------
    ex_date
        Ex-dividend date. The bootstrapper / curve enforces that this is
        strictly after the curve's reference date.
    amount
        For :attr:`DividendKind.CASH`, the cash amount per share (must be
        strictly positive). For :attr:`DividendKind.PROPORTIONAL`, the
        fractional drop ``p`` with ``0 <= p < 1``.
    kind
        Cash or proportional, see :class:`DividendKind`.
    """

    ex_date: date
    amount: float
    kind: DividendKind

    def __post_init__(self) -> None:
        """Validate the amount according to the dividend kind.

        Raises
        ------
        ValueError
            If ``amount`` is non-finite; if a cash amount is non-positive;
            or if a proportional drop is outside ``[0, 1)``.
        """
        if not math.isfinite(self.amount):
            raise ValueError(f"amount must be finite, got {self.amount}")
        if self.kind is DividendKind.CASH:
            if self.amount <= 0.0:
                raise ValueError(
                    f"cash dividend amount must be strictly positive, got {self.amount}"
                )
        else:
            if not (0.0 <= self.amount < 1.0):
                raise ValueError(
                    f"proportional dividend amount must lie in [0, 1), got {self.amount}"
                )
