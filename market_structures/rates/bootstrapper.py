"""Sequential zero-coupon curve bootstrapper using Newton-Raphson."""

import logging
import warnings
from collections.abc import Callable
from datetime import date

from market_conventions import DayCountConvention
from market_conventions.compounding import CompoundingFrequency, CompoundingType
from market_structures.interpolation.interpolators import Interpolator

from .curve import ZeroCurve
from .quotes import DepositQuote, FuturesQuote, MarketQuote, OISQuote, SwapQuote

logger = logging.getLogger(__name__)


# NOTE: every new MarketQuote subclass must be added to _RANK below.
class QuoteHierarchy:
    """Fixed priority order for resolving maturity-date collisions during bootstrapping.

    When two quotes share the same maturity date the one with the lower rank wins;
    the other is discarded with a warning. Ranks are fixed by instrument type and are
    not user-configurable — the ordering reflects standard market-data precedence.
    """

    _RANK: dict[type, int] = {
        DepositQuote: 1,
        OISQuote:     2,
        SwapQuote:    3,
        FuturesQuote: 4,
    }

    @classmethod
    def rank(
        cls,
        quote: MarketQuote,
    ) -> int:
        """Return the priority rank for a quote type (lower = higher priority).

        Parameters
        ----------
        quote
            Market quote whose type will be looked up in the rank table.

        Returns
        -------
        int
            Priority rank; lower values take precedence over higher values.

        Raises
        ------
        TypeError
            If the quote type is not registered in ``_RANK``.
        """
        t = type(quote)
        if t not in cls._RANK:
            raise TypeError(
                f"{t.__name__} is not registered in QuoteHierarchy._RANK. "
                "Add it before use."
            )
        return cls._RANK[t]

    @classmethod
    def resolve(
        cls,
        a: MarketQuote,
        b: MarketQuote,
    ) -> tuple[MarketQuote, MarketQuote]:
        """Return (winner, loser) for two quotes competing on the same maturity date.

        Parameters
        ----------
        a
            First competing quote.
        b
            Second competing quote.

        Returns
        -------
        tuple[MarketQuote, MarketQuote]
            ``(winner, loser)`` where the winner has the lower (higher-priority) rank.
        """
        return (a, b) if cls.rank(a) <= cls.rank(b) else (b, a)


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
        """Initialise the bootstrapper with quotes and curve construction parameters.

        Parameters
        ----------
        reference_date
            Curve anchor date (t=0).
        quotes
            Market instruments to bootstrap from; will be sorted by maturity
            internally.
        day_count_convention
            Day count convention passed to the constructed ``ZeroCurve``.
        compounding_type
            Compounding convention for the constructed curve. Defaults to
            ``CompoundingType.CONTINUOUS``.
        compounding_frequency
            Required when compounding_type is ``COMPOUNDED``; ignored otherwise.
        interpolator
            Interpolation strategy passed to the constructed curve. Defaults to
            ``LogLinearInterpolator``.
        max_iterations
            Maximum Newton-Raphson iterations per pillar. Defaults to ``50``.
        tolerance
            Convergence threshold for the NPV residual. Defaults to ``1e-10``.
        """
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

        Instruments are sorted by maturity date before solving. When two quotes share the
        same maturity date QuoteHierarchy resolves the conflict: the lower-rank quote is
        silently discarded with a UserWarning.

        Returns
        -------
        ZeroCurve
            Fully calibrated zero curve with one pillar per resolved quote.

        Raises
        ------
        RuntimeError
            If Newton-Raphson fails to converge for any pillar.
        """
        logger.info(
            "Bootstrapping zero curve from %d quote(s), reference_date=%s",
            len(self._quotes),
            self._reference_date,
        )
        sorted_quotes = sorted(self._quotes, key=lambda q: q.maturity_date(self._reference_date))

        resolved: dict[date, MarketQuote] = {}
        for q in sorted_quotes:
            mat = q.maturity_date(self._reference_date)
            if mat in resolved:
                winner, loser = QuoteHierarchy.resolve(resolved[mat], q)
                warnings.warn(
                    f"{type(loser).__name__} at {mat} discarded in favour of "
                    f"{type(winner).__name__} (QuoteHierarchy rank "
                    f"{QuoteHierarchy.rank(winner)} < {QuoteHierarchy.rank(loser)}).",
                    UserWarning,
                    stacklevel=2,
                )
                resolved[mat] = winner
            else:
                resolved[mat] = q

        known_dates: list[date] = []
        known_rates: list[float] = []

        for mat, quote in sorted(resolved.items()):
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

        logger.info(
            "Bootstrap complete: %d pillar(s) calibrated (first=%s, last=%s)",
            len(known_dates),
            known_dates[0] if known_dates else None,
            known_dates[-1] if known_dates else None,
        )
        return ZeroCurve(
            reference_date=self._reference_date,
            pillar_dates=known_dates,
            rates=known_rates,
            day_count_convention=self._dcc,
            compounding_type=self._compounding_type,
            compounding_frequency=self._compounding_frequency,
            interpolator=self._interpolator,
            quotes=list(resolved.values()),
        )

    def _newton_raphson(
        self,
        f: Callable[[float], float],
        x0: float,
    ) -> float:
        """Solve f(x) = 0 using Newton-Raphson with a forward finite-difference derivative.

        Parameters
        ----------
        f
            Objective function whose root is sought.
        x0
            Initial guess for the root.

        Returns
        -------
        float
            Root x such that abs(f(x)) < tolerance.

        Raises
        ------
        RuntimeError
            If a zero derivative is encountered or convergence is not achieved
            within max_iterations.
        """
        _BUMP = 1e-7
        x = x0
        for iteration in range(self._max_iterations):
            fx = f(x)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("NR iter=%d x=%.10f f(x)=%.3e", iteration, x, fx)
            if abs(fx) < self._tolerance:
                logger.info(
                    "NR converged in %d iteration(s), |f(x)|=%.3e",
                    iteration + 1,
                    abs(fx),
                )
                return x
            f_bump = f(x + _BUMP)
            deriv = (f_bump - fx) / _BUMP
            if deriv == 0.0:
                logger.error(
                    "NR zero-derivative at x=%.10f after %d iteration(s)",
                    x,
                    iteration,
                )
                raise RuntimeError(
                    f"Newton-Raphson failed: zero derivative at x={x} "
                    f"after {iteration} iterations."
                )
            x = x - fx / deriv
        logger.error(
            "NR failed to converge in %d iteration(s); last x=%.10f, f(x)=%.3e",
            self._max_iterations,
            x,
            f(x),
        )
        raise RuntimeError(
            f"Newton-Raphson did not converge after {self._max_iterations} iterations. "
            f"Last x={x:.8f}, f(x)={f(x):.2e}, tolerance={self._tolerance:.2e}."
        )
