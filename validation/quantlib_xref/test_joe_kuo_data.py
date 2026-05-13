"""Sobol direction-number parity vs QuantLib ``JoeKuoD6``.

The vendored direction-number table in :mod:`montecarlo.uniform._joe_kuo_data`
comes from Joe and Kuo's ``new-joe-kuo-6.21201`` file. The "6" refers to the
discrepancy parameter ``D`` of the paper; QuantLib exposes the matching set as
``ql.SobolRsg.JoeKuoD6``. This test confirms that

1. Our :class:`SobolSampler` and ``ql.SobolRsg(JoeKuoD6)`` agree to within the
   open-interval ULP shift (``2 ** -33`` ≈ 1.17e-10) for the first 1024 points
   in 64 dimensions, and
2. The neighbouring sets ``JoeKuoD5`` and ``JoeKuoD7`` diverge by ``O(1)`` past
   their first divergent dimension — proving the test is actually
   distinguishing direction-number sets and not just shared low-dim columns.
"""

import numpy as np
import pytest
import QuantLib as ql

from montecarlo.uniform.sobol import SobolSampler

ULP_SHIFT = 2.0 ** -32  # our SobolSampler uses (x + 0.5) / 2^32 for the open interval


def _ql_points(
    n_dims: int,
    n_pts: int,
    direction_set: int,
) -> np.ndarray:
    """Generate ``n_pts`` rows × ``n_dims`` cols from QuantLib's Sobol RSG.

    Parameters
    ----------
    n_dims
        Number of Sobol dimensions.
    n_pts
        Number of consecutive points to draw, starting from the origin.
    direction_set
        QuantLib direction-integer set constant
        (``ql.SobolRsg.JoeKuoD5``, ``JoeKuoD6``, or ``JoeKuoD7``).

    Returns
    -------
    numpy.ndarray
        ``(n_pts, n_dims)`` ``float64`` array.
    """
    rsg = ql.SobolRsg(n_dims, 0, direction_set)
    return np.array([list(rsg.nextSequence().value()) for _ in range(n_pts)])


def test_sobol_matches_joe_kuo_d6():
    """First 1024 points × 64 dims must match QL JoeKuoD6 within the open-interval shift."""
    n_pts, n_dims = 1024, 64
    ours = SobolSampler(max_dimensions=n_dims).next_block(n_pts, n_dims)
    theirs = _ql_points(n_dims, n_pts, ql.SobolRsg.JoeKuoD6)
    max_diff = float(np.max(np.abs(ours - theirs)))
    # Allow the constant 2**-33 ULP shift plus a safety factor of 2.
    assert max_diff <= 2 * ULP_SHIFT, (
        f"Sobol vs QL JoeKuoD6 max abs diff = {max_diff:.3e}, "
        f"expected <= {2 * ULP_SHIFT:.3e}"
    )


@pytest.mark.parametrize(
    ("direction_set", "name"),
    [
        (ql.SobolRsg.JoeKuoD5, "JoeKuoD5"),
        (ql.SobolRsg.JoeKuoD7, "JoeKuoD7"),
    ],
)
def test_sobol_does_not_match_neighbouring_sets(direction_set, name):
    """JoeKuoD5/D7 must diverge from our table — proves we are testing D6 specifically.

    The neighbouring direction-number sets share initial columns with D6 but
    differ in higher dimensions. If our test silently matched D5 or D7, the
    parity assertion against D6 would be untrustworthy. We therefore require
    an ``O(1)`` discrepancy on at least one column within the first 32 dims.
    """
    n_pts, n_dims = 64, 32
    ours = SobolSampler(max_dimensions=n_dims).next_block(n_pts, n_dims)
    theirs = _ql_points(n_dims, n_pts, direction_set)
    per_dim_diff = np.max(np.abs(ours - theirs), axis=0)
    assert (per_dim_diff > 0.1).any(), (
        f"QL {name} unexpectedly matches our table across all {n_dims} dims; "
        "the D6 parity test would not be distinguishing direction-number sets"
    )
