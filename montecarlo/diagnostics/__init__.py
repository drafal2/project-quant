"""Diagnostics for uniform and normal samplers, plus end-to-end integration smoke tests."""

from .integration import bs_call_price_mc, integrate_gaussian_moment
from .normal_tests import (
    anderson_darling,
    ks_normal,
    moments,
    tail_fractions,
)
from .uniform_tests import (
    chi_square_uniform,
    effective_dimension_2d,
    ks_uniform,
    l2_discrepancy,
    serial_correlation,
)

__all__ = [
    "anderson_darling",
    "bs_call_price_mc",
    "chi_square_uniform",
    "effective_dimension_2d",
    "integrate_gaussian_moment",
    "ks_normal",
    "ks_uniform",
    "l2_discrepancy",
    "moments",
    "serial_correlation",
    "tail_fractions",
]
