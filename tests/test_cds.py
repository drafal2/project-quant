"""Tests for SingleNameCDS: construction, pricing, greeks, sign conventions."""

from datetime import date

import pytest

from market_conventions import CompoundingType, DayCountConvention
from market_structures import ZeroCurve
from credit import SingleNameCDS, SurvivalCurve

REF = date(2024, 1, 2)
P12 = date(2025, 1, 2)
P36 = date(2027, 1, 2)
P60 = date(2029, 1, 2)

SPREADS = [0.01, 0.012, 0.015]
RECOVERY = 0.40
NOTIONAL = 1_000_000


def make_discount_curve():
    """Build a simple continuous discount curve."""
    return ZeroCurve(
        REF,
        [P12, P36, P60],
        [0.05, 0.052, 0.053],
        DayCountConvention.ACT_365_FIXED,
        CompoundingType.CONTINUOUS,
    )


def make_survival_curve(dc, spreads=None):
    """Bootstrap a survival curve from market spreads."""
    if spreads is None:
        spreads = SPREADS
    return SurvivalCurve.from_spreads(REF, [P12, P36, P60], spreads, dc, recovery_rate=RECOVERY)


class TestConstruction:
    def test_effective_after_maturity_raises(self):
        with pytest.raises(ValueError):
            SingleNameCDS(P60, REF, NOTIONAL, 0.01, RECOVERY)

    def test_effective_equal_maturity_raises(self):
        with pytest.raises(ValueError):
            SingleNameCDS(REF, REF, NOTIONAL, 0.01, RECOVERY)

    def test_negative_recovery_raises(self):
        with pytest.raises(ValueError):
            SingleNameCDS(REF, P60, NOTIONAL, 0.01, -0.1)

    def test_recovery_one_raises(self):
        with pytest.raises(ValueError):
            SingleNameCDS(REF, P60, NOTIONAL, 0.01, 1.0)

    def test_negative_notional_raises(self):
        with pytest.raises(ValueError):
            SingleNameCDS(REF, P60, -NOTIONAL, 0.01, RECOVERY)

    def test_zero_notional_raises(self):
        with pytest.raises(ValueError):
            SingleNameCDS(REF, P60, 0, 0.01, RECOVERY)

    def test_valid_construction(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, 0.015, RECOVERY)
        assert cds is not None


class TestParSpread:
    def setup_method(self):
        self.dc = make_discount_curve()
        self.sc = make_survival_curve(self.dc)

    def test_par_spread_round_trip(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        assert abs(cds.par_spread(self.dc, self.sc) - SPREADS[2]) < 1e-5

    def test_par_spread_at_shorter_maturity(self):
        cds = SingleNameCDS(REF, P12, NOTIONAL, coupon_spread=SPREADS[0], recovery_rate=RECOVERY)
        assert abs(cds.par_spread(self.dc, self.sc) - SPREADS[0]) < 1e-5

    def test_rpv01_positive(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        assert cds.rpv01(self.dc, self.sc) > 0

    def test_accounting_identity(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        par = cds.par_spread(self.dc, self.sc)
        rpv01 = cds.rpv01(self.dc, self.sc)
        prot = cds.protection_leg_pv(self.dc, self.sc)
        assert abs(par * rpv01 - prot / NOTIONAL) < 1e-8

    def test_protection_leg_pv_positive(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        assert cds.protection_leg_pv(self.dc, self.sc) > 0


class TestMTM:
    def setup_method(self):
        self.dc = make_discount_curve()
        self.sc = make_survival_curve(self.dc)

    def test_mtm_zero_at_par(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        par = cds.par_spread(self.dc, self.sc)
        at_par = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=par, recovery_rate=RECOVERY)
        assert abs(at_par.mtm(self.dc, self.sc)) < 1e-4

    def test_mtm_positive_buyer_coupon_below_par(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        par = cds.par_spread(self.dc, self.sc)
        below = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=par - 0.001, recovery_rate=RECOVERY)
        assert below.mtm(self.dc, self.sc) > 0

    def test_mtm_negative_buyer_coupon_above_par(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=SPREADS[2], recovery_rate=RECOVERY)
        par = cds.par_spread(self.dc, self.sc)
        above = SingleNameCDS(REF, P60, NOTIONAL, coupon_spread=par + 0.001, recovery_rate=RECOVERY)
        assert above.mtm(self.dc, self.sc) < 0

    def test_seller_flips_sign(self):
        buyer = SingleNameCDS(REF, P60, NOTIONAL, SPREADS[2], RECOVERY, is_protection_buyer=True)
        seller = SingleNameCDS(REF, P60, NOTIONAL, SPREADS[2], RECOVERY, is_protection_buyer=False)
        assert abs(buyer.mtm(self.dc, self.sc) + seller.mtm(self.dc, self.sc)) < 1e-6


class TestGreeks:
    def setup_method(self):
        self.dc = make_discount_curve()
        self.sc = make_survival_curve(self.dc)

    def test_cs01_positive_for_buyer(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, SPREADS[2], RECOVERY, is_protection_buyer=True)
        assert cds.cs01(self.dc, self.sc) > 0

    def test_cs01_negative_for_seller(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, SPREADS[2], RECOVERY, is_protection_buyer=False)
        assert cds.cs01(self.dc, self.sc) < 0

    def test_rr01_positive_for_buyer(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, SPREADS[2], RECOVERY, is_protection_buyer=True)
        assert cds.rr01(self.dc, self.sc) > 0

    def test_rr01_negative_for_seller(self):
        cds = SingleNameCDS(REF, P60, NOTIONAL, SPREADS[2], RECOVERY, is_protection_buyer=False)
        assert cds.rr01(self.dc, self.sc) < 0

    def test_cs01_proportional_to_notional(self):
        cds1 = SingleNameCDS(REF, P60, 1_000_000, SPREADS[2], RECOVERY)
        cds2 = SingleNameCDS(REF, P60, 2_000_000, SPREADS[2], RECOVERY)
        assert abs(cds2.cs01(self.dc, self.sc) / cds1.cs01(self.dc, self.sc) - 2.0) < 1e-6

    def test_rr01_proportional_to_notional(self):
        cds1 = SingleNameCDS(REF, P60, 1_000_000, SPREADS[2], RECOVERY)
        cds2 = SingleNameCDS(REF, P60, 2_000_000, SPREADS[2], RECOVERY)
        assert abs(cds2.rr01(self.dc, self.sc) / cds1.rr01(self.dc, self.sc) - 2.0) < 1e-6
