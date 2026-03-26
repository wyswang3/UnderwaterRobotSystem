# src/offnav/algo/eskf_measurements.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from offnav.algo.eskf_common import EskfInputs, get_roll_pitch_rad
from offnav.algo.event_timeline import (
    extract_dvl_be_vel_enu,
    extract_dvl_bi_vel_body_frd,
    extract_dvl_quality_row,
)
from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb


# =============================================================================
# DVL 派生量：一次提取，给 ESKF 反复使用
# =============================================================================

@dataclass
class DvlDerivedSignals:
    """
    对 DVL DataFrame 做一次性提取的派生量容器。

    重要约定（修正后的坐标系一致性）：
      - BE 速度：ENU（E, N, U），U 为“向上”为正
      - BI 速度：body(FRD)，X 前 Y 右 Z 下

    - v_be_enu : (N,3) BE 帧下的 ENU 速度（原始）
    - v_bi_body: Optional[(N,3)] BI 帧下的 body(FRD) 速度（若有 BI）
    - df_be    : 原始 BE DataFrame（用于质量 / flag 提取）
    """
    v_be_enu: np.ndarray
    df_be: pd.DataFrame
    v_bi_body: Optional[np.ndarray] = None

    @classmethod
    def from_inputs(cls, inputs: EskfInputs) -> "DvlDerivedSignals":
        df_be = inputs.dvl_be_df
        df_bi = inputs.dvl_bi_df

        if df_be is None:
            raise RuntimeError("[ESKF][MEAS] dvl_be_df is None, cannot build DvlDerivedSignals")

        # 1) BE → ENU 速度（原始）
        v_be_enu = extract_dvl_be_vel_enu(df_be)

        # 2) BI → body(FRD) 速度（如果有 BI）
        v_bi_body: Optional[np.ndarray] = None
        if df_bi is not None:
            try:
                v_bi_body = extract_dvl_bi_vel_body_frd(df_bi)
                print(f"[ESKF][MEAS] BI body-vel loaded, len={len(v_bi_body)}")
            except Exception as e:
                print(f"[ESKF][MEAS] BI body-vel extract failed, err={e!r}")
                v_bi_body = None
        else:
            print("[ESKF][MEAS] No BI dataframe, fallback to BE-only horizontal velocity")

        return cls(
            v_be_enu=np.asarray(v_be_enu, dtype=float),
            df_be=df_be,
            v_bi_body=None if v_bi_body is None else np.asarray(v_bi_body, dtype=float),
        )


# =============================================================================
# 工具：按时间索引从 IMU 序列里取 yaw
# =============================================================================

def _pick_yaw_at_index(imu_proc: Any, k: int, eskf: Any) -> float:
    """
    从 IMU 预处理结果/ESKF 里“尽量合理”地取出时刻 k 的 yaw（rad）。

    优先级（有哪个用哪个）：
      1) imu_proc.yaw_nav_rad[k]
      2) imu_proc.yaw_rad[k]
      3) imu_proc.yaw_imu_rad[k]
      4) eskf.yaw_rad （若存在）
      5) 0.0 作为兜底
    """
    yaw_field_candidates = (
        "yaw_nav_rad",
        "yaw_rad",
        "yaw_imu_rad",
    )

    for name in yaw_field_candidates:
        if hasattr(imu_proc, name):
            arr = getattr(imu_proc, name)
            try:
                if arr is not None and len(arr) > k:
                    val = float(arr[k])
                    if np.isfinite(val):
                        return val
            except Exception:
                continue

    if hasattr(eskf, "yaw_rad"):
        try:
            val = float(getattr(eskf, "yaw_rad"))
            if np.isfinite(val):
                return val
        except Exception:
            pass

    return 0.0


# =============================================================================
# DVL-BE 观测构造：BE/BI + IMU 姿态 → nav(ENU) 速度测量
# =============================================================================

def build_dvl_be_measurement(
    j: int,
    k: int,
    t_dvl: float,
    imu_t: np.ndarray,
    imu_proc: Any,
    eskf: Any,
    nav_cfg: Any,
    derived: DvlDerivedSignals,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    针对 DVL-BE 事件 (j, k, t_dvl)，生成：

      - v_meas: np.ndarray shape (3,), nav(ENU) 下的速度测量
        - 修正点：这里必须保持 ENU 约定（U 向上为正），不做 Up→Down 翻转
        - x/y 分量：
            - 若配置/数据允许：BI(body FRD) + IMU 姿态 (roll/pitch/yaw) → nav(ENU)
            - 否则：退回 BE 的 ENU 水平速度
      - row   : dict 基础字段（时间 / src / src_xy / speed 等），供 ESKF 管线补充审计信息

    注意：不做门控/阈值判断，也不调用 ESKF 更新；门控在 engine 层完成。
    """
    # ---------- 基本索引与时间 ----------
    t_imu_anchor = float(imu_t[k])
    dt = t_imu_anchor - float(t_dvl)

    # ---------- BE: ENU 速度（原始） ----------
    if not (0 <= j < len(derived.v_be_enu)):
        raise IndexError(
            f"[ESKF][MEAS] DVL BE index out of range: j={j}, len={len(derived.v_be_enu)}"
        )

    # BE 输出即 ENU（U 向上为正）
    v_be = np.asarray(derived.v_be_enu[j], dtype=float).reshape(3)
    v_meas = v_be.copy()  # 先全量采用 BE

    # ---------- 水平：优先 BI + IMU 姿态 ----------
    use_bi_cfg = bool(getattr(nav_cfg.eskf, "use_dvl_BI_vel", True))
    same_len = derived.v_bi_body is not None and len(derived.v_bi_body) == len(derived.v_be_enu)
    has_bi_sample = same_len and 0 <= j < len(derived.v_bi_body)  # only safe when BI/BE are aligned by row
    src_xy = "BE"

    if use_bi_cfg and has_bi_sample:
        try:
            # 1) BI 提供的 body(FRD) 速度
            v_b = np.asarray(derived.v_bi_body[j], dtype=float).reshape(3)

            # 2) IMU 提供 roll/pitch + yaw
            roll_rad, pitch_rad = get_roll_pitch_rad(imu_proc, k)
            yaw_rad = _pick_yaw_at_index(imu_proc, k, eskf)

            # R_nb: nav(ENU) <- body(FRD)
            R_nb = rpy_to_R_nb(AttitudeRPY(roll_rad, pitch_rad, yaw_rad))
            v_nav = R_nb @ v_b

            # 仅替换水平分量；垂向仍以 BE 的 U 为主（更稳健）
            v_meas[0] = float(v_nav[0])
            v_meas[1] = float(v_nav[1])
            src_xy = "BI"
        except Exception as e:
            print(f"[ESKF][MEAS][BI-FAIL] j={j}, fallback to BE, err={e!r}")
            v_meas[0] = float(v_be[0])
            v_meas[1] = float(v_be[1])
            src_xy = "BE"
    else:
        v_meas[0] = float(v_be[0])
        v_meas[1] = float(v_be[1])
        src_xy = "BE"

    v_meas = v_meas.astype(float).reshape(3)

    speed_h = float(np.hypot(v_meas[0], v_meas[1]))
    speed_3d = float(np.linalg.norm(v_meas))

    # ---------- 审计基础字段 ----------
    row: Dict[str, Any] = {
        "t_imu_s": t_imu_anchor,
        "t_dvl_s": float(t_dvl),
        "dt_match_s": dt,
        "src": "BE",          # 观测类型：BE-ENU 速度事件
        "src_xy": src_xy,     # 水平速度来源：BI / BE
        "vE": float(v_meas[0]),
        "vN": float(v_meas[1]),
        "vU": float(v_meas[2]),

        "speed_h": speed_h,
        "speed_3d": speed_3d,

        # 明确标注：BE 的垂向是 Up 为正（与 vU 一致）
        "vU_from_be": float(v_be[2]),
    }

    # 质量/flags 从 df_be 提取（若实现了 extract_dvl_quality_row）
    try:
        q = extract_dvl_quality_row(derived.df_be, j)
        row.update(q)
    except Exception:
        pass

    return v_meas, row
# =============================================================================
# DVL-BI 观测构造：BE/BI + IMU 姿态 → nav(ENU) 速度测量
# =============================================================================
def build_dvl_bi_measurement(
    j: int,
    k: int,
    t_dvl: float,
    imu_t: np.ndarray,
    imu_proc: Any,
    eskf: Any,
    nav_cfg: Any,
    derived: Any,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    针对 DVL-BI 事件 (j,k,t_dvl)，生成：
      - v_meas: nav(ENU) 速度观测（由 BI body(FRD) + IMU 姿态转换得到）
      - row: 审计字段
    """
    t_imu_anchor = float(imu_t[k])
    dt = t_imu_anchor - float(t_dvl)

    if derived.v_bi_body is None:
        raise RuntimeError("[ESKF][MEAS] derived.v_bi_body is None (no BI velocity available).")
    if not (0 <= j < len(derived.v_bi_body)):
        raise IndexError(f"[ESKF][MEAS] DVL BI index out of range: j={j}, len={len(derived.v_bi_body)}")

    v_b = np.asarray(derived.v_bi_body[j], dtype=float).reshape(3)

    roll_rad, pitch_rad = get_roll_pitch_rad(imu_proc, k)
    yaw_rad = _pick_yaw_at_index(imu_proc, k, eskf)  # 你工程已有的 yaw 取法

    R_nb = rpy_to_R_nb(AttitudeRPY(roll_rad, pitch_rad, yaw_rad))
    v_nav = (R_nb @ v_b).astype(float).reshape(3)

    speed_h = float(np.hypot(v_nav[0], v_nav[1]))
    speed_3d = float(np.linalg.norm(v_nav))

    row: Dict[str, Any] = {
        "t_imu_s": t_imu_anchor,
        "t_dvl_s": float(t_dvl),
        "dt_match_s": float(dt),

        "src": "BI",
        "src_xy": "BI",

        "vE": float(v_nav[0]),
        "vN": float(v_nav[1]),
        "vU": float(v_nav[2]),

        "speed_h": speed_h,
        "speed_3d": speed_3d,

        # 方便排查：原始 BI body 速度也留一下
        "vbx": float(v_b[0]),
        "vby": float(v_b[1]),
        "vbz": float(v_b[2]),
    }

    # 若你有 BI 的质量字段（通常在 df_be 同帧），也可以同样提取
    try:
        q = extract_dvl_quality_row(derived.df_be, j)
        row.update(q)
    except Exception:
        pass

    return v_nav, row
