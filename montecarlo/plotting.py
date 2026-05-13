"""Plotting helpers for visual diagnostics of sampler output.

Every function accepts an optional Matplotlib ``Axes`` and returns it,
matching the convention used in the existing :mod:`examples` notebooks. The
library itself never calls ``plt.show()`` — the notebook is responsible for
displaying figures.
"""

from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


def scatter_2d(
    points: np.ndarray,
    dims: tuple[int, int] = (0, 1),
    ax: plt.Axes | None = None,
    title: str | None = None,
) -> plt.Axes:
    """Plot two columns of ``points`` against each other as a scatter.

    Parameters
    ----------
    points
        ``float64`` array of shape ``(n_points, n_dim)``.
    dims
        Pair of column indices to plot.
    ax
        Optional Matplotlib ``Axes`` to draw on; a new one is created if
        ``None``.
    title
        Optional title for the axes.

    Returns
    -------
    matplotlib.axes.Axes
        The axes on which the scatter was drawn.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    i, j = dims
    ax.scatter(points[:, i], points[:, j], s=2, alpha=0.5)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel(f"dim {i}")
    ax.set_ylabel(f"dim {j}")
    ax.set_aspect("equal")
    if title is not None:
        ax.set_title(title)
    return ax


def lag_scatter(
    samples: np.ndarray,
    lag: int = 1,
    ax: plt.Axes | None = None,
    title: str | None = None,
) -> plt.Axes:
    """Plot ``samples[k]`` against ``samples[k + lag]`` to visualise serial correlation.

    Parameters
    ----------
    samples
        ``float64`` 1-D array (higher-dim arrays are flattened first).
    lag
        Positive integer lag.
    ax
        Optional Matplotlib ``Axes`` to draw on.
    title
        Optional title for the axes.

    Returns
    -------
    matplotlib.axes.Axes
        The axes on which the scatter was drawn.
    """
    flat = np.asarray(samples).ravel()
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(flat[:-lag], flat[lag:], s=2, alpha=0.5)
    ax.set_xlabel("x[k]")
    ax.set_ylabel(f"x[k + {lag}]")
    ax.set_aspect("equal")
    if title is not None:
        ax.set_title(title)
    return ax


def projection_grid(
    points: np.ndarray,
    max_dim: int = 6,
    figsize: tuple[float, float] | None = None,
) -> plt.Figure:
    """Plot a grid of 2D projections of ``points`` to expose dimension-pair structure.

    This is the canonical diagnostic for Halton's high-dimensional failure
    mode: a clean grid means good equidistribution, visible stripes mean the
    sequence is degenerate on that coordinate pair.

    Parameters
    ----------
    points
        ``float64`` array of shape ``(n_points, n_dim)`` with ``n_dim >= max_dim``.
    max_dim
        Number of leading dimensions to include in the grid. The figure has
        ``max_dim`` rows and ``max_dim`` columns.
    figsize
        Optional figure size in inches; default scales linearly with ``max_dim``.

    Returns
    -------
    matplotlib.figure.Figure
        Figure containing the ``max_dim`` × ``max_dim`` grid of axes.
    """
    if figsize is None:
        figsize = (1.5 * max_dim, 1.5 * max_dim)
    fig, axes = plt.subplots(max_dim, max_dim, figsize=figsize)
    for i in range(max_dim):
        for j in range(max_dim):
            ax = axes[i, j]
            if i == j:
                ax.hist(points[:, i], bins=20, range=(0, 1), color="C0", alpha=0.7)
                ax.set_xlim(0, 1)
            else:
                ax.scatter(points[:, j], points[:, i], s=1, alpha=0.4)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
            ax.set_xticks([])
            ax.set_yticks([])
            if i == max_dim - 1:
                ax.set_xlabel(f"d{j}")
            if j == 0:
                ax.set_ylabel(f"d{i}")
    fig.tight_layout()
    return fig


def qq_normal(
    samples: np.ndarray,
    ax: plt.Axes | None = None,
    title: str | None = None,
) -> plt.Axes:
    """Quantile-quantile plot of ``samples`` against ``N(0, 1)``.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before plotting.
    ax
        Optional Matplotlib ``Axes`` to draw on.
    title
        Optional title.

    Returns
    -------
    matplotlib.axes.Axes
        The axes on which the Q-Q plot was drawn.
    """
    flat = np.sort(np.asarray(samples).ravel())
    n = flat.size
    theoretical = stats.norm.ppf((np.arange(1, n + 1) - 0.5) / n)
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(theoretical, flat, s=3, alpha=0.5)
    lo = min(theoretical.min(), flat.min())
    hi = max(theoretical.max(), flat.max())
    ax.plot([lo, hi], [lo, hi], color="C3", linewidth=1)
    ax.set_xlabel("theoretical N(0,1) quantile")
    ax.set_ylabel("sample quantile")
    if title is not None:
        ax.set_title(title)
    return ax


def marginal_histogram(
    samples: np.ndarray,
    theoretical: str = "uniform",
    ax: plt.Axes | None = None,
    bins: int = 60,
    title: str | None = None,
) -> plt.Axes:
    """Histogram of ``samples`` overlaid with the theoretical density.

    Parameters
    ----------
    samples
        ``float64`` array; flattened before plotting.
    theoretical
        Either ``"uniform"`` (overlays a horizontal line at density ``1``) or
        ``"normal"`` (overlays the ``N(0, 1)`` density).
    ax
        Optional Matplotlib ``Axes`` to draw on.
    bins
        Number of histogram bins.
    title
        Optional title.

    Returns
    -------
    matplotlib.axes.Axes
        The axes on which the histogram was drawn.

    Raises
    ------
    ValueError
        If ``theoretical`` is neither ``"uniform"`` nor ``"normal"``.
    """
    flat = np.asarray(samples).ravel()
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    ax.hist(flat, bins=bins, density=True, alpha=0.6)
    if theoretical == "uniform":
        ax.axhline(1.0, color="C3", linewidth=1)
        ax.set_xlim(0, 1)
    elif theoretical == "normal":
        grid = np.linspace(flat.min(), flat.max(), 400)
        ax.plot(grid, stats.norm.pdf(grid), color="C3", linewidth=1)
    else:
        raise ValueError(f"theoretical must be 'uniform' or 'normal'; got {theoretical}")
    ax.set_xlabel("value")
    ax.set_ylabel("density")
    if title is not None:
        ax.set_title(title)
    return ax


def convergence_plot(
    path_counts: np.ndarray,
    estimates: np.ndarray,
    benchmark: float,
    label: str = "estimate",
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Log-log plot of absolute MC error against path count.

    Parameters
    ----------
    path_counts
        ``int`` array of path counts (x-axis).
    estimates
        ``float`` array of MC estimates at each path count.
    benchmark
        Reference value to compare against.
    label
        Series label for the legend.
    ax
        Optional Matplotlib ``Axes`` to draw on.

    Returns
    -------
    matplotlib.axes.Axes
        The axes on which the convergence curve was drawn.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 5))
    err = np.abs(np.asarray(estimates) - benchmark)
    ax.loglog(path_counts, err, marker="o", label=label)
    ax.set_xlabel("paths")
    ax.set_ylabel("|estimate - benchmark|")
    ax.grid(True, which="both", linestyle=":", alpha=0.5)
    ax.legend()
    return ax
