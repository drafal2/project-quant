import math
import pytest
from datetime import date

from market_conventions import CompoundingFrequency, CompoundingType, DayCountConvention
from market_data import ZeroCurve
from market_data.interpolation import LinearInterpolator

REF = date(2024, 1, 1)
PILLARS = [date(2024, 7, 1), date(2025, 1, 1), date(2026, 1, 1)]
RATES = [0.04, 0.045, 0.05]
DCC = DayCountConvention.ACT_365_FIXED


def make_curve(**kwargs) -> ZeroCurve:
    defaults = dict(
        reference_date=REF,
        pillar_dates=PILLARS,
        rates=RATES,
        day_count_convention=DCC,
    )
    return ZeroCurve(**{**defaults, **kwargs})


class TestConstruction:
    def test_sorts_unsorted_pillars(self):
        curve = ZeroCurve(
            reference_date=REF,
            pillar_dates=[date(2026, 1, 1), date(2024, 7, 1), date(2025, 1, 1)],
            rates=[0.05, 0.04, 0.045],
            day_count_convention=DCC,
        )
        assert curve._pillar_dates == sorted(PILLARS)
        assert curve._rates == RATES

    def test_raises_on_mismatched_lengths(self):
        with pytest.raises(ValueError, match="same length"):
            ZeroCurve(REF, PILLARS, [0.04, 0.05], DCC)

    def test_raises_on_empty_pillars(self):
        with pytest.raises(ValueError, match="at least one pillar"):
            ZeroCurve(REF, [], [], DCC)

    def test_raises_when_pillar_before_reference_date(self):
        with pytest.raises(ValueError, match="after reference_date"):
            ZeroCurve(REF, [date(2023, 1, 1)], [0.04], DCC)

    def test_raises_when_pillar_equals_reference_date(self):
        with pytest.raises(ValueError, match="after reference_date"):
            ZeroCurve(REF, [REF], [0.04], DCC)

    def test_raises_compounded_without_frequency(self):
        with pytest.raises(ValueError, match="compounding_frequency required"):
            make_curve(compounding_type=CompoundingType.COMPOUNDED)

    def test_accepts_compounded_with_frequency(self):
        make_curve(
            compounding_type=CompoundingType.COMPOUNDED,
            compounding_frequency=CompoundingFrequency.SEMI_ANNUAL,
        )


class TestDiscountFactor:
    def test_returns_one_at_reference_date(self):
        assert make_curve().discount_factor(REF) == 1.0

    def test_continuous_at_pillar(self):
        curve = make_curve()
        t = (PILLARS[1] - REF).days / 365.0
        assert curve.discount_factor(PILLARS[1]) == pytest.approx(math.exp(-RATES[1] * t))

    def test_simple_at_pillar(self):
        curve = make_curve(compounding_type=CompoundingType.SIMPLE)
        t = (PILLARS[1] - REF).days / 365.0
        assert curve.discount_factor(PILLARS[1]) == pytest.approx(1.0 / (1.0 + RATES[1] * t))

    def test_compounded_at_pillar(self):
        curve = make_curve(
            compounding_type=CompoundingType.COMPOUNDED,
            compounding_frequency=CompoundingFrequency.SEMI_ANNUAL,
        )
        t = (PILLARS[1] - REF).days / 365.0
        n = CompoundingFrequency.SEMI_ANNUAL.value
        assert curve.discount_factor(PILLARS[1]) == pytest.approx((1.0 + RATES[1] / n) ** (-n * t))

    def test_decreases_over_time(self):
        curve = make_curve()
        dfs = [curve.discount_factor(d) for d in PILLARS]
        for i in range(len(dfs) - 1):
            assert dfs[i] > dfs[i + 1]


class TestZeroRate:
    def test_raises_at_reference_date(self):
        with pytest.raises(ValueError, match="undefined at reference_date"):
            make_curve().zero_rate(REF)

    def test_recovers_input_rate_at_pillar_continuous(self):
        curve = make_curve()
        assert curve.zero_rate(PILLARS[1]) == pytest.approx(RATES[1])

    def test_recovers_input_rate_at_pillar_simple(self):
        curve = make_curve(compounding_type=CompoundingType.SIMPLE)
        assert curve.zero_rate(PILLARS[1]) == pytest.approx(RATES[1])

    def test_recovers_input_rate_at_pillar_compounded(self):
        curve = make_curve(
            compounding_type=CompoundingType.COMPOUNDED,
            compounding_frequency=CompoundingFrequency.QUARTERLY,
        )
        assert curve.zero_rate(PILLARS[1]) == pytest.approx(RATES[1])


class TestForwardRate:
    def test_raises_when_start_equals_end(self):
        curve = make_curve()
        with pytest.raises(ValueError, match="start must be before end"):
            curve.forward_rate(PILLARS[0], PILLARS[0])

    def test_raises_when_start_after_end(self):
        curve = make_curve()
        with pytest.raises(ValueError, match="start must be before end"):
            curve.forward_rate(PILLARS[1], PILLARS[0])

    def test_forward_rate_between_pillars_is_positive(self):
        curve = make_curve()
        assert curve.forward_rate(PILLARS[0], PILLARS[1]) > 0

    def test_forward_rate_consistent_with_discount_factors(self):
        curve = make_curve()
        start, end = PILLARS[0], PILLARS[1]
        df_start = curve.discount_factor(start)
        df_end = curve.discount_factor(end)
        t = (end - start).days / 365.0
        expected = -math.log(df_end / df_start) / t
        assert curve.forward_rate(start, end) == pytest.approx(expected)


class TestAddPillar:
    def test_raises_when_date_before_reference_date(self):
        with pytest.raises(ValueError, match="after reference_date"):
            make_curve().add_pillar(date(2023, 1, 1), 0.03)

    def test_raises_on_duplicate(self):
        with pytest.raises(ValueError, match="already exists"):
            make_curve().add_pillar(PILLARS[0], 0.04)

    def test_inserts_in_sorted_order(self):
        curve = make_curve()
        new_date = date(2025, 7, 1)
        curve.add_pillar(new_date, 0.048)
        idx = curve._pillar_dates.index(new_date)
        assert curve._pillar_dates[idx - 1] < new_date < curve._pillar_dates[idx + 1]

    def test_stored_lists_stay_consistent(self):
        curve = make_curve()
        new_date = date(2025, 7, 1)
        curve.add_pillar(new_date, 0.048)
        assert len(curve._pillar_dates) == len(curve._rates) == len(curve._times) == len(curve._dfs)

    def test_affects_subsequent_queries(self):
        curve = make_curve()
        new_date = date(2025, 7, 1)
        df_before = curve.discount_factor(new_date)
        curve.add_pillar(new_date, 0.048)
        df_after = curve.discount_factor(new_date)
        assert df_before != pytest.approx(df_after)


class TestRemovePillar:
    def test_raises_when_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            make_curve().remove_pillar(date(2030, 1, 1))

    def test_raises_when_last_pillar(self):
        curve = ZeroCurve(REF, [PILLARS[0]], [RATES[0]], DCC)
        with pytest.raises(ValueError, match="at least one pillar"):
            curve.remove_pillar(PILLARS[0])

    def test_removes_correctly(self):
        curve = make_curve()
        curve.remove_pillar(PILLARS[1])
        assert PILLARS[1] not in curve._pillar_dates

    def test_stored_lists_stay_consistent(self):
        curve = make_curve()
        curve.remove_pillar(PILLARS[1])
        assert len(curve._pillar_dates) == len(curve._rates) == len(curve._times) == len(curve._dfs)


class TestInterpolatorSwap:
    def test_linear_interpolator_accepted(self):
        curve = make_curve(interpolator=LinearInterpolator())
        assert curve.discount_factor(PILLARS[0]) == pytest.approx(
            math.exp(-RATES[0] * (PILLARS[0] - REF).days / 365.0)
        )
