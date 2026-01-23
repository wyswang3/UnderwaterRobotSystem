# src/offnav/algo/eskf_common.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple,Optional

import numpy as np
import pandas as pd

from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb
from offnav.algo.eskf_audit import audit_dataframe
from offnav.algo.event_timeline import TimeAlignmentReport
from offnav.models.eskf_state import EskfDiagnostics

from offnav.preprocess.imu_processing import ImuProcessedData

# 尝试复用 deadreckon 里的姿态插值 & BI 体速度提取函数（如果存在）
try:
    from offnav.algo.deadreckon import (
        _interp_attitude_from_imu as _interp_att_from_imu_dr,
        _extract_body_velocity as _extract_dvl_bi_body_vel,
    )
except Exception:  # noqa: BLE001
    _interp_att_from_imu_dr = None
    _extract_dvl_bi_body_vel = None


# -----------------------------------------------------------------------------
# ImuProcessedData 工具：取 roll/pitch(rad)
# -----------------------------------------------------------------------------
def get_roll_pitch_rad(imu_proc: Any, k: int) -> Tuple[float, float]:
    """
    从 ImuProcessedData 中拿 roll/pitch（单位 rad）。

    优先级：
      0) 复用 deadreckon._interp_attitude_from_imu（统一 yaw 选列逻辑）
      1) 一维数组字段：roll_rad/pitch_rad, roll_body_rad/pitch_body_rad 等
      2) rpy 向量字段：angle_est_rad / rpy_rad / rpy_est_rad
      3) DataFrame 列：roll_body_rad/pitch_body_rad 或 AngX/AngY[deg]
      4) 实在拿不到，退化为 (0,0)
    """
    # 0) 使用 deadreckon 的插值逻辑
    if _interp_att_from_imu_dr is not None:
        try:
            t_imu = np.asarray(getattr(imu_proc, "t_s", []), dtype=float).reshape(-1)
            if t_imu.size > 0:
                df = getattr(imu_proc, "raw_df", None)
                if df is None:
                    df = getattr(imu_proc, "df", None)

                if isinstance(df, pd.DataFrame) and not df.empty:
                    kk = min(max(k, 0), len(t_imu) - 1)
                    t_query = float(t_imu[kk])
                    att = _interp_att_from_imu_dr(df, t_imu, t_query)
                    return float(att.roll), float(att.pitch)
        except Exception:
            pass

    # 1) 一维数组字段
    for roll_name, pitch_name in [
        ("roll_rad", "pitch_rad"),
        ("roll_body_rad", "pitch_body_rad"),
        ("imu_roll_rad", "imu_pitch_rad"),
    ]:
        roll_arr = getattr(imu_proc, roll_name, None)
        pitch_arr = getattr(imu_proc, pitch_name, None)
        if roll_arr is None or pitch_arr is None:
            continue
        try:
            return float(roll_arr[k]), float(pitch_arr[k])
        except Exception:
            pass

    # 2) rpy 向量字段
    for name in ("angle_est_rad", "rpy_rad", "rpy_est_rad"):
        rpy = getattr(imu_proc, name, None)
        if rpy is None:
            continue
        try:
            rpy_k = np.asarray(rpy[k], dtype=float).reshape(-1)
            if rpy_k.size >= 2:
                return float(rpy_k[0]), float(rpy_k[1])
        except Exception:
            pass

    # 3) DataFrame 回退
    df = getattr(imu_proc, "df", None)
    if isinstance(df, pd.DataFrame) and not df.empty:
        kk = min(max(k, 0), len(df) - 1)
        row = df.iloc[kk]

        for roll_col, pitch_col in [
            ("roll_body_rad", "pitch_body_rad"),
            ("roll_rad", "pitch_rad"),
        ]:
            if roll_col in df.columns and pitch_col in df.columns:
                try:
                    return float(row[roll_col]), float(row[pitch_col])
                except Exception:
                    pass

        if "AngX" in df.columns and "AngY" in df.columns:
            try:
                roll = np.deg2rad(float(row["AngX"]))
                pitch = np.deg2rad(float(row["AngY"]))
                return float(roll), float(pitch)
            except Exception:
                pass

    # 4) 兜底
    return 0.0, 0.0


# -----------------------------------------------------------------------------
# 轨迹输出后处理：翻转 N 轴 + 平滑
# -----------------------------------------------------------------------------
def postprocess_traj_df(traj_df: pd.DataFrame, eskf_cfg: Any) -> pd.DataFrame:
    """
    对 ESKF 输出的轨迹做工程后处理：
      1) 坐标轴修正：按需翻转 N / vN，使 EN 平面方向与实际运动一致；
      2) 轨迹平滑：对 E/N/vE/vN 做滑动平均，减小毛刺，不改变时间采样率。

    注意：只作用于“对外输出的 CSV / 绘图”，不回写到滤波器内部状态。
    """
    df = traj_df.copy()

    # 1) 坐标轴修正：N 轴翻转
    flip_n = getattr(eskf_cfg, "flip_n_axis", False)
    if flip_n:
        if "N" in df.columns:
            df["N"] = -df["N"]
        if "vN" in df.columns:
            df["vN"] = -df["vN"]

    # 2) 平滑（使用 EskfConfig 的平铺字段）
    enable_smooth = bool(getattr(eskf_cfg, "smooth_traj_enable", False))
    window = int(getattr(eskf_cfg, "smooth_traj_window_samples", 9))

    if enable_smooth and window > 1:
        if window % 2 == 0:
            window += 1

        cols = [c for c in ("E", "N", "vE", "vN") if c in df.columns]
        for c in cols:
            df[c] = df[c].rolling(window=window, center=True, min_periods=1).mean()

    return df


# -----------------------------------------------------------------------------
# 管线输入 / 输出数据结构
# -----------------------------------------------------------------------------
@dataclass
class EskfInputs:
    """
    ESKF 管线输入：
      - imu_proc: 预处理好的 IMU（ImuProcessedData）
      - dvl_be_df: BE 速度（ENU）
      - dvl_bi_df: BI 速度（body）
    """
    imu_proc: ImuProcessedData
    dvl_be_df: pd.DataFrame
    dvl_bi_df: Optional[pd.DataFrame] = None



@dataclass
class EskfOutputs:
    """
    ESKF 管线输出：
      - traj_df: 轨迹（E,N,U,yaw 等）
      - diag:   诊断统计（EskfDiagnostics）
      - audit_df: DVL 更新审计日志（供 eskf_audit 使用）
    """
    traj_df: pd.DataFrame
    diag: "EskfDiagnostics"
    audit_df: pd.DataFrame
