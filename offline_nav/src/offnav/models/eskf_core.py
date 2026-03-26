# src/offnav/models/eskf_core.py
# -*- coding: utf-8 -*-
"""
ESKF 核心实现（yaw-only，3D 位置/速度 + IMU bias）

相对旧版增强点（保持对外 API 兼容）：
1) 名义传播使用 accel bias：acc_eff = acc_b - b_a
2) 过程噪声离散化更合理：补齐位置积分链噪声（dt^3/3, dt^2/2）
3) 线性更新可选输出诊断：创新协方差 S、NIS、残差 r（对接 eskf_state.UpdateReport）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional

import numpy as np

from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb, wrap_angle_pm_pi

# 仅用于类型对接（避免循环依赖：没有强制导入 eskf_state）
try:
    from offnav.models.eskf_state import UpdateReport  # type: ignore
except Exception:  # noqa: BLE001
    UpdateReport = None  # type: ignore


# =============================================================================
# 状态 / 参数定义
# =============================================================================

N_STATE = 11

IDX_P = slice(0, 3)
IDX_V = slice(3, 6)
IDX_YAW = 6
IDX_BA = slice(7, 10)
IDX_BGZ = 10


@dataclass
class EskfCoreParams:
    """
    ESKF 过程噪声与 IMU 模式参数。

    约定：
      - nav 坐标系：由 rpy_to_R_nb 决定（通常为 ENU: X=E, Y=N, Z=U）。
      - IMU 加速度：
          * imu_acc_kind == "linear" 时，acc_b_mps2 视为“已扣除重力后的线加速度（body）”；
          * imu_acc_kind == "specific_force" 时，acc_b_mps2 视为“比力 f_b”，本模块内部再加上 g。
      - yaw_sign 用于兼容 IMU z 轴朝向和“正向转动”的定义差异。
    """
    gravity: float = 9.78
    imu_acc_kind: str = "linear"  # "linear" | "specific_force"
    yaw_sign: float = 1.0

    # === 过程噪声（根据 IMU 诊断结果重新标定的默认值） ===
    # IMU 静止窗口中 acc_lin_std ≈ 0.02 m/s² 量级，这里略取保守值 0.03
    sigma_acc_mps2: float = 0.03

    # Gyro_in 静止窗口中 std ≈ 0.003~0.004 rad/s，这里略取保守值 0.01
    sigma_gyro_rad_s: float = 0.01

    # bias 随机游走：比测量白噪声小一到两个数量级（按经验取值）
    sigma_ba_rw_mps2_sqrt_s: float = 3.0e-4
    sigma_bgz_rw_rad_s_sqrt_s: float = 2.0e-4

    def assert_valid(self) -> None:
        if self.imu_acc_kind not in ("linear", "specific_force"):
            raise ValueError(
                f"imu_acc_kind must be 'linear' or 'specific_force', "
                f"got {self.imu_acc_kind!r}"
            )

@dataclass
class EskfState:
    t: float
    p: np.ndarray
    v: np.ndarray
    yaw: float
    ba: np.ndarray
    bgz: float
    P: np.ndarray

    def copy(self) -> "EskfState":
        return EskfState(
            t=float(self.t),
            p=self.p.astype(float, copy=True),
            v=self.v.astype(float, copy=True),
            yaw=float(self.yaw),
            ba=self.ba.astype(float, copy=True),
            bgz=float(self.bgz),
            P=self.P.astype(float, copy=True),
        )


# =============================================================================
# 工具函数
# =============================================================================

def _ensure_vec3(x: np.ndarray) -> np.ndarray:
    return np.asarray(x, dtype=float).reshape(3)


def _skew_z() -> np.ndarray:
    return np.array([[0.0, -1.0, 0.0],
                     [1.0,  0.0, 0.0],
                     [0.0,  0.0, 0.0]], dtype=float)


def _discretize_F_Q(
    F_c: np.ndarray,
    G_c: np.ndarray,
    Q_c: np.ndarray,
    dt: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    离散化：
      - Phi: 二阶级数近似 exp(F dt)
      - Qd : 更合理的近似 —— 对“δp-δv 积分链”补上 dt^3/3 等项

    说明：
    你的旧版 Qd=Qc_eff*dt 会系统性低估位置相关不确定性（尤其长时间积分）。
    这里在不引入 scipy 的情况下使用常见近似：
      对连续白噪声加速度 w_a（通过 R_nb 进入 δv），
      近似得到：
        Qvv ~ Qa * dt
        Qpv ~ Qa * dt^2/2
        Qpp ~ Qa * dt^3/3
    同时保留其它通道（yaw、bias rw）的 dt 一阶项。
    """
    n = F_c.shape[0]
    I = np.eye(n, dtype=float)

    Fdt = F_c * dt
    Phi = I + Fdt + 0.5 * (Fdt @ Fdt)

    Qc_eff = G_c @ Q_c @ G_c.T  # continuous covariance in state space

    # ---- base: dt * Qc_eff ----
    Q_d = Qc_eff * dt

    # ----补：位置积分链（仅对由 w_acc 引起的 δv 噪声）----
    # 识别“加速度噪声 -> δv”的子块：Qc_eff[IDX_V, IDX_V]
    Qvv = Qc_eff[IDX_V, IDX_V].copy()

    # 将 dt*Qvv 中的“δv 部分”保留，同时补齐 cross 与 δp 部分
    # 这里对称写入，保证数值稳定
    Q_d[IDX_P, IDX_P] += Qvv * (dt**3 / 3.0)
    Q_d[IDX_P, IDX_V] += Qvv * (dt**2 / 2.0)
    Q_d[IDX_V, IDX_P] += Qvv * (dt**2 / 2.0)

    # 数值对称化
    Q_d = 0.5 * (Q_d + Q_d.T)
    return Phi, Q_d


def _kalman_update_linear(
    state: EskfState,
    H: np.ndarray,
    r: np.ndarray,
    R: np.ndarray,
    *,
    report: Optional[object] = None,
    report_name: str = "",
) -> EskfState:
    """
    线性更新（Joseph form），并可选输出诊断 report：
      - S, nis, r, S_diag

    兼容性：
      - 旧调用不传 report/report_name 时行为完全一致
      - report 若是 eskf_state.UpdateReport，则填充其字段
    """
    x = state
    P = x.P

    H = np.asarray(H, dtype=float)
    r = np.asarray(r, dtype=float).reshape(-1)
    R = np.asarray(R, dtype=float)

    m = H.shape[0]
    if r.shape[0] != m:
        raise ValueError(f"residual dim mismatch: r.shape={r.shape}, H.shape={H.shape}")
    if R.shape != (m, m):
        raise ValueError(f"R shape mismatch: R.shape={R.shape}, expected {(m, m)}")

    S = H @ P @ H.T + R

    # 更稳健：用 solve 代替 inv
    PHt = P @ H.T
    K = np.linalg.solve(S.T, PHt.T).T  # K = PH^T S^{-1}

    dx = K @ r

    I = np.eye(P.shape[0], dtype=float)
    KH = K @ H
    P_new = (I - KH) @ P @ (I - KH).T + K @ R @ K.T
    P_new = 0.5 * (P_new + P_new.T)

    # --- optional diagnostics ---
    if report is not None:
        try:
            # NIS = r^T S^{-1} r
            nis = float(r.T @ np.linalg.solve(S, r))
            S_diag = np.diag(S).astype(float, copy=True)
            if hasattr(report, "name"):
                report.name = str(report_name)
            if hasattr(report, "t"):
                report.t = float(x.t)
            if hasattr(report, "nis"):
                report.nis = nis
            if hasattr(report, "r"):
                report.r = r.astype(float, copy=True)
            if hasattr(report, "S_diag"):
                report.S_diag = S_diag
        except Exception:
            # 诊断失败不影响滤波主流程
            pass

    # 注入误差到 nominal
    p = x.p + dx[IDX_P]
    v = x.v + dx[IDX_V]
    yaw = wrap_angle_pm_pi(x.yaw + float(dx[IDX_YAW]))
    ba = x.ba + dx[IDX_BA]
    bgz = x.bgz + float(dx[IDX_BGZ])

    return EskfState(t=x.t, p=p, v=v, yaw=yaw, ba=ba, bgz=bgz, P=P_new)


# =============================================================================
# 预测步：IMU 驱动（中点法积分）
# =============================================================================
def eskf_propagate(
    state: EskfState,
    dt: float,
    acc_b_mps2: np.ndarray,
    gyro_z_rad_s: float,
    roll_rad: float,
    pitch_rad: float,
    params: EskfCoreParams,
) -> EskfState:
    """
    名义状态传播（yaw-only）：

      - 外部提供 roll/pitch（通常来自 IMU 自带姿态解算或独立 ESKF）；
      - acc_b_mps2:
          * 若 imu_acc_kind == "linear": 视为 body 线加速度（已扣重力）；
          * 若 imu_acc_kind == "specific_force": 视为 body 比力 f_b，本函数内部加上 g。
      - gyro_z_rad_s: body z 轴角速度（符号通过 params.yaw_sign 适配）。
    """
    if dt <= 0.0:
        return state.copy()

    params.assert_valid()

    x = state
    acc_b = _ensure_vec3(acc_b_mps2)

    # 关键：用 ba 修正线加速度（你的工程中 IMU 预处理已经扣重力）
    acc_eff_b = acc_b - x.ba

    # 1) yaw 积分
    yaw_rate = params.yaw_sign * float(gyro_z_rad_s) - x.bgz
    yaw_mid = wrap_angle_pm_pi(x.yaw + 0.5 * yaw_rate * dt)
    yaw_new = wrap_angle_pm_pi(x.yaw + yaw_rate * dt)

    # 2) 中点姿态
    R_nb_mid = rpy_to_R_nb(
        AttitudeRPY(float(roll_rad), float(pitch_rad), float(yaw_mid))
    )

    # 3) a_nav_mid
    if params.imu_acc_kind == "specific_force":
        g = float(params.gravity)
        g_n = np.array([0.0, 0.0, -g], dtype=float)
        a_nav_mid = R_nb_mid @ acc_eff_b + g_n
    else:
        a_nav_mid = R_nb_mid @ acc_eff_b

    # 4) integrate v,p
    v_new = x.v + a_nav_mid * dt
    p_new = x.p + x.v * dt + 0.5 * a_nav_mid * (dt * dt)

    # === [CLAMP] 对水平速度做硬限幅，避免出现几十 m/s 的“飞车” ===
    # 如果后面想做成可配置的，可以在 EskfCoreParams 里加字段 v_hard_limit_mps
    # v_hard_limit = getattr(params, "v_hard_limit_mps", None)
    # if v_hard_limit is None:
    #     # 先用一个调试值，比如 1.5 m/s
    #     v_hard_limit = 1.5

    # if v_hard_limit is not None and v_hard_limit > 0.0:
    #     vE = float(v_new[0])
    #     vN = float(v_new[1])
    #     vU = float(v_new[2])
    #     v_h = float(np.hypot(vE, vN))  # 水平速度模长

    #     if v_h > v_hard_limit:
    #         scale = v_hard_limit / max(v_h, 1e-6)
    #         vE *= scale
    #         vN *= scale
    #         v_new = np.array([vE, vN, vU], dtype=float)
    #         # 可选 debug：
    #         # print(f"[ESKF][CLAMP] v_h={v_h:.2f} -> {np.hypot(vE, vN):.2f}")

    ba_new = x.ba.copy()
    bgz_new = x.bgz

    # 5) linearization
    F_c = np.zeros((N_STATE, N_STATE), dtype=float)
    F_c[IDX_P, IDX_V] = np.eye(3, dtype=float)

    # vdot = R_nb (acc - ba) ...
    F_c[IDX_V, IDX_BA] = -R_nb_mid

    # yaw effect: use acc_eff for better linearization
    e3x = _skew_z()
    F_v_yaw = R_nb_mid @ (e3x @ acc_eff_b)
    F_c[IDX_V, IDX_YAW] = F_v_yaw

    # yawdot = ... - bgz
    F_c[IDX_YAW, IDX_BGZ] = -1.0

    # process noise mapping
    # q = [w_acc(3), w_gyro_z, w_ba(3), w_bgz]
    G_c = np.zeros((N_STATE, 8), dtype=float)
    G_c[IDX_V, 0:3] = R_nb_mid
    G_c[IDX_YAW, 3] = 1.0
    G_c[IDX_BA, 4:7] = np.eye(3, dtype=float)
    G_c[IDX_BGZ, 7] = 1.0

    sigma_a = float(params.sigma_acc_mps2)
    sigma_g = float(params.sigma_gyro_rad_s)
    sigma_ba = float(params.sigma_ba_rw_mps2_sqrt_s)
    sigma_bg = float(params.sigma_bgz_rw_rad_s_sqrt_s)

    Q_c = np.diag(
        np.array(
            [
                sigma_a**2,
                sigma_a**2,
                sigma_a**2,
                sigma_g**2,
                sigma_ba**2,
                sigma_ba**2,
                sigma_ba**2,
                sigma_bg**2,
            ],
            dtype=float,
        )
    )

    Phi, Q_d = _discretize_F_Q(F_c, G_c, Q_c, dt)

    P_new = Phi @ x.P @ Phi.T + Q_d
    # === 额外：给速度状态加“工况相关”的过程噪声 q_vel ===
    q_vel = float(getattr(params, "q_vel", 0.0))
    if q_vel > 0.0:
        # q_vel 的单位大致可以理解为 [ (m/s)^2 / s ]
        P_new[IDX_V, IDX_V] += q_vel * dt * np.eye(3, dtype=float)
    # 数值对称化
    P_new = 0.5 * (P_new + P_new.T)

    return EskfState(
        t=x.t + dt,
        p=p_new,
        v=v_new,   # 注意：这里已经是限幅后的 v_new
        yaw=yaw_new,
        ba=ba_new,
        bgz=bgz_new,
        P=P_new,
    )

# =============================================================================
# 观测更新：DVL BE / BI / yaw / 垂向伪测量
# =============================================================================
def eskf_update_dvl_be_vel(
    state: EskfState,
    v_be_nav_mps: np.ndarray,
    R_meas: np.ndarray,
) -> EskfState:
    """
    DVL BE 速度观测更新（3 轴 nav 速度）：

    约定：
      - state.v 为 nav 坐标系下的速度（与 p 同一坐标系，例如 ENU 或 END）。
      - v_be_nav_mps 必须已经从 DVL 自身坐标（典型为 ENU: Ve,Vn,Vu）转换到
        与 state.v 相同的 nav 坐标系。例如：
          * 若 ESKF 使用 ENU，则可以直接 v_nav = [Ve, Vn, Vu]；
          * 若 ESKF 使用 END，则需要 v_nav = [Ve, Vn, -Vu]（Up→Down）。
      - R_meas 为 3x3 协方差矩阵，单位 (m/s)^2。
    """
    v_meas_nav = _ensure_vec3(v_be_nav_mps)
    v_pred_nav = state.v
    r = v_meas_nav - v_pred_nav

    H = np.zeros((3, N_STATE), dtype=float)
    H[:, IDX_V] = np.eye(3, dtype=float)

    R = np.asarray(R_meas, dtype=float)
    if R.shape != (3, 3):
        raise ValueError(f"DVL BE R must be 3x3, got {R.shape}")

    return _kalman_update_linear(state, H, r, R)


def eskf_update_dvl_be_vel_with_report(
    state: EskfState,
    v_be_nav_mps: np.ndarray,
    R_meas: np.ndarray,
    report: object,
) -> EskfState:
    """
    带诊断输出的 BE 速度更新。
    约定同 eskf_update_dvl_be_vel。
    """
    v_meas_nav = _ensure_vec3(v_be_nav_mps)
    v_pred_nav = state.v
    r = v_meas_nav - v_pred_nav

    H = np.zeros((3, N_STATE), dtype=float)
    H[:, IDX_V] = np.eye(3, dtype=float)

    R = np.asarray(R_meas, dtype=float)
    if R.shape != (3, 3):
        raise ValueError(f"DVL BE R must be 3x3, got {R.shape}")

    return _kalman_update_linear(state, H, r, R, report=report, report_name="dvl_be_vel")



def eskf_update_dvl_bi_vel(
    state: EskfState,
    v_bi_body_mps: np.ndarray,
    roll_rad: float,
    pitch_rad: float,
    R_meas: np.ndarray,
) -> EskfState:
    """
    DVL BI 体速度观测更新：

    约定：
      - body 坐标系采用 FRD：X 前、Y 右、Z 下（与你 IMU/DVL 标定一致）。
      - nav 坐标系由 rpy_to_R_nb 定义（通常 ENU）。
      - v_bi_body_mps 为 DVL 体速度（BI 行）：[Vx_body, Vy_body, Vz_body]，单位 m/s。
      - state.v 为 nav 速度，v_pred_body = R_bn @ state.v。
    """
    v_meas_b = _ensure_vec3(v_bi_body_mps)

    R_nb = rpy_to_R_nb(AttitudeRPY(float(roll_rad), float(pitch_rad), float(state.yaw)))
    R_bn = R_nb.T

    v_pred_b = R_bn @ state.v
    r = v_meas_b - v_pred_b

    H = np.zeros((3, N_STATE), dtype=float)
    H[:, IDX_V] = R_bn

    R = np.asarray(R_meas, dtype=float)
    if R.shape != (3, 3):
        raise ValueError(f"DVL BI R must be 3x3, got {R.shape}")

    return _kalman_update_linear(state, H, r, R)


def eskf_update_dvl_bi_vel_with_report(
    state: EskfState,
    v_bi_body_mps: np.ndarray,
    roll_rad: float,
    pitch_rad: float,
    R_meas: np.ndarray,
    report: object,
) -> EskfState:
    v_meas_b = _ensure_vec3(v_bi_body_mps)

    R_nb = rpy_to_R_nb(AttitudeRPY(float(roll_rad), float(pitch_rad), float(state.yaw)))
    R_bn = R_nb.T

    v_pred_b = R_bn @ state.v
    r = v_meas_b - v_pred_b

    H = np.zeros((3, N_STATE), dtype=float)
    H[:, IDX_V] = R_bn

    R = np.asarray(R_meas, dtype=float)
    if R.shape != (3, 3):
        raise ValueError(f"DVL BI R must be 3x3, got {R.shape}")

    return _kalman_update_linear(state, H, r, R, report=report, report_name="dvl_bi_vel")


def eskf_update_yaw_from_dvl(
    state: EskfState,
    yaw_meas_rad: float,
    R_meas: float,
) -> EskfState:
    yaw_pred = state.yaw
    r_yaw = wrap_angle_pm_pi(float(yaw_meas_rad) - yaw_pred)
    r = np.array([r_yaw], dtype=float)

    H = np.zeros((1, N_STATE), dtype=float)
    H[0, IDX_YAW] = 1.0

    R = np.array([[float(R_meas)]], dtype=float)
    return _kalman_update_linear(state, H, r, R)


def eskf_update_yaw_from_dvl_with_report(
    state: EskfState,
    yaw_meas_rad: float,
    R_meas: float,
    report: object,
) -> EskfState:
    yaw_pred = state.yaw
    r_yaw = wrap_angle_pm_pi(float(yaw_meas_rad) - yaw_pred)
    r = np.array([r_yaw], dtype=float)

    H = np.zeros((1, N_STATE), dtype=float)
    H[0, IDX_YAW] = 1.0

    R = np.array([[float(R_meas)]], dtype=float)
    return _kalman_update_linear(state, H, r, R, report=report, report_name="yaw_from_vel")


def eskf_update_vertical_velocity_pseudo(
    state: EskfState,
    vu_target_mps: float,
    R_meas: float,
) -> EskfState:
    """
    垂向速度伪测量更新：

    约定：
      - 使用 state.v[2] 作为 nav 坐标的 z 分量（通常为 U，如果 nav 是 ENU）。
      - 调用方必须确保 vu_target_mps 与 state.v[2] 的“正方向”一致：
          * 若 nav 为 ENU（z 向上），则 vu_target_mps 表示“向上速度”；
          * 若 nav 为 END（z 向下），则应传入 vD_target，并保持 H 对应的是 v[2]=D。
    """
    v_z_pred = float(state.v[2])
    r = np.array([float(vu_target_mps) - v_z_pred], dtype=float)

    H = np.zeros((1, N_STATE), dtype=float)
    H[0, IDX_V.start + 2] = 1.0

    R = np.array([[float(R_meas)]], dtype=float)
    return _kalman_update_linear(state, H, r, R)



def eskf_update_vertical_velocity_pseudo_with_report(
    state: EskfState,
    vu_target_mps: float,
    R_meas: float,
    report: object,
) -> EskfState:
    v_u_pred = float(state.v[2])
    r = np.array([float(vu_target_mps) - v_u_pred], dtype=float)

    H = np.zeros((1, N_STATE), dtype=float)
    H[0, IDX_V.start + 2] = 1.0

    R = np.array([[float(R_meas)]], dtype=float)
    return _kalman_update_linear(state, H, r, R, report=report, report_name="vu_pseudo")


# =============================================================================
# 初始状态辅助函数
# =============================================================================

def make_initial_state(
    t0: float,
    p0_enu: np.ndarray,
    v0_enu: np.ndarray,
    yaw0_rad: float,
    ba0_b: np.ndarray,
    bgz0: float,
    P0_diag: np.ndarray,
) -> EskfState:
    p0 = _ensure_vec3(p0_enu)
    v0 = _ensure_vec3(v0_enu)
    ba0 = _ensure_vec3(ba0_b)
    yaw0 = wrap_angle_pm_pi(float(yaw0_rad))

    P0_diag = np.asarray(P0_diag, dtype=float).reshape(N_STATE)
    P0 = np.diag(P0_diag)

    return EskfState(
        t=float(t0),
        p=p0,
        v=v0,
        yaw=yaw0,
        ba=ba0,
        bgz=float(bgz0),
        P=P0,
    )
