"""Sequential and global Newton-Raphson bootstrapper for the credit curve."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date
from enum import Enum

from market_conventions import DayCountConvention
from market_structures.rates.curve import ZeroCurve
from schedules.day_count import day_count_fraction

from .curve import CreditCurve, InterpolationVariable
from .pricing import SingleNameCDS
from .quotes import CdsQuote


class BootstrapMode(Enum):
    """Bootstrapping strategy for the credit curve.

    Attributes
    ----------
    SEQUENTIAL
        Scalar Newton-Raphson per pillar; pillar i is solved holding
        pillars < i fixed. Standard, fast, well-conditioned.
    GLOBAL
        Multivariate Newton-Raphson on the vector NPV system; all pillar
        values are updated simultaneously. Equivalent to ``SEQUENTIAL`` when
        the system is exactly determined and the interpolation is causal
        (no upstream effect on earlier pillars), but more robust when small
        numerical perturbations couple pillars.
    """

    SEQUENTIAL = "sequential"
    GLOBAL = "global"


class CreditCurveBootstrapper:
    """Bootstraps a ``CreditCurve`` from CDS spread quotes via Newton-Raphson.

    The bootstrapper instantiates a ``SingleNameCDS`` per quote (using a partial
    or candidate credit curve) and drives each NPV to zero. The interpolation
    variable controls what the solver actually solves for at each pillar:
    survival probabilities, cumulative default spreads, or forward hazard rates.
    """

    _DERIV_BUMP = 1e-7

    def __init__(
        self,
        reference_date: date,
        quotes: list[CdsQuote],
        zero_curve: ZeroCurve,
        recovery_rate: float,
        interpolation_variable: InterpolationVariable = InterpolationVariable.FORWARD_DEFAULT_SPREAD,
        day_count_convention: DayCountConvention = DayCountConvention.ACT_365_FIXED,
        mode: BootstrapMode = BootstrapMode.SEQUENTIAL,
        max_iterations: int = 50,
        tolerance: float = 1e-10,
    ) -> None:
        """Initialise the bootstrapper with quotes, curves, and solver configuration.

        Parameters
        ----------
        reference_date
            Curve anchor date (t=0); both pillar dates and zero-curve queries
            are measured relative to this date.
        quotes
            CDS spread quotes to bootstrap from. Sorted internally by maturity
            and required to have distinct maturity dates.
        zero_curve
            Risk-free discount curve used to price the candidate CDS at each
            bootstrap step.
        recovery_rate
            Constant recovery rate applied uniformly across pillars; must lie
            in [0, 1).
        interpolation_variable
            Pillar variable solved for at each step. Defaults to
            ``FORWARD_DEFAULT_SPREAD`` (piecewise-constant hazard rates).
        day_count_convention
            Day count used for time-to-pillar fractions in survival arithmetic.
            Defaults to ``ACT_365_FIXED``.
        mode
            ``SEQUENTIAL`` (default) solves one pillar at a time; ``GLOBAL``
            solves the full vector system simultaneously.
        max_iterations
            Newton-Raphson iteration cap, applied to both modes. Defaults to
            ``50``.
        tolerance
            Convergence threshold on the NPV residual (max absolute residual
            across pillars in ``GLOBAL`` mode). Defaults to ``1e-10``.

        Raises
        ------
        ValueError
            If ``quotes`` is empty, or if ``recovery_rate`` is outside [0, 1).
        """
        if not quotes:
            raise ValueError("at least one CDS quote is required")
        if not 0.0 <= recovery_rate < 1.0:
            raise ValueError("recovery_rate must lie in [0, 1)")
        self._reference_date = reference_date
        self._quotes = quotes
        self._zero_curve = zero_curve
        self._recovery_rate = recovery_rate
        self._variable = interpolation_variable
        self._dcc = day_count_convention
        self._mode = mode
        self._max_iterations = max_iterations
        self._tolerance = tolerance

    def bootstrap(self) -> CreditCurve:
        """Run the bootstrap and return the calibrated ``CreditCurve``.

        Sorts quotes by maturity, dispatches to the configured ``BootstrapMode``,
        and assembles the resulting pillar values into a fresh ``CreditCurve``
        that retains the original quotes for downstream inspection.

        Returns
        -------
        CreditCurve
            Curve with one pillar per quote, calibrated so that each quote
            prices to zero NPV under the chosen interpolation variable.

        Raises
        ------
        ValueError
            If two or more quotes share the same maturity date.
        RuntimeError
            If Newton-Raphson fails to converge within ``max_iterations``, or
            if the global Jacobian is singular.
        """
        sorted_quotes = sorted(
            self._quotes, key=lambda q: q.maturity_date(self._reference_date)
        )
        pillar_dates = [q.maturity_date(self._reference_date) for q in sorted_quotes]

        if len(set(pillar_dates)) != len(pillar_dates):
            raise ValueError("CDS quotes must have distinct maturity dates")

        if self._mode is BootstrapMode.SEQUENTIAL:
            values = self._bootstrap_sequential(sorted_quotes, pillar_dates)
        else:
            values = self._bootstrap_global(sorted_quotes, pillar_dates)

        return CreditCurve(
            reference_date=self._reference_date,
            pillar_dates=pillar_dates,
            pillar_values=values,
            interpolation_variable=self._variable,
            day_count_convention=self._dcc,
            quotes=sorted_quotes,
        )

    def _initial_guess(self, quote: CdsQuote) -> float:
        """Return a credit-triangle seed for the pillar value of the chosen variable."""
        spread = quote.quote_value()
        lam = spread / (1.0 - self._recovery_rate)
        if self._variable is InterpolationVariable.SURVIVAL_PROBABILITY:
            t = day_count_fraction(
                self._reference_date,
                quote.maturity_date(self._reference_date),
                self._dcc,
            )
            return math.exp(-lam * t)
        return lam

    def _candidate_curve(
        self,
        pillar_dates: list[date],
        values: list[float],
    ) -> CreditCurve:
        """Build a (possibly partial) ``CreditCurve`` for the solver to evaluate.

        Parameters
        ----------
        pillar_dates
            Dates of the pillars seen so far (in sequential mode) or all
            pillars (in global mode).
        values
            Pillar values for the configured ``InterpolationVariable``, one
            per date in ``pillar_dates``.

        Returns
        -------
        CreditCurve
            Curve constructed from the given pillars; quotes are not attached.
        """
        return CreditCurve(
            reference_date=self._reference_date,
            pillar_dates=pillar_dates,
            pillar_values=values,
            interpolation_variable=self._variable,
            day_count_convention=self._dcc,
        )

    def _quote_npv(
        self,
        quote: CdsQuote,
        curve: CreditCurve,
    ) -> float:
        """Return the CDS NPV for ``quote`` priced under ``curve``.

        Parameters
        ----------
        quote
            Market quote whose schedule and spread are used to instantiate a
            ``SingleNameCDS``.
        curve
            Candidate credit curve under which the trade is priced.

        Returns
        -------
        float
            Trade NPV (zero at the calibrated pillar value).
        """
        cds = SingleNameCDS(
            schedule=quote.schedule(self._reference_date),
            spread=quote.quote_value(),
            recovery_rate=self._recovery_rate,
            zero_curve=self._zero_curve,
            credit_curve=curve,
            pricing_date=self._reference_date,
        )
        return cds.npv()

    def _bootstrap_sequential(
        self,
        sorted_quotes: list[CdsQuote],
        pillar_dates: list[date],
    ) -> list[float]:
        """Solve pillar-by-pillar with scalar Newton-Raphson.

        Parameters
        ----------
        sorted_quotes
            Quotes in ascending maturity order.
        pillar_dates
            Maturity dates corresponding to ``sorted_quotes``, one per pillar.

        Returns
        -------
        list[float]
            Calibrated pillar values for the configured interpolation variable,
            in the same order as ``sorted_quotes``.
        """
        known_values: list[float] = []
        for i, q in enumerate(sorted_quotes):
            def objective(
                x: float,
                _i: int = i,
                _q: CdsQuote = q,
                _kv: list[float] = known_values,
            ) -> float:
                curve = self._candidate_curve(pillar_dates[: _i + 1], _kv + [x])
                return self._quote_npv(_q, curve)

            x = self._scalar_newton(objective, self._initial_guess(q))
            known_values.append(x)
        return known_values

    def _bootstrap_global(
        self,
        sorted_quotes: list[CdsQuote],
        pillar_dates: list[date],
    ) -> list[float]:
        """Solve all pillars simultaneously via multivariate Newton-Raphson.

        Each Newton step builds the full Jacobian by forward-bumping every
        pillar value in turn and solves the resulting linear system for the
        update vector.

        Parameters
        ----------
        sorted_quotes
            Quotes in ascending maturity order.
        pillar_dates
            Maturity dates corresponding to ``sorted_quotes``.

        Returns
        -------
        list[float]
            Calibrated pillar values for the configured interpolation variable.

        Raises
        ------
        RuntimeError
            If the Newton iteration fails to converge within ``max_iterations``,
            or if the Jacobian is (numerically) singular at any step.
        """
        n = len(sorted_quotes)
        x = [self._initial_guess(q) for q in sorted_quotes]

        def F(values: list[float]) -> list[float]:
            curve = self._candidate_curve(pillar_dates, values)
            return [self._quote_npv(q, curve) for q in sorted_quotes]

        for iteration in range(self._max_iterations):
            f = F(x)
            if max(abs(v) for v in f) < self._tolerance:
                return x
            jacobian = [[0.0] * n for _ in range(n)]
            for j in range(n):
                x_bumped = list(x)
                x_bumped[j] += self._DERIV_BUMP
                f_bumped = F(x_bumped)
                for i in range(n):
                    jacobian[i][j] = (f_bumped[i] - f[i]) / self._DERIV_BUMP
            dx = _solve_linear_system(jacobian, [-v for v in f])
            x = [xi + dxi for xi, dxi in zip(x, dx)]

        raise RuntimeError(
            f"Global Newton-Raphson did not converge after {self._max_iterations} "
            f"iterations; last residuals max={max(abs(v) for v in F(x)):.2e}, "
            f"tolerance={self._tolerance:.2e}."
        )

    def _scalar_newton(
        self,
        f: Callable[[float], float],
        x0: float,
    ) -> float:
        """Solve f(x) = 0 with scalar Newton-Raphson and a forward-difference derivative.

        Parameters
        ----------
        f
            Objective function whose root is sought.
        x0
            Initial guess.

        Returns
        -------
        float
            Root x with ``abs(f(x))`` below ``tolerance``.

        Raises
        ------
        RuntimeError
            If the derivative vanishes at any iterate, or if convergence is
            not reached within ``max_iterations``.
        """
        x = x0
        for iteration in range(self._max_iterations):
            fx = f(x)
            if abs(fx) < self._tolerance:
                return x
            f_bump = f(x + self._DERIV_BUMP)
            deriv = (f_bump - fx) / self._DERIV_BUMP
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


def _solve_linear_system(
    matrix: list[list[float]],
    rhs: list[float],
) -> list[float]:
    """Solve A x = b with Gaussian elimination and partial pivoting.

    Parameters
    ----------
    matrix
        Square coefficient matrix as a list of rows.
    rhs
        Right-hand side vector with length equal to ``len(matrix)``.

    Returns
    -------
    list[float]
        Solution vector x.

    Raises
    ------
    RuntimeError
        If the pivot at any elimination step is below 1e-14, indicating a
        (numerically) singular system.
    """
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for k in range(n):
        pivot_row = max(range(k, n), key=lambda r: abs(a[r][k]))
        if abs(a[pivot_row][k]) < 1e-14:
            raise RuntimeError("Singular Jacobian in global bootstrap")
        a[k], a[pivot_row] = a[pivot_row], a[k]
        for i in range(k + 1, n):
            factor = a[i][k] / a[k][k]
            for j in range(k, n + 1):
                a[i][j] -= factor * a[k][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = a[i][n] - sum(a[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / a[i][i]
    return x
