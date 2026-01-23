# src/offnav/viz/raw_dvl.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

from offnav.core.types import DvlRawData
from offnav.viz.style import setup_mpl, apply_axes_2d


def _get_time_s_from_dvl(dvl: DvlRawData) -> np.ndarray:
    df = dvl.df
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    elif "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    elif "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    elif "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    else:
        raise KeyError("DVL df has no EstS/MonoS/EstNS/MonoNS time column.")


def _finite_xy(t: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(t) & np.isfinite(y)
    return t[m], y[m]


def _set_y_limits_auto(ax: plt.Axes, y: np.ndarray, pad_ratio: float = 0.08) -> None:
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    if y.size == 0:
        return
    ymin = float(y.min())
    ymax = float(y.max())
    r = ymax - ymin
    pad = pad_ratio * max(r, 1e-6)
    ax.set_ylim(ymin - pad, ymax + pad)


def _set_locators(ax: plt.Axes, *, xbins: int = 6, ybins: int = 5) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(nbins=xbins, prune="both"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=ybins, prune="both"))


def save_dvl_raw_velocity(
    dvl: DvlRawData,
    out_dir: Path,
    run_id: Optional[str] = None,
) -> Path:
    """
    DVL 原始体坐标速度：三个子窗（Vx/Vy/Vz），共享 x 轴刻度。
    每个子窗一个小 legend；y 轴范围各自自适应，但刻度密度一致；
    y 轴标签由 figure 统一给出（fig.supylabel）。

    Output:
      <run_id>_dvl_raw_body_velocity.png
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or "run"

    df = dvl.df
    t_s = _get_time_s_from_dvl(dvl)

    # 列名保护：尽量早失败
    cols = ["Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"]
    for c in cols:
        if c not in df.columns:
            raise KeyError(f"DVL df missing column: {c}")

    setup_mpl()

    # 更适合 3 子窗的版式（单栏友好）
    fig, axes = plt.subplots(
        3, 1,
        sharex=True,
        figsize=(4.7, 3.8),
        dpi=300,
    )
    fig.patch.set_facecolor("white")

    # 固定语义配色：x=蓝，y=红，z=绿（跨所有图一致）
    series = [
        ("Vx", df[cols[0]].to_numpy(dtype=float), "#1f77b4"),  # blue
        ("Vy", df[cols[1]].to_numpy(dtype=float), "#d62728"),  # red
        ("Vz", df[cols[2]].to_numpy(dtype=float), "#2ca02c"),  # green
    ]

    for i, (name, y, c) in enumerate(series):
        ax = axes[i]
        apply_axes_2d(ax)

        t, yy = _finite_xy(t_s, y)
        ax.plot(t, yy, label=name, color=c, zorder=2)

        _set_y_limits_auto(ax, yy, pad_ratio=0.08)
        _set_locators(ax, xbins=6, ybins=5)

        # 每个子窗一个 legend：极简、无边框（由 style.py 全局控制）
        ax.legend(loc="upper right")

        if i < 2:
            ax.set_xlabel("")
        else:
            ax.set_xlabel("Time [s]")

    # 统一 y 轴标签（共享）
    fig.supylabel("Body velocity [m/s]")

    # 小幅压缩空白：让子窗更紧凑但不拥挤
    fig.tight_layout(pad=0.4)

    out_path = out_dir / f"{rid}_dvl_raw_body_velocity.png"
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
