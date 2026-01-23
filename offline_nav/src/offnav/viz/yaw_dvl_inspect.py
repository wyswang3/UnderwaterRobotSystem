#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
offnav.viz.yaw_dvl_inspect

用途：
  - 纯传感器层面，检查 & 可视化：
      yaw_imu_candidate(t)   vs   yaw_dvl(t) = atan2(Vn, Ve)
  - 帮助从多个 IMU yaw 列中，挑选“最可信”的 yaw 观测源。

输入：
  - 预处理后的 IMU CSV（例如 imu_filtered.csv）
  - 预处理后的 DVL BE CSV（例如 dvl_BE.csv）

输出：
  - 终端统计信息：每个 yaw 候选的 dyaw 分布（均值/方差/分位数）
  - 两张图：
      1) yaw_vs_time: yaw_dvl 与各个 yaw_imu 候选随时间变化
      2) dyaw_vs_time: 每个候选的 dyaw = wrap(yaw_imu - yaw_dvl) 随时间变化

用法示例（在 src 目录下）：
  python -m offnav.viz.yaw_dvl_inspect \
      --imu-csv ../out/proc/2026-01-10_pooltest01/2026-01-10_pooltest01_imu_filtered.csv \
      --dvl-be-csv ../out/proc/2026-01-10_pooltest01/2026-01-10_pooltest01_dvl_BE.csv \
      --speed-min 0.10
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# 小工具：时间列 / DVL 列 / yaw 处理
# ----------------------------------------------------------------------

_TIME_COL_CANDS = (
    "t_s",    # IMU 预处理后的时间列
    "Time_s",
    "EstS",   # DVL 预处理后的时间列
    "MonoS",
    "time",
    "t",
)


def _pick_time_s(df: pd.DataFrame, label: str) -> np.ndarray:
    """
    从若干候选列中挑一个时间列，转成 float seconds.
    """
    for c in _TIME_COL_CANDS:
        if c in df.columns:
            t = df[c].to_numpy(dtype=float)
            print(f"[TIME][{label}] 使用时间列: {c}, t=[{np.nanmin(t):.3f}, {np.nanmax(t):.3f}], N={len(t)}")
            return t
    raise RuntimeError(f"[TIME][{label}] 找不到时间列，当前列名: {list(df.columns)}")


def _extract_be_vel_enu(df_be: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    从 DVL BE CSV 中提取 ENU 速度 (Ve,Vn,Vu).
    针对当前你的列名：Ve_enu(m_s), Vn_enu(m_s), Vu_enu(m_s)
    如后续列名变了，可以在这里补充候选组合。
    """
    cand_sets = [
        ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"),
        ("Ve", "Vn", "Vu"),
        ("Ve(m_s)", "Vn(m_s)", "Vu(m_s)"),
    ]
    for cols in cand_sets:
        if all(c in df_be.columns for c in cols):
            Ve = df_be[cols[0]].to_numpy(dtype=float)
            Vn = df_be[cols[1]].to_numpy(dtype=float)
            Vu = df_be[cols[2]].to_numpy(dtype=float)
            print(f"[DVL-BE] 使用速度列: {cols}")
            return Ve, Vn, Vu

    print("[DVL-BE][ERROR] 找不到 ENU 速度列，当前列名如下：")
    print(list(df_be.columns))
    raise RuntimeError("[DVL-BE] 无法识别 ENU 速度列，请在 _extract_be_vel_enu 中补充列名组合。")


def _wrap_pm_pi(x: np.ndarray) -> np.ndarray:
    """
    把角度 wrap 到 (-pi, pi].
    """
    return (x + np.pi) % (2.0 * np.pi) - np.pi


def _build_yaw_candidates(df_imu: pd.DataFrame) -> List[Tuple[str, np.ndarray]]:
    """
    从 IMU DataFrame 中提取所有可能的 yaw 候选，统一转为 rad。
    返回列表 [(name, yaw_rad_array), ...]
    """
    cands: List[Tuple[str, np.ndarray]] = []

    def add_if_exists(col: str, unit: str) -> None:
        if col not in df_imu.columns:
            return
        arr = df_imu[col].to_numpy(dtype=float)
        if unit == "deg":
            arr = np.deg2rad(arr)
        # 先做 unwrap，再统一到 (-pi,pi] 区间
        arr_unwrap = np.unwrap(arr)
        arr_wrap = _wrap_pm_pi(arr_unwrap)
        cands.append((col, arr_wrap))

    # 1) 已有的工程列（rad）
    add_if_exists("yaw_nav_rad", "rad")
    add_if_exists("yaw_device_rad", "rad")

    # 2) 估计/滤波列（deg）
    add_if_exists("YawEst_deg", "deg")
    add_if_exists("YawEst_unwrapped_deg", "deg")

    # 3) 原始姿态角（deg）
    add_if_exists("AngZ_deg", "deg")

    if not cands:
        print("[YAW-CANDS][WARN] 在 IMU CSV 中没有找到任何 yaw 候选列，"
              "请检查 _build_yaw_candidates 的实现或 IMU 表头。")
    else:
        print("[YAW-CANDS] 发现的 yaw 候选列：", [name for name, _ in cands])

    return cands


# ----------------------------------------------------------------------
# 主逻辑：DVL vs IMU yaw 可视化
# ----------------------------------------------------------------------

def yaw_dvl_inspect(
    df_imu: pd.DataFrame,
    df_be: pd.DataFrame,
    speed_min: float = 0.1,
) -> None:
    """
    纯传感器层面画图：
      - yaw_dvl(t) 来自 DVL BE 水平速度方向（假定 Ve/Vn 已是 ENU）
      - yaw_imu_candidate(t) 来自 IMU 中各种 yaw 列（统一为 rad）
      - t 统一使用 DVL BE 的时间轴（插值 IMU yaw）
    """

    # ---------- 1) 时间 & 速度 ----------
    t_be = _pick_time_s(df_be, "DVL-BE")
    Ve, Vn, Vu = _extract_be_vel_enu(df_be)
    speed_h = np.hypot(Ve, Vn)

    t_imu = _pick_time_s(df_imu, "IMU")

    # 时间重叠
    t_min_imu = float(np.nanmin(t_imu))
    t_max_imu = float(np.nanmax(t_imu))
    mask_time = (t_be >= t_min_imu) & (t_be <= t_max_imu)

    # 速度门限
    mask_speed = speed_h >= speed_min

    # 暂时没有质量标志，就全通过
    mask_quality = np.ones_like(speed_h, dtype=bool)

    mask_all = mask_time & mask_speed & mask_quality
    n_all = int(np.count_nonzero(mask_all))

    print(f"[MASK] 速度通过 N_speed   = {int(np.count_nonzero(mask_speed))}/{len(speed_h)} (speed_min={speed_min} m/s)")
    print(f"[MASK] 时间重叠 N_time    = {int(np.count_nonzero(mask_time))}/{len(speed_h)} (与 IMU t_s 区间交集)")
    print(f"[MASK] 全部通过 N_all     = {n_all}/{len(speed_h)}")

    if n_all < 50:
        print(f"[WARN] 可用样本太少 (N_all={n_all})，图像/统计可能不稳定。")

    if n_all == 0:
        print("[ERROR] 有效样本数为 0，无法进行 yaw vs DVL 分析。")
        return

    # 选定用于分析的时间 & DVL 速度
    t_use = t_be[mask_all]
    Ve_use = Ve[mask_all]
    Vn_use = Vn[mask_all]

    # DVL 水平航向：假定 Ve/Vn 已在 ENU（E,N）
    yaw_dvl = np.arctan2(Vn_use, Ve_use)
    yaw_dvl = _wrap_pm_pi(yaw_dvl)

    # ---------- 2) IMU yaw 候选 ----------
    yaw_cands = _build_yaw_candidates(df_imu)
    if not yaw_cands:
        return

    # 为每个候选插值到 DVL 时间轴，并计算 dyaw
    stats_rows: List[Tuple[str, int, float, float, float, float, float]] = []
    yaw_interp_dict: Dict[str, np.ndarray] = {}
    dyaw_dict: Dict[str, np.ndarray] = {}

    for name, yaw_arr in yaw_cands:
        if len(yaw_arr) != len(t_imu):
            print(f"[WARN] yaw 列 {name} 长度({len(yaw_arr)}) != IMU 时间长度({len(t_imu)})，跳过该候选。")
            continue

        # 先用 IMU 时间轴做线性插值（对 unwrap 后的角）
        yaw_unwrap = np.unwrap(yaw_arr)
        yaw_interp_un = np.interp(t_use, t_imu, yaw_unwrap)
        yaw_imu = _wrap_pm_pi(yaw_interp_un)

        dyaw = _wrap_pm_pi(yaw_imu - yaw_dvl)
        dyaw_deg = np.rad2deg(dyaw)

        # 统计量
        mean_d = float(np.nanmean(dyaw_deg))
        std_d = float(np.nanstd(dyaw_deg))
        p50, p90, p95, p99 = np.nanpercentile(dyaw_deg, [50, 90, 95, 99])

        print(f"\n[YAW-COMPARE] Candidate {name}:")
        print(f"  N            = {len(dyaw_deg)}")
        print(f"  mean(dyaw)   = {mean_d: .3f} deg")
        print(f"  std(dyaw)    = {std_d: .3f} deg")
        print(f"  p50/p90/p95/p99 = {p50: .2f} / {p90: .2f} / {p95: .2f} / {p99: .2f} deg")

        stats_rows.append((name, len(dyaw_deg), mean_d, std_d, p50, p90, p95, p99))
        yaw_interp_dict[name] = yaw_imu
        dyaw_dict[name] = dyaw_deg

    if not stats_rows:
        print("[YAW-COMPARE][WARN] 所有 yaw 候选都无法使用（长度或 NaN 问题）。")
        return

    # 按 std(dyaw) 排序，方便你一眼看到谁最稳
    stats_rows.sort(key=lambda r: r[3])

    print("\n[YAW-COMPARE] Summary (按 std(dyaw_deg) 升序)：")
    print("  name                    | N      | mean(deg) | std(deg) | p50   | p90   | p95   | p99  ")
    for name, N, mean_d, std_d, p50, p90, p95, p99 in stats_rows:
        print(
            f"  {name:22s} | {N:6d} | {mean_d:9.3f} | {std_d:8.3f} |"
            f" {p50:5.1f} | {p90:5.1f} | {p95:5.1f} | {p99:5.1f}"
        )

    # ------------------------------------------------------------------
    # 3) 画图：yaw vs time
    # ------------------------------------------------------------------
    print("\n[FIG] 绘制 yaw_vs_time 和 dyaw_vs_time 两张图 ...")

    # 图 1：yaw vs time
    plt.figure()
    t0 = t_use[0]
    t_rel = t_use - t0  # 相对时间，单位秒，方便读图

    plt.plot(t_rel, np.rad2deg(yaw_dvl), label="yaw_dvl_from_BE")
    for name, yaw_imu in yaw_interp_dict.items():
        plt.plot(t_rel, np.rad2deg(yaw_imu), label=f"yaw_imu ({name})")

    plt.xlabel("time since first DVL sample [s]")
    plt.ylabel("yaw [deg]")
    plt.title("DVL yaw vs IMU yaw candidates")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    # 图 2：dyaw vs time
    plt.figure()
    for name, dyaw_deg in dyaw_dict.items():
        plt.plot(t_rel, dyaw_deg, label=f"dyaw ({name})")

    plt.xlabel("time since first DVL sample [s]")
    plt.ylabel("dyaw = yaw_imu - yaw_dvl [deg]")
    plt.title("dyaw vs time for IMU yaw candidates")
    plt.axhline(0.0, linestyle="--")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.show()

    print("[FIG] Done. 请结合两张图 & 上面的统计表，人工挑选最可信的 yaw 列。")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="纯传感器层面检查 DVL BE 速度方向 vs IMU yaw 候选列的关系，并可视化。"
    )
    parser.add_argument(
        "--imu-csv",
        required=True,
        help="预处理后的 IMU CSV 路径，例如 ../out/proc/..._imu_filtered.csv",
    )
    parser.add_argument(
        "--dvl-be-csv",
        required=True,
        help="预处理后的 DVL BE CSV 路径，例如 ../out/proc/..._dvl_BE.csv",
    )
    parser.add_argument(
        "--speed-min",
        type=float,
        default=0.10,
        help="只使用水平速度大于该阈值的样本，单位 m/s（默认 0.10）",
    )

    args = parser.parse_args()

    print("[ARGS] IMU CSV   :", args.imu_csv)
    print("[ARGS] DVL BE CSV:", args.dvl_be_csv)
    print("[ARGS] speed_min :", args.speed_min, "m/s")

    df_imu = pd.read_csv(args.imu_csv)
    df_be = pd.read_csv(args.dvl_be_csv)

    yaw_dvl_inspect(df_imu, df_be, speed_min=args.speed_min)
    print("[YAW-DVL-INSPECT] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
