# src/offnav/models/attitude.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional,Union

import numpy as np

EPS = 1e-12

ArrayLike = Union[float, np.ndarray]
# =========================
# 角度工具
# =========================

def wrap_angle_pm_pi(x: ArrayLike, *, keep_nan: bool = True) -> ArrayLike:
    """
    Wrap angle(s) to (-pi, pi].

    - Works for scalar or numpy array
    - NaN/inf safe:
        * keep_nan=True  -> NaN/inf stays NaN (recommended)
        * keep_nan=False -> replace non-finite with 0.0 before wrapping
    """
    # Scalar fast path
    if np.isscalar(x):
        xv = float(x)
        if not np.isfinite(xv):
            return np.nan if keep_nan else 0.0
        return (xv + np.pi) % (2.0 * np.pi) - np.pi

    a = np.asarray(x, dtype=float)
    if a.size == 0:
        return a  # empty array, keep shape

    m = np.isfinite(a)
    out = np.empty_like(a, dtype=float)

    if keep_nan:
        out[~m] = np.nan
        out[m] = (a[m] + np.pi) % (2.0 * np.pi) - np.pi
    else:
        aa = a.copy()
        aa[~m] = 0.0
        out = (aa + np.pi) % (2.0 * np.pi) - np.pi

    return out


def wrap_angle_0_2pi(x: ArrayLike) -> ArrayLike:
    """把角度 wrap 到 [0, 2pi) 区间。"""
    return x % (2.0 * np.pi)


# =========================
# 姿态表示：roll, pitch, yaw（ENU）
# =========================

@dataclass
class AttitudeRPY:
    """
    ENU 坐标系下的欧拉角表示：

        roll  : 机体绕 x 轴旋转 [rad]
        pitch : 机体绕 y 轴旋转 [rad]
        yaw   : 机体绕 z 轴旋转 [rad]

    约定（与 yaw_from_enu_velocity 保持一致）：
      - ENU（x=East, y=North, z=Up）
      - 航海式 yaw：yaw=0 朝东，yaw=pi/2 朝北
        因此：yaw = atan2(Vn, Ve)  （注意顺序）
    """
    roll: float
    pitch: float
    yaw: float


def rpy_to_R_nb(att: AttitudeRPY) -> np.ndarray:
    """
    roll/pitch/yaw → R_nb（body -> nav, ENU 约定）：

        R_nb = Rz(yaw) * Ry(pitch) * Rx(roll)
    """
    r, p, y = att.roll, att.pitch, att.yaw
    cr, sr = np.cos(r), np.sin(r)
    cp, sp = np.cos(p), np.sin(p)
    cy, sy = np.cos(y), np.sin(y)

    Rz = np.array(
        [[cy, -sy, 0.0],
         [sy,  cy, 0.0],
         [0.0, 0.0, 1.0]],
        dtype=float,
    )
    Ry = np.array(
        [[cp, 0.0, sp],
         [0.0, 1.0, 0.0],
         [-sp, 0.0, cp]],
        dtype=float,
    )
    Rx = np.array(
        [[1.0, 0.0, 0.0],
         [0.0,  cr, -sr],
         [0.0,  sr,  cr]],
        dtype=float,
    )

    return Rz @ Ry @ Rx


def rpy_to_R_bn(att: AttitudeRPY) -> np.ndarray:
    """roll/pitch/yaw → R_bn（nav -> body, ENU 约定）。"""
    R_nb = rpy_to_R_nb(att)
    return R_nb.T


# =========================
# 体/导航坐标变换
# =========================

def body_to_nav(vec_body: np.ndarray, att: AttitudeRPY) -> np.ndarray:
    """
    体坐标向量 -> 导航坐标向量。
    vec_body: (..., 3)
    返回:    (..., 3)
    """
    R_nb = rpy_to_R_nb(att)
    return (R_nb @ vec_body.T).T


def nav_to_body(vec_nav: np.ndarray, att: AttitudeRPY) -> np.ndarray:
    """导航坐标向量 -> 体坐标向量。"""
    R_bn = rpy_to_R_bn(att)
    return (R_bn @ vec_nav.T).T


# =========================
# 四元数工具（新增，不破坏旧接口）
# =========================
# 约定：q_nb 表示 body->nav 的旋转，向量变换 v_n = R_nb * v_b
# 四元数采用 [w, x, y, z]，Hamilton 乘法

def quat_normalize(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64).reshape(4)
    n = np.linalg.norm(q)
    if n < EPS:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    return q / n


def quat_conj(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64).reshape(4)
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def quat_mul(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Hamilton product, both [w,x,y,z]."""
    w1, x1, y1, z1 = np.asarray(q1, dtype=np.float64).reshape(4)
    w2, x2, y2, z2 = np.asarray(q2, dtype=np.float64).reshape(4)
    return np.array([
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
    ], dtype=np.float64)


def quat_from_rotvec(rv: np.ndarray) -> np.ndarray:
    """
    rotvec(rv, rad) -> quaternion [w,x,y,z]
    rv = axis * angle, angle = ||rv||
    """
    rv = np.asarray(rv, dtype=np.float64).reshape(3)
    theta = np.linalg.norm(rv)
    if theta < 1e-8:
        # small-angle approx: sin(theta/2)/theta ≈ 1/2
        half = 0.5
        return quat_normalize(np.array([1.0, half*rv[0], half*rv[1], half*rv[2]], dtype=np.float64))
    axis = rv / theta
    half = 0.5 * theta
    s = np.sin(half)
    return quat_normalize(np.array([np.cos(half), s*axis[0], s*axis[1], s*axis[2]], dtype=np.float64))


def quat_to_R_nb(q_nb: np.ndarray) -> np.ndarray:
    """q_nb -> R_nb (body->nav, ENU)."""
    w, x, y, z = quat_normalize(q_nb)
    ww, xx, yy, zz = w*w, x*x, y*y, z*z
    return np.array([
        [ww+xx-yy-zz, 2*(x*y - w*z), 2*(x*z + w*y)],
        [2*(x*y + w*z), ww-xx+yy-zz, 2*(y*z - w*x)],
        [2*(x*z - w*y), 2*(y*z + w*x), ww-xx-yy+zz],
    ], dtype=np.float64)


def R_nb_to_rpy(R_nb: np.ndarray) -> AttitudeRPY:
    """
    从 R_nb 提取 ZYX 欧拉角（yaw-pitch-roll），满足：
      R_nb = Rz(yaw) * Ry(pitch) * Rx(roll)

    yaw=atan2(R[1,0], R[0,0]) -> yaw=0 朝东，pi/2 朝北
    """
    R = np.asarray(R_nb, dtype=np.float64).reshape(3, 3)

    sp = -R[2, 0]
    sp = np.clip(sp, -1.0, 1.0)
    pitch = float(np.arcsin(sp))

    # gimbal lock
    if abs(abs(pitch) - np.pi/2) < 1e-6:
        roll = 0.0
        yaw = float(np.arctan2(-R[0, 1], R[1, 1]))
    else:
        roll = float(np.arctan2(R[2, 1], R[2, 2]))
        yaw = float(np.arctan2(R[1, 0], R[0, 0]))

    return AttitudeRPY(
        roll=float(wrap_angle_pm_pi(roll)),
        pitch=float(wrap_angle_pm_pi(pitch)),
        yaw=float(wrap_angle_pm_pi(yaw)),
    )


def quat_rotate(q_nb: np.ndarray, v_body: np.ndarray) -> np.ndarray:
    """v_n = q_nb ⊗ [0,v_b] ⊗ q_nb*"""
    v = np.asarray(v_body, dtype=np.float64).reshape(3)
    qv = np.array([0.0, v[0], v[1], v[2]], dtype=np.float64)
    return quat_mul(quat_mul(q_nb, qv), quat_conj(q_nb))[1:]


def quat_unrotate(q_nb: np.ndarray, v_nav: np.ndarray) -> np.ndarray:
    """v_b = q_nb* ⊗ [0,v_n] ⊗ q_nb"""
    v = np.asarray(v_nav, dtype=np.float64).reshape(3)
    qv = np.array([0.0, v[0], v[1], v[2]], dtype=np.float64)
    return quat_mul(quat_mul(quat_conj(q_nb), qv), q_nb)[1:]


# =========================
# 简单姿态积分（旧接口保留 + 新增四元数版）
# =========================

def integrate_yaw(
    t_s: np.ndarray,
    yaw_rate: np.ndarray,
    yaw0: float,
) -> np.ndarray:
    """
    仅积分 yaw 的简单欧拉法：

        yaw[k] = wrap_pi( yaw[k-1] + yaw_rate[k-1] * dt )
    """
    n = len(t_s)
    if n == 0:
        return np.zeros((0,), dtype=float)

    yaw = np.empty((n,), dtype=float)
    yaw[0] = wrap_angle_pm_pi(yaw0)

    dt = np.diff(t_s)
    for k in range(1, n):
        dt_k = dt[k - 1]
        if not np.isfinite(dt_k) or dt_k <= 0.0:
            dt_k = 0.0
        yaw[k] = wrap_angle_pm_pi(yaw[k - 1] + yaw_rate[k - 1] * dt_k)

    return yaw


def integrate_rpy_euler(
    t_s: np.ndarray,
    omega_body: np.ndarray,
    rpy0: AttitudeRPY,
) -> np.ndarray:
    """
    旧版近似：把体角速度 (wx, wy, wz) 近似为 roll/pitch/yaw 的一阶导，用欧拉法积分。
    输出 rpy_seq: (N,3)，roll/pitch/yaw（rad），wrap 到 (-pi, pi]。
    """
    n = len(t_s)
    if n == 0:
        return np.zeros((0, 3), dtype=float)

    rpy = np.empty((n, 3), dtype=float)
    rpy[0, :] = np.array([rpy0.roll, rpy0.pitch, rpy0.yaw], dtype=float)

    dt = np.diff(t_s)
    for k in range(1, n):
        dt_k = dt[k - 1]
        if not np.isfinite(dt_k) or dt_k <= 0.0:
            dt_k = 0.0
        rpy[k, :] = rpy[k - 1, :] + omega_body[k - 1, :] * dt_k
        rpy[k, :] = wrap_angle_pm_pi(rpy[k, :])

    return rpy


def integrate_rpy_quat(
    t_s: np.ndarray,
    omega_body: np.ndarray,
    rpy0: AttitudeRPY,
    return_quat: bool = False,
) -> np.ndarray | Tuple[np.ndarray, np.ndarray]:
    """
    新版：四元数积分（推荐用于扣重力/工程闭环），再回写欧拉角（ENU, yaw=0东, pi/2北）。
    这里仍保持输入/输出形态尽量接近旧接口。

    输入:
      t_s: (N,)
      omega_body: (N,3) rad/s, body 角速度 [wx,wy,wz]
      rpy0: 初始 rpy
    输出:
      rpy_seq: (N,3)
      (可选) q_seq: (N,4) [w,x,y,z], q_nb

    注意：rpy0 -> 初始 R_nb -> 初始 q_nb（用矩阵转四元数的简化实现）
    """
    t_s = np.asarray(t_s, dtype=np.float64).reshape(-1)
    omega_body = np.asarray(omega_body, dtype=np.float64).reshape(-1, 3)
    n = len(t_s)
    if n == 0:
        empty_rpy = np.zeros((0, 3), dtype=float)
        if return_quat:
            return empty_rpy, np.zeros((0, 4), dtype=float)
        return empty_rpy

    # 初始：用 rpy0 构造 R_nb，再转成 q_nb
    R0 = rpy_to_R_nb(rpy0)

    def _R_to_quat(R: np.ndarray) -> np.ndarray:
        # 经典稳定实现（对称迹）
        R = np.asarray(R, dtype=np.float64).reshape(3, 3)
        tr = np.trace(R)
        if tr > 0.0:
            S = np.sqrt(tr + 1.0) * 2.0
            w = 0.25 * S
            x = (R[2, 1] - R[1, 2]) / S
            y = (R[0, 2] - R[2, 0]) / S
            z = (R[1, 0] - R[0, 1]) / S
        else:
            if (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
                S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
                w = (R[2, 1] - R[1, 2]) / S
                x = 0.25 * S
                y = (R[0, 1] + R[1, 0]) / S
                z = (R[0, 2] + R[2, 0]) / S
            elif R[1, 1] > R[2, 2]:
                S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
                w = (R[0, 2] - R[2, 0]) / S
                x = (R[0, 1] + R[1, 0]) / S
                y = 0.25 * S
                z = (R[1, 2] + R[2, 1]) / S
            else:
                S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
                w = (R[1, 0] - R[0, 1]) / S
                x = (R[0, 2] + R[2, 0]) / S
                y = (R[1, 2] + R[2, 1]) / S
                z = 0.25 * S
        return quat_normalize(np.array([w, x, y, z], dtype=np.float64))

    q = _R_to_quat(R0)

    rpy_seq = np.empty((n, 3), dtype=np.float64)
    q_seq = np.empty((n, 4), dtype=np.float64)

    rpy_seq[0, :] = np.array([rpy0.roll, rpy0.pitch, rpy0.yaw], dtype=np.float64)
    rpy_seq[0, :] = wrap_angle_pm_pi(rpy_seq[0, :])
    q_seq[0, :] = q

    dt = np.diff(t_s)
    for k in range(1, n):
        dt_k = float(dt[k - 1])
        if not np.isfinite(dt_k) or dt_k <= 0.0:
            dt_k = 0.0

        dq = quat_from_rotvec(omega_body[k - 1, :] * dt_k)
        q = quat_normalize(quat_mul(q, dq))

        R = quat_to_R_nb(q)
        att = R_nb_to_rpy(R)

        rpy_seq[k, 0] = att.roll
        rpy_seq[k, 1] = att.pitch
        rpy_seq[k, 2] = att.yaw
        q_seq[k, :] = q

    if return_quat:
        return rpy_seq.astype(float), q_seq.astype(float)
    return rpy_seq.astype(float)


@dataclass
class AttitudeState:
    q_nb: np.ndarray
    rpy: AttitudeRPY


class AttitudeIntegrator:
    """
    流式积分器（四元数），用于在线/预处理按 dt 逐步更新姿态。
    """
    def __init__(self, rpy0: Optional[AttitudeRPY] = None):
        if rpy0 is None:
            self.q_nb = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        else:
            R0 = rpy_to_R_nb(rpy0)
            # 复用 integrate_rpy_quat 内部同款 R->q
            self.q_nb = integrate_rpy_quat(np.array([0.0, 0.0]), np.zeros((2, 3)), rpy0, return_quat=True)[1][0]
        self.q_nb = quat_normalize(self.q_nb)

    def reset(self, rpy0: Optional[AttitudeRPY] = None) -> None:
        self.__init__(rpy0=rpy0)

    def step(self, omega_body: np.ndarray, dt: float) -> AttitudeState:
        w = np.asarray(omega_body, dtype=np.float64).reshape(3)
        dt = float(dt)
        dq = quat_from_rotvec(w * dt)
        self.q_nb = quat_normalize(quat_mul(self.q_nb, dq))
        att = R_nb_to_rpy(quat_to_R_nb(self.q_nb))
        return AttitudeState(q_nb=self.q_nb.copy(), rpy=att)


# =========================
# 速度 → yaw 观测（DVL）
# =========================

def yaw_from_enu_velocity(ve: float, vn: float) -> float:
    """
    根据 ENU 水平速度 (Ve, Vn) 计算航向 yaw：

        yaw = atan2(Vn, Ve)

    对应：yaw=0 朝东，yaw=pi/2 朝北，并 wrap 到 (-pi, pi]。
    """
    z = np.arctan2(vn, ve)
    return float(wrap_angle_pm_pi(z))


def yaw_from_enu_velocity_vec(vel_enu: np.ndarray) -> np.ndarray:
    """
    批量版本：vel_enu: (N,3)，列分别为 [Ve, Vn, Vu] 或至少 [0]=Ve, [1]=Vn。
    返回 yaw 序列 (N,)。
    """
    vel_enu = np.asarray(vel_enu, dtype=np.float64)
    ve = vel_enu[:, 0]
    vn = vel_enu[:, 1]
    z = np.arctan2(vn, ve)
    return wrap_angle_pm_pi(z)
