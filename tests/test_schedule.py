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


def make_schedule(**kwargs):
    defaults = dict(
        effective_date=date(2024, 3, 20),
        termination_date=date(2026, 3, 20),
        frequency=Frequency.SEMI_ANNUAL,
        day_count_convention=DayCountConvention.ACT_360,
        business_day_convention=BusinessDayConvention.MODIFIED_FOLLOWING,
        calendar=CalendarType.USD,
        end_of_month=False,
        stub_type=StubType.SHORT_BACK,
    )
    defaults.update(kwargs)
    return Schedule(**defaults)


class TestBasicGeneration:
    def test_2y_semiannual_period_count(self):
        sch = make_schedule()
        assert len(sch.generate()) == 4

    def test_first_period_start(self):
        sch = make_schedule()
        assert sch.generate()[0].accrual_start == date(2024, 3, 20)

    def test_first_period_end(self):
        sch = make_schedule()
        assert sch.generate()[0].accrual_end == date(2024, 9, 20)

    def test_last_period_end(self):
        sch = make_schedule()
        assert sch.generate()[-1].accrual_end == date(2026, 3, 20)

    def test_dcf_sum_approx_two_years(self):
        # ACT/360 over 730 actual days = 730/360 ≈ 2.028 — tolerance must cover this
        sch = make_schedule()
        total = sum(p.dcf for p in sch.generate())
        assert abs(total - 2.0) < 0.05

    def test_pay_date_adjusted_for_weekend(self):
        # Sep 20 2024 is a Friday — no adjustment needed
        sch = make_schedule()
        assert sch.generate()[0].pay_date == date(2024, 9, 20)

    def test_iterable(self):
        sch = make_schedule()
        periods = list(sch)
        assert len(periods) == 4

    def test_invalid_dates_raises(self):
        with pytest.raises(ValueError):
            Schedule(
                effective_date=date(2026, 3, 20),
                termination_date=date(2024, 3, 20),
                frequency=Frequency.SEMI_ANNUAL,
                day_count_convention=DayCountConvention.ACT_360,
                business_day_convention=BusinessDayConvention.MODIFIED_FOLLOWING,
                calendar=CalendarType.USD,
            )


class TestEOMRule:
    def test_eom_monthly(self):
        sch = Schedule(
            effective_date=date(2024, 1, 31),
            termination_date=date(2024, 7, 31),
            frequency=Frequency.MONTHLY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
            end_of_month=True,
        )
        periods = sch.generate()
        assert periods[0].accrual_end == date(2024, 2, 29)  # leap year
        assert periods[1].accrual_end == date(2024, 3, 31)
        assert periods[2].accrual_end == date(2024, 4, 30)
        assert periods[3].accrual_end == date(2024, 5, 31)
        assert periods[4].accrual_end == date(2024, 6, 30)
        assert periods[5].accrual_end == date(2024, 7, 31)


class TestStubs:
    def test_short_back_no_stub_regular(self):
        # Exact 2Y on semi-annual — no stub needed
        sch = make_schedule(stub_type=StubType.SHORT_BACK)
        periods = sch.generate()
        assert len(periods) == 4
        for p in periods:
            days = (p.accrual_end - p.accrual_start).days
            assert 175 <= days <= 196

    def test_short_front_stub(self):
        # Off-cycle start: stub at the front
        sch = make_schedule(
            effective_date=date(2024, 2, 15),
            termination_date=date(2026, 3, 20),
            stub_type=StubType.SHORT_FRONT,
        )
        periods = sch.generate()
        first_days = (periods[0].accrual_end - periods[0].accrual_start).days
        assert first_days < 184  # shorter than a half-year
        for p in periods[1:]:
            days = (p.accrual_end - p.accrual_start).days
            assert 175 <= days <= 196

    def test_short_back_stub(self):
        # Off-cycle end: stub at the back
        sch = make_schedule(
            effective_date=date(2024, 3, 20),
            termination_date=date(2026, 5, 15),
            stub_type=StubType.SHORT_BACK,
        )
        periods = sch.generate()
        last_days = (periods[-1].accrual_end - periods[-1].accrual_start).days
        assert last_days < 184
        for p in periods[:-1]:
            days = (p.accrual_end - p.accrual_start).days
            assert 175 <= days <= 196

    def test_long_back_stub(self):
        # 7M quarterly → [3M, 4M]
        sch = Schedule(
            effective_date=date(2024, 1, 15),
            termination_date=date(2024, 8, 15),
            frequency=Frequency.QUARTERLY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
            stub_type=StubType.LONG_BACK,
        )
        periods = sch.generate()
        assert len(periods) == 2
        assert periods[0].accrual_end == date(2024, 4, 15)
        assert periods[1].accrual_end == date(2024, 8, 15)

    def test_long_front_stub(self):
        # 7M quarterly backward → [4M, 3M]
        sch = Schedule(
            effective_date=date(2024, 1, 15),
            termination_date=date(2024, 8, 15),
            frequency=Frequency.QUARTERLY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
            stub_type=StubType.LONG_FRONT,
        )
        periods = sch.generate()
        assert len(periods) == 2
        assert periods[0].accrual_end == date(2024, 5, 15)
        assert periods[1].accrual_end == date(2024, 8, 15)


class TestFrequencies:
    def test_quarterly(self):
        sch = make_schedule(
            frequency=Frequency.QUARTERLY,
            termination_date=date(2025, 3, 20),
        )
        assert len(sch.generate()) == 4

    def test_annual(self):
        sch = make_schedule(
            frequency=Frequency.ANNUAL,
            termination_date=date(2027, 3, 20),
        )
        assert len(sch.generate()) == 3

    def test_monthly(self):
        sch = make_schedule(
            frequency=Frequency.MONTHLY,
            termination_date=date(2024, 9, 20),
        )
        assert len(sch.generate()) == 6


class TestDailySchedule:
    def _make_daily(self, effective, termination, calendar=CalendarType.USD):
        return Schedule(
            effective_date=effective,
            termination_date=termination,
            frequency=Frequency.DAILY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=calendar,
        )

    def test_weekend_absorbed_into_friday_period(self):
        # Mon Jan 6 to Mon Jan 13 2025 (USD — no holidays in this range)
        # Business days: Mon 6, Tue 7, Wed 8, Thu 9, Fri 10, Mon 13
        # Periods: Mon→Tue, Tue→Wed, Wed→Thu, Thu→Fri, Fri→Mon (3 cal days)
        sch = self._make_daily(date(2025, 1, 6), date(2025, 1, 13))
        periods = sch.generate()
        assert len(periods) == 5
        # All period boundaries are business days
        for p in periods:
            assert p.accrual_start.weekday() < 5
        # Friday→Monday period spans 3 calendar days
        fri_period = next(p for p in periods if p.accrual_start == date(2025, 1, 10))
        assert fri_period.accrual_end == date(2025, 1, 13)
        assert (fri_period.accrual_end - fri_period.accrual_start).days == 3

    def test_holiday_absorbed_into_prior_period(self):
        # MLK Day 2025 = Mon Jan 20
        # effective Fri Jan 17, termination Wed Jan 22 (USD calendar)
        # Business days in range: Fri 17, Tue 21, Wed 22
        # Periods: Fri→Tue (4 cal days: Fri, Sat, Sun, MLK Mon), Tue→Wed
        sch = self._make_daily(date(2025, 1, 17), date(2025, 1, 22))
        periods = sch.generate()
        assert len(periods) == 2
        assert periods[0].accrual_start == date(2025, 1, 17)
        assert periods[0].accrual_end == date(2025, 1, 21)
        assert (periods[0].accrual_end - periods[0].accrual_start).days == 4
        assert periods[1].accrual_start == date(2025, 1, 21)
        assert periods[1].accrual_end == date(2025, 1, 22)

    def test_no_calendar_days_skipped(self):
        # Total accrual days must equal termination - effective regardless of holidays
        effective = date(2025, 1, 6)
        termination = date(2025, 1, 31)
        sch = self._make_daily(effective, termination)
        total_days = sum(
            (p.accrual_end - p.accrual_start).days for p in sch.generate()
        )
        assert total_days == (termination - effective).days

    def test_dcf_sum_matches_full_period(self):
        effective = date(2025, 1, 6)
        termination = date(2025, 1, 31)
        sch = self._make_daily(effective, termination)
        total_dcf = sum(p.dcf for p in sch.generate())
        expected = (termination - effective).days / 360
        assert abs(total_dcf - expected) < 1e-10

    def test_gbp_easter_holiday_absorbed(self):
        # Good Friday 2025 = Apr 18, Easter Monday = Apr 21
        # effective Thu Apr 17, termination Tue Apr 22 (GBP calendar)
        # Periods: Thu→Tue (5 cal days: Thu, Fri GF, Sat, Sun, Mon EM), Tue→Tue (termination same day — only 1 period)
        # Actually: Thu 17 → Tue 22 is the only period boundary pair
        sch = self._make_daily(date(2025, 4, 17), date(2025, 4, 22), CalendarType.GBP)
        periods = sch.generate()
        assert len(periods) == 1
        assert periods[0].accrual_start == date(2025, 4, 17)
        assert periods[0].accrual_end == date(2025, 4, 22)
        assert (periods[0].accrual_end - periods[0].accrual_start).days == 5


class TestPaymentLag:
    def test_zero_lag_default_pay_equals_adjusted_end(self):
        # payment_lag=0 (default): pay_date == BDC-adjusted accrual_end.
        # Use UNADJUSTED so adjusted end == raw end, making the equality trivial to verify.
        sch = make_schedule(business_day_convention=BusinessDayConvention.UNADJUSTED)
        for p in sch.generate():
            assert p.pay_date == p.accrual_end

    def test_positive_lag_pay_strictly_after_end(self):
        sch = make_schedule(payment_lag=2)
        for p in sch.generate():
            assert p.pay_date > p.accrual_end

    def test_two_biz_day_lag_midweek(self):
        # Period end: Apr 4 2024 (Thursday, UNADJUSTED); lag=2 → Apr 5 (Fri) → Apr 8 (Mon)
        sch = Schedule(
            effective_date=date(2024, 1, 4),
            termination_date=date(2024, 4, 4),
            frequency=Frequency.QUARTERLY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.UNADJUSTED,
            calendar=CalendarType.USD,
            payment_lag=2,
        )
        periods = sch.generate()
        assert len(periods) == 1
        assert periods[0].accrual_end == date(2024, 4, 4)  # Thursday, unadjusted
        assert periods[0].pay_date == date(2024, 4, 8)  # +2 biz: Fri Apr 5, Mon Apr 8

    def test_two_biz_day_lag_over_weekend(self):
        # Period end: Jan 31 2025 (Friday); MODIFIED_FOLLOWING keeps it Fri; lag=2 → Mon→Tue
        sch = Schedule(
            effective_date=date(2024, 10, 31),
            termination_date=date(2025, 1, 31),
            frequency=Frequency.QUARTERLY,
            day_count_convention=DayCountConvention.ACT_360,
            business_day_convention=BusinessDayConvention.MODIFIED_FOLLOWING,
            calendar=CalendarType.USD,
            payment_lag=2,
        )
        periods = sch.generate()
        last = periods[-1]
        assert last.accrual_end == date(2025, 1, 31)  # Friday; MF keeps it in Jan
        assert last.pay_date == date(2025, 2, 4)  # +1=Mon Feb 3, +2=Tue Feb 4

    def test_negative_lag_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            make_schedule(payment_lag=-1)

    def test_lag_does_not_affect_dcf(self):
        # DCF is computed from raw accrual dates; payment_lag must not change it
        sch_no_lag = make_schedule(payment_lag=0)
        sch_lagged = make_schedule(payment_lag=5)
        for p0, p1 in zip(sch_no_lag.generate(), sch_lagged.generate()):
            assert p0.dcf == p1.dcf
