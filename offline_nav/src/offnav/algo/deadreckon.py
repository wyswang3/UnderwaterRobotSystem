from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, List, Any

import numpy as np
import pandas as pd

from offnav.core.types import ImuRawData, DvlRawData, Trajectory
from offnav.core.nav_config import DeadReckonConfig
from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb, wrap_angle_pm_pi


# =============================================================================
# 通用小工具：bool / 时间 / 列提取
# =============================================================================
# 你给的实际安装：IMU 传感器坐标：X=右, Y=前, Z=上
R_BODY_FRD_FROM_IMU = np.array(
    [
        [1.0,  0.0,  0.0],   # X_FRD = +Y_IMU
        [0.0,  1.0,  0.0],   # Y_FRD = +X_IMU
        [0.0,  0.0, -1.0],   # Z_FRD = -Z_IMU
    ],
    dtype=float,
)

def _convert_vec_from_imu_to_frd(v_imu: np.ndarray) -> np.ndarray:
    """
    把在 IMU 传感器坐标系下的 3D 向量 v_imu，转换到 body=FRD 坐标系下。

    约定：
      - IMU 轴向：X=右, Y=前, Z=上；
      - FRD 轴向：X=前, Y=右, Z=下。
    """
    v_imu = np.asarray(v_imu, dtype=float).reshape(3)
    return R_BODY_FRD_FROM_IMU @ v_imu

def _as_bool(val: Any, default: bool = False) -> bool:
    """
    把各种类型的“布尔标志”尽量安全地转成 bool：
      - bool/np.bool_ 直接返回；
      - 数字：0 -> False，非 0 -> True（NaN -> default）；
      - 字符串："true/1/yes/ok" -> True，"false/0/no/nan/空" -> False。
    """
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if val is None:
        return default
    if isinstance(val, (int, float, np.integer, np.floating)):
        if not np.isfinite(val):
            return default
        return bool(val != 0)
    s = str(val).strip().lower()
    if s in ("true", "t", "1", "yes", "y", "ok"):
        return True
    if s in ("false", "f", "0", "no", "n", "nan", ""):
        return False
    return default


def _get_time_s_from_imu(imu: ImuRawData) -> np.ndarray:
    df = imu.df
    if "t_s" in df.columns:  # 预处理 IMU 优先
        return df["t_s"].to_numpy(dtype=float)
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError("IMU df has no t_s/EstS/MonoS/EstNS/MonoNS time column.")


def _get_time_s_from_dvl(df: pd.DataFrame) -> np.ndarray:
    if "t_s" in df.columns:  # 预处理 DVL 优先
        return df["t_s"].to_numpy(dtype=float)
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError("DVL df has no t_s/EstS/MonoS/EstNS/MonoNS time column.")


def _extract_body_velocity(df: pd.DataFrame) -> np.ndarray:
    """
    从 DVL DataFrame 中找出体坐标速度列（BI / body=FRD）。

    兼容多种命名：
      - Vx_body(m_s), Vy_body(m_s), Vz_body(m_s)   （推荐）
      - Vx_body, Vy_body, Vz_body
      - Vx_frd(m_s), Vy_frd(m_s), Vz_frd(m_s)
      - Vx_frd, Vy_frd, Vz_frd
      - Vx, Vy, Vz
      - VelX_m_s, VelY_m_s, VelZ_m_s
    """
    candidates = [
        ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"),
        ("Vx_body", "Vy_body", "Vz_body"),
        ("Vx_frd(m_s)", "Vy_frd(m_s)", "Vz_frd(m_s)"),
        ("Vx_frd", "Vy_frd", "Vz_frd"),
        ("Vx", "Vy", "Vz"),
        ("VelX_m_s", "VelY_m_s", "VelZ_m_s"),
    ]
    for cols in candidates:
        if all(c in df.columns for c in cols):
            return df[list(cols)].to_numpy(dtype=float)

    raise KeyError(
        "Cannot find DVL body velocity columns; "
        "tried Vx_body(m_s)/Vy_body(m_s)/Vz_body(m_s) etc. "
        f"Available columns: {list(df.columns)}"
    )


def _extract_enu_velocity(df: pd.DataFrame) -> np.ndarray:
    """
    从 DVL DataFrame 中找出 ENU 坐标速度列（BE / nav=ENU）。

    兼容多种命名：
      - vE_enu_m_s, vN_enu_m_s, vU_enu_m_s
      - vE_enu(m_s), vN_enu(m_s), vU_enu(m_s)
      - Ve_enu(m_s), Vn_enu(m_s), Vu_enu(m_s)
      - vE_enu, vN_enu, vU_enu
      - Ve_enu, Vn_enu, Vu_enu
    """
    candidates = [
        ("vE_enu_m_s", "vN_enu_m_s", "vU_enu_m_s"),
        ("vE_enu(m_s)", "vN_enu(m_s)", "vU_enu(m_s)"),
        ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"),  # ★ 你的当前命名
        ("vE_enu", "vN_enu", "vU_enu"),
        ("Ve_enu", "Vn_enu", "Vu_enu"),
    ]
    for cols in candidates:
        if all(c in df.columns for c in cols):
            return df[list(cols)].to_numpy(dtype=float)

    raise KeyError(
        "Cannot find DVL ENU velocity columns; "
        "tried vE_enu_m_s/vN_enu_m_s/vU_enu_m_s etc. "
        f"Available columns: {list(df.columns)}"
    )


def _extract_imu_acc_body(df_imu: pd.DataFrame) -> np.ndarray:
    """
    从 IMU DataFrame 中提取加速度（默认 body=FRD）。

    兼容命名：
      - AccX_mps2, AccY_mps2, AccZ_mps2
      - AccX, AccY, AccZ
      - Ax, Ay, Az
    """
    candidates = [
        ("AccX_mps2", "AccY_mps2", "AccZ_mps2"),
        ("AccX", "AccY", "AccZ"),
        ("Ax", "Ay", "Az"),
    ]
    for cols in candidates:
        if all(c in df_imu.columns for c in cols):
            return df_imu[list(cols)].to_numpy(dtype=float)

    raise KeyError(
        "Cannot find IMU accel columns; "
        "tried AccX_mps2/AccY_mps2/AccZ_mps2 etc. "
        f"Available columns: {list(df_imu.columns)}"
    )


def _select_dvl_indices(df: pd.DataFrame, t_dvl: np.ndarray, cfg: DeadReckonConfig) -> np.ndarray:
    """
    根据配置选择要用于 deadreckon 的 DVL 样本索引：
      - 优先使用 Src == 'BI'（体速度），除非 cfg.dvl_src 明确指定 BE/AUTO；
      - 如果存在 GateOk / SpeedOk 列，则只用通过质量门控的样本；
      - 时间必须是有限值。
    """
    n = len(df)
    mask = np.ones(n, dtype=bool)

    # 1) 根据 Src 字段选择 BI/BE
    if "Src" in df.columns:
        src = df["Src"].astype(str).str.upper().to_numpy()
        src_pref = (cfg.dvl_src or "BI").upper()

        if src_pref == "BI":
            mask &= (src == "BI")
        elif src_pref == "BE":
            mask &= (src == "BE")
        elif src_pref == "AUTO":
            mask_BI = (src == "BI")
            if np.any(mask_BI):
                mask &= mask_BI
            else:
                mask_BE = (src == "BE")
                if np.any(mask_BE):
                    mask &= mask_BE
        # 其它值就当全用

    # 2) GateOk
    if "GateOk" in df.columns:
        raw = df["GateOk"].to_numpy()
        gate_ok = np.array([_as_bool(v, default=False) for v in raw], dtype=bool)
        mask &= gate_ok

    # 3) SpeedOk
    if "SpeedOk" in df.columns:
        raw = df["SpeedOk"].to_numpy()
        speed_ok = np.array([_as_bool(v, default=False) for v in raw], dtype=bool)
        mask &= speed_ok

    # 4) 时间有限
    mask &= np.isfinite(t_dvl)

    return np.nonzero(mask)[0]


# =============================================================================
# 姿态插值（重点：yaw 列的正确使用）
# =============================================================================
def _pick_yaw_column(df_imu: pd.DataFrame) -> str | None:
    """
    从 IMU DataFrame 中挑选一个“最合理的 yaw 列名”：

      优先级（从高到低）：
        1) yaw_nav_rad, yaw_device_rad, yaw_rad
        2) YawEst_rad, YawEst_unwrapped_rad
        3) YawEst_deg, YawDeg, AngZ_deg, AngZ

      返回列名字符串；如果一个都找不到，返回 None。
    """
    # 1) 明确标成 rad 的 yaw
    cand_rad = [
        "yaw_nav_rad",
        "yaw_device_rad",
        "yaw_rad",
        "YawEst_rad",
        "YawEst_unwrapped_rad",
    ]
    for c in cand_rad:
        if c in df_imu.columns:
            return c

    # 2) 退回到 deg 版本
    cand_deg = [
        "YawEst_deg",
        "YawEst_unwrapped_deg",
        "YawDeg",
        "AngZ_deg",
        "AngZ",
    ]
    for c in cand_deg:
        if c in df_imu.columns:
            return c

    return None


def _interp_attitude_from_imu(
    df_imu: pd.DataFrame,
    t_imu: np.ndarray,
    t_query: float,
) -> AttitudeRPY:
    """
    在 IMU 时间轴上用最近邻给 t_query 找一个姿态。

    优先使用预处理列（单位 rad）：
      - roll_rad, pitch_rad
      - yaw_nav_rad / yaw_device_rad / yaw_rad / YawEst_rad / YawEst_unwrapped_rad

    若没有预处理列，再回退到原始 AngX/AngY/AngZ (deg) / YawDeg (deg)。
    """
    # ===== 只在首次调用时打印一次列名，确认 deadreckon 用的是哪份 IMU =====
    if not hasattr(_interp_attitude_from_imu, "_debug_printed_cols"):
        print("[IMU-YAW][DEBUG] IMU columns used in deadreckon:")
        print("    ", list(df_imu.columns))
        _interp_attitude_from_imu._debug_printed_cols = True

    if len(t_imu) == 0:
        return AttitudeRPY(roll=0.0, pitch=0.0, yaw=0.0)

    # 最近邻索引
    idx = int(np.searchsorted(t_imu, t_query))
    if idx <= 0:
        i = 0
    elif idx >= len(t_imu):
        i = len(t_imu) - 1
    else:
        if abs(t_imu[idx] - t_query) < abs(t_imu[idx - 1] - t_query):
            i = idx
        else:
            i = idx - 1

    row = df_imu.iloc[i]

    # ---- 1) 预处理版：roll_rad / pitch_rad / yaw_*_rad ----
    if "roll_rad" in df_imu.columns and "pitch_rad" in df_imu.columns:
        roll = float(row["roll_rad"])
        pitch = float(row["pitch_rad"])

        yaw_col = _pick_yaw_column(df_imu)

        if yaw_col is None:
            # 第一次缺失 yaw 时，打印一次完整表头，方便排查
            if not hasattr(_interp_attitude_from_imu, "_warned_no_yaw"):
                print("[IMU-YAW][WARN] No yaw column found in IMU processed CSV.")
                print("              Available columns:", list(df_imu.columns))
                _interp_attitude_from_imu._warned_no_yaw = True
            yaw = 0.0
        else:
            val = row[yaw_col]
            # yaw 列如果名字里带 "deg"，按角度制处理
            if "deg" in yaw_col.lower():
                yaw = np.deg2rad(float(val))
            else:
                yaw = float(val)

        # 防止 NaN
        if not np.isfinite(roll):
            roll = 0.0
        if not np.isfinite(pitch):
            pitch = 0.0
        if not np.isfinite(yaw):
            yaw = 0.0

    # ---- 2) 原始版：直接用设备的 AngX/AngY/AngZ / YawDeg ----
    else:
        roll = np.deg2rad(float(row.get("AngX", 0.0)))
        pitch = np.deg2rad(float(row.get("AngY", 0.0)))

        if "AngZ" in df_imu.columns:
            yaw = np.deg2rad(float(row["AngZ"]))
        elif "YawDeg" in df_imu.columns:
            yaw = np.deg2rad(float(row["YawDeg"]))
        else:
            yaw = 0.0

    # yaw wrap 到 (-pi, pi]
    yaw = float(wrap_angle_pm_pi(yaw))

    return AttitudeRPY(roll=roll, pitch=pitch, yaw=yaw)


# =============================================================================
# 诊断信息
# =============================================================================

@dataclass
class DeadReckonDiagnostics:
    n_imu: int
    n_dvl: int
    n_used: int
    duration_s: float
    mean_speed_body: float
    max_speed_body: float


# =============================================================================
# 三种模式的 deadreckon 主函数入口
# =============================================================================

def run_deadreckon_pipeline(
    imu_raw: ImuRawData,
    dvl_raw: DvlRawData,
    cfg: DeadReckonConfig,
) -> Tuple[Trajectory, DeadReckonDiagnostics]:
    """
    死算基线轨迹（支持三种模式）：

      mode:
        - "IMU_only"     : 只用 IMU 做惯导积分（p,v 均由 IMU 加速度 + 姿态积分得到）；
        - "DVL_BE_only"  : 只用 DVL_BE 的 ENU 速度积分位置；
        - "IMU+DVL"      : DVL 体速度 + IMU 姿态（你原来的默认逻辑）。

      nav frame：统一使用 ENU（E,N,U；U 向上）。
    """
    mode = (getattr(cfg, "mode", "IMU+DVL") or "IMU+DVL").upper()

    if mode == "IMU_ONLY":
        return _run_deadreckon_imu_only(imu_raw, dvl_raw, cfg)
    elif mode == "DVL_BE_ONLY":
        return _run_deadreckon_dvl_be_only(imu_raw, dvl_raw, cfg)
    elif mode in ("IMU+DVL", "IMU_DVL", "IMU_PLUS_DVL"):
        return _run_deadreckon_imu_plus_dvl(imu_raw, dvl_raw, cfg)
    else:
        print(f"[DEADRECKON][WARN] unknown mode {cfg.mode!r}, fallback to 'IMU+DVL'")
        return _run_deadreckon_imu_plus_dvl(imu_raw, dvl_raw, cfg)


# =============================================================================
# 模式 1：IMU_only —— 只用 IMU 加速度 + 姿态积分
# =============================================================================

def _run_deadreckon_imu_only(
    imu_raw: ImuRawData,
    dvl_raw: DvlRawData,
    cfg: DeadReckonConfig,
) -> Tuple[Trajectory, DeadReckonDiagnostics]:
    df_imu = imu_raw.df
    t_imu = _get_time_s_from_imu(imu_raw)
    n_imu = len(df_imu)
    n_dvl = len(dvl_raw.df)

    if n_imu < 2:
        raise ValueError("IMU 数据过少，无法做 IMU_only dead-reckon（n_imu < 2）")

    acc_body = _extract_imu_acc_body(df_imu)  # (N_imu, 3)

    # ---- dt 统计与时间守恒 ----
    dt_all = np.diff(t_imu)
    dt_all = dt_all[np.isfinite(dt_all) & (dt_all > 0.0)]
    if dt_all.size > 0:
        dt_med = float(np.median(dt_all))
        dt_p95 = float(np.percentile(dt_all, 95))
    else:
        dt_med = dt_p95 = 0.0

    cfg_max_gap = float(getattr(cfg, "max_gap_s", 0.0) or 0.0)
    if dt_med > 0.0:
        if cfg_max_gap <= 0.0:
            dt_guard = 5.0 * dt_med
        elif cfg_max_gap < 1.5 * dt_med:
            dt_guard = 3.0 * dt_med
        else:
            dt_guard = cfg_max_gap
    else:
        dt_guard = float("inf")

    # 初始状态
    p = np.array(
        [cfg.init_pose.E, cfg.init_pose.N, cfg.init_pose.U],
        dtype=float,
    )
    v = np.zeros(3, dtype=float)

    t_out: List[float] = []
    E_out: List[float] = []
    N_out: List[float] = []
    U_out: List[float] = []
    yaw_out: List[float] = []

    use_angles = True  # IMU_only 必须依赖 IMU 姿态
    yaw_arr_collect: List[float] = []

    for k in range(n_imu):
        tk = float(t_imu[k])
        if k == 0:
            dt = 0.0
        else:
            dt_raw = tk - float(t_imu[k - 1])
            if (not np.isfinite(dt_raw)) or (dt_raw <= 0.0):
                dt = 0.0
            elif dt_raw > dt_guard:
                dt = 0.0
            else:
                dt = dt_raw

        if use_angles:
            att = _interp_attitude_from_imu(df_imu, t_imu, tk)
        else:
            att = AttitudeRPY(roll=0.0, pitch=0.0, yaw=0.0)

        R_nb = rpy_to_R_nb(att)                # nav(ENU) <- body(FRD)
        a_b = acc_body[k, :]                   # 体坐标加速度
        a_n = R_nb @ a_b                       # 转到 ENU

        # 这里不做额外的重力补偿假设，只作为“IMU-only 漂移基线”使用
        v = v + a_n * dt
        p = p + v * dt

        t_out.append(tk)
        E_out.append(float(p[0]))
        N_out.append(float(p[1]))
        U_out.append(float(p[2]))
        yaw_out.append(float(att.yaw))
        yaw_arr_collect.append(float(att.yaw))

    t_out_arr = np.asarray(t_out, dtype=float)
    E_arr = np.asarray(E_out, dtype=float)
    N_arr = np.asarray(N_out, dtype=float)
    U_arr = np.asarray(U_out, dtype=float)
    yaw_arr = np.asarray(yaw_out, dtype=float)

    duration_s = float(t_out_arr[-1] - t_out_arr[0]) if len(t_out_arr) >= 2 else 0.0

    # 速度统计（严格说是 ENU 速度，但沿用 mean_speed_body 字段名）
    speeds = np.linalg.norm(np.vstack([np.diff(E_arr, prepend=E_arr[0]),
                                       np.diff(N_arr, prepend=N_arr[0]),
                                       np.diff(U_arr, prepend=U_arr[0])]).T, axis=1)
    mean_speed = float(np.nanmean(speeds))
    max_speed = float(np.nanmax(speeds))

    traj = Trajectory(
        t_s=t_out_arr,
        E=E_arr,
        N=N_arr,
        U=U_arr,
        yaw_rad=yaw_arr,
    )

    diag = DeadReckonDiagnostics(
        n_imu=n_imu,
        n_dvl=n_dvl,
        n_used=0,
        duration_s=duration_s,
        mean_speed_body=mean_speed,
        max_speed_body=max_speed,
    )

    if use_angles and len(yaw_arr_collect) > 0:
        print(
            f"[DEADRECKON][IMU_ONLY][YAW] "
            f"min={np.nanmin(yaw_arr_collect):.3f} rad  "
            f"max={np.nanmax(yaw_arr_collect):.3f} rad  "
            f"mean={np.nanmean(yaw_arr_collect):.3f} rad"
        )

    return traj, diag


# =============================================================================
# 模式 2：DVL_BE_only —— 只用 DVL_BE ENU 速度积分位置
# =============================================================================

def _run_deadreckon_dvl_be_only(
    imu_raw: ImuRawData,
    dvl_raw: DvlRawData,
    cfg: DeadReckonConfig,
) -> Tuple[Trajectory, DeadReckonDiagnostics]:
    df_dvl = dvl_raw.df
    df_imu = imu_raw.df  # 只用于统计 & 可选 yaw 初值
    t_dvl = _get_time_s_from_dvl(df_dvl)

    n_imu = len(df_imu)
    n_dvl = len(df_dvl)

    if n_dvl < 2:
        raise ValueError("DVL 数据过少，无法做 DVL_BE_only dead-reckon（n_dvl < 2）")

    vel_enu_all = _extract_enu_velocity(df_dvl)  # (N_dvl, 3)

    idx_used = _select_dvl_indices(df_dvl, t_dvl, cfg)
    if len(idx_used) < 2:
        raise ValueError(
            f"有效 DVL 样本过少：n_used={len(idx_used)}，"
            "请检查 Src / GateOk / SpeedOk / deadreckon.dvl_src 配置，或 DVL 预处理门控。"
        )

    t_d = t_dvl[idx_used]
    vel_enu = vel_enu_all[idx_used, :]

    # dt 统计
    dt_all = np.diff(t_d)
    dt_all = dt_all[np.isfinite(dt_all) & (dt_all > 0.0)]
    if dt_all.size > 0:
        dt_med = float(np.median(dt_all))
        dt_p95 = float(np.percentile(dt_all, 95))
    else:
        dt_med = dt_p95 = 0.0

    cfg_max_gap = float(getattr(cfg, "max_gap_s", 0.0) or 0.0)
    if dt_med > 0.0:
        if cfg_max_gap <= 0.0:
            dt_guard = 5.0 * dt_med
        elif cfg_max_gap < 1.5 * dt_med:
            dt_guard = 3.0 * dt_med
        else:
            dt_guard = cfg_max_gap
    else:
        dt_guard = float("inf")

    # 速度统计（ENU 速度）
    speed = np.linalg.norm(vel_enu, axis=1)
    mean_speed = float(np.nanmean(speed))
    max_speed = float(np.nanmax(speed))

    # 积分位置（ENU）
    p = np.array(
        [cfg.init_pose.E, cfg.init_pose.N, cfg.init_pose.U],
        dtype=float,
    )

    t_out: List[float] = []
    E_out: List[float] = []
    N_out: List[float] = []
    U_out: List[float] = []
    yaw_out: List[float] = []

    # yaw：从 DVL 速度方向估计；若速度太小，则保持上一帧 yaw
    yaw_cur = float(np.deg2rad(cfg.init_pose.yaw_deg))

    for k in range(len(t_d)):
        tk = float(t_d[k])
        if k == 0:
            dt = 0.0
        else:
            dt_raw = tk - float(t_d[k - 1])
            if (not np.isfinite(dt_raw)) or (dt_raw <= 0.0):
                dt = 0.0
            elif dt_raw > dt_guard:
                dt = 0.0
            else:
                dt = dt_raw

        v_n = vel_enu[k, :]  # ENU 速度

        # 推一个基于水平速度的 yaw
        vE, vN = float(v_n[0]), float(v_n[1])
        spd_h = float(np.hypot(vE, vN))
        if spd_h > 1e-3:
            yaw_cur = float(wrap_angle_pm_pi(np.arctan2(vN, vE)))

        p = p + v_n * dt

        t_out.append(tk)
        E_out.append(float(p[0]))
        N_out.append(float(p[1]))
        U_out.append(float(p[2]))
        yaw_out.append(yaw_cur)

    t_out_arr = np.asarray(t_out, dtype=float)
    E_arr = np.asarray(E_out, dtype=float)
    N_arr = np.asarray(N_out, dtype=float)
    U_arr = np.asarray(U_out, dtype=float)
    yaw_arr = np.asarray(yaw_out, dtype=float)

    duration_s = float(t_out_arr[-1] - t_out_arr[0]) if len(t_out_arr) >= 2 else 0.0

    traj = Trajectory(
        t_s=t_out_arr,
        E=E_arr,
        N=N_arr,
        U=U_arr,
        yaw_rad=yaw_arr,
    )

    diag = DeadReckonDiagnostics(
        n_imu=n_imu,
        n_dvl=n_dvl,
        n_used=len(idx_used),
        duration_s=duration_s,
        mean_speed_body=mean_speed,
        max_speed_body=max_speed,
    )

    print(
        f"[DEADRECKON][DVL_BE_ONLY] "
        f"speed: mean={mean_speed:.3f} m/s  max={max_speed:.3f} m/s"
    )

    return traj, diag


# =============================================================================
# 模式 3：IMU+DVL —— 原始逻辑：DVL 体速度 + IMU 姿态
# =============================================================================

def _run_deadreckon_imu_plus_dvl(
    imu_raw: ImuRawData,
    dvl_raw: DvlRawData,
    cfg: DeadReckonConfig,
) -> Tuple[Trajectory, DeadReckonDiagnostics]:
    """
    保留你原来的实现：DVL 体速度 + IMU 姿态，位置积分在 DVL 时间上进行。
    """
    df_imu = imu_raw.df
    df_dvl = dvl_raw.df

    t_imu = _get_time_s_from_imu(imu_raw)
    t_dvl = _get_time_s_from_dvl(df_dvl)

    n_imu = len(df_imu)
    n_dvl = len(df_dvl)

    if n_dvl < 2:
        raise ValueError("DVL 数据过少，无法做 dead-reckon（n_dvl < 2）")

    # 1) 提取“DVL 报文里的体速度”，先按原列名拿出来
    vel_body_all_raw = _extract_body_velocity(df_dvl)  # (N,3)，当前坐标系 = DVL/IMU 本地系

    # 2) 根据 Src / GateOk / SpeedOk 等选择有效 DVL 样本
    idx_used = _select_dvl_indices(df_dvl, t_dvl, cfg)
    if len(idx_used) < 2:
        raise ValueError(
            f"有效 DVL 样本过少：n_used={len(idx_used)}，"
            "请检查 Src / GateOk / SpeedOk / deadreckon.dvl_src 配置，或 DVL 预处理门控。"
        )

    # 只保留有效样本，并把“本地系速度”映射到 body=FRD
    t_d = t_dvl[idx_used]
    vel_body_raw = vel_body_all_raw[idx_used, :]          # (N_used, 3)

    # ★ 把 DVL_BI 认为是“IMU 坐标系”，统一转到 FRD
    vel_body = (R_BODY_FRD_FROM_IMU @ vel_body_raw.T).T   # (N_used, 3)

    # ---- dt 统计：估计 DVL 真实采样周期 ----
    if len(t_d) >= 2:
        dt_all = np.diff(t_d)
        dt_all = dt_all[np.isfinite(dt_all) & (dt_all > 0.0)]
        if dt_all.size > 0:
            dt_med = float(np.median(dt_all))
            dt_p95 = float(np.percentile(dt_all, 95))
        else:
            dt_med = dt_p95 = 0.0
    else:
        dt_med = dt_p95 = 0.0

    cfg_max_gap = float(getattr(cfg, "max_gap_s", 0.0) or 0.0)

    if dt_med > 0.0:
        if cfg_max_gap <= 0.0:
            dt_guard = 5.0 * dt_med
        elif cfg_max_gap < 1.5 * dt_med:
            dt_guard = 3.0 * dt_med
        else:
            dt_guard = cfg_max_gap
    else:
        dt_guard = float("inf")

    # 体速度统计
    speed_body = np.linalg.norm(vel_body, axis=1)
    mean_speed_body = float(np.nanmean(speed_body))
    max_speed_body = float(np.nanmax(speed_body))

    # 3) 位置积分（ENU）+ yaw 输出
    p0 = np.array(
        [cfg.init_pose.E, cfg.init_pose.N, cfg.init_pose.U],
        dtype=float,
    )
    p = p0.copy()

    t_out: List[float] = []
    E_out: List[float] = []
    N_out: List[float] = []
    U_out: List[float] = []
    yaw_out: List[float] = []  # 记录每一步使用的 yaw，方便下游可视化 / 对比

    use_angles = _as_bool(getattr(cfg, "use_imu_angles", True), default=True)

    for k in range(len(t_d)):
        tk = float(t_d[k])
        if k == 0:
            dt = 0.0
        else:
            dt_raw = tk - float(t_d[k - 1])
            if (not np.isfinite(dt_raw)) or (dt_raw <= 0.0):
                dt = 0.0
            elif dt_raw > dt_guard:
                dt = 0.0
            else:
                dt = dt_raw

        # 姿态对齐
        if use_angles:
            att = _interp_attitude_from_imu(df_imu, t_imu, tk)
        else:
            att = AttitudeRPY(roll=0.0, pitch=0.0, yaw=0.0)

        # 体速度 -> ENU 速度
        v_b = vel_body[k, :]        # (3,)
        R_nb = rpy_to_R_nb(att)     # nav(ENU) <- body(FRD)
        v_n = R_nb @ v_b            # (3,)

        # 积分位置
        p = p + v_n * dt

        t_out.append(tk)
        E_out.append(float(p[0]))
        N_out.append(float(p[1]))
        U_out.append(float(p[2]))
        yaw_out.append(float(att.yaw))

    t_out_arr = np.asarray(t_out, dtype=float)
    E_arr = np.asarray(E_out, dtype=float)
    N_arr = np.asarray(N_out, dtype=float)
    E_world = E_arr
    N_world = N_arr
    U_arr = np.asarray(U_out, dtype=float)
    yaw_arr = np.asarray(yaw_out, dtype=float)

    duration_s = float(t_out_arr[-1] - t_out_arr[0]) if len(t_out_arr) >= 2 else 0.0

    traj = Trajectory(
        t_s=t_out_arr,
        E=E_arr,
        N=N_world,
        U=U_arr,
        yaw_rad=yaw_arr,  # 把 dead-reckon 过程中使用的 yaw 存进来
    )

    diag = DeadReckonDiagnostics(
        n_imu=n_imu,
        n_dvl=n_dvl,
        n_used=len(idx_used),
        duration_s=duration_s,
        mean_speed_body=mean_speed_body,
        max_speed_body=max_speed_body,
    )

    # 可选：打一条简单的 yaw 使用诊断
    if use_angles and len(yaw_arr) > 0:
        print(
            f"[DEADRECKON][IMU+DVL][YAW] "
            f"min={np.nanmin(yaw_arr):.3f} rad  "
            f"max={np.nanmax(yaw_arr):.3f} rad  "
            f"mean={np.nanmean(yaw_arr):.3f} rad"
        )
    elif not use_angles:
        print("[DEADRECKON][IMU+DVL][YAW] use_imu_angles=False, dead-reckon is yaw-agnostic (body≈nav).")

    return traj, diag
