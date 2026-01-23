# offline_nav/src/offnav/eskf/config.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Eskf2DConfig:
    # --------------------------
    # 时间 / 数值稳定
    # --------------------------
    dt_max_s: float = 0.05
    dt_min_s: float = 1.0e-4
    yaw_wrap: bool = True

    # --------------------------
    # 初始化策略（最小化开关：只控制“初始 yaw 用谁”）
    # --------------------------
    # "imu": use IMU yaw (with yaw_sign + yaw_offset_rad) at first valid sample
    # "config": use init_yaw_rad (still wrapped if yaw_wrap=True)
    init_yaw_source: str = "imu"   # "imu" | "config"

    # --------------------------
    # IMU 输入含义
    # --------------------------
    imu_acc_is_linear: bool = True
    gravity_mps2: float = 9.78

    # yaw 语义（最小约定，避免引入更多坐标开关）：
    # used_yaw = yaw_sign * yaw_meas + yaw_offset_rad
    yaw_sign: float = 1.0
    yaw_offset_rad: float = 0.0   # fixed constant bias applied to IMU yaw measurement (rad)
   # yaw_offset_rad: float = 1.5707963267948966   # +90 deg
    # 或者
  #  yaw_offset_rad: float = -1.5707963267948966  # -90 deg


    # --------------------------
    # 过程噪声（核心）
    # --------------------------
    # sigma_acc_mps2: std of sampled linear acceleration (m/s^2), discrete-time
    sigma_acc_mps2: float = 0.06

    # sigma_gyro_z_rad_s: std of sampled gyro_z (rad/s), discrete-time (NOT noise density /sqrt(Hz))
    sigma_gyro_z_rad_s: float = 0.008

    # sigma_bgz_rw: bgz random-walk std in (rad/s)/sqrt(s)
    sigma_bgz_rw: float = 2.0e-5

    # --------------------------
    # DVL 观测噪声（水平速度 m/s）
    # --------------------------
    sigma_dvl_xy_mps: float = 0.008

    # ZUPT-like
    zupt_speed_mps: float = 0.04
    sigma_dvl_zupt_mps: float = 0.06

    # --------------------------
    # 初值
    # --------------------------
    init_E: float = 0.0
    init_N: float = 0.0
    init_vE: float = 0.0
    init_vN: float = 0.0
    init_yaw_rad: float = 0.0
    init_bgz: float = 0.0

    # 初始协方差（越大表示越不信初值）
    P0_pos_m2: float = 0.5**2
    P0_vel_m2s2: float = 0.6**2
    P0_yaw_rad2: float = (10.0 * 3.1415926535 / 180.0) ** 2
    P0_bgz_rad2s2: float = (0.02) ** 2

    # --------------------------
    # 输出控制
    # --------------------------
    output_full_rate: bool = True
    output_stride: int = 5

    # 诊断 CSV（聚焦：dt、v_pre、v_meas、ratio、nis）
    focus_csv_path: Optional[str] = "out/diag/eskf2d_focus.csv"
    focus_record_every: int = 1
    focus_ratio_warn: float = 4.0
    focus_vpre_warn: float = 1.2
    focus_nis_warn: float = 80.0

    print_summary: bool = True

    # -------------------------
    # Propagation stabilizer (engineering)
    # -------------------------
    vel_leak_1ps: float = 0.35
    v_hard_max_mps: float = 0.80

    # -------------------------
    # DVL gating / inflation
    # -------------------------
    nis_soft: float = 25.0
    nis_target: float = 25.0
    nis_hard: float = 120.0

    ratio_soft: float = 2.5
    ratio_hard: float = 10.0

    # meas_speed_eps_mps: denominator floor used only for ratio checks (avoid low-speed blowups)
    # keep > zupt_speed_mps to reduce ratio jitter near zero
    meas_speed_eps_mps: float = 0.07

    r_inflate_max: float = 5e3
    post_inflate_hard_reject: bool = False

    # 兜底：极端离群保护（默认几乎不触发，但防止明显坏数据把状态扭飞）
    reject_huge_residual: bool = True
    nis_abs_hard: float = 300.0

    # 数值稳定 jitter
    meas_jitter: float = 1e-9
    S_jitter: float = 1e-9

    # -------------------------
    # Process noise tuning (admit model is bad)
    # -------------------------
    q_vel_extra_mps2: float = 1.20
