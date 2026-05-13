"""Abstract base classes for implied-volatility surfaces.

A :class:`VolSurface` is a **quote object**: it represents implied volatilities
observed (or interpolated) across maturity and strike. It is **not** a
diffusion model and cannot directly drive a Monte Carlo path step. The
diffusion-side counterpart is :class:`montecarlo.volatility.VolModel`, which
consumes a surface when needed (e.g. ``DupireLocalVol(surface)``).

The canonical internal coordinate is **total implied variance**
``w(T, k_log) = sigma(T, K)^2 * T`` with ``k_log = log(K / F(T))``. This is
the natural space for the SVI family and the natural space for checking
calendar arbitrage (``dw/dT >= 0``). Concrete subclasses are free to store and
interpolate in any representation, but the public contract is fixed in this
canonical form so consumers (notably the Dupire bridge in PR 4) never need to
care which representation the surface uses internally.

:class:`DifferentiableVolSurface` is an opt-in interface that adds the partial
derivatives required for analytical Dupire. Non-parametric surfaces such as
:class:`InterpolatedVolSurface` do **not** inherit from it; the Dupire bridge
in PR 4 will dispatch on ``isinstance`` and fall back to a pre-computed
smoothed grid for plain :class:`VolSurface` instances.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date


class VolSurface(ABC):
    """Abstract implied-volatility surface, indexed by maturity and strike.

    Concrete subclasses must implement four methods:

    - :meth:`implied_vol` — the user-facing query, in strike coordinates;
    - :meth:`total_variance` — the canonical-coordinate query, in log-moneyness;
    - :meth:`forward` — the forward curve ``F(T)`` used to convert between the
      two coordinates;
    - :meth:`reference_date` — the anchor date for the time axis.
    """

    @property
    @abstractmethod
    def reference_date(self) -> date:
        """Return the surface reference date (``t = 0`` for the time axis)."""

    @abstractmethod
    def forward(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return the forward price at a time-to-expiry, in ACT/365 years.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.

        Returns
        -------
        float
            Forward price ``F(T)`` used by the surface for moneyness conversions.
        """

    @abstractmethod
    def implied_vol(
        self,
        time_to_expiry: float,
        strike: float,
    ) -> float:
        """Return the lognormal implied volatility at ``(T, K)``.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        strike
            Option strike; must be strictly positive.

        Returns
        -------
        float
            Lognormal (Black) implied volatility.
        """

    @abstractmethod
    def total_variance(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return the total implied variance ``w(T, k_log)``.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        log_moneyness
            Log-moneyness ``k_log = log(K / F(T))``.

        Returns
        -------
        float
            Total implied variance ``sigma(T, K)^2 * T``.
        """


class DifferentiableVolSurface(VolSurface):
    """Opt-in interface adding partial derivatives of total variance.

    Parametric surfaces (SVI, SSVI) implement these analytically; the Dupire
    bridge in PR 4 uses them to evaluate the local-volatility formula in
    closed form. Non-parametric surfaces do not need to inherit from this
    class — the Dupire bridge falls back to a smoothed numerical grid when
    the surface is a plain :class:`VolSurface`.

    All three derivative methods are evaluated in the canonical
    ``(time_to_expiry, log_moneyness)`` coordinates of :meth:`total_variance`.
    """

    @abstractmethod
    def dw_dT(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``dw/dT`` at fixed ``log_moneyness``.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        log_moneyness
            Log-moneyness ``k_log = log(K / F(T))``.

        Returns
        -------
        float
            Partial derivative of total variance with respect to time.
            Calendar-arbitrage freedom requires this to be non-negative.
        """

    @abstractmethod
    def dw_dk(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``dw/dk_log`` at fixed ``time_to_expiry``.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        log_moneyness
            Log-moneyness ``k_log = log(K / F(T))``.

        Returns
        -------
        float
            Partial derivative of total variance with respect to log-moneyness.
        """

    @abstractmethod
    def d2w_dk2(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``d^2 w / dk_log^2`` at fixed ``time_to_expiry``.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        log_moneyness
            Log-moneyness ``k_log = log(K / F(T))``.

        Returns
        -------
        float
            Second partial derivative of total variance with respect to
            log-moneyness. Butterfly-arbitrage freedom (Durrleman's condition)
            constrains the sign jointly with ``w``, ``dw/dk``.
        """


ForwardCallable = Callable[[float], float]
"""Callable signature for the forward curve passed into surface constructors."""
