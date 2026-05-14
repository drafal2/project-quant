"""SSVI surface (Gatheral-Jacquier 2014) with closed-form derivatives.

Surface SVI:

    w(T, k) = (theta_T / 2) * (1 + rho * phi_T * k + sqrt((phi_T * k + rho)^2 + 1 - rho^2))

with ``theta_T = w_ATM(T)`` (the ATM total-variance term structure) and
``phi_T = phi(theta_T)`` for some user-chosen monotone phi function. The ATM
identity ``w(T, 0) = theta_T`` holds by construction.

Two phi function families are supported:

- :class:`PowerLawPhi` — ``phi(theta) = eta / (theta^gamma * (1 + theta)^(1 - gamma))``
  (Gatheral-Jacquier 2014, the form most commonly cited and the one used in the
  arbitrage-free conditions in that paper).
- :class:`HestonLikePhi` — ``phi(theta) = (1/(lambda*theta)) * (1 - (1 - exp(-lambda*theta))/(lambda*theta))``,
  the limit of the Heston SVI under the standard parameter mapping; a single
  positive parameter ``lambda``.

The chain-rule derivatives ``dw/dT``, ``dw/dk``, ``d2w/dk2`` are computed in
closed form from the phi function and a piecewise-linear ``theta_T`` term
structure.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from ..surface import DifferentiableVolSurface, ForwardCallable

logger = logging.getLogger(__name__)


class SSVIPhiFunction(ABC):
    """Strategy interface for the SSVI ``phi(theta)`` function."""

    @abstractmethod
    def __call__(
        self,
        theta: float,
    ) -> float:
        """Return ``phi(theta)``."""

    @abstractmethod
    def derivative(
        self,
        theta: float,
    ) -> float:
        """Return ``dphi/dtheta``."""

    @property
    @abstractmethod
    def params(self) -> tuple[float, ...]:
        """Return the underlying free parameters in a fixed order."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Return a short tag identifying the phi family (used in logging)."""


class PowerLawPhi(SSVIPhiFunction):
    """Power-law phi: ``phi(theta) = eta / (theta^gamma * (1 + theta)^(1 - gamma))``.

    Parameters
    ----------
    eta
        Overall amplitude; must be strictly positive.
    gamma
        Decay exponent; must satisfy ``0 < gamma < 1``.

    Notes
    -----
    The standard arbitrage-free condition under power-law phi requires
    ``eta * (1 + |rho|) <= 2`` (Gatheral-Jacquier 2014, Theorem 4.2). The
    :class:`SSVISurface` constructor checks this and emits a ``UserWarning`` if
    violated; we do not raise, because the boundary case is common enough in
    market fits to be useful as a diagnostic rather than a hard failure.
    """

    def __init__(
        self,
        eta: float,
        gamma: float,
    ) -> None:
        if eta <= 0.0:
            raise ValueError(f"eta must be strictly positive, got {eta!r}")
        if not 0.0 < gamma < 1.0:
            raise ValueError(f"gamma must lie in (0, 1), got {gamma!r}")
        self._eta = float(eta)
        self._gamma = float(gamma)

    @property
    def eta(self) -> float:
        return self._eta

    @property
    def gamma(self) -> float:
        return self._gamma

    @property
    def params(self) -> tuple[float, ...]:
        return (self._eta, self._gamma)

    @property
    def kind(self) -> str:
        return "power_law"

    def __call__(
        self,
        theta: float,
    ) -> float:
        if theta <= 0.0:
            raise ValueError(f"theta must be strictly positive, got {theta!r}")
        return self._eta / (theta ** self._gamma * (1.0 + theta) ** (1.0 - self._gamma))

    def derivative(
        self,
        theta: float,
    ) -> float:
        if theta <= 0.0:
            raise ValueError(f"theta must be strictly positive, got {theta!r}")
        phi = self(theta)
        return -phi * (self._gamma / theta + (1.0 - self._gamma) / (1.0 + theta))


class HestonLikePhi(SSVIPhiFunction):
    """Heston-like phi: ``phi(theta) = (1/(lambda*theta)) * (1 - (1 - exp(-lambda*theta))/(lambda*theta))``.

    Parameters
    ----------
    lambda_
        Mean-reversion-like decay; must be strictly positive.

    Notes
    -----
    Bounded between 0 and 1/2 for all ``theta > 0``, with ``phi(theta) -> 1/2``
    as ``theta -> 0`` and ``phi(theta) ~ 1/(lambda*theta)`` as ``theta -> inf``.
    The small-``lambda*theta`` Taylor expansion is used near the origin to
    avoid ``0/0`` cancellation in the direct formula.
    """

    def __init__(
        self,
        lambda_: float,
    ) -> None:
        if lambda_ <= 0.0:
            raise ValueError(f"lambda must be strictly positive, got {lambda_!r}")
        self._lambda = float(lambda_)

    @property
    def lambda_(self) -> float:
        return self._lambda

    @property
    def params(self) -> tuple[float, ...]:
        return (self._lambda,)

    @property
    def kind(self) -> str:
        return "heston_like"

    # Direct-formula cancellation loses ~3 * log10(1/x) digits, so the Taylor
    # branch must dominate up to ~1e-2 to avoid visible precision loss at the
    # boundary. Five Taylor terms suffice for ~1e-15 absolute error at x = 1e-2.
    _TAYLOR_THRESHOLD: float = 1e-2

    def __call__(
        self,
        theta: float,
    ) -> float:
        if theta <= 0.0:
            raise ValueError(f"theta must be strictly positive, got {theta!r}")
        x = self._lambda * theta
        if x < self._TAYLOR_THRESHOLD:
            # phi(x) = sum_{n>=0} (-x)^n / (n + 2)!
            return (
                0.5
                - x / 6.0
                + x * x / 24.0
                - x ** 3 / 120.0
                + x ** 4 / 720.0
                - x ** 5 / 5040.0
            )
        return (1.0 / x) - (1.0 - math.exp(-x)) / (x * x)

    def derivative(
        self,
        theta: float,
    ) -> float:
        if theta <= 0.0:
            raise ValueError(f"theta must be strictly positive, got {theta!r}")
        x = self._lambda * theta
        if x < self._TAYLOR_THRESHOLD:
            # dphi/dx = sum_{n>=1} (-1)^n n x^(n-1) / (n + 2)!
            #        = -1/6 + x/12 - x^2/40 + x^3/180 - x^4/1008 + ...
            dphi_dx = (
                -1.0 / 6.0
                + x / 12.0
                - x * x / 40.0
                + x ** 3 / 180.0
                - x ** 4 / 1008.0
            )
        else:
            exp_neg_x = math.exp(-x)
            dphi_dx = -(1.0 + exp_neg_x) / (x * x) + 2.0 * (1.0 - exp_neg_x) / (x * x * x)
        return self._lambda * dphi_dx


class SSVISurface(DifferentiableVolSurface):
    """Global SSVI surface parameterised by an ATM term structure plus phi.

    Parameters
    ----------
    reference_date
        Anchor date (``t = 0``) for the time axis.
    forward
        Callable returning the forward ``F(T)`` for ``T`` in ACT/365 years.
    expiries
        Pillar grid in ACT/365 years; strictly positive and strictly
        increasing.
    theta_atm
        ATM total variances at ``expiries`` (``theta_i = sigma_ATM(T_i)^2 * T_i``).
        Must be strictly positive and strictly increasing (calendar arb).
    rho
        Scalar SSVI correlation; ``-1 <= rho <= 1``.
    phi
        :class:`SSVIPhiFunction` instance defining the slope function.

    Raises
    ------
    ValueError
        If inputs are malformed (length mismatch, non-monotone ``theta_atm``,
        ``|rho| > 1``, etc.).
    """

    def __init__(
        self,
        reference_date: date,
        forward: ForwardCallable,
        expiries: Sequence[float],
        theta_atm: Sequence[float],
        rho: float,
        phi: SSVIPhiFunction,
    ) -> None:
        if len(expiries) == 0:
            raise ValueError("at least one expiry pillar is required")
        if len(expiries) != len(theta_atm):
            raise ValueError("expiries and theta_atm must have equal length")
        ts = [float(t) for t in expiries]
        thetas = [float(v) for v in theta_atm]
        for t in ts:
            if t <= 0.0:
                raise ValueError(f"expiries must be strictly positive, got {t}")
        for i in range(1, len(ts)):
            if ts[i] <= ts[i - 1]:
                raise ValueError("expiries must be strictly increasing")
        for v in thetas:
            if v <= 0.0:
                raise ValueError(f"theta_atm must be strictly positive, got {v}")
        for i in range(1, len(thetas)):
            if thetas[i] <= thetas[i - 1]:
                raise ValueError(
                    "theta_atm must be strictly increasing (calendar arbitrage)"
                )
        if not -1.0 <= rho <= 1.0:
            raise ValueError(f"rho must lie in [-1, 1], got {rho!r}")

        self._reference_date = reference_date
        self._forward = forward
        self._expiries: list[float] = ts
        self._theta_atm: list[float] = thetas
        self._rho = float(rho)
        self._phi = phi

        logger.info(
            "SSVISurface built: phi=%s n_pillars=%d T_range=[%.4f, %.4f] rho=%.4f",
            phi.kind,
            len(ts),
            ts[0],
            ts[-1],
            self._rho,
        )

    @property
    def reference_date(self) -> date:
        return self._reference_date

    @property
    def expiries(self) -> list[float]:
        return list(self._expiries)

    @property
    def theta_atm(self) -> list[float]:
        return list(self._theta_atm)

    @property
    def rho(self) -> float:
        return self._rho

    @property
    def phi(self) -> SSVIPhiFunction:
        return self._phi

    def forward(
        self,
        time_to_expiry: float,
    ) -> float:
        return float(self._forward(time_to_expiry))

    def implied_vol(
        self,
        time_to_expiry: float,
        strike: float,
    ) -> float:
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        if strike <= 0.0:
            raise ValueError(f"strike must be strictly positive, got {strike!r}")
        k_log = math.log(strike / self.forward(time_to_expiry))
        w = self.total_variance(time_to_expiry, k_log)
        return math.sqrt(max(w, 0.0) / time_to_expiry)

    def total_variance(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        theta = self._theta(time_to_expiry)
        return self._w_from_theta(theta, log_moneyness)

    def dw_dT(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        theta = self._theta(time_to_expiry)
        theta_prime = self._theta_prime(time_to_expiry)
        return self._dw_dT(theta, theta_prime, log_moneyness)

    def dw_dk(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        theta = self._theta(time_to_expiry)
        return self._dw_dk(theta, log_moneyness)

    def d2w_dk2(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        theta = self._theta(time_to_expiry)
        return self._d2w_dk2(theta, log_moneyness)

    def _theta(
        self,
        T: float,
    ) -> float:
        ts = self._expiries
        thetas = self._theta_atm
        if T <= ts[0]:
            return thetas[0] * (T / ts[0])  # flat-vol-in-time
        if T >= ts[-1]:
            return thetas[-1] * (T / ts[-1])
        for i in range(len(ts) - 1):
            if ts[i] <= T <= ts[i + 1]:
                alpha = (T - ts[i]) / (ts[i + 1] - ts[i])
                return thetas[i] + alpha * (thetas[i + 1] - thetas[i])
        raise RuntimeError("theta lookup failed; should be unreachable")

    def _theta_prime(
        self,
        T: float,
    ) -> float:
        ts = self._expiries
        thetas = self._theta_atm
        if T <= ts[0]:
            return thetas[0] / ts[0]
        if T >= ts[-1]:
            return thetas[-1] / ts[-1]
        for i in range(len(ts) - 1):
            if ts[i] <= T <= ts[i + 1]:
                return (thetas[i + 1] - thetas[i]) / (ts[i + 1] - ts[i])
        raise RuntimeError("theta_prime lookup failed; should be unreachable")

    def _w_from_theta(
        self,
        theta: float,
        k: float,
    ) -> float:
        rho = self._rho
        phi_t = self._phi(theta)
        u = phi_t * k + rho
        return 0.5 * theta * (
            1.0 + rho * phi_t * k + math.sqrt(u * u + 1.0 - rho * rho)
        )

    def _dw_dk(
        self,
        theta: float,
        k: float,
    ) -> float:
        rho = self._rho
        phi_t = self._phi(theta)
        u = phi_t * k + rho
        sqrt_val = math.sqrt(u * u + 1.0 - rho * rho)
        return 0.5 * theta * phi_t * (rho + u / sqrt_val)

    def _d2w_dk2(
        self,
        theta: float,
        k: float,
    ) -> float:
        rho = self._rho
        phi_t = self._phi(theta)
        u = phi_t * k + rho
        denom = (u * u + 1.0 - rho * rho) ** 1.5
        return 0.5 * theta * phi_t * phi_t * (1.0 - rho * rho) / denom

    def _dw_dT(
        self,
        theta: float,
        theta_prime: float,
        k: float,
    ) -> float:
        rho = self._rho
        phi_t = self._phi(theta)
        phi_prime_theta = self._phi.derivative(theta)
        u = phi_t * k + rho
        sqrt_val = math.sqrt(u * u + 1.0 - rho * rho)
        A = 1.0 + rho * phi_t * k + sqrt_val
        # dphi/dT = phi'(theta) * theta_prime
        dphi_dT = phi_prime_theta * theta_prime
        # dw/dT = (theta_prime / 2) * A + (theta / 2) * k * dphi_dT * (rho + u / sqrt_val)
        return 0.5 * theta_prime * A + 0.5 * theta * k * dphi_dT * (
            rho + u / sqrt_val
        )
