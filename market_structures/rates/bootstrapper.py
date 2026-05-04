"""Sequential zero-coupon curve bootstrapper using Newton-Raphson."""

from collections.abc import Callable
from datetime import date

from market_conventions import DayCountConvention
from market_conventions.compounding import CompoundingFrequency, CompoundingType
from market_structures.interpolation.interpolators import Interpolator

from .curve import ZeroCurve
from .quotes import MarketQuote


class ZeroCurveBootstrapper:
    """Bootstraps a ZeroCurve from market quotes using sequential Newton-Raphson."""

    def __init__(
        self,
        reference_date: date,
        quotes: list[MarketQuote],
        day_count_convention: DayCountConvention,
        compounding_type: CompoundingType = CompoundingType.CONTINUOUS,
        compounding_frequency: CompoundingFrequency | None = None,
        interpolator: Interpolator | None = None,
        max_iterations: int = 50,
        tolerance: float = 1e-10,
    ) -> None:
        """Initialise the bootstrapper with quotes and curve construction parameters."""
        self._reference_date = reference_date
        self._quotes = quotes
        self._dcc = day_count_convention
        self._compounding_type = compounding_type
        self._compounding_frequency = compounding_frequency
        self._interpolator = interpolator
        self._max_iterations = max_iterations
        self._tolerance = tolerance

    def bootstrap(self) -> ZeroCurve:
        """Run the sequential bootstrap and return the calibrated ZeroCurve.

        Instruments are sorted by maturity date before solving. Raises ValueError if two
        quotes share the same maturity date.
        """
        sorted_quotes = sorted(self._quotes, key=lambda q: q.maturity_date(self._reference_date))

        seen: set[date] = set()
        for q in sorted_quotes:
            mat = q.maturity_date(self._reference_date)
            if mat in seen:

# TODO: hierarchy must be established - which quote has higher priority if two quotes share the same maturity date? Do that and do not raise error, you can raise a warning instead that one quote is ignored because another quote with the same maturity date has higher priority. Priority may be an input or a global setting - decide what is better approach

               raise ValueError(
                    f"Two quotes share maturity date {mat}. "
                    "Each pillar must be defined by exactly one instrument."
                )
            seen.add(mat)

        known_dates: list[date] = []
        known_rates: list[float] = []

        for quote in sorted_quotes:
            mat = quote.maturity_date(self._reference_date)

            def objective(r: float, _mat: date = mat, _kd: list = known_dates, _kr: list = known_rates) -> float:
                partial = ZeroCurve(
                    reference_date=self._reference_date,
                    pillar_dates=_kd + [_mat],
                    rates=_kr + [r],
                    day_count_convention=self._dcc,
                    compounding_type=self._compounding_type,
                    compounding_frequency=self._compounding_frequency,
                    interpolator=self._interpolator,
                )
                return quote.npv(self._reference_date, partial)

            r = self._newton_raphson(objective, quote.initial_guess())
            known_dates.append(mat)
            known_rates.append(r)

        return ZeroCurve(
            reference_date=self._reference_date,
            pillar_dates=known_dates,
            rates=known_rates,
            day_count_convention=self._dcc,
            compounding_type=self._compounding_type,
            compounding_frequency=self._compounding_frequency,
            interpolator=self._interpolator,
        )

    def _newton_raphson(self, f: Callable[[float], float], x0: float) -> float:
        """Solve f(x) = 0 using Newton-Raphson with a forward finite-difference derivative."""
        _BUMP = 1e-7
        x = x0
        for iteration in range(self._max_iterations):
            fx = f(x)
            if abs(fx) < self._tolerance:
                return x
            f_bump = f(x + _BUMP)
            deriv = (f_bump - fx) / _BUMP
            if deriv == 0.0:
                raise RuntimeError(
                    f"Newton-Raphson failed: zero derivative at x={x} "
                    f"after {iteration} iterations."
                )
            x = x - fx / deriv
        raise RuntimeError(
            f"Newton-Raphson did not converge after {self._max_iterations} iterations. "
            f"Last x={x:.8f}, f(x)={f(x):.2e}, tolerance={self._tolerance:.2e}."
        )
