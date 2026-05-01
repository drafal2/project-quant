from datetime import date

import pytest

from schedules.day_count import day_count_fraction
from schedules.enums import DayCountConvention


class TestACT360:
    def test_half_year_leap(self):
        # 2024-01-01 to 2024-07-01 = 182 days
        dcf = day_count_fraction(date(2024, 1, 1), date(2024, 7, 1), DayCountConvention.ACT_360)
        assert dcf == pytest.approx(182 / 360)

    def test_leap_day_included(self):
        dcf = day_count_fraction(date(2024, 2, 1), date(2024, 3, 1), DayCountConvention.ACT_360)
        assert dcf == pytest.approx(29 / 360)


class TestACT365Fixed:
    def test_half_year_leap(self):
        dcf = day_count_fraction(date(2024, 1, 1), date(2024, 7, 1), DayCountConvention.ACT_365_FIXED)
        assert dcf == pytest.approx(182 / 365)

    def test_full_year_non_leap(self):
        dcf = day_count_fraction(date(2023, 1, 1), date(2024, 1, 1), DayCountConvention.ACT_365_FIXED)
        assert dcf == pytest.approx(365 / 365)


class TestThirty360Bond:
    def test_jan31_to_mar31(self):
        # d1=31→30, d2=31 and d1=30→30 → 60 days
        dcf = day_count_fraction(date(2024, 1, 31), date(2024, 3, 31), DayCountConvention.THIRTY_360_BOND)
        assert dcf == pytest.approx(60 / 360)

    def test_jan30_to_mar31(self):
        # d1=30, d2=31 and d1=30→d2=30 → 60 days
        dcf = day_count_fraction(date(2024, 1, 30), date(2024, 3, 31), DayCountConvention.THIRTY_360_BOND)
        assert dcf == pytest.approx(60 / 360)

    def test_jan30_to_mar30(self):
        dcf = day_count_fraction(date(2024, 1, 30), date(2024, 3, 30), DayCountConvention.THIRTY_360_BOND)
        assert dcf == pytest.approx(60 / 360)

    def test_jan31_to_feb28_non_leap(self):
        # d1=31→30, d2=28 (not 31, no substitution) → 28 days
        dcf = day_count_fraction(date(2023, 1, 31), date(2023, 2, 28), DayCountConvention.THIRTY_360_BOND)
        assert dcf == pytest.approx(28 / 360)

    def test_full_year(self):
        dcf = day_count_fraction(date(2024, 1, 1), date(2025, 1, 1), DayCountConvention.THIRTY_360_BOND)
        assert dcf == pytest.approx(360 / 360)

    def test_two_year_annual_sum(self):
        dcf1 = day_count_fraction(date(2024, 1, 1), date(2025, 1, 1), DayCountConvention.THIRTY_360_BOND)
        dcf2 = day_count_fraction(date(2025, 1, 1), date(2026, 1, 1), DayCountConvention.THIRTY_360_BOND)
        assert dcf1 + dcf2 == pytest.approx(2.0)


class TestACTACTISDA:
    def test_full_non_leap_year(self):
        dcf = day_count_fraction(date(2023, 1, 1), date(2024, 1, 1), DayCountConvention.ACT_ACT_ISDA)
        assert dcf == pytest.approx(1.0)

    def test_full_leap_year(self):
        dcf = day_count_fraction(date(2024, 1, 1), date(2025, 1, 1), DayCountConvention.ACT_ACT_ISDA)
        assert dcf == pytest.approx(1.0)

    def test_spanning_year_boundary(self):
        # 2023-12-01 to 2024-06-01
        # Dec 1 to Jan 1 = 31 days in 2023 (non-leap) → 31/365
        # Jan 1 to Jun 1 = 152 days in 2024 (leap: 31+29+31+30+31=152) → 152/366
        dcf = day_count_fraction(date(2023, 12, 1), date(2024, 6, 1), DayCountConvention.ACT_ACT_ISDA)
        expected = 31 / 365 + 152 / 366
        assert dcf == pytest.approx(expected)

    def test_same_date_is_zero(self):
        dcf = day_count_fraction(date(2024, 3, 1), date(2024, 3, 1), DayCountConvention.ACT_ACT_ISDA)
        assert dcf == 0.0

    def test_leap_day(self):
        # Feb 1 to Mar 1 in leap year = 29 days / 366
        dcf = day_count_fraction(date(2024, 2, 1), date(2024, 3, 1), DayCountConvention.ACT_ACT_ISDA)
        assert dcf == pytest.approx(29 / 366)
