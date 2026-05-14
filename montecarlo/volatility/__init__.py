"""Diffusion-side volatility models for the Monte Carlo path engine.

A :class:`VolModel` is the *diffusion coefficient* the path engine consumes per
step: ``diffusion(t, spot, state=None) -> sigma`` per path. The quote-side
counterpart (:class:`market_structures.volatility.VolSurface`) stores implied
vols by ``(T, K)`` and is **not** itself a path-step driver; the bridge between
the two layers is local volatility (Dupire), added in a later PR.

Two concrete models live here today:

- :class:`ConstantVol` — a single scalar sigma, ignoring time and spot.
- :class:`BlackTermStructureVol` — pulls ATM total variance from a surface and
  returns a piecewise-constant instantaneous volatility that reprices the
  pillar ATM vanillas exactly under MC. Skew is ignored.

The ``state`` keyword on :meth:`VolModel.diffusion` is plumbed from day one for
future stochastic-vol models (Heston, SABR) that need to read variance / alpha
state evolved by the path engine; the two models in this PR ignore it.
"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

from .constant import ConstantVol
from .local_vol import DupireLocalVol
from .model import VolModel
from .term_structure import BlackTermStructureVol

__all__ = [
    "BlackTermStructureVol",
    "ConstantVol",
    "DupireLocalVol",
    "VolModel",
]
