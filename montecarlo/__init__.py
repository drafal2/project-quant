"""Monte Carlo sampling: uniform PRNGs, low-discrepancy sequences, normal transforms.

This package is the foundation of the Monte Carlo engine that will later support
equity basket autocall pricing. It exposes a dimension-aware ``Sampler`` ABC and
several concrete strategies (Knuth, L'Ecuyer MRG32k3a, Mersenne Twister, Halton,
Sobol with Joe-Kuo direction numbers), a ``NormalTransform`` ABC with five
strategies (CLT, Box-Muller, Moro, Acklam, Wichura AS241), and a
``make_normal_sampler`` factory that enforces the QMC / inversion pairing rule:
low-discrepancy sequences (``Sobol``, ``Halton``) must be paired with an
inverse-cumulative transform (``Moro``, ``Acklam``, ``WichuraAS241``); pairing
them with ``BoxMuller`` or ``CLT`` is a correctness bug and is rejected.

See ``montecarlo/CLAUDE.md`` for the pairing rules in detail.
"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

from .normal import (
    AcklamTransform,
    BoxMullerTransform,
    CLTTransform,
    MoroTransform,
    NormalSampler,
    NormalTransform,
    WichuraAS241Transform,
    make_normal_sampler,
)
from .sampler import Sampler
from .uniform import (
    HaltonSampler,
    KnuthSampler,
    LecuyerLCG1988Sampler,
    LecuyerMRG32k3a1999Sampler,
    MersenneTwisterSampler,
    SobolSampler,
)
from .volatility import (
    BlackTermStructureVol,
    ConstantVol,
    VolModel,
)

__all__ = [
    "AcklamTransform",
    "BlackTermStructureVol",
    "BoxMullerTransform",
    "CLTTransform",
    "ConstantVol",
    "HaltonSampler",
    "KnuthSampler",
    "LecuyerLCG1988Sampler",
    "LecuyerMRG32k3a1999Sampler",
    "MersenneTwisterSampler",
    "MoroTransform",
    "NormalSampler",
    "NormalTransform",
    "Sampler",
    "SobolSampler",
    "VolModel",
    "WichuraAS241Transform",
    "make_normal_sampler",
]
