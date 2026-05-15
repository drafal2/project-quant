"""Martingale-preserving Euler-log path engine.

The engine integrates the **log-spread** ``X_t = log(S_t / F(t))`` rather than
the spot or log-spot directly. Under a risk-neutral measure with a calibrated
forward curve ``F(t)``, ``S_t / F(t)`` is a martingale, so

    dX_t = -0.5 * sigma(t, S_t)^2 dt + sigma(t, S_t) dW_t,

with **no remaining drift term**: the entire forward-rate / dividend / borrow
contribution is absorbed by ``F(t)``. Discretising this on a
:class:`~montecarlo.paths.TimeGrid` ``[0 = t_0 < t_1 < ... < t_N]`` gives

    X_{k+1} = X_k - 0.5 * sigma_k^2 * dt_k + sigma_k * sqrt(dt_k) * Z_k,
    S_{k+1} = F(t_{k+1}) * exp(X_{k+1}),

where ``sigma_k = vol_model.diffusion(t_k, S_k)`` is evaluated at the **start**
of the step (Itô convention, Euler-Maruyama). The two design consequences are
worth stating explicitly:

- The scheme is **drift-discretisation-error-free**: the only discretisation
  error comes from freezing ``sigma`` at the step start, which is the standard
  Euler-Maruyama error of order ``O(sqrt(dt))`` for the weak SDE and ``O(dt)``
  for European-style functionals (Glasserman 6.4, Andersen-Piterbarg Vol. I).
- The engine never sees a ``ZeroCurve`` or dividend yield directly. The
  forward curve is the **only** drift input, so the caller is free to use
  ``EquityForward.at_time``, the new ``EquityForwardCurve`` callable, or any
  other ``ForwardCallable`` implementation without churning the engine.

``DupireLocalVol.diffusion`` is singular at ``time == 0``; the engine therefore
evaluates ``sigma`` at ``max(t_k, _T_EPS)`` with ``_T_EPS = 1e-12`` for the
first step only. This is a no-op for ``ConstantVol`` and
``BlackTermStructureVol`` and a numerically negligible bias for local-vol
models (the bias is bounded by ``O(t_1)`` on the first step's sigma, which
itself enters the path through an ``O(sqrt(dt))`` term).
"""

from __future__ import annotations

import logging
import time as _time
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from market_structures.volatility.surface import ForwardCallable

from ..normal.factory import NormalSampler
from ..volatility.model import VolModel
from .engine import PathEngine
from .time_grid import TimeGrid

if TYPE_CHECKING:
    from .correlation import Correlation  # pragma: no cover (future PR 4)

logger = logging.getLogger(__name__)

_T_EPS = 1e-12


class EulerLogPathEngine(PathEngine):
    """Euler-log path engine with martingale-preserving forward-domain stepping.

    Single-asset and multi-asset modes share one implementation: ``spots``,
    ``forward_curves``, and ``vol_models`` are coerced to length-1 sequences if
    scalars are supplied, and the output always carries the trailing
    ``n_assets`` axis.

    The variance-reduction kwargs ``antithetic``, ``brownian_bridge``, and
    ``correlation`` are accepted but inert in this PR; they raise
    :class:`NotImplementedError` if set to a non-default value, with the
    message naming the future PR that will deliver them. The reserved
    signature slots are stable so the engine call site will not churn across
    PRs.
    """

    def __init__(
        self,
        spots: float | Sequence[float],
        forward_curves: ForwardCallable | Sequence[ForwardCallable],
        vol_models: VolModel | Sequence[VolModel],
        time_grid: TimeGrid,
        normal_sampler: NormalSampler,
        *,
        antithetic: bool = False,
        brownian_bridge: bool = False,
        correlation: "Correlation | None" = None,
    ) -> None:
        """Construct the engine and validate its multi-asset shapes.

        Parameters
        ----------
        spots
            Initial spot value(s). A scalar is interpreted as the single-asset
            case; a sequence of length ``n_assets`` runs a basket.
        forward_curves
            One ``ForwardCallable`` per asset (or a single callable for the
            single-asset case). Each is invoked as ``F(t)`` with ``t`` in
            ACT/365 year fractions from the simulation reference date.
        vol_models
            One :class:`VolModel` per asset (or a single model for the
            single-asset case).
        time_grid
            :class:`TimeGrid` whose first entry is ``0.0``; the engine steps
            through the remaining ``n_steps`` entries.
        normal_sampler
            :class:`~montecarlo.normal.factory.NormalSampler` producing
            ``N(0, 1)`` blocks; called **once per simulation** with shape
            ``(n_paths, n_steps * n_assets)`` to preserve the dimension
            structure that PR 3 (Brownian bridge) will rely on.
        antithetic
            Reserved for PR 2. Must be ``False`` in this PR; ``True`` raises
            :class:`NotImplementedError`.
        brownian_bridge
            Reserved for PR 3. Must be ``False`` in this PR; ``True`` raises
            :class:`NotImplementedError`.
        correlation
            Reserved for PR 4. Must be ``None`` in this PR; any non-``None``
            value raises :class:`NotImplementedError`.

        Raises
        ------
        ValueError
            If ``spots``, ``forward_curves``, and ``vol_models`` have
            inconsistent lengths, or if any spot is non-positive.
        NotImplementedError
            If any of the reserved variance-reduction kwargs is set.
        """
        if antithetic:
            raise NotImplementedError(
                "antithetic=True is reserved for PR 2 of the path-engine roadmap"
            )
        if brownian_bridge:
            raise NotImplementedError(
                "brownian_bridge=True is reserved for PR 3 of the path-engine roadmap"
            )
        if correlation is not None:
            raise NotImplementedError(
                "correlation is reserved for PR 4 of the path-engine roadmap"
            )

        spots_arr = self._coerce_to_array(spots, "spots")
        if np.any(spots_arr <= 0.0):
            raise ValueError("all spots must be strictly positive")
        forwards = self._coerce_to_list(forward_curves)
        vols = self._coerce_to_list(vol_models)
        n_assets = spots_arr.size
        if len(forwards) != n_assets or len(vols) != n_assets:
            raise ValueError(
                f"spots, forward_curves, and vol_models must have matching "
                f"length; got {n_assets}, {len(forwards)}, {len(vols)}"
            )

        self._spots = spots_arr
        self._forwards = forwards
        self._vols = vols
        self._time_grid = time_grid
        self._sampler = normal_sampler
        self._n_assets = int(n_assets)

        logger.info(
            "EulerLogPathEngine built: n_assets=%d n_steps=%d sampler=%s",
            self._n_assets,
            time_grid.n_steps,
            type(normal_sampler.sampler).__name__,
        )

    @property
    def n_assets(self) -> int:
        """Return the basket dimension (``1`` for a single-asset engine)."""
        return self._n_assets

    @property
    def time_grid(self) -> TimeGrid:
        """Return the engine's time grid."""
        return self._time_grid

    def simulate(
        self,
        n_paths: int,
    ) -> np.ndarray:
        """Simulate ``n_paths`` correlated (or independent) paths.

        Parameters
        ----------
        n_paths
            Number of Monte Carlo paths; must be a strictly positive integer.

        Returns
        -------
        numpy.ndarray
            ``float64`` array of shape ``(n_paths, n_steps + 1, n_assets)``.
            ``out[:, 0, :]`` equals the configured spots broadcast over paths.

        Raises
        ------
        ValueError
            If ``n_paths`` is not a strictly positive integer.
        """
        if not isinstance(n_paths, int) or n_paths <= 0:
            raise ValueError(
                f"n_paths must be a strictly positive integer, got {n_paths!r}"
            )

        n_steps = self._time_grid.n_steps
        n_assets = self._n_assets
        times = self._time_grid.times
        dts = self._time_grid.dts
        sqrt_dts = np.sqrt(dts)

        # Single sampler call: locks the dimension ordering that PR 3 (Brownian
        # bridge) and PR 4 (correlation) will operate on.
        normals_flat = self._sampler.next_block(n_paths, n_steps * n_assets)
        normals = normals_flat.reshape(n_paths, n_steps, n_assets)

        paths = np.empty((n_paths, n_steps + 1, n_assets), dtype=np.float64)
        paths[:, 0, :] = self._spots  # broadcast spots across all paths

        # Pre-compute forwards at every grid time; saves N*n_assets callable
        # invocations per simulate() call.
        forwards_at_times = np.empty((n_steps + 1, n_assets), dtype=np.float64)
        forwards_at_times[0, :] = self._spots  # F(0) == S0 by definition
        for k in range(1, n_steps + 1):
            for i in range(n_assets):
                forwards_at_times[k, i] = float(self._forwards[i](float(times[k])))

        log_spread = np.zeros((n_paths, n_assets), dtype=np.float64)
        start_wall = _time.perf_counter()
        for k in range(n_steps):
            t_k = float(times[k])
            t_eval = max(t_k, _T_EPS)
            dt = float(dts[k])
            sqrt_dt = float(sqrt_dts[k])
            for i in range(n_assets):
                sigma = np.asarray(
                    self._vols[i].diffusion(t_eval, paths[:, k, i]),
                    dtype=np.float64,
                )
                log_spread[:, i] = (
                    log_spread[:, i]
                    - 0.5 * sigma * sigma * dt
                    + sigma * sqrt_dt * normals[:, k, i]
                )
                paths[:, k + 1, i] = forwards_at_times[k + 1, i] * np.exp(
                    log_spread[:, i]
                )
        elapsed = _time.perf_counter() - start_wall
        logger.info(
            "EulerLogPathEngine simulated %d paths, %d steps, %d assets in %.3fs",
            n_paths,
            n_steps,
            n_assets,
            elapsed,
        )
        return paths

    @staticmethod
    def _coerce_to_array(
        value: float | Sequence[float],
        name: str,
    ) -> np.ndarray:
        """Coerce a scalar-or-sequence numeric input to a 1-D ``float64`` array.

        Parameters
        ----------
        value
            Scalar or 1-D sequence of floats.
        name
            Parameter name used in the error message when the input is
            higher-rank than 1-D.

        Returns
        -------
        numpy.ndarray
            ``float64`` 1-D array. A scalar input becomes a length-1 array.

        Raises
        ------
        ValueError
            If ``value`` is a 2-D or higher-rank array.
        """
        if np.isscalar(value):
            arr = np.asarray([value], dtype=np.float64)
        else:
            arr = np.asarray(value, dtype=np.float64)
            if arr.ndim != 1:
                raise ValueError(
                    f"{name} must be a scalar or 1-D sequence, "
                    f"got shape {arr.shape}"
                )
        return arr

    @staticmethod
    def _coerce_to_list(
        value: object,
    ) -> list:
        """Wrap a non-sequence value in a single-element list, pass sequences through.

        Returns
        -------
        list
            ``list(value)`` if ``value`` is already a list or tuple, otherwise
            ``[value]``.
        """
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]
