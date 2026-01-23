# offline_nav/src/offnav/eskf/io_csv.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import pandas as pd


_TIME_COL_CANDIDATES = ("t_s", "EstS", "MonoS", "EstNS", "MonoNS", "time_s", "TimeS")
_NS_TIME_COLS = ("EstNS", "MonoNS")


def _pick_time_s(df: pd.DataFrame) -> np.ndarray:
    for c in _TIME_COL_CANDIDATES:
        if c in df.columns:
            t = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
            if c in _NS_TIME_COLS:
                t = t * 1e-9
            return t
    raise RuntimeError(
        f"No time column found. candidates={_TIME_COL_CANDIDATES}, cols={list(df.columns)[:30]}"
    )


def _pick_first(df: pd.DataFrame, candidates: Tuple[str, ...], name: str) -> np.ndarray:
    for c in candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
    raise RuntimeError(
        f"Missing column for {name}. candidates={candidates}, cols={list(df.columns)[:50]}"
    )


def _auto_deg_to_rad_if_needed(angle: np.ndarray, name: str) -> np.ndarray:
    """
    工程防御：如果角度明显像“度”，则转换到弧度。
    判据：p95(|angle|) > 2*pi*1.2  => treat as degrees.
    """
    a = np.asarray(angle, dtype=float)
    mask = np.isfinite(a)
    if mask.sum() < 10:
        return a

    p95 = float(np.nanpercentile(np.abs(a[mask]), 95))
    if p95 > (2.0 * np.pi * 1.2):
        return np.deg2rad(a)
    return a


def _sanitize_time_aligned(
    t: np.ndarray,
    *xs: np.ndarray,
    drop_nonfinite: bool = True,
    dedup_time: bool = True,
) -> Tuple[np.ndarray, Tuple[np.ndarray, ...]]:
    """
    统一清洗策略：
    - drop_nonfinite: 过滤 t 或任一 xs 非有限
    - dedup_time: 对重复时间戳去重（保留第一次出现）
    """
    t = np.asarray(t, dtype=float).reshape(-1)
    xs2 = [np.asarray(x) for x in xs]

    n = int(t.size)
    for i, x in enumerate(xs2):
        if x.shape[0] != n:
            raise RuntimeError(f"Length mismatch: t({n}) vs x[{i}]({x.shape[0]})")

    mask = np.ones((n,), dtype=bool)

    if drop_nonfinite:
        mask &= np.isfinite(t)
        for x in xs2:
            mask &= np.all(np.isfinite(x), axis=-1) if x.ndim > 1 else np.isfinite(x)

    t = t[mask]
    xs2 = [x[mask] for x in xs2]

    if dedup_time and t.size > 1:
        # 保留第一次出现的时间戳
        _, idx = np.unique(t, return_index=True)
        idx = np.sort(idx)
        t = t[idx]
        xs2 = [x[idx] for x in xs2]

    return t, tuple(xs2)


def apply_yaw_sign_offset(yaw_rad: np.ndarray, yaw_sign: float, yaw_offset_rad: float, wrap: bool = True) -> np.ndarray:
    """
    路线 A：只在一个地方做 yaw 归一化（sign + offset + wrap）。
    wrap 使用 [-pi, pi)。
    """
    y = np.asarray(yaw_rad, dtype=float) * float(yaw_sign) + float(yaw_offset_rad)
    if wrap:
        # 等价 wrap_pm_pi，但 io_csv 不依赖 math_utils，避免循环依赖
        y = (y + np.pi) % (2.0 * np.pi) - np.pi
    return y


@dataclass
class Imu2DSeries:
    t: np.ndarray
    roll: np.ndarray
    pitch: np.ndarray
    yaw: np.ndarray
    acc_b: np.ndarray      # (N,3) body(FRD), m/s^2
    gyro_b: np.ndarray     # (N,3) body(FRD), rad/s


@dataclass
class DvlBISeries:
    t: np.ndarray
    v_b: np.ndarray        # (M,3) body(FRD), m/s


@dataclass
class DvlBESeries:
    t: np.ndarray
    v_enu: np.ndarray      # (K,3) nav(ENU), m/s


def load_imu_filtered_csv(path: str | Path) -> Imu2DSeries:
    """
    读取 imu_filtered.csv 的关键字段（只负责“读 + 基础清洗 + 单位防御”）。
    yaw 默认优先 yaw_nav_rad -> yaw_device_rad -> yaw_rad -> yaw
    """
    p = Path(path)
    df = pd.read_csv(p)

    t = _pick_time_s(df)

    roll = _pick_first(df, ("roll_rad", "Roll_rad", "roll", "Roll", "r_rad"), "roll(rad)")
    pitch = _pick_first(df, ("pitch_rad", "Pitch_rad", "pitch", "Pitch", "p_rad"), "pitch(rad)")

    yaw = _pick_first(
        df,
        ("yaw_nav_rad", "yaw_device_rad", "yaw_rad", "Yaw_rad", "yaw", "Yaw", "y_rad"),
        "yaw(rad)",
    )

    # 单位防御：roll/pitch/yaw 都做一次 deg->rad 自动识别
    roll = _auto_deg_to_rad_if_needed(roll, "roll")
    pitch = _auto_deg_to_rad_if_needed(pitch, "pitch")
    yaw = _auto_deg_to_rad_if_needed(yaw, "yaw")

    ax = _pick_first(df, ("AccX_mps2", "acc_x_mps2", "ax_mps2", "AccX", "ax"), "acc_x")
    ay = _pick_first(df, ("AccY_mps2", "acc_y_mps2", "ay_mps2", "AccY", "ay"), "acc_y")
    az = _pick_first(df, ("AccZ_mps2", "acc_z_mps2", "az_mps2", "AccZ", "az"), "acc_z")

    gx = _pick_first(
        df,
        ("GyroX_in_rad_s", "gyro_x_in_rad_s", "GyroX_rad_s", "gyro_x_rad_s", "gx_rad_s", "GyroX", "gx"),
        "gyro_x",
    )
    gy = _pick_first(
        df,
        ("GyroY_in_rad_s", "gyro_y_in_rad_s", "GyroY_rad_s", "gyro_y_rad_s", "gy_rad_s", "GyroY", "gy"),
        "gyro_y",
    )
    gz = _pick_first(
        df,
        ("GyroZ_in_rad_s", "gyro_z_in_rad_s", "GyroZ_rad_s", "gyro_z_rad_s", "gz_rad_s", "GyroZ", "gz"),
        "gyro_z",
    )

    acc_b = np.vstack([ax, ay, az]).T.astype(float)
    gyro_b = np.vstack([gx, gy, gz]).T.astype(float)

    # 清洗：drop 非有限、去重 t
    t, (roll, pitch, yaw, acc_b, gyro_b) = _sanitize_time_aligned(
        t, roll, pitch, yaw, acc_b, gyro_b,
        drop_nonfinite=True,
        dedup_time=True,
    )

    return Imu2DSeries(t=t, roll=roll, pitch=pitch, yaw=yaw, acc_b=acc_b, gyro_b=gyro_b)


def load_dvl_bi_csv(path: str | Path) -> DvlBISeries:
    p = Path(path)
    df = pd.read_csv(p)
    t = _pick_time_s(df)

    vx = _pick_first(
        df,
        ("Vx_body(m_s)", "Vx_body", "vx_body", "vbx", "v_bx", "v_x_body", "VelX_body", "VelX", "vx"),
        "BI vx",
    )
    vy = _pick_first(
        df,
        ("Vy_body(m_s)", "Vy_body", "vy_body", "vby", "v_by", "v_y_body", "VelY_body", "VelY", "vy"),
        "BI vy",
    )
    vz = _pick_first(
        df,
        ("Vz_body(m_s)", "Vz_body", "vz_body", "vbz", "v_bz", "v_z_body", "VelZ_body", "VelZ", "vz"),
        "BI vz",
    )

    v_b = np.vstack([vx, vy, vz]).T.astype(float)
    t, (v_b,) = _sanitize_time_aligned(t, v_b, drop_nonfinite=True, dedup_time=True)
    return DvlBISeries(t=t, v_b=v_b)


def load_dvl_be_csv(path: str | Path) -> DvlBESeries:
    p = Path(path)
    df = pd.read_csv(p)
    t = _pick_time_s(df)

    vE = _pick_first(df, ("Ve_enu(m_s)", "Ve_enu", "vE", "VelE", "ve", "E_vel", "V_E"), "BE vE")
    vN = _pick_first(df, ("Vn_enu(m_s)", "Vn_enu", "vN", "VelN", "vn", "N_vel", "V_N"), "BE vN")
    vU = _pick_first(df, ("Vu_enu(m_s)", "Vu_enu", "vU", "VelU", "vu", "U_vel", "V_U"), "BE vU")

    v_enu = np.vstack([vE, vN, vU]).T.astype(float)
    t, (v_enu,) = _sanitize_time_aligned(t, v_enu, drop_nonfinite=True, dedup_time=True)
    return DvlBESeries(t=t, v_enu=v_enu)
