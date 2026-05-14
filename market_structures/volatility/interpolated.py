"""Non-parametric interpolated implied-vol surface.

Stores total implied variance ``w = sigma^2 * T`` on a per-slice
log-moneyness grid. Across time, ``w`` is linearly interpolated at fixed
log-moneyness (a sticky-moneyness scheme: the smile shape moves with the
forward, matching the convention used by Gatheral's SVI/SSVI). Within each
slice, a pluggable :class:`Interpolator` connects the quoted log-moneyness
points; the default is linear in ``w``, which preserves quoted vols exactly
at the nodes.

Two constructors are exposed:

- :meth:`from_option_prices` — full pipeline: invert each price to its
  Black-76 implied volatility via Brent, then build the canonical grid.
- :meth:`from_implied_vols` — bypass inversion when the user already has
  implied vols.

Both classmethods are equity-specific (take spot, zero curve, dividend
yield); the low-level ``__init__`` is asset-class-agnostic and takes any
forward callable plus a pre-computed ``(T, k_log, w)`` grid.
"""

from __future__ import annotations

import logging
import math
import warnings
from collections.abc import Callable, Sequence
from datetime import date

from market_conventions import DayCountConvention
from schedules.day_count import day_count_fraction

from ..interpolation.interpolators import Interpolator, LinearInterpolator
from ..rates.curve import ZeroCurve
from .forward import EquityForward
from .pricing import implied_vol_from_price, no_arb_price_bounds
from .surface import ForwardCallable, VolSurface

logger = logging.getLogger(__name__)

_EQUITY_DCC = DayCountConvention.ACT_365_FIXED


class InterpolatedVolSurface(VolSurface):
    """Non-parametric implied-vol surface on a ``(T, k_log)`` grid.

    Each maturity slice carries its own sorted log-moneyness grid; slices may
    have different lengths and need not share strikes. Queries outside the
    log-moneyness range of a slice extrapolate flat in ``w``; queries outside
    the time range extrapolate flat-vol in time (the boundary slice's
    ``sigma(k_log)`` is held constant and ``w = sigma^2 * T``).

    Attributes
    ----------
    reference_date
        Anchor date for the time axis.
    expiries
        Sorted list of per-slice times-to-expiry in ACT/365 years.
    """

    def __init__(
        self,
        reference_date: date,
        forward: ForwardCallable,
        expiries: Sequence[float],
        log_moneynesses: Sequence[Sequence[float]],
        total_variances: Sequence[Sequence[float]],
        smile_interpolator: Interpolator | None = None,
    ) -> None:
        """Build the surface from a pre-computed total-variance grid.

        Parameters
        ----------
        reference_date
            Anchor date (``t = 0``) for the time axis.
        forward
            Callable returning the forward ``F(T)`` for ``T`` in ACT/365 years;
            used by :meth:`implied_vol` to convert strikes to log-moneyness at
            query time.
        expiries
            Per-slice times-to-expiry in ACT/365 years. Must be strictly
            positive and strictly increasing.
        log_moneynesses
            Per-slice log-moneyness grids; one sequence per entry in
            ``expiries``. Each inner sequence must be strictly increasing and
            have the same length as the matching entry in ``total_variances``.
        total_variances
            Per-slice total-variance values ``w = sigma^2 * T``; same shape as
            ``log_moneynesses``. Each value must be strictly positive.
        smile_interpolator
            Strategy used to interpolate ``w`` within a slice. Defaults to
            :class:`LinearInterpolator` with ``extrapolate=True`` (flat outside
            the slice range).

        Raises
        ------
        ValueError
            If the grid is malformed (empty, mismatched lengths, non-monotone
            expiries or log-moneynesses, non-positive variances).
        """
        if len(expiries) == 0:
            raise ValueError("at least one expiry slice is required")
        if len(log_moneynesses) != len(expiries) or len(total_variances) != len(expiries):
            raise ValueError(
                "log_moneynesses and total_variances must have one sequence per expiry"
            )
        ts = [float(t) for t in expiries]
        for t in ts:
            if t <= 0.0:
                raise ValueError(f"expiries must be strictly positive, got {t}")
        for i in range(1, len(ts)):
            if ts[i] <= ts[i - 1]:
                raise ValueError("expiries must be strictly increasing")

        slices_k: list[list[float]] = []
        slices_w: list[list[float]] = []
        for i, (ks_raw, ws_raw) in enumerate(zip(log_moneynesses, total_variances)):
            ks = [float(k) for k in ks_raw]
            ws = [float(w) for w in ws_raw]
            if len(ks) != len(ws):
                raise ValueError(
                    f"slice {i}: log_moneyness and total_variance length mismatch"
                )
            if len(ks) < 2:
                raise ValueError(f"slice {i}: at least two log-moneyness points required")
            for j in range(1, len(ks)):
                if ks[j] <= ks[j - 1]:
                    raise ValueError(
                        f"slice {i}: log_moneynesses must be strictly increasing"
                    )
            for w in ws:
                if w <= 0.0:
                    raise ValueError(f"slice {i}: total_variance must be positive, got {w}")
            slices_k.append(ks)
            slices_w.append(ws)

        self._reference_date = reference_date
        self._forward = forward
        self._expiries = ts
        self._slices_k = slices_k
        self._slices_w = slices_w
        self._smile = smile_interpolator or LinearInterpolator(extrapolate=True)

        self._check_calendar_arbitrage()

        logger.info(
            "InterpolatedVolSurface built: n_expiries=%d n_quotes=%d "
            "T_range=[%.4f, %.4f]",
            len(ts),
            sum(len(ks) for ks in slices_k),
            ts[0],
            ts[-1],
        )

    @property
    def reference_date(self) -> date:
        """Return the surface reference date."""
        return self._reference_date

    @property
    def expiries(self) -> list[float]:
        """Return a copy of the per-slice times-to-expiry in ACT/365 years."""
        return list(self._expiries)

    def forward(
        self,
        time_to_expiry: float,
    ) -> float:
        """Return the forward at the given time-to-expiry by delegating to the stored callable.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.

        Returns
        -------
        float
            Forward ``F(T)``.
        """
        return float(self._forward(time_to_expiry))

    def total_variance(
        self,
        time_to_expiry: float,
        log_moneyness: float,
    ) -> float:
        """Return the total implied variance at ``(T, k_log)``.

        Interpolation scheme:

        - Within a slice: pluggable :class:`Interpolator` on ``(k_log, w)``,
          flat-extrapolation outside the slice's range.
        - Across slices: linear in ``w`` at fixed ``log_moneyness`` between
          bracketing slices; outside the surface's time range, holds the
          boundary slice's ``sigma(k_log)`` constant and rescales
          ``w`` proportionally to ``T`` (flat-vol-in-time extrapolation).

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        log_moneyness
            Log-moneyness ``k_log = log(K / F(T))``.

        Returns
        -------
        float
            Total implied variance ``w(T, k_log)``.

        Raises
        ------
        ValueError
            If ``time_to_expiry`` is non-positive.
        """
        if time_to_expiry <= 0.0:
            raise ValueError("time_to_expiry must be positive")
        ts = self._expiries
        if time_to_expiry <= ts[0]:
            # Flat-vol-in-time extrapolation: rescale boundary w by T/T_boundary
            # so the recovered sigma is the boundary slice's sigma at this k_log.
            return self._slice_w(0, log_moneyness) * (time_to_expiry / ts[0])
        if time_to_expiry >= ts[-1]:
            return self._slice_w(len(ts) - 1, log_moneyness) * (
                time_to_expiry / ts[-1]
            )
        for i in range(len(ts) - 1):
            if ts[i] <= time_to_expiry <= ts[i + 1]:
                w_left = self._slice_w(i, log_moneyness)
                w_right = self._slice_w(i + 1, log_moneyness)
                u = (time_to_expiry - ts[i]) / (ts[i + 1] - ts[i])
                return w_left + u * (w_right - w_left)
        # Unreachable: bracket loop above is exhaustive for ts[0] < T < ts[-1].
        raise RuntimeError("time bracketing failed (internal error)")

    def implied_vol(
        self,
        time_to_expiry: float,
        strike: float,
    ) -> float:
        """Return the Black-76 implied volatility at ``(T, K)``.

        Computes ``k_log = log(K / F(T))`` using the stored forward callable,
        then reads off ``w`` from :meth:`total_variance` and returns
        ``sqrt(w / T)``.

        Parameters
        ----------
        time_to_expiry
            Year fraction from :attr:`reference_date`; must be strictly positive.
        strike
            Option strike; must be strictly positive.

        Returns
        -------
        float
            Lognormal implied volatility.

        Raises
        ------
        ValueError
            If ``strike`` is non-positive.
        """
        if strike <= 0.0:
            raise ValueError(f"strike must be positive, got {strike}")
        fwd = self.forward(time_to_expiry)
        k_log = math.log(strike / fwd)
        w = self.total_variance(time_to_expiry, k_log)
        return math.sqrt(w / time_to_expiry)

    def _slice_w(
        self,
        slice_index: int,
        log_moneyness: float,
    ) -> float:
        """Return ``w`` at a given log-moneyness on a specific slice.

        Parameters
        ----------
        slice_index
            Index into :attr:`expiries` selecting the slice.
        log_moneyness
            Query log-moneyness; flat-extrapolated outside the slice's grid.

        Returns
        -------
        float
            Interpolated total variance on the slice.
        """
        ks = self._slices_k[slice_index]
        ws = self._slices_w[slice_index]
        return self._smile.interpolate(log_moneyness, ks, ws)

    def _check_calendar_arbitrage(self) -> None:
        """Emit ``UserWarning`` when ``w`` is non-monotone in ``T`` across slices.

        For each adjacent pair of slices, evaluates ``w`` on the union of the
        two slices' log-moneyness grids and warns on any point where the
        later slice has strictly lower total variance than the earlier slice.
        """
        for i in range(len(self._expiries) - 1):
            ks_union = sorted(set(self._slices_k[i]) | set(self._slices_k[i + 1]))
            for k in ks_union:
                w_left = self._slice_w(i, k)
                w_right = self._slice_w(i + 1, k)
                if w_right < w_left:
                    warnings.warn(
                        f"Calendar arbitrage at k_log={k:.4f}: "
                        f"w(T={self._expiries[i]:.4f})={w_left:.6g} > "
                        f"w(T={self._expiries[i + 1]:.4f})={w_right:.6g}.",
                        UserWarning,
                        stacklevel=3,
                    )

    @classmethod
    def from_option_prices(
        cls,
        reference_date: date,
        spot: float,
        dividend_yield: float,
        zero_curve: ZeroCurve,
        expiries: Sequence[date],
        strikes: Sequence[Sequence[float]],
        prices: Sequence[Sequence[float]],
        option_types: Sequence[Sequence[str]],
        smile_interpolator: Interpolator | None = None,
        inversion_tolerance: float = 1e-8,
    ) -> "InterpolatedVolSurface":
        """Build the surface from raw European option prices by inverting each to a Black vol.

        For each ``(expiry, strike, price, option_type)``, runs
        :func:`implied_vol_from_price` (Brent on the Black-76 price residual)
        and stores the resulting ``(k_log, w)`` pair on the matching slice.
        Quotes that fall outside the static no-arbitrage bounds are skipped
        with a ``UserWarning`` rather than aborting construction.

        Parameters
        ----------
        reference_date
            Anchor date for the time axis. Must match
            ``zero_curve.reference_date``.
        spot
            Underlying spot at ``reference_date``; must be strictly positive.
        dividend_yield
            Continuous dividend yield ``q`` in ACT/365.
        zero_curve
            Risk-free discount curve used both to discount option prices and
            to build the equity forward via :class:`EquityForward`.
        expiries
            Sorted list of slice expiry dates, all strictly after
            ``reference_date``.
        strikes
            Per-slice strike grids; one sequence per entry in ``expiries``.
        prices
            Per-slice market prices (present-value premiums); same shape as
            ``strikes``.
        option_types
            Per-slice option-type tags ``"C"`` or ``"P"``; same shape as
            ``strikes``.
        smile_interpolator
            Within-slice interpolator on ``(k_log, w)``. Defaults to
            :class:`LinearInterpolator`.
        inversion_tolerance
            Brent tolerance on ``sigma`` for each price-to-vol inversion.
            Defaults to ``1e-8``.

        Returns
        -------
        InterpolatedVolSurface
            Calibrated surface; each retained quote evaluates back to the
            input vol to within ``inversion_tolerance`` (and back to the input
            price to within the implied price tolerance).

        Raises
        ------
        ValueError
            If ``reference_date`` does not match the curve, if shape constraints
            are violated, or if any slice ends up with fewer than two quotes
            after arb-bound filtering.
        """
        if reference_date != zero_curve.reference_date:
            raise ValueError(
                f"reference_date {reference_date} does not match "
                f"zero_curve.reference_date {zero_curve.reference_date}"
            )
        n = len(expiries)
        if not (len(strikes) == n and len(prices) == n and len(option_types) == n):
            raise ValueError(
                "strikes, prices, and option_types must have one entry per expiry"
            )

        equity_forward = EquityForward(spot, zero_curve, dividend_yield)

        ts: list[float] = []
        slices_k: list[list[float]] = []
        slices_w: list[list[float]] = []
        max_residual = 0.0
        n_skipped = 0

        for slice_idx, expiry in enumerate(expiries):
            if expiry <= reference_date:
                raise ValueError(f"expiry {expiry} must be strictly after reference_date")
            t_i = day_count_fraction(reference_date, expiry, _EQUITY_DCC)
            f_i = equity_forward.at_date(expiry)
            df_i = zero_curve.discount_factor(expiry)

            ks_slice = strikes[slice_idx]
            prices_slice = prices[slice_idx]
            types_slice = option_types[slice_idx]
            if not (len(ks_slice) == len(prices_slice) == len(types_slice)):
                raise ValueError(
                    f"slice {slice_idx}: strikes / prices / option_types length mismatch"
                )

            pairs: list[tuple[float, float]] = []
            for k, p, ot in zip(ks_slice, prices_slice, types_slice):
                lower, upper = no_arb_price_bounds(f_i, float(k), df_i, ot)
                if not lower < p < upper:
                    warnings.warn(
                        f"slice {slice_idx} (T={t_i:.4f}): quote K={k} price={p} "
                        f"outside no-arb bounds ({lower:.6g}, {upper:.6g}); skipping.",
                        UserWarning,
                        stacklevel=2,
                    )
                    n_skipped += 1
                    continue
                sigma = implied_vol_from_price(
                    price=float(p),
                    forward=f_i,
                    strike=float(k),
                    time_to_expiry=t_i,
                    df_funding=df_i,
                    option_type=ot,
                    tolerance=inversion_tolerance,
                )
                from .pricing import black_scholes_price  # local import avoids cycles
                residual = abs(
                    black_scholes_price(f_i, float(k), t_i, sigma, df_i, ot) - float(p)
                )
                max_residual = max(max_residual, residual)
                k_log = math.log(float(k) / f_i)
                pairs.append((k_log, sigma * sigma * t_i))

            if len(pairs) < 2:
                raise ValueError(
                    f"slice {slice_idx} has fewer than two usable quotes after "
                    f"arb-bound filtering ({len(pairs)} retained)"
                )
            pairs.sort(key=lambda kv: kv[0])
            slice_ks = [kv[0] for kv in pairs]
            slice_ws = [kv[1] for kv in pairs]
            ts.append(t_i)
            slices_k.append(slice_ks)
            slices_w.append(slice_ws)

        logger.info(
            "from_option_prices inverted %d quote(s) across %d slice(s); "
            "skipped=%d max_residual=%.2e",
            sum(len(ks) for ks in slices_k),
            len(ts),
            n_skipped,
            max_residual,
        )

        return cls(
            reference_date=reference_date,
            forward=equity_forward.at_time,
            expiries=ts,
            log_moneynesses=slices_k,
            total_variances=slices_w,
            smile_interpolator=smile_interpolator,
        )

    @classmethod
    def from_implied_vols(
        cls,
        reference_date: date,
        spot: float,
        dividend_yield: float,
        zero_curve: ZeroCurve,
        expiries: Sequence[date],
        strikes: Sequence[Sequence[float]],
        implied_vols: Sequence[Sequence[float]],
        smile_interpolator: Interpolator | None = None,
    ) -> "InterpolatedVolSurface":
        """Build the surface directly from quoted implied vols, skipping price inversion.

        Equivalent to :meth:`from_option_prices` when the caller already has
        Black-76 implied volatilities and only needs the canonical
        ``(T, k_log, w)`` grid built. No arb-bound filtering is performed
        on the implied vols themselves (vols are already in the post-inversion
        space); calendar-arbitrage warnings are still emitted on construction.

        Parameters
        ----------
        reference_date
            Anchor date for the time axis. Must match
            ``zero_curve.reference_date``.
        spot
            Underlying spot at ``reference_date``.
        dividend_yield
            Continuous dividend yield ``q`` in ACT/365.
        zero_curve
            Risk-free discount curve, used only to construct the equity
            forward.
        expiries
            Sorted list of slice expiry dates.
        strikes
            Per-slice strike grids.
        implied_vols
            Per-slice Black-76 implied vols; same shape as ``strikes``. Must
            be strictly positive.
        smile_interpolator
            Within-slice interpolator on ``(k_log, w)``. Defaults to
            :class:`LinearInterpolator`.

        Returns
        -------
        InterpolatedVolSurface
            Calibrated surface.

        Raises
        ------
        ValueError
            If shape constraints are violated, if expiries are not strictly
            after ``reference_date``, or if any vol is non-positive.
        """
        if reference_date != zero_curve.reference_date:
            raise ValueError(
                f"reference_date {reference_date} does not match "
                f"zero_curve.reference_date {zero_curve.reference_date}"
            )
        n = len(expiries)
        if not (len(strikes) == n and len(implied_vols) == n):
            raise ValueError("strikes and implied_vols must have one entry per expiry")

        equity_forward = EquityForward(spot, zero_curve, dividend_yield)

        ts: list[float] = []
        slices_k: list[list[float]] = []
        slices_w: list[list[float]] = []

        for slice_idx, expiry in enumerate(expiries):
            if expiry <= reference_date:
                raise ValueError(f"expiry {expiry} must be strictly after reference_date")
            t_i = day_count_fraction(reference_date, expiry, _EQUITY_DCC)
            f_i = equity_forward.at_date(expiry)

            ks_slice = strikes[slice_idx]
            vols_slice = implied_vols[slice_idx]
            if len(ks_slice) != len(vols_slice):
                raise ValueError(
                    f"slice {slice_idx}: strikes / implied_vols length mismatch"
                )
            pairs: list[tuple[float, float]] = []
            for k, v in zip(ks_slice, vols_slice):
                if v <= 0.0:
                    raise ValueError(
                        f"slice {slice_idx}: implied_vol must be positive, got {v}"
                    )
                k_log = math.log(float(k) / f_i)
                pairs.append((k_log, float(v) * float(v) * t_i))
            pairs.sort(key=lambda kv: kv[0])
            ts.append(t_i)
            slices_k.append([kv[0] for kv in pairs])
            slices_w.append([kv[1] for kv in pairs])

        return cls(
            reference_date=reference_date,
            forward=equity_forward.at_time,
            expiries=ts,
            log_moneynesses=slices_k,
            total_variances=slices_w,
            smile_interpolator=smile_interpolator,
        )
