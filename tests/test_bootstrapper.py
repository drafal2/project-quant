"""Tests for the zero-coupon curve bootstrapper and market quote types."""

from datetime import date

import pytest

from market_conventions import BusinessDayConvention, DayCountConvention, StubType
from market_structures.rates.bootstrapper import ZeroCurveBootstrapper
from market_structures.rates.bootstrapper import QuoteHierarchy
from market_structures.rates.quotes import (
    DepositQuote,
    FuturesQuote,
    MaturityReference,
    OISQuote,
    SwapQuote,
)
from schedules.date_utils import add_spot_lag, imm_date, parse_tenor
from market_structures.rates.curve import ZeroCurve
from schedules.calendars import CalendarType, HolidayCalendar
from schedules.schedule import Frequency

# Reference date: Tuesday 2024-01-02; spot with lag=2 => 2024-01-04
REF = date(2024, 1, 2)
ROUND_TRIP_TOL = 1e-8

USD = CalendarType.USD
MF = BusinessDayConvention.MODIFIED_FOLLOWING
ACT360 = DayCountConvention.ACT_360
ACT365 = DayCountConvention.ACT_365_FIXED


def _bootstrapper(quotes, **kwargs):
    return ZeroCurveBootstrapper(
        reference_date=REF,
        quotes=quotes,
        day_count_convention=ACT365,
        **kwargs,
    )


def _simple_discount_curve():
    """Three-pillar external discount curve for swap tests."""
    return ZeroCurve(
        reference_date=REF,
        pillar_dates=[date(2025, 1, 2), date(2026, 1, 2), date(2027, 1, 2), date(2029, 1, 2)],
        rates=[0.05, 0.052, 0.054, 0.056],
        day_count_convention=ACT365,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestParseTenor:
    def test_months(self):
        assert parse_tenor("3M") == (3, "M")

    def test_years(self):
        assert parse_tenor("2Y") == (2, "Y")

    def test_weeks(self):
        assert parse_tenor("1W") == (1, "W")

    def test_days(self):
        assert parse_tenor("7D") == (7, "D")

    def test_lowercase(self):
        assert parse_tenor("6m") == (6, "M")

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Unrecognised tenor unit"):
            parse_tenor("3X")

    def test_zero_quantity(self):
        with pytest.raises(ValueError, match="positive"):
            parse_tenor("0M")


class TestAddSpotLag:
    def test_zero_lag(self):
        d = date(2024, 1, 2)
        cal = HolidayCalendar(USD)
        assert add_spot_lag(d, 0, cal) == d

    def test_skips_weekend(self):
        # 2024-01-05 is a Friday; +1 biz day = Monday 2024-01-08
        cal = HolidayCalendar(USD)
        assert add_spot_lag(date(2024, 1, 5), 1, cal) == date(2024, 1, 8)

    def test_two_biz_days_from_tuesday(self):
        # 2024-01-02 (Tue) + 2 biz = 2024-01-04 (Thu)
        cal = HolidayCalendar(USD)
        assert add_spot_lag(REF, 2, cal) == date(2024, 1, 4)


class TestIMMDate:
    def test_H26(self):
        # March 2026: 1st = Sunday; first Wed = Mar 4; 3rd Wed = Mar 18
        assert imm_date("H26") == date(2026, 3, 18)

    def test_M26(self):
        # June 2026: 1st = Monday; first Wed = Jun 3; 3rd Wed = Jun 17
        assert imm_date("M26") == date(2026, 6, 17)

    def test_U26(self):
        # Sep 2026: 1st = Tuesday; first Wed = Sep 2; 3rd Wed = Sep 16
        assert imm_date("U26") == date(2026, 9, 16)

    def test_Z26(self):
        # Dec 2026: 1st = Tuesday; first Wed = Dec 2; 3rd Wed = Dec 16
        assert imm_date("Z26") == date(2026, 12, 16)

    def test_lowercase(self):
        assert imm_date("h26") == date(2026, 3, 18)

    def test_invalid_letter(self):
        with pytest.raises(ValueError, match="Invalid IMM month letter"):
            imm_date("A26")


# ---------------------------------------------------------------------------
# Deposit bootstrap
# ---------------------------------------------------------------------------

class TestDepositBootstrap:
    def _quote(self, rate="0.05", tenor="3M"):
        return DepositQuote(
            rate=float(rate),
            tenor=tenor,
            spot_lag=2,
            calendar=USD,
            business_day_convention=MF,
            day_count_convention=ACT360,
        )

    def test_single_round_trip(self):
        q = self._quote()
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_pillar_date_correct(self):
        q = self._quote()
        curve = _bootstrapper([q]).bootstrap()
        expected_mat = q.maturity_date(REF)
        assert curve._pillar_dates == [expected_mat]

    def test_zero_rate_sensible(self):
        q = self._quote()
        curve = _bootstrapper([q]).bootstrap()
        z = curve.zero_rate(q.maturity_date(REF))
        # ACT/360 deposit rate and ACT/365 zero rate differ slightly; within 20 bps is fine
        assert abs(z - 0.05) < 0.002

    def test_multi_deposit_all_round_trip(self):
        quotes = [
            self._quote("0.048", "1M"),
            self._quote("0.050", "3M"),
            self._quote("0.052", "6M"),
        ]
        curve = _bootstrapper(quotes).bootstrap()
        for q in quotes:
            assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_zero_spot_lag(self):
        q = DepositQuote(rate=0.05, tenor="3M", spot_lag=0, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_overnight_round_trip(self):
        """O/N deposit: spot_lag=0, tenor=1D — start=reference_date, mat=next business day."""
        q = DepositQuote(rate=0.05, tenor="1D", spot_lag=0, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        # REF=2024-01-02 (Tue) → mat=2024-01-03 (Wed)
        assert q.maturity_date(REF) == date(2024, 1, 3)
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_tom_next_round_trip(self):
        """T/N deposit: spot_lag=1, tenor=1D — start=next business day, mat=day after."""
        q = DepositQuote(rate=0.05, tenor="1D", spot_lag=1, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        # REF=2024-01-02 (Tue); spot=2024-01-03 (Wed); mat=2024-01-04 (Thu)
        assert q.maturity_date(REF) == date(2024, 1, 4)
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_overnight_friday_matures_monday(self):
        """O/N on Friday: FOLLOWING BDC skips the weekend, mat=Monday (3-calendar-day dcf)."""
        ref_fri = date(2024, 1, 5)
        q = DepositQuote(rate=0.05, tenor="1D", spot_lag=0, calendar=USD,
                         business_day_convention=BusinessDayConvention.FOLLOWING,
                         day_count_convention=ACT360)
        assert q.maturity_date(ref_fri) == date(2024, 1, 8)
        curve = ZeroCurveBootstrapper(
            reference_date=ref_fri,
            quotes=[q],
            day_count_convention=ACT365,
        ).bootstrap()
        assert abs(q.npv(ref_fri, curve)) < ROUND_TRIP_TOL

    def test_overnight_then_standard_deposit_chain(self):
        """O/N + 3M deposit bootstrapped together; both round-trip."""
        q_on = DepositQuote(rate=0.049, tenor="1D", spot_lag=0, calendar=USD,
                            business_day_convention=MF, day_count_convention=ACT360)
        q_3m = DepositQuote(rate=0.050, tenor="3M", spot_lag=2, calendar=USD,
                            business_day_convention=MF, day_count_convention=ACT360)
        curve = _bootstrapper([q_on, q_3m]).bootstrap()
        assert abs(q_on.npv(REF, curve)) < ROUND_TRIP_TOL
        assert abs(q_3m.npv(REF, curve)) < ROUND_TRIP_TOL


# ---------------------------------------------------------------------------
# Futures bootstrap
# ---------------------------------------------------------------------------

class TestFuturesBootstrap:
    def _quote(self, price=95.0, imm_code="H26", convexity=0.0):
        return FuturesQuote(
            price=price,
            imm_code=imm_code,
            tenor="3M",
            calendar=USD,
            business_day_convention=MF,
            day_count_convention=ACT360,
            convexity_adjustment=convexity,
        )

    def _seed_deposits(self):
        """Short-end deposits to anchor the curve before the IMM date."""
        return [
            DepositQuote(rate=0.048, tenor="1M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360),
            DepositQuote(rate=0.050, tenor="3M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360),
        ]

    def test_single_round_trip(self):
        deps = self._seed_deposits()
        q = self._quote()
        curve = _bootstrapper(deps + [q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_convexity_adjustment_reduces_rate(self):
        deps = self._seed_deposits()
        q_no_ca  = self._quote(price=95.0, convexity=0.0)
        q_with_ca = self._quote(price=95.0, convexity=0.0005)
        c1 = _bootstrapper(deps + [q_no_ca]).bootstrap()
        c2 = _bootstrapper(deps + [q_with_ca]).bootstrap()
        mat = q_no_ca.maturity_date(REF)
        # convexity adjustment lowers the effective rate → higher DF → lower zero rate
        assert c2.zero_rate(mat) < c1.zero_rate(mat)

    def test_deposit_then_futures_all_round_trip(self):
        deps = self._seed_deposits()
        q = self._quote()
        quotes = deps + [q]
        curve = _bootstrapper(quotes).bootstrap()
        for inst in quotes:
            assert abs(inst.npv(REF, curve)) < ROUND_TRIP_TOL


# ---------------------------------------------------------------------------
# OIS bootstrap
# ---------------------------------------------------------------------------

class TestOISBootstrap:
    def _quote(self, rate=0.05, tenor="1Y", freq=Frequency.ANNUAL):
        return OISQuote(
            rate=rate,
            tenor=tenor,
            spot_lag=2,
            frequency=freq,
            calendar=USD,
            business_day_convention=MF,
            day_count_convention=ACT365,
        )

    def test_single_round_trip(self):
        q = self._quote()
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_two_pillar_both_round_trip(self):
        q1 = self._quote(rate=0.048, tenor="6M", freq=Frequency.SEMI_ANNUAL)
        q2 = self._quote(rate=0.052, tenor="2Y")
        curve = _bootstrapper([q1, q2]).bootstrap()
        assert abs(q1.npv(REF, curve)) < ROUND_TRIP_TOL
        assert abs(q2.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_no_external_discount_curve_required(self):
        q = self._quote()
        # OIS is self-discounting; no discount_curve param in bootstrapper
        curve = _bootstrapper([q]).bootstrap()
        assert curve is not None

    def test_quarterly_ois_round_trip(self):
        q = self._quote(rate=0.051, tenor="1Y", freq=Frequency.QUARTERLY)
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL


# ---------------------------------------------------------------------------
# Swap bootstrap
# ---------------------------------------------------------------------------

class TestSwapBootstrap:
    def _quote(self, rate=0.055, tenor="2Y", disc_curve=None):
        if disc_curve is None:
            disc_curve = _simple_discount_curve()
        return SwapQuote(
            rate=rate,
            tenor=tenor,
            spot_lag=2,
            fixed_frequency=Frequency.SEMI_ANNUAL,
            fixed_day_count=ACT365,
            floating_frequency=Frequency.QUARTERLY,
            floating_day_count=ACT360,
            calendar=USD,
            business_day_convention=MF,
            discount_curve=disc_curve,
        )

    def test_single_round_trip(self):
        q = self._quote()
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_three_pillar_all_round_trip(self):
        disc = _simple_discount_curve()
        quotes = [
            self._quote(rate=0.050, tenor="1Y", disc_curve=disc),
            self._quote(rate=0.055, tenor="3Y", disc_curve=disc),
            self._quote(rate=0.058, tenor="5Y", disc_curve=disc),
        ]
        curve = _bootstrapper(quotes).bootstrap()
        for q in quotes:
            assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL


# ---------------------------------------------------------------------------
# Mixed instruments
# ---------------------------------------------------------------------------

class TestMixedBootstrap:
    def test_all_types_combined_round_trip(self):
        disc = _simple_discount_curve()
        dep = DepositQuote(rate=0.048, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        dep2 = DepositQuote(rate=0.050, tenor="6M", spot_lag=2, calendar=USD,
                            business_day_convention=MF, day_count_convention=ACT360)
        fut = FuturesQuote(price=95.0, imm_code="H26", tenor="3M", calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        ois = OISQuote(rate=0.052, tenor="2Y", spot_lag=2, frequency=Frequency.ANNUAL,
                       calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        swp = SwapQuote(rate=0.056, tenor="5Y", spot_lag=2,
                        fixed_frequency=Frequency.SEMI_ANNUAL, fixed_day_count=ACT365,
                        floating_frequency=Frequency.QUARTERLY, floating_day_count=ACT360,
                        calendar=USD, business_day_convention=MF, discount_curve=disc)

        # Provide in reverse maturity order to test auto-sorting
        quotes = [swp, ois, fut, dep2, dep]
        curve = _bootstrapper(quotes).bootstrap()
        for q in quotes:
            assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_unsorted_input_produces_sorted_pillars(self):
        q1 = DepositQuote(rate=0.048, tenor="3M", spot_lag=2, calendar=USD,
                          business_day_convention=MF, day_count_convention=ACT360)
        q2 = DepositQuote(rate=0.050, tenor="6M", spot_lag=2, calendar=USD,
                          business_day_convention=MF, day_count_convention=ACT360)
        curve = _bootstrapper([q2, q1]).bootstrap()
        assert curve._pillar_dates == sorted(curve._pillar_dates)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestQuoteHierarchy:
    def test_deposit_beats_ois(self):
        dep = DepositQuote(rate=0.05, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        ois = OISQuote(rate=0.05, tenor="3M", spot_lag=2, frequency=Frequency.ANNUAL,
                       calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        winner, loser = QuoteHierarchy.resolve(dep, ois)
        assert isinstance(winner, DepositQuote)
        assert isinstance(loser, OISQuote)

    def test_ois_beats_swap(self):
        ois = OISQuote(rate=0.05, tenor="1Y", spot_lag=2, frequency=Frequency.ANNUAL,
                       calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        swp = SwapQuote(rate=0.05, tenor="1Y", spot_lag=2,
                        fixed_frequency=Frequency.SEMI_ANNUAL, fixed_day_count=ACT365,
                        floating_frequency=Frequency.QUARTERLY, floating_day_count=ACT360,
                        calendar=USD, business_day_convention=MF,
                        discount_curve=_simple_discount_curve())
        winner, loser = QuoteHierarchy.resolve(ois, swp)
        assert isinstance(winner, OISQuote)
        assert isinstance(loser, SwapQuote)

    def test_swap_beats_futures(self):
        swp = SwapQuote(rate=0.05, tenor="1Y", spot_lag=2,
                        fixed_frequency=Frequency.SEMI_ANNUAL, fixed_day_count=ACT365,
                        floating_frequency=Frequency.QUARTERLY, floating_day_count=ACT360,
                        calendar=USD, business_day_convention=MF,
                        discount_curve=_simple_discount_curve())
        fut = FuturesQuote(price=95.0, imm_code="H25", tenor="3M", calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        winner, loser = QuoteHierarchy.resolve(swp, fut)
        assert isinstance(winner, SwapQuote)
        assert isinstance(loser, FuturesQuote)

    def test_resolve_is_symmetric(self):
        dep = DepositQuote(rate=0.05, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        fut = FuturesQuote(price=95.0, imm_code="H25", tenor="3M", calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        w1, l1 = QuoteHierarchy.resolve(dep, fut)
        w2, l2 = QuoteHierarchy.resolve(fut, dep)
        assert type(w1) == type(w2)
        assert type(l1) == type(l2)

    def test_unregistered_type_raises(self):
        class UnknownQuote(DepositQuote):
            pass
        q = UnknownQuote(rate=0.05, tenor="3M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        with pytest.raises(TypeError, match="not registered"):
            QuoteHierarchy.rank(q)

    def test_collision_emits_warning_and_winner_survives(self):
        dep = DepositQuote(rate=0.049, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        ois = OISQuote(rate=0.052, tenor="3M", spot_lag=2, frequency=Frequency.ANNUAL,
                       calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        assert dep.maturity_date(REF) == ois.maturity_date(REF)
        with pytest.warns(UserWarning, match="OISQuote.*discarded.*DepositQuote"):
            curve = _bootstrapper([dep, ois]).bootstrap()
        assert len(curve._pillar_dates) == 1
        assert abs(dep.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_collision_loser_does_not_round_trip(self):
        dep = DepositQuote(rate=0.049, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        ois = OISQuote(rate=0.060, tenor="3M", spot_lag=2, frequency=Frequency.ANNUAL,
                       calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        assert dep.maturity_date(REF) == ois.maturity_date(REF)
        with pytest.warns(UserWarning):
            curve = _bootstrapper([dep, ois]).bootstrap()
        assert abs(dep.npv(REF, curve)) < ROUND_TRIP_TOL
        assert abs(ois.npv(REF, curve)) > 1e-6


class TestEdgeCases:

    def test_nr_non_convergence_raises(self):
        bootstrapper = ZeroCurveBootstrapper(
            reference_date=REF,
            quotes=[],
            day_count_convention=ACT365,
            max_iterations=5,
            tolerance=1e-30,
        )
        # x**2 + 1 has no real roots and a nonzero derivative everywhere
        with pytest.raises(RuntimeError, match="did not converge"):
            bootstrapper._newton_raphson(lambda x: x ** 2 + 1, x0=0.05)

    def test_nr_zero_derivative_raises(self):
        bootstrapper = ZeroCurveBootstrapper(
            reference_date=REF,
            quotes=[],
            day_count_convention=ACT365,
        )
        # f(x) = 0.5 everywhere → derivative = 0 → RuntimeError on deriv==0
        # (forward difference: f(x+bump) - f(x) = 0)
        with pytest.raises(RuntimeError, match="zero derivative"):
            bootstrapper._newton_raphson(lambda x: 0.5, x0=0.05)

    def test_single_pillar_produces_valid_curve(self):
        q = DepositQuote(rate=0.05, tenor="3M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        curve = _bootstrapper([q]).bootstrap()
        assert isinstance(curve, ZeroCurve)
        assert len(curve._pillar_dates) == 1

    def test_output_is_zero_curve(self):
        q = DepositQuote(rate=0.05, tenor="3M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        result = _bootstrapper([q]).bootstrap()
        assert isinstance(result, ZeroCurve)


# ---------------------------------------------------------------------------
# MaturityReference
# ---------------------------------------------------------------------------

class TestMaturityReference:
    def _ois(self, maturity_reference=MaturityReference.ACCRUAL_END, payment_lag=2):
        return OISQuote(
            rate=0.05, tenor="1Y", spot_lag=2, frequency=Frequency.ANNUAL,
            calendar=USD, business_day_convention=MF, day_count_convention=ACT365,
            payment_lag=payment_lag, maturity_reference=maturity_reference,
        )

    def _swap(self, maturity_reference=MaturityReference.ACCRUAL_END, payment_lag=2):
        return SwapQuote(
            rate=0.055, tenor="2Y", spot_lag=2,
            fixed_frequency=Frequency.SEMI_ANNUAL, fixed_day_count=ACT365,
            floating_frequency=Frequency.QUARTERLY, floating_day_count=ACT360,
            calendar=USD, business_day_convention=MF,
            discount_curve=_simple_discount_curve(),
            payment_lag=payment_lag, maturity_reference=maturity_reference,
        )

    def test_accrual_end_default_unchanged(self):
        # ACCRUAL_END is the default; maturity_date must equal plain accrual termination
        q_default = OISQuote(rate=0.05, tenor="1Y", spot_lag=2, frequency=Frequency.ANNUAL,
                             calendar=USD, business_day_convention=MF,
                             day_count_convention=ACT365, payment_lag=2)
        q_explicit = self._ois(MaturityReference.ACCRUAL_END)
        assert q_default.maturity_date(REF) == q_explicit.maturity_date(REF)

    def test_payment_date_maturity_later_than_accrual_end(self):
        q_ae = self._ois(MaturityReference.ACCRUAL_END)
        q_pd = self._ois(MaturityReference.PAYMENT_DATE)
        assert q_pd.maturity_date(REF) > q_ae.maturity_date(REF)

    def test_payment_date_offset_equals_payment_lag(self):
        # With lag=2, the PAYMENT_DATE maturity must be exactly 2 business days later
        cal = HolidayCalendar(USD)
        q_ae = self._ois(MaturityReference.ACCRUAL_END)
        q_pd = self._ois(MaturityReference.PAYMENT_DATE)
        expected = cal.add_business_days(q_ae.maturity_date(REF), 2)
        assert q_pd.maturity_date(REF) == expected

    def test_zero_lag_both_references_equal(self):
        # With payment_lag=0 there is no offset regardless of reference
        q_ae = self._ois(MaturityReference.ACCRUAL_END,  payment_lag=0)
        q_pd = self._ois(MaturityReference.PAYMENT_DATE, payment_lag=0)
        assert q_ae.maturity_date(REF) == q_pd.maturity_date(REF)

    def test_ois_payment_date_round_trip(self):
        q = self._ois(MaturityReference.PAYMENT_DATE)
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_swap_payment_date_round_trip(self):
        q = self._swap(MaturityReference.PAYMENT_DATE)
        curve = _bootstrapper([q]).bootstrap()
        assert abs(q.npv(REF, curve)) < ROUND_TRIP_TOL

    def test_swap_payment_date_pillar_placed_at_payment_date(self):
        q = self._swap(MaturityReference.PAYMENT_DATE)
        curve = _bootstrapper([q]).bootstrap()
        cal = HolidayCalendar(USD)
        q_ae = self._swap(MaturityReference.ACCRUAL_END)
        expected_pillar = cal.add_business_days(q_ae.maturity_date(REF), 2)
        assert curve._pillar_dates[-1] == expected_pillar

    def test_accrual_end_and_payment_date_produce_different_pillars(self):
        q_ae = self._swap(MaturityReference.ACCRUAL_END)
        q_pd = self._swap(MaturityReference.PAYMENT_DATE)
        curve_ae = _bootstrapper([q_ae]).bootstrap()
        curve_pd = _bootstrapper([q_pd]).bootstrap()
        assert curve_ae._pillar_dates[-1] != curve_pd._pillar_dates[-1]


# ---------------------------------------------------------------------------
# start_date / quote_value
# ---------------------------------------------------------------------------

class TestStartDateAndQuoteValue:

    def test_deposit_start_date_is_spot(self):
        q = DepositQuote(rate=0.04, tenor="3M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        # spot = REF + 2 business days from Tuesday 2024-01-02 = 2024-01-04
        assert q.start_date(REF) == date(2024, 1, 4)

    def test_deposit_start_date_zero_lag(self):
        q = DepositQuote(rate=0.04, tenor="1D", spot_lag=0, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        assert q.start_date(REF) == REF

    def test_deposit_quote_value(self):
        q = DepositQuote(rate=0.035, tenor="6M", spot_lag=2, calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        assert q.quote_value() == pytest.approx(0.035)

    def test_futures_start_date_isimm_date(self):
        q = FuturesQuote(price=95.25, imm_code="H26", tenor="3M", calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        assert q.start_date(REF) == imm_date("H26")

    def test_futures_start_date_independent_of_reference(self):
        q = FuturesQuote(price=95.25, imm_code="M26", tenor="3M", calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        assert q.start_date(REF) == q.start_date(date(2025, 6, 1))

    def test_futures_quote_value_is_exchange_price(self):
        q = FuturesQuote(price=95.5, imm_code="H26", tenor="3M", calendar=USD,
                         business_day_convention=MF, day_count_convention=ACT360)
        assert q.quote_value() == pytest.approx(95.5)

    def test_ois_start_date_is_spot(self):
        q = OISQuote(rate=0.05, tenor="1Y", spot_lag=2, frequency=Frequency.ANNUAL,
                     calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        assert q.start_date(REF) == date(2024, 1, 4)

    def test_ois_quote_value_is_fixed_rate(self):
        q = OISQuote(rate=0.048, tenor="1Y", spot_lag=2, frequency=Frequency.ANNUAL,
                     calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        assert q.quote_value() == pytest.approx(0.048)

    def test_swap_start_date_is_spot(self):
        q = SwapQuote(rate=0.055, tenor="2Y", spot_lag=2,
                      fixed_frequency=Frequency.SEMI_ANNUAL, fixed_day_count=ACT365,
                      floating_frequency=Frequency.QUARTERLY, floating_day_count=ACT360,
                      calendar=USD, business_day_convention=MF,
                      discount_curve=_simple_discount_curve())
        assert q.start_date(REF) == date(2024, 1, 4)

    def test_swap_quote_value_is_fixed_rate(self):
        q = SwapQuote(rate=0.052, tenor="3Y", spot_lag=2,
                      fixed_frequency=Frequency.SEMI_ANNUAL, fixed_day_count=ACT365,
                      floating_frequency=Frequency.QUARTERLY, floating_day_count=ACT360,
                      calendar=USD, business_day_convention=MF,
                      discount_curve=_simple_discount_curve())
        assert q.quote_value() == pytest.approx(0.052)


# ---------------------------------------------------------------------------
# ZeroCurve.summary()
# ---------------------------------------------------------------------------

class TestCurveSummary:

    def _bootstrap_multi(self):
        dep = DepositQuote(rate=0.04, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        ois = OISQuote(rate=0.045, tenor="1Y", spot_lag=2, frequency=Frequency.ANNUAL,
                       calendar=USD, business_day_convention=MF, day_count_convention=ACT365)
        return _bootstrapper([dep, ois]).bootstrap()

    def test_summary_returns_string(self):
        curve = self._bootstrap_multi()
        assert isinstance(curve.summary(), str)

    def test_summary_contains_instrument_types(self):
        curve = self._bootstrap_multi()
        s = curve.summary()
        assert "DepositQuote" in s
        assert "OISQuote" in s

    def test_summary_contains_dates(self):
        curve = self._bootstrap_multi()
        s = curve.summary()
        assert "2024-01-04" in s  # spot date

    def test_summary_empty_when_no_quotes(self):
        curve = ZeroCurve(
            reference_date=REF,
            pillar_dates=[date(2025, 1, 2)],
            rates=[0.05],
            day_count_convention=ACT365,
        )
        assert curve.summary() == ""

    def test_summary_quote_count_matches_pillars(self):
        curve = self._bootstrap_multi()
        # header + separator + 2 data rows = 4 lines
        lines = curve.summary().splitlines()
        data_rows = [l for l in lines if not l.startswith("-") and "Type" not in l]
        assert len(data_rows) == 2

    def test_bootstrapped_curve_stores_quotes(self):
        dep = DepositQuote(rate=0.04, tenor="3M", spot_lag=2, calendar=USD,
                           business_day_convention=MF, day_count_convention=ACT360)
        curve = _bootstrapper([dep]).bootstrap()
        assert len(curve._quotes) == 1
        assert isinstance(curve._quotes[0], DepositQuote)
