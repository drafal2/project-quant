"""Monte Carlo path generation: time grids and Euler-log path engines.

The package consumes uniform / normal samplers from :mod:`montecarlo` and
volatility models from :mod:`montecarlo.volatility`, and produces the spot
path tensor consumed by future payoff modules. See ``CLAUDE.md`` in this
directory for the dimension contract and the forward-domain step derivation.
"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

from .engine import PathEngine
from .euler_log import EulerLogPathEngine
from .time_grid import TimeGrid

__all__ = [
    "EulerLogPathEngine",
    "PathEngine",
    "TimeGrid",
]
