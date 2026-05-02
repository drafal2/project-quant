import math
from abc import ABC, abstractmethod


class Interpolator(ABC):
    def __init__(self, extrapolate: bool = True) -> None:
        self._extrapolate = extrapolate

    def interpolate(self, x: float, xs: list[float], ys: list[float]) -> float:
        """Interpolate y at x given sorted (xs, ys) pairs.

        Args:
            x: The point at which to interpolate.
            xs: Sorted list of pillar x-values.
            ys: Corresponding y-values.

        Returns:
            Interpolated y value. If x is outside [xs[0], xs[-1]] and
            extrapolate is True, returns the nearest boundary value (flat
            extrapolation). Raises ValueError if extrapolate is False.

        Raises:
            ValueError: If x is outside the pillar range and extrapolate is False.
        """
        if x == xs[0]:
            return ys[0]
        if x == xs[-1]:
            return ys[-1]
        if x < xs[0] or x > xs[-1]:
            if not self._extrapolate:
                raise ValueError(f"x={x} is outside the pillar range [{xs[0]}, {xs[-1]}]")
            return ys[0] if x < xs[0] else ys[-1]
        return self._interpolate(x, xs, ys)

    @abstractmethod
    def _interpolate(self, x: float, xs: list[float], ys: list[float]) -> float:
        """Interpolate within the pillar range.

        x is guaranteed to be strictly between xs[0] and xs[-1].
        """
        ...


class LinearInterpolator(Interpolator):
    """Linear interpolator.

    Interpolates linearly between adjacent pillars. When extrapolate is True,
    values outside the pillar range are held flat at the nearest boundary value.
    """

    def __init__(self, extrapolate: bool = True) -> None:
        super().__init__(extrapolate)

    def _interpolate(self, x: float, xs: list[float], ys: list[float]) -> float:
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                t = (x - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])


class LogLinearInterpolator(Interpolator):
    """Log-linear interpolator.

    Interpolates linearly on log(y), which is the market standard for discount
    factors. When extrapolate is True, values outside the pillar range are held
    flat at the nearest boundary value.
    """

    def __init__(self, extrapolate: bool = True) -> None:
        super().__init__(extrapolate)

    def _interpolate(self, x: float, xs: list[float], ys: list[float]) -> float:
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                t = (x - xs[i]) / (xs[i + 1] - xs[i])
                return math.exp(math.log(ys[i]) + t * (math.log(ys[i + 1]) - math.log(ys[i])))


class V2TInterpolator(Interpolator):
    """Variance-to-time (V2T) interpolator for implied volatility.

    Interpolates by linearly interpolating total variance (σ² × T) across
    expiries, then converting back to implied volatility. This ensures total
    variance is non-decreasing, preventing calendar spread arbitrage.

    xs are times-to-expiry; ys are implied volatilities.

    When extrapolate is True, values outside the pillar range are held flat
    at the nearest boundary volatility.
    """

    def __init__(self, extrapolate: bool = True) -> None:
        super().__init__(extrapolate)

    def _interpolate(self, x: float, xs: list[float], ys: list[float]) -> float:
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                w_left = ys[i] ** 2 * xs[i]
                w_right = ys[i + 1] ** 2 * xs[i + 1]
                t = (x - xs[i]) / (xs[i + 1] - xs[i])
                w = w_left + t * (w_right - w_left)
                return math.sqrt(w / x)
