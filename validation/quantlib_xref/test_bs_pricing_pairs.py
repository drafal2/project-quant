"""End-to-end Black-Scholes pricing for every compatible ``(sampler, transform)`` pair.

The pricing test is the only cross-check that exercises the **whole stack**
(uniform → normal → discounted payoff). Layer-level tests can pass while a
composition is silently wrong — this module is the safety net for that.

Reference price comes from :class:`QuantLib.BlackCalculator` which is a
closed-form analytic Black-Scholes pricer. The MC estimate from each pair
must agree with that reference to within a multiple of its own sampling
standard error (for PRNG pairs) or within a tight absolute tolerance
(for QMC pairs, where the standard error is not a valid confidence
indicator but the deterministic error is small).

The 21 compatible pairs are:

- **PRNG × any transform** (3 × 5 = 15 pairs): Knuth, MT19937, L'Ecuyer
  combined with CLT, Box-Muller, Moro, Acklam, AS241.
- **QMC × QMC-safe transform** (2 × 3 = 6 pairs): Halton, Sobol combined
  with Moro, Acklam, AS241.

Box-Muller and CLT paired with a QMC base are rejected by
``make_normal_sampler``; those combinations are explicitly **excluded** here.

Observed bias / std error per pair is logged via ``--basetemp`` and is
summarised in ``REPORT.md``.
"""

from __future__ import annotations

import math
import warnings
from typing import NamedTuple

import numpy as np
import pytest
import QuantLib as ql

from montecarlo.diagnostics.integration import bs_call_price_mc
from montecarlo.normal.acklam import AcklamTransform
from montecarlo.normal.box_muller import BoxMullerTransform
from montecarlo.normal.clt import CLTTransform
from montecarlo.normal.factory import make_normal_sampler
from montecarlo.normal.moro import MoroTransform
from montecarlo.normal.wichura import WichuraAS241Transform
from montecarlo.uniform.halton import HaltonSampler
from montecarlo.uniform.knuth import KnuthSampler
from montecarlo.uniform.lecuyer_mrg import LecuyerMRG32k3a1999Sampler
from montecarlo.uniform.mersenne import MersenneTwisterSampler
from montecarlo.uniform.sobol import SobolSampler

S0, K, R, SIGMA, T = 100.0, 100.0, 0.05, 0.20, 1.0
N_PATHS = 65_536  # 2^16 — Sobol equidistribution power of two; ~0.07 SE for PRNG
SEED = 20260512

PRNG_SE_TOLERANCE = 5.0  # multiples of MC std error allowed
QMC_ABS_TOLERANCE = 0.05  # absolute price difference (QMC SE is not a CI)


class _Pair(NamedTuple):
    """One compatible (sampler-factory, transform-factory) combination."""

    label: str
    sampler_factory: object
    transform_factory: object
    is_qmc: bool


def _ql_reference_price() -> float:
    """Compute the analytic Black-Scholes call price via QL's BlackCalculator.

    Returns
    -------
    float
        Closed-form European call price for the module's parameter set.
    """
    payoff = ql.PlainVanillaPayoff(ql.Option.Call, K)
    forward = S0 * math.exp(R * T)
    stdev = SIGMA * math.sqrt(T)
    discount = math.exp(-R * T)
    return float(ql.BlackCalculator(payoff, forward, stdev, discount).value())


def _build_pair_matrix() -> list[_Pair]:
    """Enumerate the 21 compatible (sampler, transform) pairs.

    Returns
    -------
    list[_Pair]
        21 named pairs: 15 PRNG combinations + 6 QMC combinations.
    """
    prng_factories = [
        ("Knuth", lambda: KnuthSampler(seed=SEED), False),
        ("MT19937", lambda: MersenneTwisterSampler(seed=SEED), False),
        ("LEcuyer", lambda: LecuyerMRG32k3a1999Sampler(seed=SEED), False),
    ]
    qmc_factories = [
        ("Halton", lambda: HaltonSampler(max_dimensions=16), True),
        ("Sobol", lambda: SobolSampler(max_dimensions=16), True),
    ]
    all_transforms = [
        ("CLT", lambda: CLTTransform(), False),
        ("BoxMuller", lambda: BoxMullerTransform(), False),
        ("Moro", lambda: MoroTransform(), True),
        ("Acklam", lambda: AcklamTransform(), True),
        ("AS241", lambda: WichuraAS241Transform(), True),
    ]
    pairs: list[_Pair] = []
    for s_name, s_fact, is_qmc in prng_factories:
        for t_name, t_fact, _ in all_transforms:
            pairs.append(_Pair(f"{s_name}+{t_name}", s_fact, t_fact, is_qmc))
    for s_name, s_fact, is_qmc in qmc_factories:
        for t_name, t_fact, qmc_safe in all_transforms:
            if not qmc_safe:
                continue
            pairs.append(_Pair(f"{s_name}+{t_name}", s_fact, t_fact, is_qmc))
    return pairs


PAIRS = _build_pair_matrix()


def test_pair_matrix_has_expected_size():
    """Sanity check: matrix expansion produced exactly 21 pairs."""
    assert len(PAIRS) == 21, f"expected 21 compatible pairs, got {len(PAIRS)}"


@pytest.mark.parametrize("pair", PAIRS, ids=[p.label for p in PAIRS])
def test_bs_pricing_agrees_with_quantlib(pair, capsys):
    """Each compatible pair must price the European call within tolerance.

    Tolerance:

    - PRNG pairs: ``|estimate − QL| ≤ 5 × SE`` (~one false-failure in 3.5 M
      under the normal sampling-error model). The 5-SE margin absorbs the
      small systematic bias of CLT and the occasional tail event without
      hiding a genuine bug.
    - QMC pairs: ``|estimate − QL| ≤ 0.05`` absolute. The reported SE for
      QMC is not a confidence interval; the deterministic error at
      ``N = 65_536`` is empirically well under this bound for Sobol and
      Halton with a QMC-safe inversion transform.

    Per-pair observed error and SE are emitted to stdout for the
    ``REPORT.md`` write-up.
    """
    with warnings.catch_warnings():
        # CLTTransform emits a UserWarning on construction by design.
        warnings.simplefilter("ignore", category=UserWarning)
        normal_sampler = make_normal_sampler(pair.sampler_factory(), pair.transform_factory())

    result = bs_call_price_mc(
        normal_sampler=normal_sampler,
        spot=S0,
        strike=K,
        rate=R,
        sigma=SIGMA,
        maturity=T,
        n_paths=N_PATHS,
    )
    ql_price = _ql_reference_price()
    error = result.estimate - ql_price

    # Diagnostic line — captured by pytest and used to build REPORT.md
    print(
        f"PAIR={pair.label:25s} "
        f"estimate={result.estimate:.6f} ql_ref={ql_price:.6f} "
        f"error={error:+.4e} se={result.std_error:.4e}"
    )

    if pair.is_qmc:
        assert abs(error) < QMC_ABS_TOLERANCE, (
            f"{pair.label}: |error|={abs(error):.4e} exceeds QMC abs tol "
            f"{QMC_ABS_TOLERANCE}"
        )
    else:
        assert abs(error) < PRNG_SE_TOLERANCE * result.std_error, (
            f"{pair.label}: |error|={abs(error):.4e} exceeds "
            f"{PRNG_SE_TOLERANCE}*SE={PRNG_SE_TOLERANCE * result.std_error:.4e}"
        )
