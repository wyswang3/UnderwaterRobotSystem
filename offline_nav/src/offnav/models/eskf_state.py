from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any

import numpy as np

from offnav.core.nav_config import (
    DeadReckonInitPose,
    EskfConfig,
    EskfInitCovConfig,
    DvlNoiseConfig,
    FramesConfig,
    NavConfig,
    load_nav_config,
)

from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb, wrap_angle_pm_pi

from offnav.models.eskf_core import (
    EskfCoreParams,
    EskfState as CoreState,
    N_STATE,
    make_initial_state,
    eskf_propagate,
    eskf_update_dvl_be_vel,
    eskf_update_dvl_bi_vel,
    eskf_update_yaw_from_dvl,
    eskf_update_vertical_velocity_pseudo,
)


# ============================================================================
# （可选）简化结构体：初始状态 / 协方差配置（保留，兼容旧工程习惯）
# ============================================================================

@dataclass
class EskfStateSimple:
    """
    简化版主状态（不含协方差，用于配置 / 其它模块）：

    nav frame: ENU (E, N, U；U 向上)
    body frame: FRD (F:前, R:右, D:下)
    """
    p_enu: np.ndarray
    v_enu: np.ndarray
    yaw_rad: float
    ba_b: np.ndarray
    bgz_rad_s: float

    @classmethod
    def from_config(cls, init_pose: DeadReckonInitPose, eskf_cfg: EskfConfig) -> "EskfStateSimple":
        p = np.array([init_pose.E, init_pose.N, init_pose.U], dtype=float)
        v = np.zeros(3, dtype=float)
        if eskf_cfg.init_yaw_source == "config":
            yaw = float(eskf_cfg.init_yaw_rad)
        else:
            yaw = float(init_pose.yaw_deg) * np.pi / 180.0
        ba = np.zeros(3, dtype=float)
        bgz = 0.0
        return cls(p_enu=p, v_enu=v, yaw_rad=yaw, ba_b=ba, bgz_rad_s=bgz)


@dataclass
class EskfCov:
    """
    11 维状态协方差配置帮助类：
      x = [pE, pN, pU, vE, vN, vU, yaw, ba_x, ba_y, ba_z, bgz]^T
    """
    P: np.ndarray  # shape (11, 11)

    @classmethod
    def from_init_cov(cls, cfg: EskfInitCovConfig) -> "EskfCov":
        P = np.zeros((11, 11), dtype=float)
        P[0:3, 0:3] = np.eye(3) * (cfg.p0_m ** 2)
        P[3:6, 3:6] = np.eye(3) * (cfg.v0_mps ** 2)
        P[6, 6] = cfg.yaw0_rad ** 2
        P[7:10, 7:10] = np.eye(3) * (cfg.ba0_mps2 ** 2)
        P[10, 10] = cfg.bgz0_rad_s ** 2
        return cls(P=P)


# ============================================================================
# 观测更新诊断（用于 runner 落盘）
# ============================================================================

@dataclass
class UpdateReport:
    """
    单次观测更新的诊断快照（供 eskf_runner.py 落盘成 CSV）。

    - name: 更新类型标签，例如 "dvl_be_vel" / "yaw_from_vel" / "dvl_bi_vel" / "vu_pseudo"
    - t   : 更新时间戳（秒）
    - r   : residual 向量（z - h(x)）
    - S_diag : 创新协方差 S 的对角（便于快速看尺度）
    - nis : Normalized Innovation Squared = r^T S^{-1} r（门控/一致性判断）
    """
    name: str
    t: float
    r: np.ndarray
    S_diag: np.ndarray
    nis: float


# ============================================================================
# 诊断信息（供 CLI 打印；保持字段兼容）
# ============================================================================

@dataclass
class EskfDiagnostics:
    # IMU / DVL 计数
    n_imu: int = 0
    n_dvl: int = 0

    # DVL 使用计数
    n_dvl_used_vel_BE: int = 0
    n_dvl_used_vel_BI: int = 0
    n_dvl_used_yaw: int = 0

    # 导航启动门控（和 cli_nav 里的打印字段兼容）
    nav_started: bool = False
    nav_start_t: float = 0.0
    nav_start_reason: str = ""

    # dt 守恒保护（过大间隔跳过）
    n_dt_guard_skip: int = 0

    # GyroZ 兜底 / 垂向伪测量
    n_gyro_z_fallback: int = 0
    n_vu_pseudo: int = 0

    # yaw 观测异常计数（避免访问不存在字段）
    n_yaw_invalid: int = 0

    # 新增：观测更新诊断列表（runner 可落盘）
    updates: list[UpdateReport] = field(default_factory=list)


# ============================================================================
# ESKF Filter：封装 eskf_core 的数学核（对外兼容旧接口 + 新增增强接口）
# ============================================================================

class EskfFilter:
    """
    对外保持旧接口：
      - set_initial_time(t0)
      - propagate_imu(t_s, acc_b, gyro_b, roll_rad, pitch_rad)
      - correct_dvl_vel_enu(vel_enu_meas, dvl_noise_cfg)

    新增接口：
      - correct_yaw_from_dvl(yaw_meas_rad, R_meas)
      - correct_vertical_velocity_pseudo(vu_target_mps, R_meas)
      - correct_dvl_vel_body(v_b_frd, roll_rad, pitch_rad, dvl_noise_cfg)

    同时新增 diag.updates 以支持“观测更新可视化/落盘”。

    nav frame 约定：
      - 当前实现把状态解释为 ENU：p = [E,N,U]^T，v = [vE,vN,vU]^T（U 向上）
      - DVL BE 观测预期为 ENU (E,N,U)，其中 Vu 向上（不再翻号）
    """

    # ------------------------ 便捷构造函数 ------------------------

    @classmethod
    def from_nav_config(cls, nav_cfg: NavConfig) -> "EskfFilter":
        """
        直接从 NavConfig 创建 ESKF：
            nav_cfg = load_nav_config("configs/nav.yaml")
            eskf = EskfFilter.from_nav_config(nav_cfg)
        """
        return cls(
            eskf_cfg=nav_cfg.eskf,
            frames_cfg=nav_cfg.frames,
            init_pose=nav_cfg.deadreckon.init_pose,
        )

    @classmethod
    def from_config_path(cls, path: str | Path) -> "EskfFilter":  # type: ignore[name-defined]
        """
        直接从 nav.yaml 路径创建 ESKF：
            eskf = EskfFilter.from_config_path("configs/nav.yaml")
        """
        nav_cfg = load_nav_config(path)
        return cls.from_nav_config(nav_cfg)

    # ------------------------ 核心构造函数 ------------------------

    def __init__(
        self,
        eskf_cfg: EskfConfig,
        frames_cfg: FramesConfig,
        init_pose: DeadReckonInitPose,
    ) -> None:
        self.cfg = eskf_cfg
        self.frames = frames_cfg

        # ========== 0) 简单一致性检查：frame 与 DVL BE 翻号 ==========
        try:
            nav_name = str(self.frames.eskf_nav).upper()
            out_nav_name = str(self.frames.output_nav).upper()
            if nav_name != "ENU":
                print(f"[ESKF][WARN] frames.eskf_nav={self.frames.eskf_nav!r} "
                      f"(当前实现假定 ENU；请确认输入/输出是否转好了坐标系)")
            if out_nav_name != "ENU":
                print(f"[ESKF][WARN] frames.output_nav={self.frames.output_nav!r} "
                      f"(当前绘图/输出约定 ENU；请确认调用方是否一致)")
            # DVL BE: ENU + Vu 向上；如果 convert_vu_up_to_down=True 且 nav=ENU，可能发生“双重翻号”
            if nav_name == "ENU" and getattr(self.frames.dvl_be, "convert_vu_up_to_down", False):
                print("[ESKF][WARN] frames.dvl_be.convert_vu_up_to_down=True 且 eskf_nav=ENU，"
                      "请确认 DVL BE 预处理是否已经把 Vu 翻为 Down，避免在 ESKF 侧再次当作 Up 使用。")
        except Exception:
            # 配置不完整时不阻塞 ESKF 初始化
            pass

        # ========== 1) CoreParams ==========
        self.params = EskfCoreParams(
            gravity=eskf_cfg.gravity,
            imu_acc_kind=eskf_cfg.imu_acc_kind,
            yaw_sign=eskf_cfg.yaw_sign,
            sigma_acc_mps2=eskf_cfg.imu_noise.sigma_acc_mps2,
            sigma_gyro_rad_s=eskf_cfg.imu_noise.sigma_gyro_rad_s,
            sigma_ba_rw_mps2_sqrt_s=eskf_cfg.imu_noise.sigma_ba_rw_mps2_sqrt_s,
            sigma_bgz_rw_rad_s_sqrt_s=eskf_cfg.imu_noise.sigma_bgz_rw_rad_s_sqrt_s,
        )

        # ========== 2) 初始 state + P0 ==========
        # nav frame 解释为 ENU: [E,N,U]
        p0 = np.array([init_pose.E, init_pose.N, init_pose.U], dtype=float)
        v0 = np.zeros(3, dtype=float)

        if eskf_cfg.init_yaw_source == "config":
            yaw0 = float(eskf_cfg.init_yaw_rad)
        else:
            # 回退：若 init_yaw_source 不是 "config"，则用 init_pose.yaw_deg
            yaw0 = float(init_pose.yaw_deg) * np.pi / 180.0

        ba0 = np.zeros(3, dtype=float)
        bgz0 = 0.0

        ic = eskf_cfg.init_cov
        P0_diag = np.zeros(N_STATE, dtype=float)
        P0_diag[0:3] = ic.p0_m ** 2
        P0_diag[3:6] = ic.v0_mps ** 2
        P0_diag[6] = ic.yaw0_rad ** 2
        P0_diag[7:10] = ic.ba0_mps2 ** 2
        P0_diag[10] = ic.bgz0_rad_s ** 2

        self.state: CoreState = make_initial_state(
            t0=0.0,
            p0_enu=p0,
            v0_enu=v0,
            yaw0_rad=yaw0,
            ba0_b=ba0,
            bgz0=bgz0,
            P0_diag=P0_diag,
        )

        # ========== 3) 运行时变量 ==========
        self.diag = EskfDiagnostics()
        self.last_t_s: Optional[float] = None

    # -------------------------------------------------------------------------
    # 时间初始化
    # -------------------------------------------------------------------------
    def set_initial_time(self, t0_s: float) -> None:
        t0 = float(t0_s)
        self.last_t_s = t0
        self.state.t = t0

    # -------------------------------------------------------------------------
    # 内部：记录一次 update 诊断
    # -------------------------------------------------------------------------
    def _append_update_report(self, name: str, t_s: float, r: np.ndarray, S: np.ndarray) -> None:
        r = np.asarray(r, dtype=float).reshape(-1)
        S = np.asarray(S, dtype=float)
        S_diag = np.diag(S).astype(float, copy=True) if S.ndim == 2 else np.array([float(S)], dtype=float)

        # NIS = r^T S^{-1} r
        try:
            if S.ndim == 2:
                nis = float(r.T @ np.linalg.solve(S, r))
            else:
                nis = float((r[0] * r[0]) / float(S))
        except Exception:
            nis = float("nan")

        self.diag.updates.append(
            UpdateReport(
                name=str(name),
                t=float(t_s),
                r=r.astype(float, copy=True),
                S_diag=S_diag,
                nis=nis,
            )
        )

    # -------------------------------------------------------------------------
    # 过程模型：IMU 传播
    # -------------------------------------------------------------------------
    def propagate_imu(
        self,
        t_s: float,
        acc_b_mps2: np.ndarray,
        gyro_b_rad_s: np.ndarray,
        roll_rad: float,
        pitch_rad: float,
    ) -> None:
        t_cur = float(t_s)
        acc_b = np.asarray(acc_b_mps2, dtype=float).reshape(3)
        gyro_b = np.asarray(gyro_b_rad_s, dtype=float).reshape(3)

        # 初次调用：仅对齐时间基
        if self.last_t_s is None:
            self.last_t_s = t_cur
            self.state.t = t_cur
            return

        dt = t_cur - self.last_t_s
        if dt <= 0.0:
            self.last_t_s = t_cur
            self.state.t = t_cur
            return

        # dt 守恒保护：缺口太大直接跳过这段
        if dt > self.cfg.max_gap_s:
            self.diag.n_dt_guard_skip += 1
            self.last_t_s = t_cur
            self.state.t = t_cur
            return

        gyro_z = float(gyro_b[2])

        self.state = eskf_propagate(
            state=self.state,
            dt=dt,
            acc_b_mps2=acc_b,
            gyro_z_rad_s=gyro_z,
            roll_rad=float(roll_rad),
            pitch_rad=float(pitch_rad),
            params=self.params,
        )

        self.last_t_s = t_cur
        self.diag.n_imu += 1

        if not self.diag.nav_started:
            self.diag.nav_started = True
            self.diag.nav_start_t = t_cur
            self.diag.nav_start_reason = "first_imu"

    # -------------------------------------------------------------------------
    # 观测模型：DVL BE（ENU 速度）
    # -------------------------------------------------------------------------
    def correct_dvl_vel_enu(self, vel_enu_meas: np.ndarray, eskf_cfg: EskfConfig) -> None:
        # 强约束：防止外部传入乱对象（比如 dict / DvlNoiseConfig）
        if not isinstance(eskf_cfg, EskfConfig):
            raise TypeError(
                "correct_dvl_vel_enu expects eskf_cfg: EskfConfig (nav_cfg.eskf). "
                f"Got: {type(eskf_cfg)!r}"
            )

        v = np.asarray(vel_enu_meas, dtype=float).reshape(3)

        # 只从 eskf_cfg 读取噪声配置（避免外部“临时改参”）
        dvl_noise: DvlNoiseConfig = eskf_cfg.dvl_noise

        # ---- 噪声建模（保持你原先逻辑）----
        speed = float(np.linalg.norm(v))
        sigma_floor = float(getattr(dvl_noise, "floor_be_mps", 0.02))
        enable_sd = bool(getattr(dvl_noise, "enable_speed_dependent", True))
        percent = float(getattr(dvl_noise, "percent", 0.02))
        inflate = float(getattr(dvl_noise, "be_inflate", 1.0))

        if enable_sd:
            sigma = float(np.sqrt((percent * max(speed, 0.0)) ** 2 + sigma_floor ** 2))
        else:
            sigma = sigma_floor
        sigma *= inflate
        R = np.eye(3, dtype=float) * (sigma ** 2)

        # ---- diag（不改）----
        r = v - self.state.v
        H = np.zeros((3, N_STATE), dtype=float)
        H[:, 3:6] = np.eye(3, dtype=float)
        S = H @ self.state.P @ H.T + R
        self._append_update_report("dvl_be_vel", t_s=float(self.state.t), r=r, S=S)

        # ---- update（不改）----
        self.state = eskf_update_dvl_be_vel(
            state=self.state,
            v_be_nav_mps=v,
            R_meas=R,
        )

        self.diag.n_dvl += 1
        self.diag.n_dvl_used_vel_BE += 1
    # -------------------------------------------------------------------------
    # DVL yaw-from-velocity 更新（可选）
    # -------------------------------------------------------------------------
    def correct_yaw_from_dvl(self, yaw_meas_rad: float, R_meas: float) -> None:
        dy = float(yaw_meas_rad) - float(self.state.yaw)
        if not np.isfinite(dy):
            self.diag.n_yaw_invalid += 1
            return

        r_yaw = wrap_angle_pm_pi(dy)
        r = np.array([r_yaw], dtype=float)

        H = np.zeros((1, N_STATE), dtype=float)
        H[0, 6] = 1.0
        R = np.array([[float(R_meas)]], dtype=float)
        S = H @ self.state.P @ H.T + R
        self._append_update_report("yaw_from_vel", t_s=float(self.state.t), r=r, S=S)

        self.state = eskf_update_yaw_from_dvl(
            state=self.state,
            yaw_meas_rad=float(yaw_meas_rad),
            R_meas=float(R_meas),
        )
        self.diag.n_dvl_used_yaw += 1

    # -------------------------------------------------------------------------
    # 垂向伪测量（可选）
    # -------------------------------------------------------------------------
    def correct_vertical_velocity_pseudo(self, vu_target_mps: float, R_meas: float) -> None:
        # residual: z - v_u
        r = np.array([float(vu_target_mps) - float(self.state.v[2])], dtype=float)

        H = np.zeros((1, N_STATE), dtype=float)
        H[0, 3 + 2] = 1.0  # vU
        R = np.array([[float(R_meas)]], dtype=float)
        S = H @ self.state.P @ H.T + R
        self._append_update_report("vu_pseudo", t_s=float(self.state.t), r=r, S=S)

        self.state = eskf_update_vertical_velocity_pseudo(
            state=self.state,
            vu_target_mps=float(vu_target_mps),
            R_meas=float(R_meas),
        )
        self.diag.n_vu_pseudo += 1

    # -------------------------------------------------------------------------
    # DVL BI（体速度 FRD）更新（可选）
    # -------------------------------------------------------------------------
    def correct_dvl_vel_body(
        self,
        vel_body_frd_mps: np.ndarray,
        roll_rad: float,
        pitch_rad: float,
        eskf_cfg: EskfConfig,
    ) -> None:
        if not isinstance(eskf_cfg, EskfConfig):
            raise TypeError(
                "correct_dvl_vel_body expects eskf_cfg: EskfConfig (nav_cfg.eskf). "
                f"Got: {type(eskf_cfg)!r}"
            )

        v_b = np.asarray(vel_body_frd_mps, dtype=float).reshape(3)

        dvl_noise: DvlNoiseConfig = eskf_cfg.dvl_noise

        speed = float(np.linalg.norm(v_b))
        sigma_floor = float(getattr(dvl_noise, "floor_bi_mps", getattr(dvl_noise, "floor_be_mps", 0.02)))
        enable_sd = bool(getattr(dvl_noise, "enable_speed_dependent", True))
        percent = float(getattr(dvl_noise, "percent", 0.02))
        inflate = float(getattr(dvl_noise, "bi_inflate", getattr(dvl_noise, "be_inflate", 1.0)))

        if enable_sd:
            sigma = float(np.sqrt((percent * max(speed, 0.0)) ** 2 + sigma_floor ** 2))
        else:
            sigma = sigma_floor
        sigma *= inflate
        R = np.eye(3, dtype=float) * (sigma ** 2)

        R_nb = rpy_to_R_nb(AttitudeRPY(float(roll_rad), float(pitch_rad), float(self.state.yaw)))
        R_bn = R_nb.T

        v_pred_b = R_bn @ self.state.v
        r = v_b - v_pred_b

        H = np.zeros((3, N_STATE), dtype=float)
        H[:, 3:6] = R_bn
        S = H @ self.state.P @ H.T + R
        self._append_update_report("dvl_bi_vel", t_s=float(self.state.t), r=r, S=S)

        self.state = eskf_update_dvl_bi_vel(
            state=self.state,
            v_bi_body_mps=v_b,
            roll_rad=float(roll_rad),
            pitch_rad=float(pitch_rad),
            R_meas=R,
        )
        self.diag.n_dvl_used_vel_BI += 1
    # -------------------------------------------------------------------------
    # 便捷访问器（给 runner / 可视化用）
    # -------------------------------------------------------------------------
    @property
    def p_enu(self) -> np.ndarray:
        return self.state.p

    @property
    def v_enu(self) -> np.ndarray:
        return self.state.v

    @property
    def yaw_rad(self) -> float:
        return float(self.state.yaw)

    # -------------------------------------------------------------------------
    # Snapshot / restore（用于 NIS 门控重试）
    # -------------------------------------------------------------------------
    def snapshot(self):
        """
        Lightweight snapshot of filter runtime state.

        Snapshot content:
          - state (via state.copy())
          - last_t_s
          - length of diag.updates (for trimming)
          - key diagnostic counters
        """
        st = self.state.copy()
        last_t = self.last_t_s

        # length of updates list
        upd_len = (
            len(self.diag.updates)
            if hasattr(self.diag, "updates") and isinstance(self.diag.updates, list)
            else 0
        )

        # snapshot counters explicitly
        counts = (
            self.diag.n_imu,
            self.diag.n_dvl,
            self.diag.n_dvl_used_vel_BE,
            self.diag.n_dvl_used_vel_BI,
            self.diag.n_dvl_used_yaw,
            self.diag.n_dt_guard_skip,
            self.diag.n_gyro_z_fallback,
            self.diag.n_vu_pseudo,
            self.diag.n_yaw_invalid,
        )

        return (st, last_t, upd_len, counts)

    def restore(self, snap) -> None:
        """
        Restore filter state from snapshot().

        Expected snapshot tuple:
            (state, last_t_s, upd_len, counts)
        """
        if not isinstance(snap, tuple) or len(snap) != 4:
            raise ValueError(
                "snapshot must be a 4-tuple: (state, last_t_s, upd_len, counts)"
            )

        st, last_t, upd_len, counts = snap

        # restore core state
        self.state = st.copy()
        self.last_t_s = last_t

        # restore counters
        (
            self.diag.n_imu,
            self.diag.n_dvl,
            self.diag.n_dvl_used_vel_BE,
            self.diag.n_dvl_used_vel_BI,
            self.diag.n_dvl_used_yaw,
            self.diag.n_dt_guard_skip,
            self.diag.n_gyro_z_fallback,
            self.diag.n_vu_pseudo,
            self.diag.n_yaw_invalid,
        ) = counts

        # trim any updates appended after snapshot
        ups = getattr(self.diag, "updates", None)
        if isinstance(ups, list) and len(ups) > int(upd_len):
            self.diag.updates = ups[: int(upd_len)]

    # -------------------------------------------------------------------------
    # NEW: BE velocity update with explicit R（runner 可以做 robust inflate / gate）
    # -------------------------------------------------------------------------
    def correct_dvl_vel_enu_R(self, vel_enu_meas: np.ndarray, R_meas: np.ndarray) -> None:
        v = np.asarray(vel_enu_meas, dtype=float).reshape(3)
        R = np.asarray(R_meas, dtype=float)
        if R.shape != (3, 3):
            raise ValueError(f"R_meas must be 3x3, got {R.shape}")

        # diag
        r = v - self.state.v
        H = np.zeros((3, N_STATE), dtype=float)
        H[:, 3:6] = np.eye(3, dtype=float)
        S = H @ self.state.P @ H.T + R
        self._append_update_report("dvl_be_vel", t_s=float(self.state.t), r=r, S=S)

        # update
        self.state = eskf_update_dvl_be_vel(self.state, v_be_nav_mps=v, R_meas=R)
        self.diag.n_dvl += 1
        self.diag.n_dvl_used_vel_BE += 1
