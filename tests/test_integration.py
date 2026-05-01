from datetime import date

import pytest

from schedules import (
    BusinessDayConvention,
    CalendarType,
    DayCountConvention,
    Frequency,
    Schedule,
    StubType,
)


class TestGBPCalendarIntegration:
    def test_easter_adjacent_pay_dates_2024(self):
        # Easter 2024: Good Friday Mar 29, Easter Monday Apr 1
        # Schedule starting Feb 29 (leap) → first period ends Mar 29 (Good Friday)
        # FOLLOWING must skip Mar 29 (GF) and Apr 1 (EM) → pay Apr 2
        sch = Schedule(
            effective_date=date(2024, 2, 29),
            termination_date=date(2024, 5, 29),
            frequency=Frequency.MONTHLY,
            day_count_convention=DayCountConvention.ACT_365_FIXED,
            business_day_convention=BusinessDayConvention.FOLLOWING,
            calendar=CalendarType.GBP,
        )
        periods = sch.generate()
        assert periods[0].accrual_end == date(2024, 3, 29)
        assert periods[0].pay_date == date(2024, 4, 2)

    def test_summer_bank_holiday_2024(self):
        # GBP Summer BH 2024 = Aug 26 (Mon)
        # Period ending Aug 26 → Aug 27 (FOLLOWING)
        sch = Schedule(
            effective_date=date(2024, 8, 1),
            termination_date=date(2024, 9, 1),
            frequency=Frequency.MONTHLY,
            day_count_convention=DayCountConvention.ACT_365_FIXED,
            business_day_convention=BusinessDayConvention.FOLLOWING,
            calendar=CalendarType.GBP,
        )
        # The accrual end is Sep 1, not Aug 26 — so test directly via calendar
        from schedules.calendars import HolidayCalendar
        from schedules.enums import CalendarType as CT, BusinessDayConvention as BDC
        cal = HolidayCalendar(CT.GBP)
        assert cal.adjust(date(2024, 8, 26), BDC.FOLLOWING) == date(2024, 8, 27)


class TestEURTargetIntegration:
    def test_christmas_and_boxing_day(self):
        from schedules.calendars import HolidayCalendar
        from schedules.enums import CalendarType as CT, BusinessDayConvention as BDC
        cal = HolidayCalendar(CT.EUR)
        # Dec 25 and Dec 26 both holidays; FOLLOWING lands on Dec 27
        assert cal.adjust(date(2024, 12, 25), BDC.FOLLOWING) == date(2024, 12, 27)

    def test_eur_swap_skips_christmas(self):
        sch = Schedule(
            effective_date=date(2024, 12, 1),
            termination_date=date(2025, 6, 1),
            frequency=Frequency.MONTHLY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.FOLLOWING,
            calendar=CalendarType.EUR,
        )
        periods = sch.generate()
        dec_period = next(p for p in periods if p.accrual_end == date(2025, 1, 1))
        # Jan 1 (New Year's) is a TARGET holiday → FOLLOWING = Jan 2
        assert dec_period.pay_date == date(2025, 1, 2)


class TestACTACTISDAIntegration:
    def test_sum_to_1_non_leap(self):
        dcf_total = 0.0
        sch = Schedule(
            effective_date=date(2023, 1, 1),
            termination_date=date(2024, 1, 1),
            frequency=Frequency.QUARTERLY,
            day_count_convention=DayCountConvention.ACT_ACT_ISDA,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
        )
        for p in sch:
            dcf_total += p.dcf
        assert dcf_total == pytest.approx(1.0)

    def test_sum_to_1_leap(self):
        sch = Schedule(
            effective_date=date(2024, 1, 1),
            termination_date=date(2025, 1, 1),
            frequency=Frequency.QUARTERLY,
            day_count_convention=DayCountConvention.ACT_ACT_ISDA,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
        )
        total = sum(p.dcf for p in sch)
        assert total == pytest.approx(1.0)


class TestThirty360Integration:
    def test_2y_annual_sums_to_2(self):
        sch = Schedule(
            effective_date=date(2024, 1, 1),
            termination_date=date(2026, 1, 1),
            frequency=Frequency.ANNUAL,
            day_count_convention=DayCountConvention.THIRTY_360_BOND,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
        )
        total = sum(p.dcf for p in sch)
        assert total == pytest.approx(2.0)


class TestModifiedFollowingMonthBoundary:
    def test_dec31_rolls_back_usd(self):
        # Dec 31 2022 = Saturday; Jan 1 2023 = Sunday → observed Jan 2 Monday
        # FOLLOWING lands Jan 3 (first USD business day) → crosses month → PRECEDING = Dec 30
        from schedules.calendars import HolidayCalendar
        from schedules.enums import CalendarType as CT, BusinessDayConvention as BDC
        cal = HolidayCalendar(CT.USD)
        result = cal.adjust(date(2022, 12, 31), BDC.MODIFIED_FOLLOWING)
        assert result == date(2022, 12, 30)
