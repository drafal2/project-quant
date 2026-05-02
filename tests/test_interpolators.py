import math
import pytest

from market_data.interpolation import LinearInterpolator, LogLinearInterpolator, V2TInterpolator

XS = [1.0, 2.0, 4.0]
YS = [0.1, 0.3, 0.5]


class TestLinearInterpolator:
    def test_recovers_pillar_values(self):
        interp = LinearInterpolator()
        for x, y in zip(XS, YS):
            assert interp.interpolate(x, XS, YS) == pytest.approx(y)

    def test_midpoint(self):
        interp = LinearInterpolator()
        assert interp.interpolate(1.5, XS, YS) == pytest.approx(0.2)

    def test_extrapolate_left_flat(self):
        interp = LinearInterpolator()
        assert interp.interpolate(0.0, XS, YS) == pytest.approx(YS[0])

    def test_extrapolate_right_flat(self):
        interp = LinearInterpolator()
        assert interp.interpolate(10.0, XS, YS) == pytest.approx(YS[-1])

    def test_raises_left_when_no_extrapolation(self):
        interp = LinearInterpolator(extrapolate=False)
        with pytest.raises(ValueError, match="outside the pillar range"):
            interp.interpolate(0.0, XS, YS)

    def test_raises_right_when_no_extrapolation(self):
        interp = LinearInterpolator(extrapolate=False)
        with pytest.raises(ValueError, match="outside the pillar range"):
            interp.interpolate(10.0, XS, YS)

    def test_in_range_allowed_when_no_extrapolation(self):
        interp = LinearInterpolator(extrapolate=False)
        assert interp.interpolate(1.5, XS, YS) == pytest.approx(0.2)


class TestLogLinearInterpolator:
    def test_recovers_pillar_values(self):
        interp = LogLinearInterpolator()
        for x, y in zip(XS, YS):
            assert interp.interpolate(x, XS, YS) == pytest.approx(y)

    def test_midpoint_is_geometric(self):
        interp = LogLinearInterpolator()
        xs = [1.0, 2.0]
        ys = [0.5, 0.25]
        # log-linear midpoint: exp((log(0.5) + log(0.25)) / 2) = sqrt(0.5 * 0.25)
        expected = math.sqrt(0.5 * 0.25)
        assert interp.interpolate(1.5, xs, ys) == pytest.approx(expected)

    def test_extrapolate_left_flat(self):
        interp = LogLinearInterpolator()
        assert interp.interpolate(0.0, XS, YS) == pytest.approx(YS[0])

    def test_extrapolate_right_flat(self):
        interp = LogLinearInterpolator()
        assert interp.interpolate(10.0, XS, YS) == pytest.approx(YS[-1])

    def test_raises_outside_range_when_no_extrapolation(self):
        interp = LogLinearInterpolator(extrapolate=False)
        with pytest.raises(ValueError, match="outside the pillar range"):
            interp.interpolate(10.0, XS, YS)


class TestV2TInterpolator:
    VOL_XS = [0.25, 0.5, 1.0, 2.0]
    VOL_YS = [0.20, 0.22, 0.25, 0.28]

    def test_recovers_pillar_vols(self):
        interp = V2TInterpolator()
        for x, y in zip(self.VOL_XS, self.VOL_YS):
            assert interp.interpolate(x, self.VOL_XS, self.VOL_YS) == pytest.approx(y)

    def test_total_variance_non_decreasing(self):
        interp = V2TInterpolator()
        ts = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
        vols = [interp.interpolate(t, self.VOL_XS, self.VOL_YS) for t in ts]
        variances = [v ** 2 * t for v, t in zip(vols, ts)]
        for i in range(len(variances) - 1):
            assert variances[i] <= variances[i + 1] + 1e-12

    def test_interpolated_value_between_pillars(self):
        interp = V2TInterpolator()
        xs = [1.0, 2.0]
        ys = [0.20, 0.30]
        # w_left = 0.04, w_right = 0.18, at t=1.5: w = 0.04 + 0.5*(0.18-0.04) = 0.11
        expected = math.sqrt(0.11 / 1.5)
        assert interp.interpolate(1.5, xs, ys) == pytest.approx(expected)

    def test_extrapolate_left_flat(self):
        interp = V2TInterpolator()
        assert interp.interpolate(0.1, self.VOL_XS, self.VOL_YS) == pytest.approx(self.VOL_YS[0])

    def test_extrapolate_right_flat(self):
        interp = V2TInterpolator()
        assert interp.interpolate(5.0, self.VOL_XS, self.VOL_YS) == pytest.approx(self.VOL_YS[-1])

    def test_raises_outside_range_when_no_extrapolation(self):
        interp = V2TInterpolator(extrapolate=False)
        with pytest.raises(ValueError, match="outside the pillar range"):
            interp.interpolate(5.0, self.VOL_XS, self.VOL_YS)
