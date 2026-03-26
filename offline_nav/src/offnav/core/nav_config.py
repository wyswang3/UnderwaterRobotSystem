# src/offnav/core/nav_config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import numpy as np
import yaml


# =====================================================================
# 基础工具
# =====================================================================

DEFAULT_NAV_CONFIG_PATH = Path("configs/nav.yaml")


def _as_float(d: Mapping[str, Any], key: str, default: float) -> float:
    v = d.get(key, default)
    return float(v)


def _as_bool(d: Mapping[str, Any], key: str, default: bool) -> bool:
    v = d.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("1", "true", "yes", "on")
    return bool(v)


def _as_str(d: Mapping[str, Any], key: str, default: str) -> str:
    v = d.get(key, default)
    return str(v)


def _as_axis_map(d: Mapping[str, Any], key: str, default: Optional[np.ndarray] = None) -> np.ndarray:
    v = d.get(key, None)
    if v is None:
        if default is None:
            raise KeyError(f"axis_map {key!r} missing and no default provided")
        return default
    arr = np.asarray(v, dtype=float)
    if arr.shape != (3, 3):
        raise ValueError(f"{key!r} must be 3x3 matrix, got shape {arr.shape}")
    return arr


# =====================================================================
# deadreckon 配置
# =====================================================================
@dataclass
class DeadReckonInitPose:
    E: float = 0.0
    N: float = 0.0
    U: float = 0.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DeadReckonInitPose":
        if d is None:
            d = {}
        return cls(
            E=_as_float(d, "E", 0.0),
            N=_as_float(d, "N", 0.0),
            U=_as_float(d, "U", 0.0),
            yaw_deg=_as_float(d, "yaw_deg", 0.0),
            pitch_deg=_as_float(d, "pitch_deg", 0.0),
            roll_deg=_as_float(d, "roll_deg", 0.0),
        )


@dataclass
class DeadReckonConfig:
    """
    deadreckon 模式配置：

      mode:
        - "IMU_only"     : 只用 IMU 做惯导积分（完全不看 DVL）
        - "DVL_BE_only"  : 只用 DVL_BE 的 ENU 速度积分位置
        - "IMU+DVL"      : IMU 提供姿态/辅助，DVL 提供速度的混合死算基线
    """
    mode: str = "IMU+DVL"          # IMU_only / DVL_BE_only / IMU+DVL

    dvl_src: str = "BI"
    use_processed_imu: bool = True
    use_processed_dvl: bool = True
    init_pose: DeadReckonInitPose = DeadReckonInitPose()
    use_imu_angles: bool = True
    max_gap_s: float = 0.05

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DeadReckonConfig":
        if d is None:
            d = {}
        init_pose = DeadReckonInitPose.from_dict(d.get("init_pose", {}))
        return cls(
            mode=_as_str(d, "mode", "IMU+DVL"),
            dvl_src=_as_str(d, "dvl_src", "BI"),
            use_processed_imu=_as_bool(d, "use_processed_imu", True),
            use_processed_dvl=_as_bool(d, "use_processed_dvl", True),
            init_pose=init_pose,
            use_imu_angles=_as_bool(d, "use_imu_angles", True),
            max_gap_s=_as_float(d, "max_gap_s", 0.05),
        )

# =====================================================================
# ESKF 配置
# =====================================================================

@dataclass
class ImuNoiseConfig:
    sigma_acc_mps2: float = 0.01
    sigma_gyro_rad_s: float = 0.001
    sigma_ba_rw_mps2_sqrt_s: float = 1.0e-5
    sigma_bgz_rw_rad_s_sqrt_s: float = 1.0e-5

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "ImuNoiseConfig":
        if d is None:
            d = {}
        return cls(
            sigma_acc_mps2=_as_float(d, "sigma_acc_mps2", 0.01),
            sigma_gyro_rad_s=_as_float(d, "sigma_gyro_rad_s", 0.001),
            sigma_ba_rw_mps2_sqrt_s=_as_float(d, "sigma_ba_rw_mps2_sqrt_s", 1.0e-5),
            sigma_bgz_rw_rad_s_sqrt_s=_as_float(d, "sigma_bgz_rw_rad_s_sqrt_s", 1.0e-5),
        )


@dataclass
class DvlNoiseConfig:
    enable_speed_dependent: bool = True
    percent: float = 0.004
    floor_bi_mps: float = 0.002
    floor_be_mps: float = 0.005
    be_inflate: float = 1.0

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DvlNoiseConfig":
        if d is None:
            d = {}
        return cls(
            enable_speed_dependent=_as_bool(d, "enable_speed_dependent", True),
            percent=_as_float(d, "percent", 0.004),
            floor_bi_mps=_as_float(d, "floor_bi_mps", 0.002),
            floor_be_mps=_as_float(d, "floor_be_mps", 0.005),
            be_inflate=_as_float(d, "be_inflate", 1.0),
        )


@dataclass
class EskfInitCovConfig:
    p0_m: float = 0.5
    v0_mps: float = 0.05
    yaw0_rad: float = 0.35
    ba0_mps2: float = 0.2
    bgz0_rad_s: float = 0.02

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "EskfInitCovConfig":
        if d is None:
            d = {}
        return cls(
            p0_m=_as_float(d, "p0_m", 0.5),
            v0_mps=_as_float(d, "v0_mps", 0.05),
            yaw0_rad=_as_float(d, "yaw0_rad", 0.35),
            ba0_mps2=_as_float(d, "ba0_mps2", 0.2),
            bgz0_rad_s=_as_float(d, "bgz0_rad_s", 0.02),
        )
@dataclass
class EskfSmoothTrajConfig:
    """
    轨迹后处理平滑配置（只作用于输出的 traj_df，不影响滤波内部状态）：
      - enable         : 是否启用平滑
      - window_samples : 滑动窗口长度（样本点数，建议奇数）
    """
    enable: bool = False
    window_samples: int = 9

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "EskfSmoothTrajConfig":
        if d is None:
            d = {}
        return cls(
            enable=_as_bool(d, "enable", False),
            # 没有 _as_int 时，用 _as_float 再转 int 也可以
            window_samples=int(_as_float(d, "window_samples", 9)),
        )

@dataclass
class EskfLocalVelConfig:
    """
    局部 ESKF 调试模式的配置：
      - vel_trust_alpha:
          0.0 -> 每次 DVL 更新后 v_enu 完全等于 v_dvl（最“信 DVL”）
          1.0 -> 完全保留 ESKF 自己传播得到的 v_enu（等价于不启用该模式）
      - keep_pos_from_imu:
          False -> p_enu 基本不信 IMU 积分位移，只作弱记录/补偿
          True  -> 仍按传统 INS 方式积分位置
    """
    vel_trust_alpha: float = 0.0
    keep_pos_from_imu: bool = False

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "EskfLocalVelConfig":
        if d is None:
            d = {}
        return cls(
            vel_trust_alpha=_as_float(d, "vel_trust_alpha", 0.0),
            keep_pos_from_imu=_as_bool(d, "keep_pos_from_imu", False),
        )

@dataclass
class EskfConfig:
    # 运行模式
    mode: str = "full_ins"

    # 局部速度模式
    local_vel: EskfLocalVelConfig = EskfLocalVelConfig()

    # 数据源 / 单位
    imu_rollpitch_source: str = "processed"
    imu_yaw_source: str       = "processed"
    imu_acc_source: str       = "processed"
    imu_gyro_source: str      = "processed"

    imu_raw_g_to_mps2: float = 9.78
    gravity: float           = 9.78

    # yaw 初始化
    init_yaw_source: str = "config"  # "config" | "imu" | "dvl"
    init_yaw_rad: float  = 0.0
    yaw_sign: float      = 1.0

    # DVL 使用策略
    use_dvl_BI_vel: bool         = False
    use_dvl_BE_vel: bool         = False
    use_dvl_yaw_from_vel: bool   = True
    min_speed_for_yaw_dvl: float = 0.08

    # <<< 新增：低速时是否跳过 DVL 速度更新的阈值（ENU 水平速度）
    # speed_h < min_speed_for_dvl_update 时，不做 DVL vel 更新，只记 audit
    min_speed_for_dvl_update: float = 0.0

    # 噪声配置
    imu_noise: ImuNoiseConfig    = ImuNoiseConfig()
    dvl_noise: DvlNoiseConfig    = DvlNoiseConfig()
    init_cov:  EskfInitCovConfig = EskfInitCovConfig()

    # IMU 积分类别 / 时间间隔防护
    imu_acc_kind: str = "linear"
    max_gap_s: float  = 0.05

    # DVL 匹配 / 过滤
    dvl_match_policy: str    = "anchor_next"
    dvl_match_window_s: float = 0.05
    dvl_drop_older_than_s: float = 0.5
    require_gate_ok: bool   = True
    require_speed_ok: bool  = True
    require_valid: bool     = False

    # 旧接口下的 Q/R（EskfFilter 目前很可能还是用这几个）
    q_vel: float = 1.0e-3
    q_yaw: float = 5.0e-4
    q_ba:  float = 1.0e-7
    q_bgz: float = 1.0e-9

    r_dvl_bi_vel: float = 4.0e-2   # ≈(0.2 m/s)^2
    r_dvl_be_vel: float = 4.0e-2
    r_dvl_yaw:     float = 0.0349  # ≈ (10°)^2

    # DVL 的显式 sigma（新接口，供统一生成 R 或 audit）
    sigma_dvl_xy_mps: float = 0.25   # 水平速度噪声
    sigma_dvl_z_mps:  float = 0.06   # 垂向速度噪声

    # 输出后处理（坐标轴翻转 / 平滑）
    flip_n_axis: bool = False
    smooth_traj_enable: bool = False
    smooth_traj_window_samples: int = 9

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "EskfConfig":
        if d is None:
            d = {}

        imu_noise_cfg  = ImuNoiseConfig.from_dict(d.get("imu_noise"))
        dvl_noise_cfg  = DvlNoiseConfig.from_dict(d.get("dvl_noise"))
        init_cov_cfg   = EskfInitCovConfig.from_dict(d.get("init_cov"))
        local_vel_cfg  = EskfLocalVelConfig.from_dict(d.get("local_vel"))

        return cls(
            mode=_as_str(d, "mode", "full_ins"),
            local_vel=local_vel_cfg,

            imu_rollpitch_source=_as_str(d, "imu_rollpitch_source", "processed"),
            imu_yaw_source=_as_str(d, "imu_yaw_source", "processed"),
            imu_acc_source=_as_str(d, "imu_acc_source", "processed"),
            imu_gyro_source=_as_str(d, "imu_gyro_source", "processed"),

            imu_raw_g_to_mps2=_as_float(d, "imu_raw_g_to_mps2", 9.78),
            gravity=_as_float(d, "gravity", 9.78),

            init_yaw_source=_as_str(d, "init_yaw_source", "config"),
            init_yaw_rad=_as_float(d, "init_yaw_rad", 0.0),
            yaw_sign=_as_float(d, "yaw_sign", 1.0),

            use_dvl_BI_vel=_as_bool(d, "use_dvl_BI_vel", True),
            use_dvl_BE_vel=_as_bool(d, "use_dvl_BE_vel", True),
            use_dvl_yaw_from_vel=_as_bool(d, "use_dvl_yaw_from_vel", True),
            min_speed_for_yaw_dvl=_as_float(d, "min_speed_for_yaw_dvl", 0.08),

            # <<< 新增字段，从字典里取
            min_speed_for_dvl_update=_as_float(
                d, "min_speed_for_dvl_update", 0.0
            ),

            imu_noise=imu_noise_cfg,
            dvl_noise=dvl_noise_cfg,
            init_cov=init_cov_cfg,

            imu_acc_kind=_as_str(d, "imu_acc_kind", "linear"),
            max_gap_s=_as_float(d, "max_gap_s", 0.05),

            dvl_match_policy=_as_str(d, "dvl_match_policy", "anchor_next"),
            dvl_match_window_s=_as_float(d, "dvl_match_window_s", 0.05),
            dvl_drop_older_than_s=_as_float(d, "dvl_drop_older_than_s", 0.5),
            require_gate_ok=_as_bool(d, "require_gate_ok", True),
            require_speed_ok=_as_bool(d, "require_speed_ok", True),
            require_valid=_as_bool(d, "require_valid", False),

            q_vel=_as_float(d, "q_vel", 1.0e-3),
            q_yaw=_as_float(d, "q_yaw", 5.0e-4),
            q_ba=_as_float(d, "q_ba", 1.0e-7),
            q_bgz=_as_float(d, "q_bgz", 1.0e-9),

            r_dvl_bi_vel=_as_float(d, "r_dvl_bi_vel", 4.0e-2),
            r_dvl_be_vel=_as_float(d, "r_dvl_be_vel", 4.0e-2),
            r_dvl_yaw=_as_float(d, "r_dvl_yaw", 0.0349),

            sigma_dvl_xy_mps=_as_float(d, "sigma_dvl_xy_mps", 0.25),
            sigma_dvl_z_mps=_as_float(d, "sigma_dvl_z_mps", 0.06),

            flip_n_axis=_as_bool(d, "flip_n_axis", False),
            smooth_traj_enable=_as_bool(d, "smooth_traj_enable", False),
            smooth_traj_window_samples=int(
                _as_float(d, "smooth_traj_window_samples", 9)
            ),
        )

    def to_eskf_kwargs(self) -> Dict[str, Any]:
        """
        把 EskfConfig 展开成 EskfFilter 所需的 kwargs。
        注意：key 名要和 EskfFilter.__init__ 一一对应。
        """
        return {
            "mode": self.mode,
            "local_vel_cfg": {
                "vel_trust_alpha": self.local_vel.vel_trust_alpha,
                "keep_pos_from_imu": self.local_vel.keep_pos_from_imu,
            },

            "gravity": self.gravity,
            "imu_acc_kind": self.imu_acc_kind,
            "yaw_sign": self.yaw_sign,

            # 噪声
            "imu_noise_cfg": {
                "sigma_acc_mps2": self.imu_noise.sigma_acc_mps2,
                "sigma_gyro_rad_s": self.imu_noise.sigma_gyro_rad_s,
                "sigma_ba_rw_mps2_sqrt_s": self.imu_noise.sigma_ba_rw_mps2_sqrt_s,
                "sigma_bgz_rw_rad_s_sqrt_s": self.imu_noise.sigma_bgz_rw_rad_s_sqrt_s,
            },
            "init_cov_cfg": {
                "p0_m": self.init_cov.p0_m,
                "v0_mps": self.init_cov.v0_mps,
                "yaw0_rad": self.init_cov.yaw0_rad,
                "ba0_mps2": self.init_cov.ba0_mps2,
                "bgz0_rad_s": self.init_cov.bgz0_rad_s,
            },

            # 旧接口下的 Q/R
            "q_vel": self.q_vel,
            "q_yaw": self.q_yaw,
            "q_ba": self.q_ba,
            "q_bgz": self.q_bgz,
            "r_dvl_bi_vel": self.r_dvl_bi_vel,
            "r_dvl_be_vel": self.r_dvl_be_vel,
            "r_dvl_yaw": self.r_dvl_yaw,

            # DVL 噪声新接口（供内部统一生成 R 或 audit 使用）
            "dvl_noise_cfg": {
                "enable_speed_dependent": self.dvl_noise.enable_speed_dependent,
                "percent": self.dvl_noise.percent,
                "floor_bi_mps": self.dvl_noise.floor_bi_mps,
                "floor_be_mps": self.dvl_noise.floor_be_mps,
                "be_inflate": self.dvl_noise.be_inflate,
                "sigma_xy_mps": self.sigma_dvl_xy_mps,
                "sigma_z_mps": self.sigma_dvl_z_mps,
            },

            # 模式 / 源选择（EskfFilter 如果需要的话）
            "use_dvl_BI_vel": self.use_dvl_BI_vel,
            "use_dvl_BE_vel": self.use_dvl_BE_vel,
            "use_dvl_yaw_from_vel": self.use_dvl_yaw_from_vel,
            "min_speed_for_yaw_dvl": self.min_speed_for_yaw_dvl,

            # <<< 新增：传给 EskfFilter 或后端逻辑的“低速 DVL 更新门限”
            "min_speed_for_dvl_update": self.min_speed_for_dvl_update,
        }

# =====================================================================
# graph 配置
# =====================================================================

@dataclass
class GraphConfig:
    use_eskf_init: bool = False
    node_timebase: str = "imu"
    verbose: bool = True

    max_iterations: int = 10
    lambda_init: float = 1.0
    lambda_min: float = 1.0e-6
    lambda_max: float = 1.0e3

    use_robust_loss: bool = True
    robust_loss_type: str = "huber"
    robust_loss_param: float = 1.0

    keyframe_stride: int = 50
    max_nodes: int = 200

    max_imu_samples: int = 0
    max_dvl_samples: int = 0

    use_dvl_BE_vel: bool = True
    use_dvl_BI_vel: bool = True
    use_dvl_yaw_from_vel: bool = False
    enable_imu_factor: bool = False

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "GraphConfig":
        if d is None:
            d = {}
        return cls(
            use_eskf_init=_as_bool(d, "use_eskf_init", False),
            node_timebase=_as_str(d, "node_timebase", "imu"),
            verbose=_as_bool(d, "verbose", True),
            max_iterations=int(d.get("max_iterations", 10)),
            lambda_init=_as_float(d, "lambda_init", 1.0),
            lambda_min=_as_float(d, "lambda_min", 1.0e-6),
            lambda_max=_as_float(d, "lambda_max", 1.0e3),
            use_robust_loss=_as_bool(d, "use_robust_loss", True),
            robust_loss_type=_as_str(d, "robust_loss_type", "huber"),
            robust_loss_param=_as_float(d, "robust_loss_param", 1.0),
            keyframe_stride=int(d.get("keyframe_stride", 50)),
            max_nodes=int(d.get("max_nodes", 200)),
            max_imu_samples=int(d.get("max_imu_samples", 0)),
            max_dvl_samples=int(d.get("max_dvl_samples", 0)),
            use_dvl_BE_vel=_as_bool(d, "use_dvl_BE_vel", True),
            use_dvl_BI_vel=_as_bool(d, "use_dvl_BI_vel", True),
            use_dvl_yaw_from_vel=_as_bool(d, "use_dvl_yaw_from_vel", False),
            enable_imu_factor=_as_bool(d, "enable_imu_factor", False),
        )


# =====================================================================
# frames 配置（坐标系）
# =====================================================================

@dataclass
class ImuFrameConfig:
    acc_units: str = "g"
    gyro_units: str = "deg_s"
    axis_map: np.ndarray = np.eye(3)
    z_positive: str = "up"  # 硬件自身 Z 轴正方向

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "ImuFrameConfig":
        if d is None:
            d = {}
        default_axis = np.eye(3, dtype=float)
        return cls(
            acc_units=_as_str(d, "acc_units", "g"),
            gyro_units=_as_str(d, "gyro_units", "deg_s"),
            axis_map=_as_axis_map(d, "axis_map", default_axis),
            z_positive=_as_str(d, "z_positive", "up"),
        )


@dataclass
class DvlBiFrameConfig:
    units: str = "mps"
    frame: str = "FRD"
    axis_map: np.ndarray = np.eye(3)
    z_positive: str = "down"

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DvlBiFrameConfig":
        if d is None:
            d = {}
        default_axis = np.eye(3, dtype=float)
        return cls(
            units=_as_str(d, "units", "mps"),
            frame=_as_str(d, "frame", "FRD"),
            axis_map=_as_axis_map(d, "axis_map", default_axis),
            z_positive=_as_str(d, "z_positive", "down"),
        )


@dataclass
class DvlBeFrameConfig:
    units: str = "mps"
    frame: str = "ENU"
    z_positive: str = "up"
    convert_vu_up_to_down: bool = False  # nav=ENU 时默认不翻 Vu

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DvlBeFrameConfig":
        if d is None:
            d = {}
        return cls(
            units=_as_str(d, "units", "mps"),
            frame=_as_str(d, "frame", "ENU"),
            z_positive=_as_str(d, "z_positive", "up"),
            convert_vu_up_to_down=_as_bool(d, "convert_vu_up_to_down", False),
        )


@dataclass
class FramesConfig:
    eskf_nav: str = "ENU"
    eskf_body: str = "FRD"
    output_nav: str = "ENU"

    imu: ImuFrameConfig = ImuFrameConfig()
    dvl_bi: DvlBiFrameConfig = DvlBiFrameConfig()
    dvl_be: DvlBeFrameConfig = DvlBeFrameConfig()

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "FramesConfig":
        if d is None:
            d = {}
        imu_cfg = ImuFrameConfig.from_dict(d.get("imu"))
        dvl_bi_cfg = DvlBiFrameConfig.from_dict(d.get("dvl_bi"))
        dvl_be_cfg = DvlBeFrameConfig.from_dict(d.get("dvl_be"))
        return cls(
            eskf_nav=_as_str(d, "eskf_nav", "ENU"),
            eskf_body=_as_str(d, "eskf_body", "FRD"),
            output_nav=_as_str(d, "output_nav", "ENU"),
            imu=imu_cfg,
            dvl_bi=dvl_bi_cfg,
            dvl_be=dvl_be_cfg,
        )


# =====================================================================
# dvl_gate 配置
# =====================================================================

@dataclass
class DvlGateConfig:
    hz: float = 10.0
    speed_min_m_s: float = 0.05
    speed_max_m_s: float = 2.0
    dv_axis_max_m_s: float = 0.20
    dv_xy_max_m_s: float = 0.25
    be_vu_abs_max_m_s: float = 0.30
    vel_src_set: tuple[str, ...] = ("BI", "BE")
    keep_all_vel_rows: bool = True
    keep_stream: bool = True
    require_speed_ok: bool = True
    require_bottom_track: bool = True

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DvlGateConfig":
        if d is None:
            d = {}
        vel_src = d.get("vel_src_set", ("BI", "BE"))
        if isinstance(vel_src, (list, tuple)):
            vel_src_t = tuple(str(x) for x in vel_src)
        else:
            vel_src_t = (str(vel_src),)
        return cls(
            hz=_as_float(d, "hz", 10.0),
            speed_min_m_s=_as_float(d, "speed_min_m_s", 0.05),
            speed_max_m_s=_as_float(d, "speed_max_m_s", 2.0),
            dv_axis_max_m_s=_as_float(d, "dv_axis_max_m_s", 0.20),
            dv_xy_max_m_s=_as_float(d, "dv_xy_max_m_s", 0.25),
            be_vu_abs_max_m_s=_as_float(d, "be_vu_abs_max_m_s", 0.30),
            vel_src_set=vel_src_t,
            keep_all_vel_rows=_as_bool(d, "keep_all_vel_rows", True),
            keep_stream=_as_bool(d, "keep_stream", True),
            require_speed_ok=_as_bool(d, "require_speed_ok", True),
            require_bottom_track=_as_bool(d, "require_bottom_track", True),
        )


# =====================================================================
# 顶层 NavConfig
# =====================================================================

@dataclass
class NavConfig:
    deadreckon: DeadReckonConfig
    eskf: EskfConfig
    graph: GraphConfig
    frames: FramesConfig
    dvl_gate: DvlGateConfig

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "NavConfig":
        return cls(
            deadreckon=DeadReckonConfig.from_dict(d.get("deadreckon")),
            eskf=EskfConfig.from_dict(d.get("eskf")),
            graph=GraphConfig.from_dict(d.get("graph")),
            frames=FramesConfig.from_dict(d.get("frames")),
            dvl_gate=DvlGateConfig.from_dict(d.get("dvl_gate")),
        )


# =====================================================================
# 对外 API
# =====================================================================

def load_nav_config(path: str | Path = DEFAULT_NAV_CONFIG_PATH) -> NavConfig:
    """
    读取 nav.yaml 并返回 NavConfig。
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"nav config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise TypeError(f"nav config root must be a mapping, got {type(data)!r}")
    return NavConfig.from_dict(data)
