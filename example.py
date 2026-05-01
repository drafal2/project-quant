import calendar
from datetime import date
from schedules import Schedule, Frequency, DayCountConvention, BusinessDayConvention, CalendarType

effective = date(2024, 3, 20)

print("--- Semi-annual schedule ---")
sch = Schedule(
    effective_date=effective,
    termination_date=date(2026, 3, 20),
    frequency=Frequency.SEMI_ANNUAL,
    day_count_convention=DayCountConvention.ACT_360,
    business_day_convention=BusinessDayConvention.MODIFIED_FOLLOWING,
    calendar=CalendarType.USD,
)
for p in sch:
    print(p.accrual_start, p.accrual_end, p.pay_date, f"{p.dcf:.6f}")

print("\n--- Daily schedule (1 month) ---")
t_year = effective.year + (effective.month // 12)
t_month = (effective.month % 12) + 1
t_day = min(effective.day, calendar.monthrange(t_year, t_month)[1])
termination = date(t_year, t_month, t_day)

sch_daily = Schedule(
    effective_date=effective,
    termination_date=termination,
    frequency=Frequency.DAILY,
    day_count_convention=DayCountConvention.ACT_360,
    business_day_convention=BusinessDayConvention.UNADJUSTED,
    calendar=CalendarType.USD,
)
for p in sch_daily:
    print(p.accrual_start, p.accrual_end, p.pay_date, f"{p.dcf:.6f}")
