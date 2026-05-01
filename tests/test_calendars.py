from datetime import date

import pytest

from schedules.calendars import HolidayCalendar
from scripts.holiday_generators import _easter, _usd_holidays, _eur_holidays, _gbp_holidays
from schedules.conventions import BusinessDayConvention
from schedules.calendars import CalendarType


def test_easter_known_dates():
    assert _easter(2024) == date(2024, 3, 31)
    assert _easter(2025) == date(2025, 4, 20)
    assert _easter(2023) == date(2023, 4, 9)


class TestUSDCalendar:
    cal = HolidayCalendar(CalendarType.USD)

    def test_new_years_day(self):
        assert self.cal.is_holiday(date(2024, 1, 1))

    def test_mlk_day_2024(self):
        # 3rd Monday of January 2024 = Jan 15
        assert self.cal.is_holiday(date(2024, 1, 15))

    def test_presidents_day_2024(self):
        # 3rd Monday of February 2024 = Feb 19
        assert self.cal.is_holiday(date(2024, 2, 19))

    def test_memorial_day_2024(self):
        # Last Monday of May 2024 = May 27
        assert self.cal.is_holiday(date(2024, 5, 27))

    def test_juneteenth_2024(self):
        assert self.cal.is_holiday(date(2024, 6, 19))

    def test_independence_day_2024(self):
        assert self.cal.is_holiday(date(2024, 7, 4))

    def test_labor_day_2024(self):
        # 1st Monday of September 2024 = Sep 2
        assert self.cal.is_holiday(date(2024, 9, 2))

    def test_thanksgiving_2024(self):
        # 4th Thursday of November 2024 = Nov 28
        assert self.cal.is_holiday(date(2024, 11, 28))

    def test_christmas_2024(self):
        assert self.cal.is_holiday(date(2024, 12, 25))

    def test_good_friday_not_usd(self):
        # Good Friday 2024 = March 29 — NOT a USD holiday
        assert not self.cal.is_holiday(date(2024, 3, 29))

    def test_weekend_is_not_business_day(self):
        assert not self.cal.is_business_day(date(2024, 1, 6))  # Saturday

    def test_regular_day_is_business_day(self):
        assert self.cal.is_business_day(date(2024, 1, 2))


class TestEURCalendar:
    cal = HolidayCalendar(CalendarType.EUR)

    def test_new_years(self):
        assert self.cal.is_holiday(date(2024, 1, 1))

    def test_good_friday_2024(self):
        assert self.cal.is_holiday(date(2024, 3, 29))

    def test_easter_monday_2024(self):
        assert self.cal.is_holiday(date(2024, 4, 1))

    def test_labour_day(self):
        assert self.cal.is_holiday(date(2024, 5, 1))

    def test_christmas(self):
        assert self.cal.is_holiday(date(2024, 12, 25))

    def test_boxing_day(self):
        assert self.cal.is_holiday(date(2024, 12, 26))

    def test_mlk_not_eur(self):
        assert not self.cal.is_holiday(date(2024, 1, 15))


class TestGBPCalendar:
    cal = HolidayCalendar(CalendarType.GBP)

    def test_new_years_2024(self):
        # Jan 1 2024 is Monday
        assert self.cal.is_holiday(date(2024, 1, 1))

    def test_good_friday_2024(self):
        assert self.cal.is_holiday(date(2024, 3, 29))

    def test_easter_monday_2024(self):
        assert self.cal.is_holiday(date(2024, 4, 1))

    def test_early_may_2024(self):
        # 1st Monday of May 2024 = May 6
        assert self.cal.is_holiday(date(2024, 5, 6))

    def test_spring_bh_2024(self):
        # Last Monday of May 2024 = May 27
        assert self.cal.is_holiday(date(2024, 5, 27))

    def test_summer_bh_2024(self):
        # Last Monday of August 2024 = Aug 26
        assert self.cal.is_holiday(date(2024, 8, 26))

    def test_christmas_2024(self):
        assert self.cal.is_holiday(date(2024, 12, 25))

    def test_boxing_day_2024(self):
        assert self.cal.is_holiday(date(2024, 12, 26))


class TestBusinessDayAdjustment:
    usd = HolidayCalendar(CalendarType.USD)
    gbp = HolidayCalendar(CalendarType.GBP)

    def test_following(self):
        # Jan 1 2024 (Monday holiday) → Jan 2
        result = self.usd.adjust(date(2024, 1, 1), BusinessDayConvention.FOLLOWING)
        assert result == date(2024, 1, 2)

    def test_preceding(self):
        # Jan 1 2024 (Monday holiday) → Dec 29 2023
        result = self.usd.adjust(date(2024, 1, 1), BusinessDayConvention.PRECEDING)
        assert result == date(2023, 12, 29)

    def test_unadjusted(self):
        d = date(2024, 1, 1)
        assert self.usd.adjust(d, BusinessDayConvention.UNADJUSTED) == d

    def test_modified_following_stays_in_month(self):
        # Nov 30 2024 is a Saturday — Following = Dec 2, crosses month → Preceding = Nov 29
        result = self.usd.adjust(date(2024, 11, 30), BusinessDayConvention.MODIFIED_FOLLOWING)
        assert result == date(2024, 11, 29)

    def test_modified_following_no_cross(self):
        # Sep 21 2024 is a Saturday → Following = Sep 23 (same month)
        result = self.usd.adjust(date(2024, 9, 21), BusinessDayConvention.MODIFIED_FOLLOWING)
        assert result == date(2024, 9, 23)

    def test_modified_following_dec31_rolls_back(self):
        # Dec 31 2022 is Saturday; Jan 1 2023 is Sunday observed Monday Jan 2
        # Following would land on Jan 3 2023 (crosses month) → falls back to Dec 30 2022
        result = self.usd.adjust(date(2022, 12, 31), BusinessDayConvention.MODIFIED_FOLLOWING)
        assert result == date(2022, 12, 30)
