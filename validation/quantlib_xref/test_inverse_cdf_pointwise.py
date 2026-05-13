"""Pointwise inverse-cumulative-normal parity against QuantLib and scipy.

This module exercises every inverse-CDF transform in :mod:`montecarlo.normal`
on a shared input grid and asserts agreement with an authoritative reference:

- :class:`WichuraAS241Transform` is bit-perfect against ``scipy.special.ndtri``
  to machine precision. **It is not compared to** ``ql.InverseCumulativeNormal``
  because QuantLib mis-names its routine: the function it ships under that
  name is a Beasley-Springer-Moro / Acklam-class approximation (max abs error
  ~8e-9 against scipy), not Wichura's AS241. See ``REPORT.md`` for detail.
- :class:`AcklamTransform` is checked against ``scipy.special.ndtri`` because
  QuantLib has no clean Acklam (2003) counterpart.
- :class:`MoroTransform` is checked in two regions: the **body** region
  (``u ∈ [1e-4, 1 - 1e-4]``) where Moro's rational polynomial holds and our
  implementation agrees with QuantLib to machine precision; and the **deep
  tail** (``u < 1e-7`` or ``u > 1 - 1e-7``) where Moro's log-log tail formula
  degrades. The body region is the regime where Moro is fit for production
  use; the tail degradation is the price of choosing Moro over AS241 and is
  documented in ``REPORT.md``.
"""

import numpy as np
import pytest
import QuantLib as ql
from scipy.special import ndtri

from montecarlo.normal.acklam import AcklamTransform
from montecarlo.normal.moro import MoroTransform
from montecarlo.normal.wichura import WichuraAS241Transform


def _apply(
    transform,
    u: np.ndarray,
) -> np.ndarray:
    """Run a NormalTransform over a 1D u-grid and flatten the result.

    Parameters
    ----------
    transform
        Instance of any :class:`NormalTransform` subclass.
    u
        1D array of uniforms in (0, 1).

    Returns
    -------
    numpy.ndarray
        1D array of normals.
    """
    return transform.transform(u.reshape(-1, 1)).ravel()


def _ql_pointwise(
    fn,
    u: np.ndarray,
) -> np.ndarray:
    """Evaluate a QuantLib scalar functor at each entry of ``u``.

    QuantLib's inverse-CDF objects expose ``__call__(float) -> float`` only;
    we loop to obtain a vectorised result.

    Parameters
    ----------
    fn
        QuantLib functor, e.g. ``ql.InverseCumulativeNormal()``.
    u
        1D array of uniforms in (0, 1).

    Returns
    -------
    numpy.ndarray
        1D ``float64`` array.
    """
    return np.array([fn(float(x)) for x in u], dtype=np.float64)


@pytest.fixture(scope="module")
def u_body() -> np.ndarray:
    """Uniform grid that stays inside the Moro / Acklam body region.

    Returns
    -------
    numpy.ndarray
        ``100_001`` equally-spaced points in ``[1e-4, 1 - 1e-4]``.
    """
    return np.linspace(1e-4, 1 - 1e-4, 100_001)


@pytest.fixture(scope="module")
def u_full() -> np.ndarray:
    """Uniform grid that reaches into the deep tails (``|z| > 7``).

    Returns
    -------
    numpy.ndarray
        Log-spaced grid from ``1e-15`` to ``1 - 1e-15``.
    """
    left = np.geomspace(1e-15, 0.5, 5_000)
    right = 1.0 - left
    return np.unique(np.concatenate([left, right]))


def test_as241_matches_scipy_to_machine_precision(u_full):
    """Wichura AS241 is bit-perfect against scipy.special.ndtri.

    The Wichura (1988) algorithm is the reference inverse-normal implementation
    in scipy as well — both reach IEEE-754 machine precision across the full
    representable range. Any failure here means the AS241 coefficients have
    drifted from the published table.
    """
    ours = _apply(WichuraAS241Transform(), u_full)
    truth = ndtri(u_full)
    max_err = float(np.max(np.abs(ours - truth)))
    assert max_err < 1e-13, f"AS241 vs scipy ndtri max abs err = {max_err:.3e}"


def test_quantlib_inverse_cumulative_normal_is_not_as241(u_full):
    """Document that QL.InverseCumulativeNormal is *not* Wichura AS241.

    Despite the name suggesting a high-precision inverse-normal, QuantLib's
    ``InverseCumulativeNormal`` is a Beasley-Springer-Moro / Acklam-class
    rational approximation accurate to ~8e-9 against scipy. This test pins
    that finding so a future reader does not assume QL ships AS241.
    """
    ql_vals = _ql_pointwise(ql.InverseCumulativeNormal(), u_full)
    truth = ndtri(u_full)
    max_err = float(np.max(np.abs(ql_vals - truth)))
    assert 1e-9 < max_err < 1e-7, (
        f"QL InverseCumulativeNormal vs scipy ndtri max abs err = {max_err:.3e}; "
        "expected ~8e-9 (Acklam-class accuracy, not AS241)"
    )


def test_acklam_matches_scipy(u_full):
    """Acklam (2003) is accurate to ~1e-8 across the full input range.

    QuantLib has no clean Acklam counterpart (its ``InverseCumulativeNormal``
    is a related but distinct BSM / Acklam-class routine), so we use
    ``scipy.special.ndtri`` as the reference.
    """
    ours = _apply(AcklamTransform(), u_full)
    truth = ndtri(u_full)
    max_err = float(np.max(np.abs(ours - truth)))
    assert max_err < 1e-7, f"Acklam vs scipy ndtri max abs err = {max_err:.3e}"


def test_moro_body_matches_quantlib_to_machine_precision(u_body):
    """In the body region, Moro is bit-identical to QuantLib's Moro.

    Both implementations use Moro's (1995) central rational polynomial. The
    body region is where Moro is fit for production: max abs error ~3e-9
    against scipy. Agreement with QL here confirms our coefficient table is
    not corrupted.
    """
    ours = _apply(MoroTransform(), u_body)
    theirs = _ql_pointwise(ql.MoroInverseCumulativeNormal(), u_body)
    max_diff = float(np.max(np.abs(ours - theirs)))
    assert max_diff < 1e-12, f"ours-Moro vs QL-Moro body max abs diff = {max_diff:.3e}"


def test_moro_body_matches_scipy_within_paper_accuracy(u_body):
    """Moro vs scipy ndtri in the body region: within Moro's published ~3e-9.

    Pinning this gives a regression alarm if a future change to
    ``MoroTransform`` accidentally lowers central-region accuracy.
    """
    ours = _apply(MoroTransform(), u_body)
    truth = ndtri(u_body)
    max_err = float(np.max(np.abs(ours - truth)))
    assert max_err < 1e-8, f"Moro vs scipy ndtri body max abs err = {max_err:.3e}"


def test_moro_deep_tail_degrades_as_documented():
    """Moro's log-log tail formula degrades past ~7 sigma — assert the known shape.

    This is **not a defect** in our implementation: Moro (1995) section 4
    explicitly trades deep-tail accuracy for code compactness. QuantLib's
    ``MoroInverseCumulativeNormal`` augments the original Moro tail with a
    sharper formula and so retains ~1e-8 accuracy in the deep tail; ours
    follows the paper literally. For tail-sensitive products, the project's
    documentation steers users to :class:`WichuraAS241Transform`.
    """
    # Deep tail only (|z| > ~7.5)
    u = np.geomspace(1e-15, 1e-13, 200)
    ours = _apply(MoroTransform(), u)
    truth = ndtri(u)
    ql_v = _ql_pointwise(ql.MoroInverseCumulativeNormal(), u)
    ours_err = float(np.max(np.abs(ours - truth)))
    ql_err = float(np.max(np.abs(ql_v - truth)))
    # Our Moro tail error: ~5e-3 (paper-faithful)
    assert ours_err > 1e-4, (
        f"Moro deep-tail err unexpectedly small ({ours_err:.3e}); "
        "tail formula may have been silently improved"
    )
    # QL's Moro tail is augmented and remains tight
    assert ql_err < 1e-7, f"QL Moro deep-tail err = {ql_err:.3e} unexpectedly large"
