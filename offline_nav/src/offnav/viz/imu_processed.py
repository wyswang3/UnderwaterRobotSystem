from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from offnav.preprocess.imu_processing import ImuProcessedData
from offnav.viz.style import setup_mpl


# =============================================================================
# Layout (anchored) + visual policy
# =============================================================================

@dataclass(frozen=True)
class ImuPlotLayout:
    """
    Anchored layout for consistent, publication-friendly figures.
    - Fixed canvas size (inch) and DPI
    - Fixed margins and subplot spacing
    - Adaptive typography/ticks derived from canvas size (not data length)
    - Enforced y-axis major ticks to 3 (stable readability)
    """
    # canvas (fixed)
    fig_w_in: float = 5.0
    fig_h_in: float = 4.8
    dpi: int = 450

    # margins (fixed)
    left: float = 0.12
    right: float = 0.98
    bottom: float = 0.14
    top: float = 0.93

    # spacing (fixed)
    hspace: float = 0.26

    # tick policy
    x_nbins: int = 6
    y_nticks: int = 3
    y_pad_frac: float = 0.03

    # legend styling
    legend_alpha: float = 0.75
    legend_face_rgba: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 0.75)

    # typography scale reference
    ref_in: float = 5.0

    def scale(self) -> float:
        return min(self.fig_w_in, self.fig_h_in) / self.ref_in

    def title_fs(self) -> float:
        return 10.0 * self.scale()

    def label_fs(self) -> float:
        return 9.0 * self.scale()

    def tick_fs(self) -> float:
        return 8.0 * self.scale()

    def legend_fs(self) -> float:
        return 8.0 * self.scale()

    def lw(self) -> float:
        return 1.1 * self.scale()

    def tick_len_major(self) -> float:
        return 3.2 * self.scale()

    def tick_len_minor(self) -> float:
        return 2.0 * self.scale()

    def tick_w_major(self) -> float:
        return 0.8 * self.scale()

    def tick_w_minor(self) -> float:
        return 0.6 * self.scale()


def _apply_legend_style(leg, alpha: float, face_rgba: Tuple[float, float, float, float]) -> None:
    if leg is None:
        return
    fr = leg.get_frame()
    fr.set_alpha(alpha)
    fr.set_facecolor(face_rgba)
    fr.set_edgecolor("none")

def _set_y_ticks_pretty_3(ax: plt.Axes, y_pad_frac: float) -> None:
    """
    Prefer "nice" ticks (round numbers) close to 3 ticks.
    Fallback to 25/50/75 axis positions if locator degenerates.

    Outcome: typically 3 major ticks, visually pleasing and robust.
    """
    # 1) autoscale y
    ax.relim()
    ax.autoscale(enable=True, axis="y", tight=False)

    y0, y1 = ax.get_ylim()
    if not (np.isfinite(y0) and np.isfinite(y1)):
        return

    span = float(y1 - y0)
    if span == 0.0:
        eps = 1e-6 if y0 == 0.0 else abs(y0) * 1e-3
        y0, y1 = y0 - eps, y1 + eps
        span = float(y1 - y0)

    # 2) padding (avoid edge-dominated / degenerate)
    pad = abs(span) * float(y_pad_frac)
    ax.set_ylim(y0 - pad, y1 + pad)
    y0, y1 = ax.get_ylim()

    # 3) try "nice" ticks
    # MaxNLocator with prune can avoid placing ticks exactly at bounds sometimes.
    locator = mticker.MaxNLocator(nbins=3, min_n_ticks=3, steps=[1, 2, 2.5, 5, 10])
    ax.yaxis.set_major_locator(locator)

    ticks = ax.get_yticks()
    ticks = ticks[np.isfinite(ticks)]

    # Keep ticks within current view
    ticks_in = ticks[(ticks >= y0 - 1e-12) & (ticks <= y1 + 1e-12)]

    # If locator didn't give us a reasonable 3-tick set, fallback to 25/50/75
    if len(ticks_in) < 3:
        pos = np.array([0.25, 0.5, 0.75], dtype=float)
        ax.set_yticks(y0 + (y1 - y0) * pos)
        return

    # If locator gives more than 3, pick the most central 3 (avoid clutter)
    if len(ticks_in) > 3:
        mid = 0.5 * (y0 + y1)
        order = np.argsort(np.abs(ticks_in - mid))
        sel = np.sort(ticks_in[order[:3]])
        ax.set_yticks(sel)
        return

    # Else keep ticks_in as-is (3 ticks)
    ax.set_yticks(ticks_in[:3])

def _extract_yaw_series(imu_proc: ImuProcessedData, n: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns (yaw_before_rad, yaw_after_rad), each shape (n,).
      - before: yaw_device_rad if available else zeros
      - after : angle_est_rad[:,2] else angle_rad[:,2] else zeros
    """
    yaw_before = None
    if imu_proc.yaw_device_rad is not None:
        yaw_before = np.asarray(imu_proc.yaw_device_rad).reshape(-1)

    yaw_after = None
    if imu_proc.angle_est_rad is not None:
        a = np.asarray(imu_proc.angle_est_rad)
        if a.ndim == 2 and a.shape[0] == n and a.shape[1] == 3:
            yaw_after = a[:, 2]

    if yaw_after is None and imu_proc.angle_rad is not None:
        a = np.asarray(imu_proc.angle_rad)
        if a.ndim == 2 and a.shape[0] == n and a.shape[1] == 3:
            yaw_after = a[:, 2]

    if yaw_before is None:
        yaw_before = np.zeros((n,), dtype=float)
    if yaw_after is None:
        yaw_after = np.zeros((n,), dtype=float)

    if yaw_before.shape[0] != n:
        nn = min(n, yaw_before.shape[0])
        yaw_before = yaw_before[:nn]
        yaw_after = yaw_after[:nn] if yaw_after.shape[0] >= nn else np.pad(
            yaw_after, (0, nn - yaw_after.shape[0]), mode="edge"
        )
    return yaw_before, yaw_after


def save_imu_filtered_9axis(
    imu_proc: ImuProcessedData,
    out_dir: Path,
    run_id: Optional[str] = None,
) -> Path:
    """
    IMU processed plots (3 rows):

      Row 1: Acceleration (m/s^2) - X/Y/Z
      Row 2: Angular rate (rad/s) - X/Y/Z
      Row 3: Yaw angle (deg) - before vs after

    Visual policy:
      - Titles do NOT repeat "X/Y/Z"; titles include units only.
      - Fixed canvas size / margins / spacing (anchored composition).
      - Typography & tick sizes adapt to canvas size.
      - Only bottom subplot shows x tick labels (sharex).
      - Colors: X=C0, Y=C1, Z=C2; legend semi-transparent.
      - y-axis major ticks enforced to 3 for readability.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or "run"

    # -----------------------------
    # Validate core arrays
    # -----------------------------
    t_s = np.asarray(imu_proc.t_s).reshape(-1)
    acc = np.asarray(imu_proc.acc_mps2)
    gyro = np.asarray(imu_proc.gyro_out_rad_s)

    if acc.ndim != 2 or acc.shape[1] != 3:
        raise ValueError(f"acc_mps2 must be (N,3), got {acc.shape}")
    if gyro.ndim != 2 or gyro.shape[1] != 3:
        raise ValueError(f"gyro_out_rad_s must be (N,3), got {gyro.shape}")

    n = len(t_s)
    if acc.shape[0] != n or gyro.shape[0] != n:
        raise ValueError(f"length mismatch: t_s={n}, acc={acc.shape[0]}, gyro={gyro.shape[0]}")

    yaw_before_rad, yaw_after_rad = _extract_yaw_series(imu_proc, n)

    if yaw_before_rad.shape[0] != n:
        n2 = yaw_before_rad.shape[0]
        t_s = t_s[:n2]
        acc = acc[:n2, :]
        gyro = gyro[:n2, :]
        yaw_after_rad = yaw_after_rad[:n2]
        n = n2

    # -----------------------------
    # Anchored layout + adaptive visuals
    # -----------------------------
    setup_mpl()
    layout = ImuPlotLayout()
    lw = layout.lw()

    fig, axes = plt.subplots(
        3, 1, sharex=True,
        figsize=(layout.fig_w_in, layout.fig_h_in),
        dpi=layout.dpi,
        gridspec_kw={"hspace": layout.hspace},
    )

    # x ticks: stable density (avoid crowding)
    x_locator = mticker.MaxNLocator(nbins=layout.x_nbins)

    for i, ax in enumerate(axes):
        ax.xaxis.set_major_locator(x_locator)

        ax.tick_params(
            axis="both",
            which="major",
            labelsize=layout.tick_fs(),
            width=layout.tick_w_major(),
            length=layout.tick_len_major(),
        )
        ax.tick_params(
            axis="both",
            which="minor",
            labelsize=layout.tick_fs(),
            width=layout.tick_w_minor(),
            length=layout.tick_len_minor(),
        )

        if i < 2:
            ax.tick_params(axis="x", which="both", labelbottom=False)

    # -----------------------------
    # Row 1: Acc (m/s^2)
    # -----------------------------
    ax = axes[0]
    l1, = ax.plot(t_s, acc[:, 0], linewidth=lw, color="C0")
    l2, = ax.plot(t_s, acc[:, 1], linewidth=lw, color="C1")
    l3, = ax.plot(t_s, acc[:, 2], linewidth=lw, color="C2")
    ax.set_title("Acceleration (m/s$^2$)", fontsize=layout.title_fs())

    leg = ax.legend(
        [l1, l2, l3],
        ["X axis", "Y axis", "Z axis"],
        loc="upper right",
        frameon=True,
        fontsize=layout.legend_fs(),
    )
    _apply_legend_style(leg, layout.legend_alpha, layout.legend_face_rgba)
    _set_y_ticks_pretty_3(ax, layout.y_pad_frac)

    # -----------------------------
    # Row 2: Gyro (rad/s)
    # -----------------------------
    ax = axes[1]
    l1, = ax.plot(t_s, gyro[:, 0], linewidth=lw, color="C0")
    l2, = ax.plot(t_s, gyro[:, 1], linewidth=lw, color="C1")
    l3, = ax.plot(t_s, gyro[:, 2], linewidth=lw, color="C2")
    ax.set_title("Angular rate (rad/s)", fontsize=layout.title_fs())

    leg = ax.legend(
        [l1, l2, l3],
        ["X axis", "Y axis", "Z axis"],
        loc="upper right",
        frameon=True,
        fontsize=layout.legend_fs(),
    )
    _apply_legend_style(leg, layout.legend_alpha, layout.legend_face_rgba)
    _set_y_ticks_pretty_3(ax, layout.y_pad_frac)

    # -----------------------------
    # Row 3: Yaw (deg) — before vs after
    # -----------------------------
    ax = axes[2]
    yb = np.rad2deg(yaw_before_rad[:n])
    ya = np.rad2deg(yaw_after_rad[:n])

    lb, = ax.plot(t_s, yb, linestyle="--", alpha=0.75, linewidth=lw, color="C0")
    la, = ax.plot(t_s, ya, linestyle="-",  alpha=0.90, linewidth=lw, color="C3")

    ax.set_title("Yaw angle (deg)", fontsize=layout.title_fs())
    ax.set_xlabel("Time (s)", fontsize=layout.label_fs())

    leg = ax.legend(
        [lb, la],
        ["Yaw (before)", "Yaw (after)"],
        loc="upper right",
        frameon=True,
        fontsize=layout.legend_fs(),
    )
    _apply_legend_style(leg, layout.legend_alpha, layout.legend_face_rgba)
    _set_y_ticks_pretty_3(ax, layout.y_pad_frac)

    # -----------------------------
    # Margins (anchored)
    # -----------------------------
    fig.subplots_adjust(
        left=layout.left,
        right=layout.right,
        bottom=layout.bottom,
        top=layout.top,
    )

    out_path = out_dir / f"{rid}_imu_filtered_9axis.png"
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
