# offline_nav/src/offnav/viz/traj_basic.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, List, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, AutoMinorLocator

from offnav.core.types import Trajectory
from offnav.viz.style import (
    setup_mpl,
    apply_axes_2d,
    plot_traj_line,
    plot_start_end,
    TrajStyle,
    get_figsize_two_panels,
)


# =========================
# Ticks / Save
# =========================

def _fine_ticks(ax: plt.Axes, *, xbins: int = 7, ybins: int = 7, minor: int = 2) -> None:
    """More readable ticks (major + minor), without overcrowding."""
    ax.xaxis.set_major_locator(MaxNLocator(nbins=xbins, prune="both"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=ybins, prune="both"))
    ax.xaxis.set_minor_locator(AutoMinorLocator(minor))
    ax.yaxis.set_minor_locator(AutoMinorLocator(minor))
    ax.tick_params(which="major", length=3.2, width=0.8)
    ax.tick_params(which="minor", length=1.8, width=0.6)

def _savefig(fig: plt.Figure, path: Path) -> None:
    """
    IMPORTANT:
    - Do NOT use bbox_inches="tight": it will change output canvas depending on content.
    - Keep fixed canvas ratio by saving the figure as-is.
    """
    fig.savefig(path, dpi=600)


# =========================
# Data utilities
# =========================

def _finite_mask3(e: np.ndarray, n: np.ndarray, u: np.ndarray) -> np.ndarray:
    return np.isfinite(e) & np.isfinite(n) & np.isfinite(u)

def _snap_small_to_zero(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x[np.abs(x) < eps] = 0.0
    return x

def _ensure_clean_series(
    traj: Trajectory,
    eps_zero: float = 1e-6
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Uniform cleaning:
    - to float
    - snap tiny residuals to 0
    - finite mask on (t, E, N, U)
    """
    t = np.asarray(traj.t_s, dtype=float)
    E = _snap_small_to_zero(np.asarray(traj.E, dtype=float), eps_zero)
    N = _snap_small_to_zero(np.asarray(traj.N, dtype=float), eps_zero)
    U = _snap_small_to_zero(np.asarray(traj.U, dtype=float), eps_zero)

    m = _finite_mask3(E, N, U) & np.isfinite(t)
    return t[m], E[m], N[m], U[m]


# =========================
# Axis range helpers (beauty-first)
# =========================

def _set_limits_with_pad(ax: plt.Axes, x: np.ndarray, y: np.ndarray, pad_ratio: float = 0.05) -> None:
    """Set x/y limits with padding based on data span."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mx = np.isfinite(x)
    my = np.isfinite(y)
    m = mx & my
    x = x[m]
    y = y[m]
    if x.size == 0:
        return
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    dx = xmax - xmin
    dy = ymax - ymin
    base = max(dx, dy, 1e-6)
    pad = pad_ratio * base
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)

def _set_y_limits_auto_robust(
    ax: plt.Axes,
    y: np.ndarray,
    pad_ratio: float = 0.06,
    min_span: float = 0.02,
) -> None:
    """Robust y auto-limits: handle near-constant series."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    if y.size == 0:
        return
    ymin = float(y.min())
    ymax = float(y.max())
    span = ymax - ymin
    if span < 1e-12:
        c = 0.5 * (ymin + ymax)
        half = 0.5 * max(min_span, abs(c) * pad_ratio)
        ax.set_ylim(c - half, c + half)
        return
    pad = pad_ratio * span
    ax.set_ylim(ymin - pad, ymax + pad)

def _soft_balance_limits(ax: plt.Axes, x: np.ndarray, y: np.ndarray, pad_ratio: float = 0.05, balance: float = 3.0) -> None:
    """
    Beauty-first axis limits:
    - still auto limits
    - but if dx:dy is extremely imbalanced, expand the smaller axis a bit,
      so the trajectory won't look overly skinny in a fixed-rectangle canvas.

    balance=3.0 means allow up to 1:3 or 3:1 before expanding.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]
    y = y[m]
    if x.size == 0:
        return

    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    dx = max(xmax - xmin, 1e-9)
    dy = max(ymax - ymin, 1e-9)

    # base padding
    base = max(dx, dy)
    pad = pad_ratio * base

    # expand the smaller axis if too imbalanced
    if dx / dy > balance:
        # x much larger: expand y
        target = dx / balance
        extra = 0.5 * max(target - dy, 0.0)
        ymin -= extra
        ymax += extra
        dy = ymax - ymin
    elif dy / dx > balance:
        # y much larger: expand x
        target = dy / balance
        extra = 0.5 * max(target - dx, 0.0)
        xmin -= extra
        xmax += extra
        dx = xmax - xmin

    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)

def _set_aspect_beauty(ax: plt.Axes) -> None:
    """
    Fixed canvas ratio, do NOT enforce equal data units.
    """
    ax.set_aspect("auto")


# =========================
# Figure A: Planar trajectory (E-N)
# =========================

def save_planar_en(
    traj: Trajectory,
    out_dir: Path,
    run_id: str,
    method_name: str,
    *,
    color: Optional[str] = None,
) -> Path:
    """
    E-N planar trajectory (beauty-first, fixed canvas ratio):
    - Trajectory line: thinner
    - Start: green filled circle
    - End: red filled square
    - Legend: Trajectory / Start / End (no method name)
    - Ticks: fine but not crowded
    - Aspect: auto (do not force equal units)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    method_safe = method_name.replace(" ", "_")
    out_path = out_dir / f"{run_id}_traj_en_{method_safe}.png"

    setup_mpl()
    t, E, N, U = _ensure_clean_series(traj)
    if E.size < 2:
        fig, ax = plt.subplots(1, 1, figsize=(4.7, 3.3), dpi=300, constrained_layout=True)
        apply_axes_2d(ax)
        ax.set_xlabel("East [m]")
        ax.set_ylabel("North [m]")
        _savefig(fig, out_path)
        plt.close(fig)
        return out_path

    if color is None:
        color = "#0072B2"  # trajectory line

    fig, ax = plt.subplots(1, 1, figsize=(4.7, 3.3), dpi=300, constrained_layout=True)
    fig.patch.set_facecolor("white")
    apply_axes_2d(ax)

    # trajectory line (no label)
    ax.plot(E, N, color=color, linewidth=0.95, alpha=0.95, zorder=2)

    # start / end markers (fixed semantics)
    ax.scatter(E[0], N[0], s=26, marker="o",
               facecolors="#2ca02c", edgecolors="#2ca02c",
               linewidths=0.0, zorder=4)
    ax.scatter(E[-1], N[-1], s=30, marker="s",
               facecolors="#d62728", edgecolors="#d62728",
               linewidths=0.0, zorder=4)

    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")

    # fixed canvas; beauty-first limits
    _set_aspect_beauty(ax)
    _soft_balance_limits(ax, E, N, pad_ratio=0.05, balance=3.0)

    # ticks
    _fine_ticks(ax, xbins=6, ybins=6, minor=2)

    # manual legend
    handles = [
        Line2D([0], [0], color=color, lw=0.95, label="Trajectory"),
        Line2D([0], [0], marker="o", linestyle="None",
               markerfacecolor="#2ca02c", markeredgecolor="#2ca02c",
               markersize=5.6, label="Start"),
        Line2D([0], [0], marker="s", linestyle="None",
               markerfacecolor="#d62728", markeredgecolor="#d62728",
               markersize=5.9, label="End"),
    ]
    ax.legend(handles=handles, loc="best", frameon=False, handlelength=2.0)

    _savefig(fig, out_path)
    plt.close(fig)
    return out_path


# =========================
# Figure B: Depth vs time (U-t)
# =========================

def save_depth_ut(
    traj: Trajectory,
    out_dir: Path,
    run_id: str,
    method_name: str,
    *,
    color: Optional[str] = None,
    depth_label: str = "Depth [m]",
) -> Path:
    """
    Depth(t), beauty-first:
    - Depth = -U (down positive)
    - single line, no legend
    - fixed canvas ratio
    - robust y auto limits
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    method_safe = method_name.replace(" ", "_")
    out_path = out_dir / f"{run_id}_depth_ut_{method_safe}.png"

    setup_mpl()
    t, E, N, U = _ensure_clean_series(traj)
    if t.size < 2:
        fig, ax = plt.subplots(1, 1, figsize=(4.7, 3.0), dpi=300, constrained_layout=True)
        apply_axes_2d(ax)
        ax.set_xlabel("Time [s]")
        ax.set_ylabel(depth_label)
        _savefig(fig, out_path)
        plt.close(fig)
        return out_path

    t_rel = t - float(t[0])
    depth = -U  # down positive

    if color is None:
        color = "#D55E00"

    fig, ax = plt.subplots(1, 1, figsize=(4.7, 3.0), dpi=300, constrained_layout=True)
    fig.patch.set_facecolor("white")
    apply_axes_2d(ax)

    ax.plot(t_rel, depth, color=color, linewidth=0.95, alpha=0.95, zorder=2)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel(depth_label)

    # fixed canvas; auto limits
    _set_aspect_beauty(ax)
    _set_limits_with_pad(ax, t_rel, depth, pad_ratio=0.04)  # mainly for xlim
    _set_y_limits_auto_robust(ax, depth, pad_ratio=0.08, min_span=0.02)

    # ticks: time axis can be slightly denser
    _fine_ticks(ax, xbins=7, ybins=7, minor=2)

    _savefig(fig, out_path)
    plt.close(fig)
    return out_path


# =========================
# Two-panels combined figure (E-N + Depth-t)
# =========================

def save_traj_and_depth_two_panels(
    traj: Trajectory,
    out_dir: Path,
    run_id: str,
    method_name: str,
    *,
    traj_color: Optional[str] = None,
    depth_color: Optional[str] = None,
    ts: TrajStyle = TrajStyle(),
) -> Path:
    """
    One figure, two panels: left EN, right Depth-t.
    Fixed canvas ratio (from get_figsize_two_panels).
    Legend:
      - left: Trajectory / Start / End
      - right: none
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    method_safe = method_name.replace(" ", "_")
    out_path = out_dir / f"{run_id}_traj_en_depth_ut_{method_safe}.png"

    setup_mpl()
    t, E, N, U = _ensure_clean_series(traj)
    if t.size < 2 or E.size < 2:
        fig, ax = plt.subplots(1, 1, figsize=(4.7, 3.3), dpi=300, constrained_layout=True)
        apply_axes_2d(ax)
        _savefig(fig, out_path)
        plt.close(fig)
        return out_path

    if traj_color is None:
        traj_color = "#0072B2"
    if depth_color is None:
        depth_color = "#D55E00"

    t_rel = t - float(t[0])
    depth = -U

    fig_w, fig_h = get_figsize_two_panels()
    fig, (ax_en, ax_dt) = plt.subplots(
        1, 2,
        figsize=(fig_w, fig_h),
        dpi=300,
        constrained_layout=True
    )
    fig.patch.set_facecolor("white")

    # --- left: EN ---
    apply_axes_2d(ax_en)
    ax_en.plot(E, N, color=traj_color, linewidth=0.95, alpha=0.95, zorder=2)
    ax_en.scatter(E[0], N[0], s=24, marker="o",
                  facecolors="#2ca02c", edgecolors="#2ca02c",
                  linewidths=0.0, zorder=4)
    ax_en.scatter(E[-1], N[-1], s=28, marker="s",
                  facecolors="#d62728", edgecolors="#d62728",
                  linewidths=0.0, zorder=4)

    ax_en.set_xlabel("East [m]")
    ax_en.set_ylabel("North [m]")
    _set_aspect_beauty(ax_en)
    _soft_balance_limits(ax_en, E, N, pad_ratio=0.05, balance=3.0)
    _fine_ticks(ax_en, xbins=6, ybins=6, minor=2)

    handles = [
        Line2D([0], [0], color=traj_color, lw=0.95, label="Trajectory"),
        Line2D([0], [0], marker="o", linestyle="None",
               markerfacecolor="#2ca02c", markeredgecolor="#2ca02c",
               markersize=5.4, label="Start"),
        Line2D([0], [0], marker="s", linestyle="None",
               markerfacecolor="#d62728", markeredgecolor="#d62728",
               markersize=5.7, label="End"),
    ]
    ax_en.legend(handles=handles, loc="best", frameon=False, handlelength=2.0)

    # --- right: Depth-t ---
    apply_axes_2d(ax_dt)
    ax_dt.plot(t_rel, depth, color=depth_color, linewidth=0.95, alpha=0.95, zorder=2)
    ax_dt.set_xlabel("Time [s]")
    ax_dt.set_ylabel("Depth [m]")
    _set_aspect_beauty(ax_dt)
    _set_limits_with_pad(ax_dt, t_rel, depth, pad_ratio=0.04)
    _set_y_limits_auto_robust(ax_dt, depth, pad_ratio=0.08, min_span=0.02)
    _fine_ticks(ax_dt, xbins=7, ybins=7, minor=2)

    _savefig(fig, out_path)
    plt.close(fig)
    return out_path


# =========================
# Multi-method comparison (E-N)
# =========================

def save_traj_compare_en(
    traj_map: Dict[str, Trajectory],
    out_dir: Path,
    run_id: str,
    method_order: Optional[Iterable[str]] = None,
    *,
    ts: TrajStyle = TrajStyle(),
) -> Path:
    """
    Multi-method EN comparison.
    - fixed canvas ratio
    - beauty-first limits
    - legend: methods only (no Start/End duplication)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}_traj_en_compare.png"

    if method_order is None:
        method_order = list(traj_map.keys())

    setup_mpl()

    fig, ax = plt.subplots(1, 1, figsize=(4.7, 3.3), dpi=300, constrained_layout=True)
    fig.patch.set_facecolor("white")
    apply_axes_2d(ax)

    all_E: List[np.ndarray] = []
    all_N: List[np.ndarray] = []

    plotted_any = False
    for name in method_order:
        if name not in traj_map:
            continue
        t, E, N, U = _ensure_clean_series(traj_map[name])
        if E.size < 2:
            continue

        (line,) = ax.plot(E, N, linewidth=0.95, alpha=0.90, label=name, zorder=2)

        c = line.get_color()
        ax.scatter(E[0], N[0], s=18, marker="o",
                   facecolors="white", edgecolors=c, linewidths=0.9, zorder=3)
        ax.scatter(E[-1], N[-1], s=20, marker="o",
                   facecolors=c, edgecolors=c, linewidths=0.9, zorder=3)

        all_E.append(E)
        all_N.append(N)
        plotted_any = True

    if not plotted_any:
        _savefig(fig, out_path)
        plt.close(fig)
        return out_path

    E_cat = np.concatenate(all_E)
    N_cat = np.concatenate(all_N)

    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")

    _set_aspect_beauty(ax)
    _soft_balance_limits(ax, E_cat, N_cat, pad_ratio=0.05, balance=3.0)
    _fine_ticks(ax, xbins=6, ybins=6, minor=2)

    ax.legend(loc="best", frameon=False)

    _savefig(fig, out_path)
    plt.close(fig)
    return out_path


# =========================
# Backward-compatible names
# =========================

def save_traj_3d_single(
    traj: Trajectory,
    out_dir: Path,
    run_id: str,
    method_name: str,
    color: Optional[str] = None,
) -> Path:
    return save_planar_en(traj, out_dir, run_id, method_name, color=color)

def save_traj_3d_multi(
    traj_map: Dict[str, Trajectory],
    out_dir: Path,
    run_id: str,
    method_order: Optional[Iterable[str]] = None,
) -> Path:
    return save_traj_compare_en(traj_map, out_dir, run_id, method_order=method_order)
