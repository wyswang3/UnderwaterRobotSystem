# src/offnav/viz/dvl_processed.py

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 这里沿用你现在的导入方式：DvlProcessedData 是 dvl_processing.DvlEventsData 的别名
from offnav.preprocess.dvl_processing import DvlProcessedData
from offnav.viz.style import setup_mpl


def _get_time_s_from_df(df: pd.DataFrame) -> np.ndarray:
    """从 DVL DataFrame 里提取时间轴（秒）。"""
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


def save_dvl_filtered_velocity(
    dvl_proc: DvlProcessedData,
    out_dir: Path,
    run_id: Optional[str] = None,
    subset: str = "BI_BE",  # 仅为兼容旧调用，实际固定画 BI+BE
) -> Path:
    """
    绘制“滤波后的 DVL 速度”一张图、两个图窗：

      - 上图窗：BI 子集的 Vx/Vy/Vz (body)，标题居中 "BI (m/s)"
               legend 只标 Vx/Vy，突出水平速度；
      - 下图窗：BE 子集的速度曲线：
               若存在 Ve_enu/Vn_enu/Vu_enu，则用 ENU 速度；
               否则退回用 Vx_body/Vy_body/Vz_body。
               legend 只标第三条曲线（通常是垂向分量）。

      - 两个子图共享时间轴 (sharex=True)，X 轴标签仅在下图窗标 "Time (s)"。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or "run"

    # ★ 新版预处理输出字段名：df_bi / df_be
    df_bi = dvl_proc.df_bi
    df_be = dvl_proc.df_be

    if df_bi is None or df_bi.empty:
        raise ValueError("DVL subset 'BI' is empty, nothing to plot.")

    has_be = df_be is not None and (not df_be.empty)

    # ---------- BI: 使用 body 速度 ----------
    t_bi = _get_time_s_from_df(df_bi)
    vx_bi = df_bi["Vx_body(m_s)"].to_numpy(dtype=float)
    vy_bi = df_bi["Vy_body(m_s)"].to_numpy(dtype=float)
    vz_bi = df_bi["Vz_body(m_s)"].to_numpy(dtype=float)

    # ---------- BE: 优先使用 ENU 速度 ----------
    if has_be:
        t_be = _get_time_s_from_df(df_be)

        if {"Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"}.issubset(df_be.columns):
            # 当前实验：BE 写在 ENU 列
            vx_be = df_be["Ve_enu(m_s)"].to_numpy(dtype=float)
            vy_be = df_be["Vn_enu(m_s)"].to_numpy(dtype=float)
            vz_be = df_be["Vu_enu(m_s)"].to_numpy(dtype=float)
            be_title = "BE ENU velocity (m/s)"
            vz_label = "Vu (ENU)"
        else:
            # 兜底：如果将来 BE 也写在 body 列，就直接用 body
            vx_be = df_be["Vx_body(m_s)"].to_numpy(dtype=float)
            vy_be = df_be["Vy_body(m_s)"].to_numpy(dtype=float)
            vz_be = df_be["Vz_body(m_s)"].to_numpy(dtype=float)
            be_title = "BE body velocity (m/s)"
            vz_label = "Vz (body)"

    setup_mpl()

    if has_be:
        fig, axes = plt.subplots(2, 1, sharex=True, figsize=(4.7, 3.6))
        ax_bi, ax_be = axes[0], axes[1]
    else:
        fig, ax_single = plt.subplots(1, 1, figsize=(4.7, 2.0))
        ax_bi, ax_be = ax_single, None

    # -------- 图窗 1：BI (m/s) --------
    ax = ax_bi
    l1, = ax.plot(t_bi, vx_bi)
    l2, = ax.plot(t_bi, vy_bi)
    l3, = ax.plot(t_bi, vz_bi)  # Z 轴也画出来，但不进 legend
    ax.set_title("BI body velocity (m/s)", fontsize=10)

    leg = ax.legend(
        [l1, l2],
        ["Vx (body)", "Vy (body)"],
        loc="upper right",
        frameon=True,
        fontsize=8,
    )
    leg_frame = leg.get_frame()
    leg_frame.set_alpha(0.75)
    leg_frame.set_facecolor((1.0, 1.0, 1.0, 0.75))
    leg_frame.set_edgecolor("none")

    # 不显示上图窗 X 轴文字
    ax.tick_params(labelbottom=False)

    # -------- 图窗 2：BE (m/s) --------
    if has_be and ax_be is not None:
        ax = ax_be
        l1b, = ax.plot(t_be, vx_be)
        l2b, = ax.plot(t_be, vy_be)
        l3b, = ax.plot(t_be, vz_be)
        ax.set_title(be_title, fontsize=10)
        ax.set_xlabel("Time (s)")

        # 只标第三条曲线（通常为垂向分量）
        leg = ax.legend(
            [l3b],
            [vz_label],
            loc="upper right",
            frameon=True,
            fontsize=8,
        )
        leg_frame = leg.get_frame()
        leg_frame.set_alpha(0.75)
        leg_frame.set_facecolor((1.0, 1.0, 1.0, 0.75))
        leg_frame.set_edgecolor("none")
    else:
        # 没有 BE 时，把 X 轴标签放在 BI 图窗
        ax_bi.set_xlabel("Time (s)")

    fig.subplots_adjust(
        top=0.92,
        bottom=0.14,
        left=0.12,
        right=0.97,
        hspace=0.24,
    )

    out_path = out_dir / f"{rid}_dvl_filtered_velocity_BI_BE.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    return out_path
