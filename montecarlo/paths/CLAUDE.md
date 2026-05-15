# montecarlo/paths/

Monte Carlo path generation. This package consumes the uniform / normal
samplers in `montecarlo/` and the diffusion-side `VolModel` family in
`montecarlo/volatility/`, and produces the spot path tensor that downstream
payoff modules will price against. PR 1 ships the single-asset core;
variance-reduction (PR 2 antithetic, PR 3 Brownian bridge) and basket
(PR 4 correlation) extensions slot into the same engine class via kwargs that
are already locked in the signature.

## Layout

- **`time_grid.py`** — `TimeGrid`: ordered year-fraction grid
  `[0 = t_0 < t_1 < ... < t_N]`. The anchor `t_0 = 0` is mandatory and explicit;
  the engine reads `n_steps = N` and per-step lengths `dts` directly. Two
  constructors: `TimeGrid(year_fractions)` for an explicit grid (must start at
  zero) and `TimeGrid.from_dates(reference_date, dates)` which converts dates
  strictly after the reference to ACT/365 year fractions and prepends `0.0`.
- **`engine.py`** — `PathEngine` ABC. Single abstract method: `simulate(n_paths)`
  returns a `float64` array of shape `(n_paths, n_steps + 1, n_assets)`. The
  trailing asset axis is always present, including `n_assets == 1`; consumers
  who want a 2-D view squeeze it themselves. Time index `0` holds the broadcast
  initial spots; subsequent indices follow the engine's discretisation scheme.
- **`euler_log.py`** — `EulerLogPathEngine`: the concrete single-/multi-asset
  Euler-log engine. Integrates the log-spread `X_t = log(S_t / F(t))` rather
  than spot directly: `dX_t = -0.5 sigma^2 dt + sigma dW_t` under any
  risk-neutral measure whose forward curve is `F(t)`. The discretisation is
  `X_{k+1} = X_k - 0.5 sigma_k^2 dt + sigma_k sqrt(dt) Z_k`, then
  `S_{k+1} = F(t_{k+1}) exp(X_{k+1})`. `sigma_k` is evaluated at the **start**
  of the step (Itô convention); for the first step (`t_0 = 0`) the engine
  passes `max(t_0, 1e-12)` to `VolModel.diffusion` so the `DupireLocalVol`
  contract (`time > 0` required) is honoured without special-casing.

## Invariants

- **Output shape is permanent**: `(n_paths, n_steps + 1, n_assets)`. The asset
  axis is preserved across all PRs of this roadmap so the engine call site does
  not churn between single-asset and basket modes.
- **Forward-domain step**: drift is absorbed entirely by the `ForwardCallable`.
  The engine never sees a `ZeroCurve`, a dividend yield, or a borrow rate
  directly — the caller bakes those into `F(t)` via `EquityForward.at_time`,
  `EquityForwardCurve.__call__`, or any custom callable matching the
  `market_structures.volatility.surface.ForwardCallable` protocol. This keeps
  the engine asset-class-agnostic; future FX / commodity siblings of
  `EquityForwardCurve` drop in unchanged.
- **Single sampler call per `simulate()`**: the engine asks `normal_sampler`
  for one block of shape `(n_paths, n_steps * n_assets)` and reshapes to
  `(n_paths, n_steps, n_assets)`. Re-entering the sampler mid-step would break
  the QMC dimension structure that PR 3 (Brownian bridge) and PR 4
  (correlation) rely on. New variance-reduction features wrap or post-process
  the block; they never split the call.
- **Reserved kwargs**: `antithetic`, `brownian_bridge`, and `correlation` are
  accepted in the constructor but raise `NotImplementedError` if set in PR 1.
  They must remain in the signature so future PRs land without breaking
  callers.

## Logging convention

- `engine.py`-level INFO once per `__init__` summarising `n_assets`, `n_steps`,
  and the sampler class. Once per `simulate()` summarising path counts and
  wall-clock time.
- No DEBUG inside the step loop. With `n_steps * n_assets` iterations this
  fires too often to be useful; the existing INFO summary plus the sampler /
  vol-model lifecycle logs are the diagnostic surface.

## Extension points (deferred to later PRs)

- **PR 2 — antithetic variates**: an `AntitheticNormalSampler` wrapper that
  doubles the path block by sign-flipping each draw. Wrapping a quasi base is
  refused by the same rule that rejects Box-Muller + Sobol.
- **PR 3 — Brownian bridge**: a `BrownianBridge` constructed from the
  `TimeGrid` reorders the `(n_paths, n_steps, n_assets)` normal block so the
  largest-variance Brownian increments consume the lowest QMC dimensions.
- **PR 4 — multi-asset correlation**: a `Correlation` object holding the
  basket correlation matrix and its Cholesky factor; per-step normals are
  transformed as `Z @ L.T` before entering the step update.
