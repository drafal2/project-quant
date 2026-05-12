"""Uniform sampler agreement against QuantLib.

After porting `KnuthSampler` and adding `LecuyerLCG1988Sampler`, four of the
six uniform samplers now match QuantLib **bit-for-bit** for any non-zero
seed:

- **Mersenne Twister** — same MT19937 algorithm, same seed expansion, same
  ``(int32 + 0.5) / 2^32`` floating-point conversion.
- **Knuth** — port of QL's RANARRAY (`ranf_start` + `ranf_array`) algorithm
  in IEEE doubles, KK=100 / LL=37 / TT=70.
- **L'Ecuyer combined-LCG (1988)** — port of QL's `LecuyerUniformRng`
  (two LCGs + Bays-Durham shuffle; Numerical Recipes ``ran2``).
- **Halton** with ``random_start=True`` — uses MT to draw per-dimension
  start offsets, matching QL's ``randomStart=True`` mode.
- **Halton** with ``random_start=False`` — already bit-exact against
  ``ql.HaltonRsg(d, seed, randomStart=False)``.
- **Sobol** — already bit-exact (mod 2^-33 open-interval ULP shift) against
  ``ql.SobolRsg(JoeKuoD6)``; covered separately in ``test_joe_kuo_data.py``.

`LecuyerMRG32k3a1999Sampler` (L'Ecuyer 1999 MRG) has **no QuantLib counterpart**;
QL's `LecuyerUniformRng` is the older 1988 LCG and is matched by the new
`LecuyerLCG1988Sampler` instead. We retain a distributional check against
QL's older sampler as a sanity baseline that the two implementations agree
on the relevant statistical contract (KS / moments at large N), since both
are L'Ecuyer's work.

See ``REPORT.md`` for the observed numbers and the seed=0 caveat (QL maps
seed=0 to a clock-randomised seed; our samplers do not — pass a non-zero
seed for reproducible bit-parity).
"""

from __future__ import annotations

import numpy as np
import pytest
import QuantLib as ql
from scipy.stats import kstest

from montecarlo.uniform.halton import HaltonSampler
from montecarlo.uniform.knuth import KnuthSampler
from montecarlo.uniform.lecuyer import LecuyerMRG32k3a1999Sampler
from montecarlo.uniform.lecuyer_lcg import LecuyerLCG1988Sampler
from montecarlo.uniform.mersenne import MersenneTwisterSampler

KS_ALPHA = 1e-4
BIT_PARITY_SEEDS = [1, 15, 42, 12345, 999_999]


def _ql_prng_draws(
    rng,
    n: int,
) -> np.ndarray:
    """Draw ``n`` uniforms from a QuantLib uniform RNG.

    Parameters
    ----------
    rng
        A ``ql.MersenneTwisterUniformRng`` / ``KnuthUniformRng`` /
        ``LecuyerUniformRng`` instance.
    n
        Number of draws.

    Returns
    -------
    numpy.ndarray
        1D ``float64`` array of length ``n``.
    """
    return np.array([rng.next().value() for _ in range(n)], dtype=np.float64)


@pytest.mark.parametrize("seed", BIT_PARITY_SEEDS)
def test_mt19937_bit_exact_match(seed):
    """``MersenneTwisterSampler`` matches ``ql.MersenneTwisterUniformRng`` bit-exact.

    Same algorithm and same ``(uint32 + 0.5) / 2^32`` conversion mean
    byte-for-byte agreement for any non-zero seed. We compare 500
    consecutive draws to keep cost low while spanning more than one
    refill of the 624-word state.
    """
    n = 500
    ours = MersenneTwisterSampler(seed=seed).next_block(n, 1).ravel()
    theirs = _ql_prng_draws(ql.MersenneTwisterUniformRng(seed), n)
    assert np.array_equal(ours, theirs), (
        f"MT bit-parity failed at seed={seed}: "
        f"max abs diff = {np.max(np.abs(ours - theirs)):.3e}"
    )


@pytest.mark.parametrize("seed", BIT_PARITY_SEEDS)
def test_knuth_bit_exact_match(seed):
    """``KnuthSampler`` (RANARRAY port) matches ``ql.KnuthUniformRng`` bit-exact.

    Knuth's quality trick only uses the first ``KK = 100`` values of every
    ``QUALITY = 1009`` block; 500 draws exercises five regeneration cycles.
    """
    n = 500
    ours = KnuthSampler(seed=seed).next_block(n, 1).ravel()
    theirs = _ql_prng_draws(ql.KnuthUniformRng(seed), n)
    assert np.array_equal(ours, theirs), (
        f"Knuth bit-parity failed at seed={seed}: "
        f"max abs diff = {np.max(np.abs(ours - theirs)):.3e}"
    )


@pytest.mark.parametrize("seed", BIT_PARITY_SEEDS)
def test_lecuyer_lcg_1988_bit_exact_match(seed):
    """``LecuyerLCG1988Sampler`` matches ``ql.LecuyerUniformRng`` bit-exact.

    Both implement the 1988 combined-LCG + Bays-Durham shuffle from
    Numerical Recipes ``ran2``; 500 draws is well beyond the 32-element
    shuffle buffer.
    """
    n = 500
    ours = LecuyerLCG1988Sampler(seed=seed).next_block(n, 1).ravel()
    theirs = _ql_prng_draws(ql.LecuyerUniformRng(seed), n)
    assert np.array_equal(ours, theirs), (
        f"LecuyerLCG1988 bit-parity failed at seed={seed}: "
        f"max abs diff = {np.max(np.abs(ours - theirs)):.3e}"
    )


@pytest.mark.parametrize("seed", [1, 10, 42, 12345])
def test_halton_random_start_bit_exact_match(seed):
    """``HaltonSampler(random_start=True)`` matches ``ql.HaltonRsg(randomStart=True)``.

    Both implementations draw per-dimension start offsets from MT19937
    (which itself is bit-exact between the two libraries), then apply the
    offsets to the van der Corput counter. Bit-parity for any non-zero
    seed.
    """
    n_pts, n_dims = 64, 8
    ours = HaltonSampler(
        max_dimensions=n_dims, seed=seed, random_start=True
    ).next_block(n_pts, n_dims)
    rsg = ql.HaltonRsg(n_dims, seed, True, False)
    theirs = np.array([list(rsg.nextSequence().value()) for _ in range(n_pts)])
    assert np.array_equal(ours, theirs), (
        f"Halton random_start bit-parity failed at seed={seed}: "
        f"max abs diff = {np.max(np.abs(ours - theirs)):.3e}"
    )


@pytest.mark.parametrize("seed", [1, 42, 12345])
def test_halton_deterministic_bit_exact_match(seed):
    """``HaltonSampler`` default (``random_start=False``) bit-matches QL.

    The seed is a no-op when ``random_start=False`` on both sides, so any
    seed value should give the canonical Halton sequence starting at the
    second van der Corput point.
    """
    n_pts, n_dims = 1024, 8
    ours = HaltonSampler(max_dimensions=n_dims).next_block(n_pts, n_dims)
    rsg = ql.HaltonRsg(n_dims, seed, False, False)
    theirs = np.array([list(rsg.nextSequence().value()) for _ in range(n_pts)])
    assert np.array_equal(ours, theirs), (
        f"Halton deterministic bit-parity failed at seed={seed}: "
        f"max abs diff = {np.max(np.abs(ours - theirs)):.3e}"
    )


def test_mrg32k3a_distributional_against_ql_lecuyer_1988():
    """``LecuyerMRG32k3a1999Sampler`` (1999) is distributionally indistinguishable from QL's 1988 LCG.

    These are **different algorithms** (a multiple-recursive generator vs
    a combined LCG with shuffle), both due to L'Ecuyer; no bit-match is
    possible or expected. We confirm only that both pass a one-sample KS
    test against ``U(0, 1)`` and that their first two moments agree, as a
    sanity baseline showing the project's production sampler is at least
    as statistically faithful as QL's reference implementation.
    """
    n = 200_000
    ours = LecuyerMRG32k3a1999Sampler(seed=42).next_block(n, 1).ravel()
    theirs = _ql_prng_draws(ql.LecuyerUniformRng(42), n)
    p_ours = float(kstest(ours, "uniform").pvalue)
    p_theirs = float(kstest(theirs, "uniform").pvalue)
    assert p_ours > KS_ALPHA, f"MRG32k3a KS p-value = {p_ours:.3e}"
    assert p_theirs > KS_ALPHA, f"QL LecuyerUniformRng KS p-value = {p_theirs:.3e}"
    assert abs(ours.mean() - theirs.mean()) < 5e-3
    assert abs(ours.var() - theirs.var()) < 5e-3
