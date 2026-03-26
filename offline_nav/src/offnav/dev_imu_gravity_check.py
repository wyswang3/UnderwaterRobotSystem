#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev_imu_gravity_check.py

针对“静止 IMU 数据”的重力 / 坐标变换单元测试：
- 直接从 CSV 读原始 IMU（AccX/AccY/AccZ, GyroX/Y/Z, AngX/Y/Z）
- 走 preprocess_imu_simple 的全链路（RFU->FRD + 重力投影 + bias 估计）
- 在全程静止假设下，检查：
    1) 传感器坐标系 S 下的平均加速度（单位 g 和 m/s^2）
    2) 机体系 B(FRD) 下的原始比力 acc_b_mps2_raw 的均值
    3) 机体系下的重力向量 g_body_mps2 的均值
    4) acc_b_mps2_raw + g_body_mps2 的均值（理想情况下应接近 0）
    5) 线加速度 acc_mps2 的均值（应 ~0）
    6) 厂家 yaw vs 转换后的 body yaw 的对比
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from offnav.preprocess.imu_processing import (
    ImuPreprocessConfig,
    preprocess_imu_simple,
)
from offnav.preprocess.imu_processing import _extract_time_s  # 直接复用内部工具


@dataclass
class SimpleImuRaw:
    df: pd.DataFrame


def run_check(csv_path: str) -> None:
    csv_path = str(csv_path)
    print(f"[CHECK] Loading IMU CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    if df is None or df.empty:
        raise RuntimeError(f"IMU CSV is empty: {csv_path}")

    # 0) 时间轴 & 采样率估计（只是打印一下）
    t_s = _extract_time_s(df)
    if t_s.size < 2:
        raise RuntimeError("Not enough samples in IMU CSV")

    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    fs_hz = 1.0 / float(np.median(dt)) if dt.size > 0 else float("nan")
    print(f"[CHECK] fs_hz_est ≈ {fs_hz:.3f} Hz, N={t_s.size}")

    # 1) 直接在“传感器坐标系 S”下看 AccX/Y/Z 的均值（单位 g 和 m/s^2）
    for c in ("AccX", "AccY", "AccZ"):
        if c not in df.columns:
            raise KeyError(f"IMU CSV missing column {c!r}")

    acc_s_g = df[["AccX", "AccY", "AccZ"]].to_numpy(dtype=float)
    acc_s_g_mean = np.nanmean(acc_s_g, axis=0)

    g_to_mps2 = 9.78
    acc_s_mps2 = acc_s_g * g_to_mps2
    acc_s_mps2_mean = np.nanmean(acc_s_mps2, axis=0)

    print("\n[CHECK] Sensor frame S (RFU) mean acc (静止窗，全程平均)：")
    print(f"  mean(acc_s_g)      = ({acc_s_g_mean[0]:+8.4f}, {acc_s_g_mean[1]:+8.4f}, {acc_s_g_mean[2]:+8.4f})  [g]")
    print(f"  mean(acc_s_mps2)   = ({acc_s_mps2_mean[0]:+8.4f}, {acc_s_mps2_mean[1]:+8.4f}, {acc_s_mps2_mean[2]:+8.4f})  [m/s^2]")

    # 2) 走 preprocess_imu_simple（注意：bias_duration_s 设成一个大值，让“全程”都作为静止窗）
    imu_raw = SimpleImuRaw(df=df)
    cfg = ImuPreprocessConfig(
        sensor_to_body_map="rfu_to_frd",
        mount_rpy_rad=(0.0, 0.0, 0.0),
        bias_duration_s=9999.0,   # 整段都用来估计 bias
        g_to_mps2=g_to_mps2,
        gyro_unit="deg/s",
        nav_frame="END",
        keep_debug=True,
        keep_raw_df=False,
    )
    imu_proc = preprocess_imu_simple(imu_raw, cfg)

    # 3) 机体系 B(FRD) 下的原始比力 / 重力 / 线加速度
    acc_b_raw = imu_proc.acc_raw_mps2      # (N,3) RFU->FRD 后、还未扣重力
    g_body    = imu_proc.g_body_mps2       # (N,3) 由角度推出来的重力在 body 中的分量
    acc_lin   = imu_proc.acc_mps2          # (N,3) 已扣重力 + bias 的线加速度

    if acc_b_raw is None or g_body is None:
        raise RuntimeError("acc_raw_mps2 or g_body_mps2 is None; ensure keep_debug=True in ImuPreprocessConfig")

    acc_b_raw_mean = np.nanmean(acc_b_raw, axis=0)
    g_body_mean    = np.nanmean(g_body, axis=0)
    residual_mean  = np.nanmean(acc_b_raw + g_body, axis=0)
    acc_lin_mean   = np.nanmean(acc_lin, axis=0)

    print("\n[CHECK] Body frame B (FRD) means (静止窗，全程平均)：")
    print(f"  mean(acc_b_raw_mps2) = ({acc_b_raw_mean[0]:+8.4f}, {acc_b_raw_mean[1]:+8.4f}, {acc_b_raw_mean[2]:+8.4f})  [m/s^2]")
    print(f"  mean(g_body_mps2)    = ({g_body_mean[0]:+8.4f}, {g_body_mean[1]:+8.4f}, {g_body_mean[2]:+8.4f})  [m/s^2]")
    print(f"  mean(acc_b_raw + g)  = ({residual_mean[0]:+8.4f}, {residual_mean[1]:+8.4f}, {residual_mean[2]:+8.4f})  [m/s^2]")
    print(f"  mean(acc_lin_mps2)   = ({acc_lin_mean[0]:+8.4f}, {acc_lin_mean[1]:+8.4f}, {acc_lin_mean[2]:+8.4f})  [m/s^2]")

    # 4) Yaw 对比（设备 yaw vs 机体 yaw）
    yaw_dev = getattr(imu_proc, "yaw_device_rad", None)
    yaw_body = None
    if imu_proc.angle_est_rad is not None:
        yaw_body = imu_proc.angle_est_rad[:, 2]

    print("\n[CHECK] yaw 对比（deg）：")
    if yaw_dev is not None:
        yaw_dev_deg = np.rad2deg(yaw_dev)
        print(f"  device yaw  (mean,std) = ({np.nanmean(yaw_dev_deg):+8.3f}, {np.nanstd(yaw_dev_deg):+8.3f})")
    else:
        print("  device yaw  : <not available>")

    if yaw_body is not None:
        yaw_body_deg = np.rad2deg(yaw_body)
        print(f"  body yaw    (mean,std) = ({np.nanmean(yaw_body_deg):+8.3f}, {np.nanstd(yaw_body_deg):+8.3f})")
    else:
        print("  body yaw    : <not available>")

    print("\n[CHECK] Done.\n")


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Unit-test gravity / frame mapping for static IMU CSV")
    ap.add_argument("--csv", required=True, help="Path to IMU CSV (static run)")
    args = ap.parse_args()

    run_check(args.csv)


if __name__ == "__main__":
    main()
