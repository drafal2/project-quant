"""Tests for the CreditCurve interpolation parameterisations."""

import math
from datetime import date

import pytest

from credit.curve import CreditCurve, InterpolationVariable
from market_conventions import DayCountConvention

REF = date(2024, 1, 2)
ACT365 = DayCountConvention.ACT_365_FIXED


def _t(d: date) -> float:
    return (d - REF).days / 365.0


class TestForwardDefaultSpread:
    def test_pillar_recovery(self):
        pillars = [date(2025, 1, 2), date(2027, 1, 2)]
        lambdas = [0.02, 0.03]
        curve = CreditCurve(REF, pillars, lambdas, InterpolationVariable.FORWARD_DEFAULT_SPREAD, ACT365)
        q1 = math.exp(-0.02 * _t(pillars[0]))
        q2 = q1 * math.exp(-0.03 * (_t(pillars[1]) - _t(pillars[0])))
        assert curve.non_default_probability(pillars[0]) == pytest.approx(q1, rel=1e-12)
        assert curve.non_default_probability(pillars[1]) == pytest.approx(q2, rel=1e-12)

    def test_default_probability_complement(self):
        curve = CreditCurve(REF, [date(2026, 1, 2)], [0.05], InterpolationVariable.FORWARD_DEFAULT_SPREAD, ACT365)
        d = date(2025, 7, 1)
        assert curve.default_probability(d) == pytest.approx(1.0 - curve.non_default_probability(d))

    def test_forward_spread_matches_segment_lambda(self):
        pillars = [date(2025, 1, 2), date(2027, 1, 2)]
        lambdas = [0.02, 0.04]
        curve = CreditCurve(REF, pillars, lambdas, InterpolationVariable.FORWARD_DEFAULT_SPREAD, ACT365)
        fwd = curve.forward_default_spread(pillars[0], pillars[1])
        assert fwd == pytest.approx(0.04, rel=1e-12)


class TestDefaultSpread:
    def test_pillar_recovery(self):
        pillars = [date(2025, 1, 2), date(2027, 1, 2)]
        spreads = [0.015, 0.020]
        curve = CreditCurve(REF, pillars, spreads, InterpolationVariable.DEFAULT_SPREAD, ACT365)
        for d, s in zip(pillars, spreads):
            assert curve.default_spread(d) == pytest.approx(s, rel=1e-12)
            assert curve.non_default_probability(d) == pytest.approx(math.exp(-s * _t(d)), rel=1e-12)


class TestSurvivalProbability:
    def test_pillar_recovery(self):
        pillars = [date(2025, 1, 2), date(2027, 1, 2)]
        qs = [0.97, 0.92]
        curve = CreditCurve(REF, pillars, qs, InterpolationVariable.SURVIVAL_PROBABILITY, ACT365)
        for d, q in zip(pillars, qs):
            assert curve.non_default_probability(d) == pytest.approx(q, rel=1e-12)

    def test_q_monotone_decreasing(self):
        pillars = [date(2025, 1, 2), date(2027, 1, 2), date(2030, 1, 2)]
        qs = [0.97, 0.92, 0.85]
        curve = CreditCurve(REF, pillars, qs, InterpolationVariable.SURVIVAL_PROBABILITY, ACT365)
        prev = 1.0
        d = REF
        for _ in range(10):
            d = date(d.year + 1, d.month, d.day)
            q = curve.non_default_probability(d)
            assert q <= prev + 1e-12
            prev = q


class TestValidation:
    def test_pillar_dates_after_ref(self):
        with pytest.raises(ValueError, match="after reference_date"):
            CreditCurve(REF, [REF], [0.01], InterpolationVariable.FORWARD_DEFAULT_SPREAD, ACT365)

    def test_negative_lambda(self):
        with pytest.raises(ValueError, match=">= 0"):
            CreditCurve(REF, [date(2025, 1, 2)], [-0.01], InterpolationVariable.FORWARD_DEFAULT_SPREAD, ACT365)

    def test_q_must_be_non_increasing(self):
        with pytest.raises(ValueError, match="non-increasing"):
            CreditCurve(
                REF,
                [date(2025, 1, 2), date(2027, 1, 2)],
                [0.9, 0.95],
                InterpolationVariable.SURVIVAL_PROBABILITY,
                ACT365,
            )

    def test_q_above_one(self):
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            CreditCurve(
                REF,
                [date(2025, 1, 2)],
                [1.5],
                InterpolationVariable.SURVIVAL_PROBABILITY,
                ACT365,
            )
