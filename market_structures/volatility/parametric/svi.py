"""Raw SVI parameterisation (Gatheral 2004).

Per-slice SVI:

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

with parameter constraints ``b >= 0``, ``|rho| <= 1``, ``sigma > 0``, and
``a + b * sigma * sqrt(1 - rho^2) >= 0`` (the no-negative-variance bound at
``k = m``).

The first two derivatives in log-moneyness are closed-form:

    w'(k)  = b * (rho + (k - m) / sqrt((k - m)^2 + sigma^2))
    w''(k) = b * sigma^2 / ((k - m)^2 + sigma^2)^(3/2)

The full surface :class:`SVISurface` is a collection of :class:`SVISlice`
objects, one per expiry pillar. Cross-T behaviour is linear in total variance
``w`` at fixed log-moneyness (sticky-moneyness, Gatheral convention), matching
:class:`~market_structures.volatility.InterpolatedVolSurface`. Time-boundary
extrapolation is **flat-vol in time** — the boundary slice's ``sigma(k_log)``
is held constant and ``w`` rescales linearly with ``T``.
"""

from __future__ import annotations

import logging
import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..surface import DifferentiableVolSurface, ForwardCallable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SVIParameters:
    """Raw SVI parameter set ``(a, b, rho, m, sigma)``.

    Parameters
    ----------
    a
        Vertical translation; sets the floor of ``w``. Must satisfy
        ``a + b * sigma * sqrt(1 - rho^2) >= 0`` so the variance at ``k = m``
        does not turn negative.
    b
        Wing slope amplitude; must be non-negative.
    rho
        Skew parameter; ``-1 <= rho <= 1``.
    m
        Horizontal translation along ``k``.
    sigma
        Smoothness parameter at the vertex; must be strictly positive.

    Raises
    ------
    ValueError
        If any of the SVI constraints is violated at construction time.
    """

    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def __post_init__(self) -> None:
        if self.b < 0.0:
            raise ValueError(f"b must be non-negative, got {self.b!r}")
        if not -1.0 <= self.rho <= 1.0:
            raise ValueError(f"rho must lie in [-1, 1], got {self.rho!r}")
        if self.sigma <= 0.0:
            raise ValueError(f"sigma must be strictly positive, got {self.sigma!r}")
        floor = self.a + self.b * self.sigma * math.sqrt(1.0 - self.rho * self.rho)
        if floor < -1e-12:
            raise ValueError(
                "no-negative-variance bound violated: "
                f"a + b * sigma * sqrt(1 - rho^2) = {floor!r}"
            )


@dataclass(frozen=True)
class SVISlice:
    """Single-expiry SVI slice with closed-form total variance and derivatives.

    Parameters
    ----------
    expiry
        Time-to-expiry in ACT/365 years; strictly positive.
    params
        :class:`SVIParameters` defining the slice.
    """

    expiry: float
    params: SVIParameters

    def __post_init__(self) -> None:
        if self.expiry <= 0.0:
            raise ValueError(f"expiry must be strictly positive, got {self.expiry!r}")

    def total_variance(
        self,
        log_moneyness: float,
    ) -> float:
        """Return ``w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))``."""
        p = self.params
        x = log_moneyness - p.m
        return p.a + p.b * (p.rho * x + math.sqrt(x * x + p.sigma * p.sigma))

    def dw_dk(
        self,
        log_moneyness: float,
    ) -> float:
        """Return ``w'(k) = b * (rho + (k - m) / sqrt((k - m)^2 + sigma^2))``."""
        p = self.params
        x = log_moneyness - p.m
        return p.b * (p.rho + x / math.sqrt(x * x + p.sigma * p.sigma))

    def d2w_dk2(
        self,
        log_moneyness: float,
    ) -> float:
        """Return ``w''(k) = b * sigma^2 / ((k - m)^2 + sigma^2)^(3/2)``."""
        p = self.params
        x = log_moneyness - p.m
        denom = (x * x + p.sigma * p.sigma) ** 1.5
        return p.b * p.sigma * p.sigma / denom


class SVISurface(DifferentiableVolSurface):
    """Implied-vol surface stitched from a sequence of :class:`SVISlice` objects.

    Parameters
    ----------
    reference_date
        Anchor date (``t = 0``) for the time axis.
    forward
        Callable returning the forward ``F(T)`` for ``T`` in ACT/365 years.
    slices
        Per-expiry slices in strictly increasing time-to-expiry. At least one
        slice is required.

    Notes
    -----
    Cross-slice interpolation is linear in total variance ``w`` at fixed
    log-moneyness (sticky-moneyness, Gatheral convention). Outside the
    quoted time range, the boundary slice's ``sigma(k_log)`` is held constant
    and ``w`` rescales linearly with ``T`` (flat-vol-in-time extrapolation,
    matching :class:`~market_structures.volatility.InterpolatedVolSurface`).
    """

    def __init__(
        self,
        reference_date: date,
        forward: ForwardCallable,
        slices: Sequence[SVISlice],
    ) -> None:
        if len(slices) == 0:
            raise ValueError("at least one SVI slice is required")
        ordered = list(slices)
        for i in range(1, len(ordered)):
            if ordered[i].expiry <= ordered[i - 1].expiry:
                raise ValueError("slice expiries must be strictly increasing")

        self._reference_date = reference_date
        self._forward = forward
        self._slices: list[SVISlice] = ordered
        self._expiries: list[float] = [s.expiry for s in ordered]

        self._check_calendar_arbitrage_at_slice_boundaries()

        logger.info(
            "SVISurface built: n_slices=%d T_range=[%.4f, %.4f] max_abs_rho=%.4f",
            len(ordered),
            ordered[0].expiry,
            ordered[-1].expiry,
            max(abs(s.params.rho) for s in ordered),
        )

    @property
    def reference_date(self) -> date:
        """Return the surface reference date."""
        return self._reference_date

    @property
    def expiries(self) -> list[float]:
        """Return a copy of the slice expiries in ACT/365 years."""
        return list(self._expiries)

    @property
    def slices(self) -> list[SVISlice]:
        """Return a shallow copy of the slice list."""
        return list(self._slices)

    def forward(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return the forward at ``time_to_expiry``."""
        return float(self._forward(time_to_expiry))

    def total_variance(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return interpolated total variance at ``(T, k_log)``."""
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        return self._interp_w(time_to_expiry, log_moneyness)

    def implied_vol(
        self,
        time_to_expiry: float,
        strike: float,
    ) -> float:
        """Return the implied volatility ``sigma(T, K)``."""
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        if strike <= 0.0:
            raise ValueError(f"strike must be strictly positive, got {strike!r}")
        k_log = math.log(strike / self.forward(time_to_expiry))
        w = self._interp_w(time_to_expiry, k_log)
        return math.sqrt(max(w, 0.0) / time_to_expiry)

    def dw_dT(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``dw/dT`` at fixed ``log_moneyness``."""
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        return self._dw_dT(time_to_expiry, log_moneyness)

    def dw_dk(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``dw/dk_log`` at fixed ``time_to_expiry``."""
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        return self._interp_derivative(time_to_expiry, log_moneyness, order=1)

    def d2w_dk2(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return ``d2w/dk_log2`` at fixed ``time_to_expiry``."""
        if time_to_expiry <= 0.0:
            raise ValueError(
                f"time_to_expiry must be strictly positive, got {time_to_expiry!r}"
            )
        return self._interp_derivative(time_to_expiry, log_moneyness, order=2)

    def _interp_w(
        self,
        T: float,
        k_log: float,
    ) -> float:
        ts = self._expiries
        slices = self._slices
        if T <= ts[0]:
            # Flat-vol-in-time: w = w_0(k) * T / T_0.
            return slices[0].total_variance(k_log) * (T / ts[0])
        if T >= ts[-1]:
            return slices[-1].total_variance(k_log) * (T / ts[-1])
        # Locate segment (T_i, T_{i+1}]; linear in w at fixed k_log.
        i = self._segment_index(T)
        w_lo = slices[i].total_variance(k_log)
        w_hi = slices[i + 1].total_variance(k_log)
        alpha = (T - ts[i]) / (ts[i + 1] - ts[i])
        return w_lo + alpha * (w_hi - w_lo)

    def _dw_dT(
        self,
        T: float,
        k_log: float,
    ) -> float:
        ts = self._expiries
        slices = self._slices
        if T <= ts[0]:
            # w(T, k) = w_0(k) * T / T_0 -> dw/dT = w_0(k) / T_0.
            return slices[0].total_variance(k_log) / ts[0]
        if T >= ts[-1]:
            return slices[-1].total_variance(k_log) / ts[-1]
        i = self._segment_index(T)
        w_lo = slices[i].total_variance(k_log)
        w_hi = slices[i + 1].total_variance(k_log)
        return (w_hi - w_lo) / (ts[i + 1] - ts[i])

    def _interp_derivative(
        self,
        T: float,
        k_log: float,
        order: int,
    ) -> float:
        """Linear cross-T interpolation of a per-slice k-derivative."""
        ts = self._expiries
        slices = self._slices

        def slope_or_curv(slc: SVISlice) -> float:
            return slc.dw_dk(k_log) if order == 1 else slc.d2w_dk2(k_log)

        if T <= ts[0]:
            # Flat-vol-in-time: w(T, k) = w_0(k) * T / T_0, so
            # d/dk w(T, k) = w_0'(k) * T / T_0 and same scaling for d2/dk2.
            return slope_or_curv(slices[0]) * (T / ts[0])
        if T >= ts[-1]:
            return slope_or_curv(slices[-1]) * (T / ts[-1])
        i = self._segment_index(T)
        d_lo = slope_or_curv(slices[i])
        d_hi = slope_or_curv(slices[i + 1])
        alpha = (T - ts[i]) / (ts[i + 1] - ts[i])
        return d_lo + alpha * (d_hi - d_lo)

    def _segment_index(
        self,
        T: float,
    ) -> int:
        ts = self._expiries
        for i in range(len(ts) - 1):
            if ts[i] <= T <= ts[i + 1]:
                return i
        # Defensive — caller has already handled T outside [ts[0], ts[-1]].
        raise RuntimeError("segment lookup failed; should be unreachable")

    def _check_calendar_arbitrage_at_slice_boundaries(self) -> None:
        """Warn if adjacent slices cross at any union-grid log-moneyness."""
        slices = self._slices
        for i in range(len(slices) - 1):
            # Sample on the union of vertex+wing points of both slices.
            ms = (slices[i].params.m, slices[i + 1].params.m)
            sample_k = [ms[0], ms[1], (ms[0] + ms[1]) / 2.0, -2.0, -1.0, 0.0, 1.0, 2.0]
            for k in sample_k:
                w_lo = slices[i].total_variance(k)
                w_hi = slices[i + 1].total_variance(k)
                if w_hi + 1e-12 < w_lo:
                    warnings.warn(
                        "calendar arbitrage between SVI slices at "
                        f"T={slices[i].expiry:.4f} and T={slices[i + 1].expiry:.4f} "
                        f"at k_log={k:.4f}: w decreases from {w_lo:.6f} to {w_hi:.6f}",
                        UserWarning,
                        stacklevel=3,
                    )
                    return
