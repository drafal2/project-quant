"""Calibration entry points for SVI and SSVI parametric surfaces.

Two algorithmic families live here:

- :func:`fit_svi_slice` — Zeliade Systems / De Marco-Martini 2009 quasi-explicit
  calibration. For fixed ``(m, sigma)`` the SVI ansatz reparameterises as
  ``w(k) = a + d * y + c * z`` with ``y = k - m``, ``z = sqrt(y^2 + sigma^2)``,
  ``d = b * rho``, ``c = b``. The inner problem is a constrained linear
  least-squares in ``(a, d, c)`` with seven linear inequality constraints
  enforcing the SVI parameter set; the outer problem is a 2-D minimisation in
  ``(m, sigma)`` via Nelder-Mead. Per-slice calibration; far more robust to
  local minima than a direct 5-D Levenberg-Marquardt.
- :func:`fit_ssvi` — Levenberg-Marquardt fit of the global SSVI parameters
  ``(rho, *phi_params)``. The ATM term structure ``theta_T`` is read off the
  input data (linear-in-``w`` per-slice interpolation at ``k_log = 0``); the
  surface model is then ``w(T, k) = (theta_T / 2) * (1 + ...)``.

Both entry points accept an optional ``weights`` argument; default is uniform
in ``w``-space. Pass a vega array (computed by the caller) to mirror the
common "vega-weighted" market calibration.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import Literal

import numpy as np
from scipy.optimize import least_squares, minimize

from .parametric.ssvi import HestonLikePhi, PowerLawPhi, SSVIPhiFunction, SSVISurface
from .parametric.svi import SVIParameters, SVISlice, SVISurface
from .surface import ForwardCallable

logger = logging.getLogger(__name__)


def fit_svi_slice(
    log_moneynesses: Sequence[float],
    total_variances: Sequence[float],
    weights: Sequence[float] | None = None,
) -> SVIParameters:
    """Fit a raw-SVI slice to ``(k, w)`` data via Zeliade's quasi-explicit method.

    Parameters
    ----------
    log_moneynesses
        Log-moneyness samples ``k_log = log(K / F(T))``; at least 5 points
        recommended for a stable 5-parameter fit.
    total_variances
        Target total variances ``w = sigma^2 * T`` at each ``log_moneyness``.
        All values must be strictly positive.
    weights
        Optional per-point weights applied in the residual norm. Default
        ``None`` means uniform-in-``w`` (equal-weighted squared residuals).
        Pass an array of equal length to the data for non-uniform weighting
        (e.g. Black-Scholes vega).

    Returns
    -------
    SVIParameters
        The recovered raw-SVI parameter set.

    Raises
    ------
    ValueError
        If shapes mismatch, fewer than 5 points are provided, or any variance
        is non-positive.
    RuntimeError
        If the outer Nelder-Mead optimisation fails to converge.
    """
    k = np.asarray(log_moneynesses, dtype=np.float64)
    w = np.asarray(total_variances, dtype=np.float64)
    if k.shape != w.shape:
        raise ValueError("log_moneynesses and total_variances must have equal shape")
    if k.size < 5:
        raise ValueError(
            f"need at least 5 points for SVI calibration, got {k.size}"
        )
    if np.any(w <= 0.0):
        raise ValueError("all total_variances must be strictly positive")
    if weights is None:
        wt = np.ones_like(w)
    else:
        wt = np.asarray(weights, dtype=np.float64)
        if wt.shape != w.shape:
            raise ValueError("weights must have the same shape as the data")
        if np.any(wt < 0.0):
            raise ValueError("weights must be non-negative")

    def outer_objective(theta: np.ndarray) -> float:
        m, sigma = theta
        if sigma <= 1e-8:
            return 1e20
        (_a, _d, _c), rss = _inner_constrained_lsq(m, sigma, k, w, wt)
        return rss

    # Multi-start: sweep m at quantiles of the data, sigma on a log grid.
    # The SVI objective in (m, sigma) is non-convex; a single start from
    # (mean, std) often lands in a local minimum away from the smile vertex.
    k_min, k_max = float(np.min(k)), float(np.max(k))
    k_range = max(k_max - k_min, 1e-6)
    m_starts = [
        k_min,
        k_min + 0.25 * k_range,
        float(np.mean(k)),
        k_min + 0.75 * k_range,
        k_max,
    ]
    sigma_starts = [0.05, 0.1, 0.25, 0.5, 1.0]
    debug_enabled = logger.isEnabledFor(logging.DEBUG)
    iter_counter = {"n": 0}

    def callback(xk: np.ndarray) -> None:
        if debug_enabled:
            iter_counter["n"] += 1
            logger.debug(
                "fit_svi_slice NM iter=%d m=%.6f sigma=%.6f",
                iter_counter["n"],
                xk[0],
                xk[1],
            )

    best_rss = float("inf")
    best_x: np.ndarray | None = None
    for m_start in m_starts:
        for sigma_start in sigma_starts:
            local = minimize(
                outer_objective,
                x0=np.array([m_start, sigma_start]),
                method="Nelder-Mead",
                callback=callback if debug_enabled else None,
                options={"xatol": 1e-10, "fatol": 1e-16, "maxiter": 2000},
            )
            if local.success and local.fun < best_rss:
                best_rss = float(local.fun)
                best_x = local.x
    if best_x is None:
        raise RuntimeError("SVI outer Nelder-Mead failed at every starting point")
    m_opt, sigma_opt = best_x
    (a_opt, d_opt, c_opt), rss = _inner_constrained_lsq(
        m_opt, sigma_opt, k, w, wt
    )
    b_opt = c_opt
    rho_opt = d_opt / c_opt if c_opt > 1e-12 else 0.0
    params = SVIParameters(
        a=float(a_opt),
        b=float(b_opt),
        rho=float(np.clip(rho_opt, -1.0, 1.0)),
        m=float(m_opt),
        sigma=float(sigma_opt),
    )
    logger.info(
        "fit_svi_slice: n=%d max_resid=%.3e a=%.4f b=%.4f rho=%+.4f m=%+.4f sigma=%.4f",
        k.size,
        float(np.sqrt(rss / max(k.size, 1))),
        params.a,
        params.b,
        params.rho,
        params.m,
        params.sigma,
    )
    return params


def _inner_constrained_lsq(
    m: float,
    sigma: float,
    k: np.ndarray,
    w: np.ndarray,
    weights: np.ndarray,
) -> tuple[tuple[float, float, float], float]:
    """Constrained linear LSQ in ``(a, d, c)`` for fixed ``(m, sigma)``.

    Constraints (linear inequalities, all of the form ``f(x) >= 0``):

    - ``a >= 0``
    - ``c >= 0``
    - ``c >= |d|`` (i.e. ``c - d >= 0`` and ``c + d >= 0``)
    - ``c <= 4 * sigma``
    - ``c + |d| <= 4 * sigma``

    Returns the optimum ``(a, d, c)`` and the weighted residual sum-of-squares.
    """
    y = k - m
    z = np.sqrt(y * y + sigma * sigma)
    sqrt_w = np.sqrt(weights)
    A = np.column_stack([np.ones_like(y), y, z]) * sqrt_w[:, None]
    b = w * sqrt_w

    def obj(x: np.ndarray) -> float:
        r = A @ x - b
        return float(r @ r)

    def obj_jac(x: np.ndarray) -> np.ndarray:
        r = A @ x - b
        return 2.0 * A.T @ r

    four_sigma = 4.0 * sigma
    constraints = [
        {"type": "ineq", "fun": lambda x: x[0]},                          # a >= 0
        {"type": "ineq", "fun": lambda x: x[2]},                          # c >= 0
        {"type": "ineq", "fun": lambda x: x[2] - x[1]},                   # c - d >= 0
        {"type": "ineq", "fun": lambda x: x[2] + x[1]},                   # c + d >= 0
        {"type": "ineq", "fun": lambda x: four_sigma - x[2]},             # 4σ - c >= 0
        {"type": "ineq", "fun": lambda x: four_sigma - x[2] - x[1]},      # c + d <= 4σ
        {"type": "ineq", "fun": lambda x: four_sigma - x[2] + x[1]},      # c - d <= 4σ
    ]

    a0 = max(float(np.min(w)) * 0.5, 0.0)
    c0 = min(sigma, four_sigma * 0.5)
    x0 = np.array([a0, 0.0, c0])

    result = minimize(
        obj,
        x0=x0,
        jac=obj_jac,
        method="SLSQP",
        constraints=constraints,
        options={"ftol": 1e-14, "maxiter": 200},
    )
    if not result.success:
        # Fall back: clip the unconstrained solution onto the feasible set.
        x_unc, *_ = np.linalg.lstsq(A, b, rcond=None)
        a_unc, d_unc, c_unc = x_unc
        c_clip = float(np.clip(c_unc, 0.0, four_sigma))
        d_clip = float(np.clip(d_unc, -c_clip, c_clip))
        a_clip = max(float(a_unc), 0.0)
        x = np.array([a_clip, d_clip, c_clip])
        return (float(x[0]), float(x[1]), float(x[2])), obj(x)
    x = result.x
    return (float(x[0]), float(x[1]), float(x[2])), float(result.fun)


def fit_svi_surface(
    reference_date: date,
    forward: ForwardCallable,
    expiries: Sequence[float],
    log_moneynesses_by_slice: Sequence[Sequence[float]],
    total_variances_by_slice: Sequence[Sequence[float]],
    weights_by_slice: Sequence[Sequence[float]] | None = None,
) -> SVISurface:
    """Calibrate a full SVI surface, one slice at a time.

    Parameters
    ----------
    reference_date
        Anchor date for the surface.
    forward
        Forward callable for the surface.
    expiries
        Per-slice times-to-expiry in ACT/365 years, strictly increasing.
    log_moneynesses_by_slice
        One log-moneyness array per expiry.
    total_variances_by_slice
        One total-variance array per expiry, matching shapes.
    weights_by_slice
        Optional one weight array per expiry. ``None`` means uniform on every
        slice.

    Returns
    -------
    SVISurface
        Surface with one calibrated :class:`SVISlice` per expiry.
    """
    n = len(expiries)
    if (
        len(log_moneynesses_by_slice) != n
        or len(total_variances_by_slice) != n
    ):
        raise ValueError(
            "log_moneynesses_by_slice and total_variances_by_slice must align with expiries"
        )
    if weights_by_slice is not None and len(weights_by_slice) != n:
        raise ValueError("weights_by_slice must align with expiries")
    slices: list[SVISlice] = []
    max_resid = 0.0
    for i, T in enumerate(expiries):
        params = fit_svi_slice(
            log_moneynesses_by_slice[i],
            total_variances_by_slice[i],
            weights=None if weights_by_slice is None else weights_by_slice[i],
        )
        slc = SVISlice(expiry=float(T), params=params)
        slices.append(slc)
        ks = np.asarray(log_moneynesses_by_slice[i], dtype=np.float64)
        ws = np.asarray(total_variances_by_slice[i], dtype=np.float64)
        residuals = np.array([slc.total_variance(float(k)) - w for k, w in zip(ks, ws)])
        max_resid = max(max_resid, float(np.max(np.abs(residuals))))
    surface = SVISurface(
        reference_date=reference_date,
        forward=forward,
        slices=slices,
    )
    logger.info(
        "fit_svi_surface: n_slices=%d max_abs_resid=%.3e",
        n,
        max_resid,
    )
    return surface


def fit_ssvi(
    reference_date: date,
    forward: ForwardCallable,
    expiries: Sequence[float],
    log_moneynesses_by_slice: Sequence[Sequence[float]],
    total_variances_by_slice: Sequence[Sequence[float]],
    phi_kind: Literal["power_law", "heston_like"],
    weights_by_slice: Sequence[Sequence[float]] | None = None,
    rho_init: float = -0.7,
) -> SSVISurface:
    """Calibrate a global SSVI surface to a market grid.

    The ATM term structure ``theta_T`` is set by linear-in-``w`` per-slice
    interpolation at ``k_log = 0``. The remaining parameters ``(rho,
    *phi_params)`` are then fit jointly by Levenberg-Marquardt on the full
    grid residual ``w_model(T_i, k_ij) - w_market(T_i, k_ij)``.

    Parameters
    ----------
    reference_date
        Anchor date.
    forward
        Forward callable.
    expiries
        Per-slice times-to-expiry, strictly increasing.
    log_moneynesses_by_slice
        Per-slice log-moneyness arrays (need not share a common grid).
    total_variances_by_slice
        Matching per-slice total-variance arrays.
    phi_kind
        ``"power_law"`` (2 params: ``eta``, ``gamma``) or ``"heston_like"``
        (1 param: ``lambda``).
    weights_by_slice
        Optional per-slice weights. ``None`` means uniform on every slice.
    rho_init
        Starting value for ``rho``; equity defaults to ``-0.7`` (negative
        skew). Used only as an initial guess.

    Returns
    -------
    SSVISurface
        Calibrated SSVI surface.
    """
    n = len(expiries)
    if (
        len(log_moneynesses_by_slice) != n
        or len(total_variances_by_slice) != n
    ):
        raise ValueError(
            "log_moneynesses_by_slice and total_variances_by_slice must align with expiries"
        )
    if weights_by_slice is not None and len(weights_by_slice) != n:
        raise ValueError("weights_by_slice must align with expiries")

    expiries_arr = np.asarray(expiries, dtype=np.float64)
    theta_atm = np.array(
        [
            _interp_w_at_k0(
                np.asarray(log_moneynesses_by_slice[i], dtype=np.float64),
                np.asarray(total_variances_by_slice[i], dtype=np.float64),
            )
            for i in range(n)
        ],
        dtype=np.float64,
    )
    if np.any(np.diff(theta_atm) <= 0.0):
        raise ValueError(
            "ATM total variance theta_T must be strictly increasing (calendar arbitrage)"
        )

    # Flatten data for joint LM fit.
    T_flat: list[float] = []
    k_flat: list[float] = []
    w_flat: list[float] = []
    wt_flat: list[float] = []
    for i in range(n):
        ks = np.asarray(log_moneynesses_by_slice[i], dtype=np.float64)
        ws = np.asarray(total_variances_by_slice[i], dtype=np.float64)
        if weights_by_slice is None:
            wts = np.ones_like(ws)
        else:
            wts = np.asarray(weights_by_slice[i], dtype=np.float64)
        for kk, ww, ww_t in zip(ks, ws, wts):
            T_flat.append(float(expiries_arr[i]))
            k_flat.append(float(kk))
            w_flat.append(float(ww))
            wt_flat.append(float(ww_t))
    T_arr = np.array(T_flat)
    k_arr = np.array(k_flat)
    w_arr = np.array(w_flat)
    wt_arr = np.array(wt_flat)
    sqrt_wt = np.sqrt(wt_arr)

    if phi_kind == "power_law":
        x0 = np.array([rho_init, 1.0, 0.5])  # rho, eta, gamma
        lb = np.array([-0.999, 1e-6, 1e-6])
        ub = np.array([0.999, 100.0, 1.0 - 1e-6])

        def build_phi(eta: float, gamma: float) -> SSVIPhiFunction:
            return PowerLawPhi(eta=eta, gamma=gamma)

        def split(x: np.ndarray) -> tuple[float, SSVIPhiFunction]:
            return float(x[0]), build_phi(float(x[1]), float(x[2]))
    elif phi_kind == "heston_like":
        x0 = np.array([rho_init, 1.0])  # rho, lambda
        lb = np.array([-0.999, 1e-6])
        ub = np.array([0.999, 100.0])

        def build_phi(lambda_: float) -> SSVIPhiFunction:
            return HestonLikePhi(lambda_=lambda_)

        def split(x: np.ndarray) -> tuple[float, SSVIPhiFunction]:
            return float(x[0]), build_phi(float(x[1]))
    else:
        raise ValueError(
            f"phi_kind must be 'power_law' or 'heston_like', got {phi_kind!r}"
        )

    def residuals(x: np.ndarray) -> np.ndarray:
        rho, phi = split(x)
        # Build a temporary surface to evaluate w on the (T, k) flat grid.
        # Pass the same theta_atm and pillars; we only need the SSVI w formula.
        try:
            ss = SSVISurface(
                reference_date=reference_date,
                forward=forward,
                expiries=list(expiries_arr),
                theta_atm=list(theta_atm),
                rho=rho,
                phi=phi,
            )
        except ValueError:
            return np.full(w_arr.size, 1e6)
        w_model = np.array(
            [ss.total_variance(float(t), float(k)) for t, k in zip(T_arr, k_arr)]
        )
        return (w_model - w_arr) * sqrt_wt

    result = least_squares(
        residuals,
        x0=x0,
        bounds=(lb, ub),
        method="trf",
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
        max_nfev=10000,
    )
    if not result.success:
        raise RuntimeError(f"SSVI LM failed to converge: {result.message}")
    rho_opt, phi_opt = split(result.x)
    max_resid = float(np.max(np.abs(result.fun)))
    surface = SSVISurface(
        reference_date=reference_date,
        forward=forward,
        expiries=list(expiries_arr),
        theta_atm=list(theta_atm),
        rho=rho_opt,
        phi=phi_opt,
    )
    logger.info(
        "fit_ssvi: phi=%s n_points=%d max_abs_resid=%.3e rho=%+.4f phi_params=%s",
        phi_opt.kind,
        w_arr.size,
        max_resid,
        rho_opt,
        phi_opt.params,
    )
    return surface


def _interp_w_at_k0(
    k: np.ndarray,
    w: np.ndarray,
) -> float:
    """Linear-in-``w`` interpolation of a single slice at ``k = 0``."""
    if np.any(np.diff(k) <= 0):
        raise ValueError("log_moneyness within a slice must be strictly increasing")
    if k[0] > 0.0 or k[-1] < 0.0:
        raise ValueError(
            f"slice does not bracket ATM (k=0): k_min={k[0]:.4f} k_max={k[-1]:.4f}"
        )
    # Find segment containing 0.
    idx = int(np.searchsorted(k, 0.0))
    if k[idx] == 0.0:
        return float(w[idx])
    lo = idx - 1
    hi = idx
    alpha = (0.0 - k[lo]) / (k[hi] - k[lo])
    return float(w[lo] + alpha * (w[hi] - w[lo]))
