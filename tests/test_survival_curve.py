"""Tests for SurvivalCurve: construction, survival probability, hazard rate, pillar management, bootstrap."""

import math
from datetime import date

import pytest

from market_conventions import CompoundingType, DayCountConvention
from market_structures import ZeroCurve
from schedules.day_count import day_count_fraction
from credit import SurvivalCurve, CdsQuote
from credit.survival_curve import _par_spread_from_schedule

REF = date(2024, 1, 2)
P12 = date(2025, 1, 2)
P36 = date(2027, 1, 2)
P60 = date(2029, 1, 2)


def make_curve(hazard_rates=None, pillars=None):
    """Build a default 3-pillar survival curve."""
    if pillars is None:
        pillars = [P12, P36, P60]
    if hazard_rates is None:
        hazard_rates = [0.01, 0.015, 0.02]
    return SurvivalCurve(REF, pillars, hazard_rates)


def make_discount_curve():
    """Build a simple continuous discount curve."""
    return ZeroCurve(
        REF,
        [P12, P36, P60],
        [0.05, 0.052, 0.053],
        DayCountConvention.ACT_365_FIXED,
        CompoundingType.CONTINUOUS,
    )


class TestConstruction:
    def test_mismatched_lengths(self):
        with pytest.raises(ValueError):
            SurvivalCurve(REF, [P12, P36], [0.01])

    def test_empty(self):
        with pytest.raises(ValueError):
            SurvivalCurve(REF, [], [])

    def test_pillar_before_ref(self):
        with pytest.raises(ValueError):
            SurvivalCurve(REF, [date(2023, 12, 31)], [0.01])

    def test_pillar_equal_to_ref(self):
        with pytest.raises(ValueError):
            SurvivalCurve(REF, [REF], [0.01])

    def test_negative_hazard(self):
        with pytest.raises(ValueError):
            SurvivalCurve(REF, [P12], [-0.001])

    def test_single_pillar_ok(self):
        sc = SurvivalCurve(REF, [P12], [0.05])
        assert sc.survival_probability(P12) < 1.0


class TestSurvivalProbability:
    def test_at_reference_date(self):
        sc = make_curve()
        assert sc.survival_probability(REF) == 1.0

    def test_before_reference_date(self):
        sc = make_curve()
        assert sc.survival_probability(date(2023, 6, 1)) == 1.0

    def test_monotone_decreasing(self):
        sc = make_curve()
        q1 = sc.survival_probability(P12)
        q3 = sc.survival_probability(P36)
        q5 = sc.survival_probability(P60)
        assert q1 > q3 > q5

    def test_in_range_01(self):
        sc = make_curve()
        for d in [P12, P36, P60]:
            q = sc.survival_probability(d)
            assert 0.0 < q <= 1.0

    def test_exact_single_pillar(self):
        h = 0.03
        sc = SurvivalCurve(REF, [P12], [h])
        t = day_count_fraction(REF, P12, DayCountConvention.ACT_365_FIXED)
        assert abs(sc.survival_probability(P12) - math.exp(-h * t)) < 1e-12

    def test_flat_extrapolation_beyond_last_pillar(self):
        sc = make_curve([0.01, 0.015, 0.02])
        late = date(2035, 1, 2)
        t_last = day_count_fraction(REF, P60, DayCountConvention.ACT_365_FIXED)
        t_late = day_count_fraction(REF, late, DayCountConvention.ACT_365_FIXED)
        expected = math.exp(-(sc._cumulative_hazard[-1] + 0.02 * (t_late - t_last)))
        assert abs(sc.survival_probability(late) - expected) < 1e-12

    def test_midpoint_first_segment(self):
        h = 0.02
        sc = SurvivalCurve(REF, [P12], [h])
        mid = date(2024, 7, 2)
        t = day_count_fraction(REF, mid, DayCountConvention.ACT_365_FIXED)
        assert abs(sc.survival_probability(mid) - math.exp(-h * t)) < 1e-12


class TestHazardRate:
    def test_first_segment(self):
        sc = make_curve([0.01, 0.015, 0.02])
        mid = date(2024, 7, 2)
        assert sc.hazard_rate(mid) == 0.01

    def test_second_segment(self):
        sc = make_curve([0.01, 0.015, 0.02])
        mid = date(2026, 1, 2)
        assert sc.hazard_rate(mid) == 0.015

    def test_third_segment(self):
        sc = make_curve([0.01, 0.015, 0.02])
        mid = date(2028, 1, 2)
        assert sc.hazard_rate(mid) == 0.02

    def test_flat_extrapolation_beyond_last(self):
        sc = make_curve([0.01, 0.015, 0.02])
        assert sc.hazard_rate(date(2035, 1, 1)) == 0.02

    def test_at_or_before_ref(self):
        sc = make_curve([0.01, 0.015, 0.02])
        assert sc.hazard_rate(REF) == 0.01


class TestAddRemovePillar:
    def test_add_pillar_sorted_order(self):
        sc = SurvivalCurve(REF, [P12, P60], [0.01, 0.02])
        sc.add_pillar(P36, 0.015)
        assert sc._pillar_dates == [P12, P36, P60]
        assert sc._hazard_rates == [0.01, 0.015, 0.02]

    def test_add_pillar_before_ref_raises(self):
        sc = make_curve()
        with pytest.raises(ValueError):
            sc.add_pillar(date(2023, 1, 1), 0.01)

    def test_add_duplicate_raises(self):
        sc = make_curve()
        with pytest.raises(ValueError):
            sc.add_pillar(P12, 0.01)

    def test_add_negative_hazard_raises(self):
        sc = SurvivalCurve(REF, [P12, P60], [0.01, 0.02])
        with pytest.raises(ValueError):
            sc.add_pillar(P36, -0.001)

    def test_add_clears_bootstrap_meta(self):
        sc = SurvivalCurve(REF, [P12, P60], [0.01, 0.02])
        sc._bootstrap_meta = {"dummy": True}
        sc.add_pillar(P36, 0.015)
        assert sc._bootstrap_meta is None

    def test_remove_pillar(self):
        sc = make_curve()
        sc.remove_pillar(P36)
        assert P36 not in sc._pillar_dates

    def test_remove_missing_raises(self):
        sc = make_curve()
        with pytest.raises(ValueError):
            sc.remove_pillar(date(2026, 6, 1))

    def test_remove_last_raises(self):
        sc = SurvivalCurve(REF, [P12], [0.01])
        with pytest.raises(ValueError):
            sc.remove_pillar(P12)

    def test_remove_clears_bootstrap_meta(self):
        sc = make_curve()
        sc._bootstrap_meta = {"dummy": True}
        sc.remove_pillar(P36)
        assert sc._bootstrap_meta is None

    def test_add_remove_roundtrip(self):
        sc = SurvivalCurve(REF, [P12, P60], [0.01, 0.02])
        q_before = sc.survival_probability(P60)
        sc.add_pillar(P36, 0.015)
        sc.remove_pillar(P36)
        assert abs(sc.survival_probability(P60) - q_before) < 1e-12

    def test_cumulative_hazard_recomputed_after_add(self):
        sc = SurvivalCurve(REF, [P12, P60], [0.01, 0.02])
        sc.add_pillar(P36, 0.015)
        assert len(sc._cumulative_hazard) == 3


TENORS = ["1Y", "3Y", "5Y"]
SPREADS_BOOT = [0.01, 0.012, 0.015]


def make_cds_quotes(tenors=None, spreads=None):
    """Build CdsQuote list with default conventions."""
    if tenors is None:
        tenors = TENORS
    if spreads is None:
        spreads = SPREADS_BOOT
    return [CdsQuote(spread=s, tenor=t) for s, t in zip(spreads, tenors)]


class TestFromCdsSpreads:
    def setup_method(self):
        self.dc = make_discount_curve()
        self.quotes = make_cds_quotes()
        self.spreads = SPREADS_BOOT
        self.sc = SurvivalCurve.from_cds_spreads(
            REF, self.quotes, self.dc, recovery_rate=0.40
        )
        self.pillar_dates = [q.maturity_date(REF) for q in self.quotes]

    def _par_at_pillar(self, idx):
        periods = self.quotes[idx].schedule(REF)
        return _par_spread_from_schedule(periods, self.dc, self.sc, 0.40)

    def test_round_trip_pillar_1(self):
        assert abs(self._par_at_pillar(0) - self.spreads[0]) < 1e-6

    def test_round_trip_pillar_2(self):
        assert abs(self._par_at_pillar(1) - self.spreads[1]) < 1e-6

    def test_round_trip_pillar_3(self):
        assert abs(self._par_at_pillar(2) - self.spreads[2]) < 1e-6

    def test_bootstrap_meta_stored(self):
        assert self.sc._bootstrap_meta is not None

    def test_hazard_rates_positive(self):
        assert all(h > 0 for h in self.sc._hazard_rates)

    def test_survival_probabilities_valid(self):
        for d in self.pillar_dates:
            q = self.sc.survival_probability(d)
            assert 0.0 < q < 1.0

    def test_quotes_sorted_by_maturity(self):
        quotes = make_cds_quotes(["5Y", "1Y", "3Y"], [0.015, 0.01, 0.012])
        sc = SurvivalCurve.from_cds_spreads(REF, quotes, self.dc, recovery_rate=0.40)
        expected = sorted(q.maturity_date(REF) for q in quotes)
        assert sc._pillar_dates == expected


class TestBump:
    def setup_method(self):
        self.dc = make_discount_curve()
        quotes = make_cds_quotes()
        self.sc = SurvivalCurve.from_cds_spreads(
            REF, quotes, self.dc, recovery_rate=0.40
        )

    def test_raises_if_not_bootstrapped(self):
        sc = SurvivalCurve(REF, [P12, P36, P60], [0.01, 0.012, 0.015])
        with pytest.raises(ValueError):
            sc.bump(0.0001)

    def test_higher_hazard_rates_after_positive_bump(self):
        bumped = self.sc.bump(0.001)
        for h_base, h_bump in zip(self.sc._hazard_rates, bumped._hazard_rates):
            assert h_bump > h_base

    def test_lower_survival_probs_after_positive_bump(self):
        bumped = self.sc.bump(0.001)
        for d in [P12, P36, P60]:
            assert bumped.survival_probability(d) < self.sc.survival_probability(d)

    def test_bumped_curve_has_bootstrap_meta(self):
        bumped = self.sc.bump(0.001)
        assert bumped._bootstrap_meta is not None
