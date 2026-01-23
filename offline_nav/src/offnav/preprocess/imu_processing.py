from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Literal

import numpy as np
import pandas as pd

from offnav.core.types import ImuRawData
from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb, wrap_angle_pm_pi


# =============================================================================
# Frames (HARD CONTRACT)
# =============================================================================
"""
Sensor frame S (vendor): RFU, right-handed
  +X_s: Right
  +Y_s: Forward
  +Z_s: Up

Body frame B (project standard): FRD, right-handed
  +X_b: Forward
  +Y_b: Right
  +Z_b: Down

Nav frame N (project standard): ENU, right-handed
  +X_n: East
  +Y_n: North
  +Z_n: Up (positive Up)

Gravity in ENU:
  g_n = [0, 0, -g]

IMPORTANT (acc model):
  Most IMUs output "specific force" f (a - g), often in units of g.
  With Z_s up, static rest typically gives +1g on +Z_s.

  After mapping to body FRD (Z_b down):
    - for a level body, gravity in body is approximately g_b ≈ [0, 0, +g] (Down positive)
    - at rest a=0 => f_b ≈ -g_b ≈ [0, 0, -g]
  Therefore linear acceleration should be:
    a_lin_b = f_b + g_b - b_a

  (Key: use +g_b, not subtracting g.)
"""


# =============================================================================
# Types / Config
# =============================================================================

GyroUnit = Literal["deg/s", "rad/s"]
AccModel = Literal["specific_force"]


@dataclass
class ImuPreprocessConfig:
    # ---- Frames / mapping ----
    sensor_to_body_map: str = "rfu_to_frd"
    mount_rpy_rad: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # extra mount correction in BODY

    # ---- Bias window ----
    bias_duration_s: float = 20.0

    # ---- Units ----
    g_to_mps2: float = 9.78
    gyro_unit: GyroUnit = "deg/s"
    acc_model: AccModel = "specific_force"

    # ---- Filters ----
    lowpass_window_s: float = 0.5
    gyro_threshold_rad_s: float = np.deg2rad(0.10)  # ONLY for gyro_out (plots)

    # ---- Attitude / gravity ----
    nav_frame: str = "ENU"
    use_device_angle: bool = True                 # use AngX/AngY/AngZ
    gravity_yaw_zero: bool = True                 # yaw not needed for gravity projection

    # ---- Keep extra fields ----
    keep_debug: bool = True
    keep_raw_df: bool = False


@dataclass
class ImuProcessedData:
    # core
    t_s: np.ndarray
    fs_hz: float

    # outputs in body(FRD)
    acc_mps2: np.ndarray            # (N,3) linear accel (gravity compensated)
    gyro_in_rad_s: np.ndarray       # (N,3) lowpass only (for ESKF yaw propagation)
    gyro_out_rad_s: np.ndarray      # (N,3) lowpass + threshold (for plots)

    # debug / attitude
    acc_raw_mps2: Optional[np.ndarray] = None
    g_body_mps2: Optional[np.ndarray] = None
    angle_rad: Optional[np.ndarray] = None         # sensor semantics (rad, AngX/Y/Z)
    angle_est_rad: Optional[np.ndarray] = None     # body semantics (roll/pitch/yaw, rad)

    # yaw series
    yaw_device_rad: Optional[np.ndarray] = None    # 设备输出 yaw（由 AngZ/YawDeg 得来，wrap 到 [-pi,pi)）
    yaw_nav_rad: Optional[np.ndarray] = None       # body 语义 yaw，经去偏置 + unwrap + 低通后的 yaw（rad）

    # bias / noise diag
    bias_acc_mps2: Optional[np.ndarray] = None
    bias_gyro_rad_s: Optional[np.ndarray] = None

    std_acc_mps2: Optional[np.ndarray] = None
    std_gyro_rad_s: Optional[np.ndarray] = None
    nd_acc: Optional[np.ndarray] = None
    nd_gyro: Optional[np.ndarray] = None

    raw_df: Optional[pd.DataFrame] = None


# =============================================================================
# Public: CSV loader (kept as-is, but robust)
# =============================================================================
def load_imu_processed_csv(
    csv_path: str,
    *,
    prefer_gyro_for_eskf: Literal["gyro_in", "gyro_out"] = "gyro_in",
    strict_gyro_in: bool = True,
) -> ImuProcessedData:
    df = pd.read_csv(csv_path)
    if df is None or df.empty:
        raise RuntimeError(f"IMU processed CSV is empty: {csv_path!r}")

    if "t_s" not in df.columns:
        raise KeyError(f"IMU processed CSV missing 't_s': {csv_path!r}")
    t_s = df["t_s"].to_numpy(dtype=float)
    fs_hz = _estimate_fs_hz(t_s)

    # --- linear accel ---
    for c in ("AccX_mps2", "AccY_mps2", "AccZ_mps2"):
        if c not in df.columns:
            raise KeyError(f"IMU processed CSV missing {c!r}: {csv_path!r}")
    acc = df[["AccX_mps2", "AccY_mps2", "AccZ_mps2"]].to_numpy(dtype=float)

    # --- gyro_in (for ESKF) ---
    gyro_in = None
    if all(c in df.columns for c in ("GyroX_in_rad_s", "GyroY_in_rad_s", "GyroZ_in_rad_s")):
        gyro_in = df[["GyroX_in_rad_s", "GyroY_in_rad_s", "GyroZ_in_rad_s"]].to_numpy(dtype=float)

    # --- gyro_out (for plots) ---
    gyro_out = None
    if all(c in df.columns for c in ("GyroX_out_rad_s", "GyroY_out_rad_s", "GyroZ_out_rad_s")):
        gyro_out = df[["GyroX_out_rad_s", "GyroY_out_rad_s", "GyroZ_out_rad_s"]].to_numpy(dtype=float)
    elif all(c in df.columns for c in ("GyroX_rad_s", "GyroY_rad_s", "GyroZ_rad_s")):
        gyro_out = df[["GyroX_rad_s", "GyroY_rad_s", "GyroZ_rad_s"]].to_numpy(dtype=float)

    if strict_gyro_in and gyro_in is None:
        raise ImportError(
            "[IMU][LOAD] Gyro*_in_rad_s is missing. ESKF should NOT run with thresholded gyro.\n"
            f"  file={csv_path}\n"
            "Fix: ensure imu_processing.py exports gyro_in and cli_proc.py writes Gyro*_in_rad_s."
        )

    if gyro_out is None and gyro_in is not None:
        gyro_out = gyro_in.copy()

    if gyro_in is None:
        if gyro_out is None:
            raise ImportError(
                f"[IMU][LOAD] No gyro columns found in {csv_path!r}. "
                "Expected Gyro*_in_rad_s and/or Gyro*_out_rad_s / Gyro*_rad_s."
            )
        gyro_in = gyro_out.copy()

    if prefer_gyro_for_eskf == "gyro_out":
        gyro_in = gyro_out.copy()

    yaw_device_rad: Optional[np.ndarray]
    yaw_nav_rad: Optional[np.ndarray]

    if "yaw_device_rad" in df.columns:
        yaw_device_rad = df["yaw_device_rad"].to_numpy(dtype=float)
    else:
        yaw_device_rad = None

    if "yaw_nav_rad" in df.columns:
        yaw_nav_rad = df["yaw_nav_rad"].to_numpy(dtype=float)
    else:
        yaw_nav_rad = None

    return ImuProcessedData(
        t_s=t_s,
        fs_hz=float(fs_hz),
        acc_mps2=acc,
        gyro_in_rad_s=gyro_in,
        gyro_out_rad_s=gyro_out,
        yaw_device_rad=yaw_device_rad,
        yaw_nav_rad=yaw_nav_rad,
        raw_df=df,
    )


# =============================================================================
# Helpers: time / stats
# =============================================================================

def _extract_time_s(df: pd.DataFrame) -> np.ndarray:
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError("IMU df has no time column (need EstS/MonoS/EstNS/MonoNS).")


def _estimate_fs_hz(t_s: np.ndarray) -> float:
    if t_s.size < 2:
        return float("nan")
    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return float("nan")
    return 1.0 / float(np.median(dt))


def _select_bias_window(t_s: np.ndarray, duration_s: float) -> np.ndarray:
    if t_s.size == 0:
        return np.array([], dtype=bool)
    t0 = float(t_s[0])
    t1 = t0 + float(duration_s)
    m = (t_s >= t0) & (t_s <= t1)
    if not np.any(m):
        m = np.ones_like(t_s, dtype=bool)
    return m


def _moving_average(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x.astype(float, copy=True)
    kernel = np.ones(window, dtype=float) / float(window)
    y = np.empty_like(x, dtype=float)
    for i in range(x.shape[1]):
        y[:, i] = np.convolve(x[:, i], kernel, mode="same")
    return y


def _apply_threshold(x: np.ndarray, thr: float) -> np.ndarray:
    y = x.copy()
    y[np.abs(y) < thr] = 0.0
    return y


def _wrap_rpy_rad(rpy: np.ndarray) -> np.ndarray:
    out = np.asarray(rpy, dtype=float).copy()
    out[:, 0] = np.vectorize(wrap_angle_pm_pi)(out[:, 0])
    out[:, 1] = np.vectorize(wrap_angle_pm_pi)(out[:, 1])
    out[:, 2] = np.vectorize(wrap_angle_pm_pi)(out[:, 2])
    return out


# =============================================================================
# Helpers: transforms (single source of truth)
# =============================================================================

def _R_sb_from_name(name: str) -> np.ndarray:
    """
    Returns R_sb such that v_b = R_sb * v_s.
    """
    n = name.lower().strip()
    if n == "identity":
        return np.eye(3, dtype=float)

    if n in ("rfu_to_frd", "wit_rfu_to_frd", "rotz_p90"):
        R = np.array([[0, 1, 0],
                      [1, 0, 0],
                      [0, 0, -1]], dtype=float)
        det = float(np.linalg.det(R))
        if abs(det - 1.0) > 1e-6:
            raise ValueError(f"rfu_to_frd det should be +1, got {det}")
        if n == "rotz_p90":
            print("[IMU][WARN] sensor_to_body_map='rotz_p90' treated as alias of 'rfu_to_frd'.")
        return R

    raise ValueError(f"Unknown sensor_to_body_map={name!r}")


def _R_mount_from_rpy(mount_rpy_rad: Tuple[float, float, float]) -> np.ndarray:
    mr, mp, my = mount_rpy_rad
    if abs(mr) < 1e-12 and abs(mp) < 1e-12 and abs(my) < 1e-12:
        return np.eye(3, dtype=float)
    return rpy_to_R_nb(AttitudeRPY(float(mr), float(mp), float(my)))


def _map_vec_s_to_b(v_s: np.ndarray, R_sb_total: np.ndarray) -> np.ndarray:
    return (R_sb_total @ v_s.T).T


def _rpy_to_R_nb_batch(rpy: np.ndarray) -> np.ndarray:
    n = rpy.shape[0]
    out = np.empty((n, 3, 3), dtype=float)
    for k in range(n):
        out[k] = rpy_to_R_nb(AttitudeRPY(float(rpy[k, 0]), float(rpy[k, 1]), float(rpy[k, 2])))
    return out


def _R_to_rpy_zyx(R: np.ndarray) -> np.ndarray:
    r20 = float(np.clip(R[2, 0], -1.0, 1.0))
    pitch = -np.arcsin(r20)
    cp = np.cos(pitch)
    if abs(cp) < 1e-8:
        roll = 0.0
        yaw = np.arctan2(-float(R[0, 1]), float(R[1, 1]))
    else:
        roll = np.arctan2(float(R[2, 1]), float(R[2, 2]))
        yaw = np.arctan2(float(R[1, 0]), float(R[0, 0]))
    return np.array([wrap_angle_pm_pi(roll), wrap_angle_pm_pi(pitch), wrap_angle_pm_pi(yaw)], dtype=float)


def _convert_device_angles_to_body_rpy(
    angle_sensor_rad: np.ndarray,
    R_sb_total: np.ndarray,
) -> np.ndarray:
    R_ns = _rpy_to_R_nb_batch(angle_sensor_rad)          # sensor->nav(ENU)
    R_bs = R_sb_total.T                                   # body->sensor
    R_nb = R_ns @ R_bs
    out = np.empty_like(angle_sensor_rad, dtype=float)
    for k in range(out.shape[0]):
        out[k] = _R_to_rpy_zyx(R_nb[k])
    return _wrap_rpy_rad(out)


def _gravity_in_body_ENU(angle_body_rad: np.ndarray, g: float) -> np.ndarray:
    """
    nav=ENU: g_n=[0,0,-g]
    g_b = R_bn * g_n = R_nb^T * g_n
    """
    n = angle_body_rad.shape[0]
    g_n = np.array([0.0, 0.0, -float(g)], dtype=float).reshape(3, 1)
    R_nb = _rpy_to_R_nb_batch(angle_body_rad)
    R_bn = np.transpose(R_nb, (0, 2, 1))
    return (R_bn @ g_n).reshape(n, 3)


# =============================================================================
# Main API
# =============================================================================

def preprocess_imu_simple(imu: ImuRawData, cfg: ImuPreprocessConfig) -> ImuProcessedData:
    if cfg.nav_frame.upper() != "ENU":
        raise ValueError(f"Only nav_frame='ENU' is supported, got {cfg.nav_frame!r}")
    if cfg.acc_model != "specific_force":
        raise ValueError(f"Only acc_model='specific_force' is supported, got {cfg.acc_model!r}")

    df = imu.df
    if df is None or df.empty:
        raise RuntimeError("IMU dataframe is empty")

    for c in ("AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"):
        if c not in df.columns:
            raise KeyError(f"IMU df missing column {c!r}")

    if cfg.use_device_angle:
        for c in ("AngX", "AngY", "AngZ"):
            if c not in df.columns:
                raise KeyError("use_device_angle=True but missing AngX/AngY/AngZ")

    # ---- time ----
    t_s = _extract_time_s(df)
    fs_hz = _estimate_fs_hz(t_s)

    # ---- single transform source of truth ----
    R_sb = _R_sb_from_name(cfg.sensor_to_body_map)
    R_mount = _R_mount_from_rpy(cfg.mount_rpy_rad)
    R_sb_total = R_mount @ R_sb  # sensor->body (final)

    # ---- acc: g -> m/s^2 then map to body ----
    acc_s_g = df[["AccX", "AccY", "AccZ"]].to_numpy(dtype=float)
    f_s_mps2 = acc_s_g * float(cfg.g_to_mps2)
    f_b_mps2_raw = _map_vec_s_to_b(f_s_mps2, R_sb_total)  # specific force in body

    # ---- gyro: unit convert then map to body ----
    gyro_s = df[["GyroX", "GyroY", "GyroZ"]].to_numpy(dtype=float)
    if cfg.gyro_unit == "deg/s":
        gyro_s_rad = np.deg2rad(gyro_s)
    elif cfg.gyro_unit == "rad/s":
        gyro_s_rad = gyro_s.astype(float, copy=True)
    else:
        raise ValueError(f"Unknown gyro_unit={cfg.gyro_unit!r}")
    gyro_b_rad_raw = _map_vec_s_to_b(gyro_s_rad, R_sb_total)

    # ---- static window ----
    bw = _select_bias_window(t_s, cfg.bias_duration_s)

    # ---- gyro bias / lowpass / threshold ----
    bias_gyro = gyro_b_rad_raw[bw].mean(axis=0)
    gyro_b_detrend = gyro_b_rad_raw - bias_gyro[None, :]

    if np.isfinite(fs_hz) and fs_hz > 0:
        win = max(1, int(round(cfg.lowpass_window_s * fs_hz)))
    else:
        win = 5

    gyro_in = _moving_average(gyro_b_detrend, win)
    gyro_out = _apply_threshold(gyro_in, float(cfg.gyro_threshold_rad_s))

    # ---- angles -> body semantics, then gravity ----
    angle_sensor_rad: Optional[np.ndarray]
    angle_body_rad: Optional[np.ndarray]
    if cfg.use_device_angle:
        ang_deg = df[["AngX", "AngY", "AngZ"]].to_numpy(dtype=float)
        angle_sensor_rad = _wrap_rpy_rad(np.deg2rad(ang_deg))
        angle_body_rad = _convert_device_angles_to_body_rpy(angle_sensor_rad, R_sb_total)

        angle_for_g = angle_body_rad.copy()
        if cfg.gravity_yaw_zero:
            angle_for_g[:, 2] = 0.0
        g_body = _gravity_in_body_ENU(angle_for_g, float(cfg.g_to_mps2))
    else:
        angle_sensor_rad = None
        angle_body_rad = None
        g_body = np.zeros_like(f_b_mps2_raw)

    # ---- yaw series ----
    yaw_device_rad: Optional[np.ndarray] = None
    yaw_src_deg: Optional[np.ndarray] = None
    if "YawDeg" in df.columns:
        yaw_src_deg = df["YawDeg"].to_numpy(dtype=float)
    elif "AngZ" in df.columns:
        yaw_src_deg = df["AngZ"].to_numpy(dtype=float)

    if yaw_src_deg is not None:
        yaw_rad_raw = np.deg2rad(yaw_src_deg)
        finite = np.isfinite(yaw_rad_raw)
        yaw_wrapped = yaw_rad_raw.copy()
        if np.any(finite):
            yaw_wrapped[finite] = np.vectorize(wrap_angle_pm_pi)(yaw_rad_raw[finite])
        yaw_device_rad = yaw_wrapped

    yaw_nav_rad: Optional[np.ndarray] = None
    if angle_body_rad is not None:
        yaw_body = angle_body_rad[:, 2]
        yaw_unwrapped = np.unwrap(yaw_body)

        if np.any(bw):
            yaw_bias = float(np.nanmean(yaw_unwrapped[bw]))
        else:
            yaw_bias = float(yaw_unwrapped[0])

        yaw_nav = yaw_unwrapped - yaw_bias
        yaw_nav = np.vectorize(wrap_angle_pm_pi)(yaw_nav)

        yaw_nav_2d = yaw_nav.reshape(-1, 1)
        yaw_nav_filt = _moving_average(yaw_nav_2d, win)[:, 0]
        yaw_nav_rad = yaw_nav_filt

    # ---- accel bias & linear acceleration (SPECIFIC FORCE MODEL) ----
    bias_acc = (f_b_mps2_raw[bw] + g_body[bw]).mean(axis=0)
    acc_lin = f_b_mps2_raw + g_body - bias_acc[None, :]

    # ---- noise proxies ----
    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    dt0 = float(np.median(dt)) if dt.size > 0 else (1.0 / fs_hz if np.isfinite(fs_hz) and fs_hz > 0 else 0.01)

    std_acc = acc_lin[bw].std(axis=0)
    std_gyro = gyro_b_detrend[bw].std(axis=0)
    nd_acc = std_acc * np.sqrt(dt0)
    nd_gyro = std_gyro * np.sqrt(dt0)

    return ImuProcessedData(
        t_s=t_s,
        fs_hz=float(fs_hz),

        acc_mps2=acc_lin,
        gyro_in_rad_s=gyro_in,
        gyro_out_rad_s=gyro_out,

        acc_raw_mps2=(f_b_mps2_raw if cfg.keep_debug else None),
        g_body_mps2=(g_body if cfg.keep_debug else None),

        angle_rad=(angle_sensor_rad if (cfg.keep_debug and angle_sensor_rad is not None) else None),
        angle_est_rad=(angle_body_rad if (cfg.keep_debug and angle_body_rad is not None) else None),

        yaw_device_rad=yaw_device_rad,
        yaw_nav_rad=yaw_nav_rad,

        bias_acc_mps2=(bias_acc if cfg.keep_debug else None),
        bias_gyro_rad_s=(bias_gyro if cfg.keep_debug else None),

        std_acc_mps2=(std_acc if cfg.keep_debug else None),
        std_gyro_rad_s=(std_gyro if cfg.keep_debug else None),
        nd_acc=(nd_acc if cfg.keep_debug else None),
        nd_gyro=(nd_gyro if cfg.keep_debug else None),

        raw_df=(df.copy() if cfg.keep_raw_df else None),
    )
