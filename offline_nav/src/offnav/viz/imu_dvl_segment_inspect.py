#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
offnav.viz.imu_dvl_segment_inspect

目的：
  在一个给定时间窗口内（默认 500~600 s）做一个极简诊断：

  1) 从 IMU 预处理 CSV 中取 AccX/AccY + yaw_nav_rad，
     在仅考虑 yaw 的前提下把加速度投影到 ENU 平面，并积分得到 vE_IMU / vN_IMU；
  2) 从 DVL BE CSV 中取 Ve_enu/Vn_enu，插值到 IMU 时间轴，得到 vE_DVL / vN_DVL；
  3) 比较两者的速度曲线、速度模长，以及 yaw_IMU vs yaw_DVL；

  这一步完全绕过 ESKF，只看 IMU+RPY 预处理和 DVL 数据本身，
  帮助定位「轨迹偏大」到底是 IMU 积分的问题，还是 DVL/坐标变换的问题。

使用示例（在 offline_nav/src 目录下）：
  python -m offnav.viz.imu_dvl_segment_inspect \
    --imu-csv ../out/proc/2026-01-10_pooltest01/2026-01-10_pooltest01_imu_filtered.csv \
    --dvl-be-csv ../out/proc/2026-01-10_pooltest01/2026-01-10_pooltest01_dvl_BE.csv \
    --t-min 500 --t-max 600

如果不传 --t-min / --t-max，默认使用 [500, 600] 秒。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------

_TIME_COL_CANDS = ("t_s", "EstS", "MonoS", "time_s", "Time", "time")


def _pick_time_s(df: pd.DataFrame, label: str) -> np.ndarray:
    """从若干候选列中选择时间列，并返回 float 型数组（秒）"""
    for c in _TIME_COL_CANDS:
        if c in df.columns:
            t = df[c].to_numpy(dtype=float)
            print(f"[TIME][{label}] 使用时间列: {c}, t=[{t[0]:.3f}, {t[-1]:.3f}], N={len(t)}")
            return t
    raise RuntimeError(f"[TIME][{label}] 找不到合适的时间列，请检查 CSV 表头。")


def _wrap_pm_pi(a: np.ndarray) -> np.ndarray:
    """把角度（rad）wrap 到 [-pi, pi]"""
    return (a + np.pi) % (2.0 * np.pi) - np.pi


# ----------------------------------------------------------------------
# 主逻辑
# ----------------------------------------------------------------------

def analyze_segment(
    imu_csv: Path,
    dvl_be_csv: Path,
    t_min: float,
    t_max: float,
) -> None:
    print(f"[SEG-ARGS] IMU CSV   : {imu_csv}")
    print(f"[SEG-ARGS] DVL BE CSV: {dvl_be_csv}")
    print(f"[SEG-ARGS] t_range   : [{t_min:.1f}, {t_max:.1f}] s")

    df_imu = pd.read_csv(imu_csv)
    df_be = pd.read_csv(dvl_be_csv)

    # 1) 取时间轴
    t_imu = _pick_time_s(df_imu, "IMU")
    t_be = _pick_time_s(df_be, "DVL-BE")

    # 2) 截取时间窗口
    mask_imu = (t_imu >= t_min) & (t_imu <= t_max)
    mask_be = (t_be >= t_min) & (t_be <= t_max)

    if np.count_nonzero(mask_imu) < 10 or np.count_nonzero(mask_be) < 10:
        print(
            f"[SEG][WARN] 在区间 [{t_min:.1f}, {t_max:.1f}] 内数据太少："
            f"IMU N={np.count_nonzero(mask_imu)}, DVL-BE N={np.count_nonzero(mask_be)}"
        )

    t_imu_seg = t_imu[mask_imu]
    t_be_seg = t_be[mask_be]

    print(
        f"[SEG] IMU seg: t=[{t_imu_seg[0]:.3f}, {t_imu_seg[-1]:.3f}], N={len(t_imu_seg)}"
    )
    print(
        f"[SEG] DVL seg: t=[{t_be_seg[0]:.3f}, {t_be_seg[-1]:.3f}], N={len(t_be_seg)}"
    )

    # 3) 取 IMU 加速度 & yaw（这里约定使用 yaw_nav_rad）
    required_imu_cols = ("AccX_mps2", "AccY_mps2", "yaw_nav_rad")
    for c in required_imu_cols:
        if c not in df_imu.columns:
            raise RuntimeError(f"[SEG][IMU] 缺少列: {c}")

    accX = df_imu.loc[mask_imu, "AccX_mps2"].to_numpy(dtype=float)
    accY = df_imu.loc[mask_imu, "AccY_mps2"].to_numpy(dtype=float)
    yaw_imu = df_imu.loc[mask_imu, "yaw_nav_rad"].to_numpy(dtype=float)
    yaw_imu = _wrap_pm_pi(yaw_imu)

    # 4) 取 DVL BE 水平速度
    be_cols = ("Ve_enu(m_s)", "Vn_enu(m_s)")
    for c in be_cols:
        if c not in df_be.columns:
            raise RuntimeError(f"[SEG][DVL-BE] 缺少列: {c}")

    Ve_be = df_be.loc[mask_be, be_cols[0]].to_numpy(dtype=float)
    Vn_be = df_be.loc[mask_be, be_cols[1]].to_numpy(dtype=float)

    # 5) 在 IMU 时间轴上插值 DVL 速度
    Ve_be_i = np.interp(t_imu_seg, t_be_seg, Ve_be)
    Vn_be_i = np.interp(t_imu_seg, t_be_seg, Vn_be)

     # 6) 用「仅考虑 yaw」的简化模型，把 IMU body 加速度转换到 EN 平面并积分
    #    假设：X 前、Y 右，忽略 roll/pitch 对水平面的影响，只看 yaw。
    #    aE =  ax*cos(yaw) - ay*sin(yaw)
    #    aN =  ax*sin(yaw) + ay*cos(yaw)
    aE = accX * np.cos(yaw_imu) - accY * np.sin(yaw_imu)
    aN = accX * np.sin(yaw_imu) + accY * np.cos(yaw_imu)

    # --- 数值积分得到 IMU 在 EN 平面的速度 ---
    vE_imu = np.zeros_like(aE)
    vN_imu = np.zeros_like(aN)

    for i in range(1, len(t_imu_seg)):
        dt_i = float(t_imu_seg[i] - t_imu_seg[i - 1])
        # 防御：dt 不能为负/零，也不能太大（>50 ms 当作异常跳变）
        if not np.isfinite(dt_i) or dt_i <= 0.0 or dt_i > 0.05:
            # 异常时间步：直接继承上一时刻速度
            vE_imu[i] = vE_imu[i - 1]
            vN_imu[i] = vN_imu[i - 1]
            continue

        vE_imu[i] = vE_imu[i - 1] + aE[i - 1] * dt_i
        vN_imu[i] = vN_imu[i - 1] + aN[i - 1] * dt_i

    speed_imu = np.hypot(vE_imu, vN_imu)
    speed_be_i = np.hypot(Ve_be_i, Vn_be_i)

    # --- 利用速度变化估算“平均多出来的加速度”与等效倾角误差 ---
    dt_total = float(t_imu_seg[-1] - t_imu_seg[0])
    if dt_total > 0.0:
        dvE_imu = float(vE_imu[-1] - vE_imu[0])
        dvN_imu = float(vN_imu[-1] - vN_imu[0])

        mean_aE_imu = dvE_imu / dt_total
        mean_aN_imu = dvN_imu / dt_total
        mean_aH = float(np.hypot(mean_aE_imu, mean_aN_imu))

        tilt_err_rad = np.arcsin(np.clip(mean_aH / 9.78, -1.0, 1.0))
        tilt_err_deg = float(np.rad2deg(tilt_err_rad))

        print(f"[SEG][ACC] mean aE_imu = {mean_aE_imu:.4f} m/s^2")
        print(f"[SEG][ACC] mean aN_imu = {mean_aN_imu:.4f} m/s^2")
        print(f"[SEG][ACC] mean aH_imu = {mean_aH:.4f} m/s^2")
        print(f"[SEG][TILT] equivalent tilt error ≈ {tilt_err_deg:.2f} deg (if from gravity leakage)")
    else:
        print("[SEG][ACC] dt_total <= 0, skip tilt estimation")

    # 7) 计算 DVL yaw，并与 IMU yaw 比较
    yaw_dvl = np.arctan2(Vn_be_i, Ve_be_i)
    dyaw = _wrap_pm_pi(yaw_imu - yaw_dvl)
    yaw_imu_deg = np.rad2deg(yaw_imu)
    yaw_dvl_deg = np.rad2deg(yaw_dvl)
    dyaw_deg = np.rad2deg(dyaw)

    # 统计信息
    finite_mask = np.isfinite(speed_be_i) & np.isfinite(speed_imu)
    if np.count_nonzero(finite_mask) > 10:
        corr_vE = np.corrcoef(vE_imu[finite_mask], Ve_be_i[finite_mask])[0, 1]
        corr_vN = np.corrcoef(vN_imu[finite_mask], Vn_be_i[finite_mask])[0, 1]
        ratio = speed_imu[finite_mask] / np.maximum(speed_be_i[finite_mask], 1e-6)

        print("\n[SEG][STATS] 速度相关性 / 尺度：")
        print(f"  corr(vE_imu, vE_dvl) = {corr_vE: .3f}")
        print(f"  corr(vN_imu, vN_dvl) = {corr_vN: .3f}")
        print(
            "  |v_imu|/|v_dvl|: "
            f"mean={np.mean(ratio):.3f}, p50={np.percentile(ratio,50):.3f}, "
            f"p90={np.percentile(ratio,90):.3f}, p95={np.percentile(ratio,95):.3f}"
        )

    if np.any(np.isfinite(dyaw_deg)):
        d = dyaw_deg[np.isfinite(dyaw_deg)]
        print("\n[SEG][STATS] yaw_imu - yaw_dvl 分布：")
        print(
            f"  mean={np.mean(d): .3f} deg, std={np.std(d): .3f} deg, "
            f"p50={np.percentile(d,50): .2f}, p90={np.percentile(d,90): .2f}, "
            f"p95={np.percentile(d,95): .2f}"
        )

    # 8) 画图
    t0 = t_imu_seg[0]
    t_rel = t_imu_seg - t0

    out_dir = imu_csv.parent.parent / "plots_seg"
    out_dir.mkdir(parents=True, exist_ok=True)

    # (1) 速度对比
    fig1, ax1 = plt.subplots(3, 1, sharex=True, figsize=(12, 9))
    fig1.suptitle(f"IMU vs DVL velocities (t=[{t_min},{t_max}] s)")

    ax1[0].plot(t_rel, vE_imu, label="vE_imu (integrated)")
    ax1[0].plot(t_rel, Ve_be_i, label="vE_dvl (BE interp)", linestyle="--")
    ax1[0].set_ylabel("vE [m/s]")
    ax1[0].legend()
    ax1[0].grid(True)

    ax1[1].plot(t_rel, vN_imu, label="vN_imu (integrated)")
    ax1[1].plot(t_rel, Vn_be_i, label="vN_dvl (BE interp)", linestyle="--")
    ax1[1].set_ylabel("vN [m/s]")
    ax1[1].legend()
    ax1[1].grid(True)

    ax1[2].plot(t_rel, speed_imu, label="|v_imu|")
    ax1[2].plot(t_rel, speed_be_i, label="|v_dvl|", linestyle="--")
    ax1[2].set_ylabel("|v| [m/s]")
    ax1[2].set_xlabel("time since segment start [s]")
    ax1[2].legend()
    ax1[2].grid(True)

    fig1.tight_layout()
    f1_path = out_dir / f"imu_dvl_vel_seg_{int(t_min)}_{int(t_max)}.png"
    fig1.savefig(f1_path, dpi=150)
    plt.close(fig1)
    print(f"[SEG][FIG] 速度对比图已保存: {f1_path}")

    # (2) yaw & dyaw
    fig2, ax2 = plt.subplots(2, 1, sharex=True, figsize=(12, 8))
    fig2.suptitle(f"IMU yaw vs DVL yaw (t=[{t_min},{t_max}] s)")

    ax2[0].plot(t_rel, yaw_imu_deg, label="yaw_imu (yaw_nav_rad)")
    ax2[0].plot(t_rel, yaw_dvl_deg, label="yaw_dvl_from_BE", linestyle="--")
    ax2[0].set_ylabel("yaw [deg]")
    ax2[0].legend()
    ax2[0].grid(True)

    ax2[1].plot(t_rel, dyaw_deg, label="dyaw = yaw_imu - yaw_dvl")
    ax2[1].axhline(0.0, color="k", linestyle="--", linewidth=0.8)
    ax2[1].set_ylabel("dyaw [deg]")
    ax2[1].set_xlabel("time since segment start [s]")
    ax2[1].legend()
    ax2[1].grid(True)

    fig2.tight_layout()
    f2_path = out_dir / f"imu_dvl_yaw_seg_{int(t_min)}_{int(t_max)}.png"
    fig2.savefig(f2_path, dpi=150)
    plt.close(fig2)
    print(f"[SEG][FIG] yaw 对比图已保存: {f2_path}")

    print("\n[SEG] Done. 请结合两张图 + 上面打印的相关性/比例，判断：")
    print("      - 是 IMU 积分速度整体偏大，还是 DVL 速度偏小；")
    print("      - yaw_imu 与 yaw_dvl 在这 100 秒内是否存在稳定偏角或剧烈抖动。")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="IMU vs DVL segment-level diagnostic (pure sensors, no ESKF)."
    )
    parser.add_argument("--imu-csv", type=Path, required=True)
    parser.add_argument("--dvl-be-csv", type=Path, required=True)
    parser.add_argument("--t-min", type=float, default=500.0)
    parser.add_argument("--t-max", type=float, default=600.0)
    args = parser.parse_args()

    analyze_segment(args.imu_csv, args.dvl_be_csv, args.t_min, args.t_max)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
