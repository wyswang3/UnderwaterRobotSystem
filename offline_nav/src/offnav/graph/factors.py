from __future__ import annotations

"""
Factor definitions for offline factor-graph navigation (IMU + DVL, LV1 bias model).

本模块定义“离线因子图导航”所需的各类因子：
- 先验因子: PriorStateBiasFactor
- IMU 过程因子: ImuProcessFactor
- DVL 速度因子 (BE/BI): DvlBEVelFactor, DvlBIVelFactor
- DVL yaw-from-velocity 因子: YawFromVelFactor

所有因子都基于同一个参数向量 θ:
    θ = [x_0(7), x_1(7), ..., x_{N-1}(7), ba(3), bgz(1)]
其中:
    x_k = [p_k(3), v_k(3), yaw_k(1)]

注意:
- 本模块只负责“局部数学”和“从 θ 中取块”的 glue，不负责整体矩阵拼接和求解；
- 雅可比在第一版采用有限差分实现，后续可逐步替换为解析形式。
"""

from dataclasses import dataclass, field
from typing import Protocol, Callable, List, Sequence

import numpy as np

from offnav.graph.states import (
    STATE_SIZE,
    BIAS_SIZE,
    state_slice,
    bias_slice,
    wrap_yaw,
)
from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb, yaw_from_enu_velocity


# ============================================================
# 通用 Factor 接口
# ============================================================


class Factor(Protocol):
    """
    因子接口约定.

    每个因子 f_j(θ) 提供:
    - residual(θ): 返回局部残差 r_j ∈ R^m
    - jacobian(θ): 返回对全局 θ 的雅可比 J_j ∈ R^{m×D}
    - weight_chol(): 返回观测噪声协方差 R_j 的 Cholesky 逆 (R^{-1/2}),
                     第一版默认对角协方差 -> 返回 diag(1/std_i).
    """

    def residual(self, theta: np.ndarray) -> np.ndarray:
        ...

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        ...

    def weight_chol(self) -> np.ndarray:
        ...


# ============================================================
# 有限差分工具（局部稀疏数值雅可比）
# ============================================================


def _finite_diff_jacobian(
    theta: np.ndarray,
    residual_func: Callable[[np.ndarray], np.ndarray],
    param_indices: Sequence[int],
    eps: float = 1e-6,
) -> np.ndarray:
    """
    针对“只依赖 θ 若干维”的因子，使用有限差分在这些维度上构造稀疏雅可比.
    """
    theta = np.asarray(theta, dtype=float).reshape(-1)
    r0 = residual_func(theta)
    r0 = np.asarray(r0, dtype=float).reshape(-1)
    m = r0.shape[0]
    D = theta.shape[0]

    J = np.zeros((m, D), dtype=float)

    for idx in param_indices:
        theta_pert = theta.copy()
        theta_pert[idx] += eps
        r1 = residual_func(theta_pert).reshape(-1)
        J[:, idx] = (r1 - r0) / eps

    return J


# ============================================================
# 1) 先验因子: 状态 + bias
# ============================================================


@dataclass
class PriorStateBiasFactor:
    """
    先验因子: 对 x_0 和全局 bias 给出高斯先验.

    残差向量:
        r = [
            p_0 - p0_mean (3)
            v_0 - v0_mean (3)
            wrap(yaw_0 - yaw0_mean) (1)
            ba  - ba_mean (3)
            bgz - bgz_mean (1)
        ] ∈ R^{11}
    """

    num_states: int

    # 先验均值
    p0_mean: np.ndarray  # shape (3,)
    v0_mean: np.ndarray  # shape (3,)
    yaw0_mean: float
    ba_mean: np.ndarray  # shape (3,)
    bgz_mean: float

    # 先验 std
    prior_p_std: float
    prior_v_std: float
    prior_yaw_std: float
    prior_ba_std: float
    prior_bgz_std: float

    # 有限差分步长
    eps: float = 1e-6

    # 调试开关
    debug: bool = False
    _printed_once: bool = field(default=False, init=False, repr=False)

    def _std_vec(self) -> np.ndarray:
        std = np.zeros(11, dtype=float)
        std[0:3] = self.prior_p_std
        std[3:6] = self.prior_v_std
        std[6] = self.prior_yaw_std
        std[7:10] = self.prior_ba_std
        std[10] = self.prior_bgz_std
        return std

    def residual(self, theta: np.ndarray) -> np.ndarray:
        theta = np.asarray(theta, dtype=float).reshape(-1)

        # x_0
        s0 = state_slice(0, self.num_states)
        x0 = theta[s0]  # [p(3), v(3), yaw]

        p0 = x0[0:3]
        v0 = x0[3:6]
        yaw0 = wrap_yaw(float(x0[6]))

        # bias
        sb = bias_slice(self.num_states)
        b = theta[sb]
        ba = b[0:3]
        bgz = float(b[3])

        r = np.zeros(11, dtype=float)

        r[0:3] = p0 - self.p0_mean.reshape(3)
        r[3:6] = v0 - self.v0_mean.reshape(3)
        r[6] = wrap_yaw(yaw0 - float(self.yaw0_mean))
        r[7:10] = ba - self.ba_mean.reshape(3)
        r[10] = bgz - float(self.bgz_mean)

        if self.debug and not self._printed_once:
            self._printed_once = True
            print(
                "[FACTOR][PRIOR] "
                f"|r_p|={np.linalg.norm(r[0:3]):.3e}, "
                f"|r_v|={np.linalg.norm(r[3:6]):.3e}, "
                f"r_yaw={r[6]:.3e}, "
                f"|r_ba|={np.linalg.norm(r[7:10]):.3e}, "
                f"r_bgz={r[10]:.3e}"
            )

        return r

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        # 关联变量: x_0(前 7 维) + bias(最后 4 维)
        s0 = state_slice(0, self.num_states)
        sb = bias_slice(self.num_states)
        idxs: List[int] = []
        idxs.extend(range(s0.start, s0.stop))
        idxs.extend(range(sb.start, sb.stop))

        return _finite_diff_jacobian(theta, self.residual, idxs, eps=self.eps)

    def weight_chol(self) -> np.ndarray:
        """
        返回 diag(1 / std_i)，维度 11×11.
        """
        std = self._std_vec()
        inv_std = np.where(std > 0.0, 1.0 / std, 0.0)
        return np.diag(inv_std)


# ============================================================
# 2) IMU 过程因子（LV1 简化版）
# ============================================================


@dataclass
class ImuProcessFactor:
    """
    IMU 过程因子: 连接 x_k, x_{k+1}, bias.

    当前 LV1 简化模型只使用“位姿连续性约束”，不显式用到加速度/角速度：

        state layout: x_k = [p_k(3), v_k(3), yaw_k(1)]

        r_pos = p_{k+1} - (p_k + v_k * dt)
        r_vel = v_{k+1} - v_k
        r_yaw = wrap_yaw(yaw_{k+1} - yaw_k)

    分别用 std_pos / std_vel / std_yaw 做尺度归一化。
    """

    num_states: int
    k: int            # 区间 [k, k+1]
    dt: float

    # IMU 输入暂时保留接口，后续 LV2/真实模型会重新启用
    acc_body: np.ndarray  # shape (3,)
    gyro_body: np.ndarray  # shape (3,)
    roll_rad: float
    pitch_rad: float

    # 重力（当前简化模型未用，保留字段）
    g_val: float = 9.78

    # 过程噪声 std（注意: 这里是“离散步”的 std，不是连续谱密度）
    std_pos: float = 1.0e-3
    std_vel: float = 1.0e-2
    std_yaw: float = np.deg2rad(1.0)

    eps: float = 1e-6

    # 调试
    debug: bool = False
    _printed_once: bool = field(default=False, init=False, repr=False)

    def _std_vec(self) -> np.ndarray:
        std = np.zeros(7, dtype=float)
        std[0:3] = self.std_pos
        std[3:6] = self.std_vel
        std[6] = self.std_yaw
        return std

    def residual(self, theta: np.ndarray) -> np.ndarray:
        theta = np.asarray(theta, dtype=float).reshape(-1)

        sk = state_slice(self.k, self.num_states)
        sk1 = state_slice(self.k + 1, self.num_states)

        xk = theta[sk]
        xk1 = theta[sk1]

        p_k = xk[0:3]
        v_k = xk[3:6]
        yaw_k = float(xk[6])

        p_k1 = xk1[0:3]
        v_k1 = xk1[3:6]
        yaw_k1 = float(xk1[6])

        dt = float(self.dt)

        # 未归一化残差
        r_pos = p_k1 - (p_k + v_k * dt)
        r_vel = v_k1 - v_k
        r_yaw = wrap_yaw(yaw_k1 - yaw_k)

        # 归一化
        std_pos = float(self.std_pos)
        std_vel = float(self.std_vel)
        std_yaw = float(self.std_yaw)

        r_pos_n = r_pos / std_pos
        r_vel_n = r_vel / std_vel
        r_yaw_n = r_yaw / std_yaw

        r = np.concatenate(
            [r_pos_n, r_vel_n, np.array([r_yaw_n], dtype=float)],
            axis=0,
        )

        if self.debug and not self._printed_once:
            self._printed_once = True
            print(
                f"[FACTOR][IMU] k={self.k}, dt={dt:.3f} "
                f"|r_pos|={np.linalg.norm(r_pos):.3e}, "
                f"|r_vel|={np.linalg.norm(r_vel):.3e}, "
                f"r_yaw={r_yaw:.3e}"
            )

        return r

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        """
        当前使用有限差分 Jacobian（对 [x_k, x_{k+1}, bias] 求导），
        保证正确性优先；后续如需提速可替换为解析形式。
        """
        theta = np.asarray(theta, dtype=float).reshape(-1)
        sk = state_slice(self.k, self.num_states)
        sk1 = state_slice(self.k + 1, self.num_states)
        sb = bias_slice(self.num_states)

        idxs: List[int] = []
        idxs.extend(range(sk.start, sk.stop))
        idxs.extend(range(sk1.start, sk1.stop))
        idxs.extend(range(sb.start, sb.stop))

        return _finite_diff_jacobian(theta, self.residual, idxs, eps=self.eps)

    def weight_chol(self) -> np.ndarray:
        std = self._std_vec()
        inv_std = np.where(std > 0.0, 1.0 / std, 0.0)
        return np.diag(inv_std)


# ============================================================
# 3) DVL 速度因子 (BE: ENU 速度)
# ============================================================


@dataclass
class DvlBEVelFactor:
    """
    DVL ENU 速度观测因子（BE 源）：

    - 关联变量: 第 k 个状态 x_k = [p(3), v(3), yaw]
    - 模型:     v_k (state) 直接对应 ENU 速度观测 vel_enu
    - 残差:   r = v_k - vel_enu  ∈ R^3
    """

    num_states: int
    k: int
    vel_enu: np.ndarray      # shape (3,), [Ve, Vn, Vu] in ENU
    std_be: float            # 观测噪声 std [m/s]

    debug: bool = False
    _printed_once: bool = field(default=False, init=False, repr=False)

    def residual(self, theta: np.ndarray) -> np.ndarray:
        theta = np.asarray(theta, dtype=float).reshape(-1)

        if not (0 <= self.k < self.num_states):
            raise IndexError(f"DvlBEVelFactor k={self.k} out of [0, {self.num_states})")

        sk = state_slice(self.k, self.num_states)
        xk = theta[sk]
        v_k = xk[3:6]

        z = self.vel_enu.reshape(3)
        r = v_k - z

        if self.debug and not self._printed_once:
            self._printed_once = True
            print(
                f"[FACTOR][DVL_BE] k={self.k} "
                f"v_state={v_k}, v_meas={z}, |r|={np.linalg.norm(r):.3e}"
            )

        return r.astype(float)

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        """
        残差只依赖于 x_k 的速度分量 v_k，因此:

            ∂r/∂v_k = I, 其它维度为 0
        """
        theta = np.asarray(theta, dtype=float).reshape(-1)
        D = theta.shape[0]
        J = np.zeros((3, D), dtype=float)

        sk = state_slice(self.k, self.num_states)
        idx_v0 = sk.start + 3
        idx_v1 = sk.start + 4
        idx_v2 = sk.start + 5

        J[0, idx_v0] = 1.0
        J[1, idx_v1] = 1.0
        J[2, idx_v2] = 1.0

        return J

    def weight_chol(self) -> np.ndarray:
        std = float(self.std_be)
        if std <= 0.0:
            return np.eye(3, dtype=float)
        inv_std = 1.0 / std
        return inv_std * np.eye(3, dtype=float)


# ============================================================
# 4) DVL 速度因子 (BI: Body 速度)
# ============================================================


@dataclass
class DvlBIVelFactor:
    """
    DVL 体坐标速度观测因子（BI 源）：

    - 关联变量: 第 k 个状态 x_k = [p(3), v(3), yaw]
    - 外部参数: roll_rad, pitch_rad 来自 IMU（体->导航之间的姿态）
    - 模型:     v_body_pred = R_bn * v_enu
               其中 R_bn = R_nb^T, R_nb 由 (roll,pitch,yaw) 构造

    - 残差:   r = v_body_pred - vel_body ∈ R^3
    """

    num_states: int
    k: int
    vel_body: np.ndarray      # shape (3,), DVL 体坐标速度 [Vx, Vy, Vz] (m/s)
    roll_rad: float           # 对应时刻 IMU roll
    pitch_rad: float          # 对应时刻 IMU pitch
    std_bi: float             # 体速度观测噪声 std (m/s)
    eps: float = 1.0e-6

    debug: bool = False
    _printed_once: bool = field(default=False, init=False, repr=False)

    def _vel_body_pred(self, theta: np.ndarray) -> np.ndarray:
        """从当前 θ 中读取 x_k 的 v_enu 和 yaw，推算预测的体坐标速度。"""
        theta = np.asarray(theta, dtype=float).reshape(-1)
        if not (0 <= self.k < self.num_states):
            raise IndexError(f"DvlBIVelFactor k={self.k} out of [0, {self.num_states})")

        sk = state_slice(self.k, self.num_states)
        xk = theta[sk]
        v_enu = xk[3:6]
        yaw = wrap_yaw(float(xk[6]))

        att = AttitudeRPY(
            roll=float(self.roll_rad),
            pitch=float(self.pitch_rad),
            yaw=yaw,
        )
        R_nb = rpy_to_R_nb(att)   # body -> nav (ENU)
        R_bn = R_nb.T             # nav  -> body

        v_body_pred = R_bn @ v_enu
        return v_body_pred

    def residual(self, theta: np.ndarray) -> np.ndarray:
        v_body_pred = self._vel_body_pred(theta)
        z = self.vel_body.reshape(3)
        r = v_body_pred - z

        if self.debug and not self._printed_once:
            self._printed_once = True
            print(
                f"[FACTOR][DVL_BI] k={self.k} "
                f"v_body_pred={v_body_pred}, v_body_meas={z}, |r|={np.linalg.norm(r):.3e}"
            )

        return r.astype(float)

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        """
        为了稳妥，BI 因子用有限差分 Jacobian（只对 x_k 的 7 个维度求导）。
        """
        theta = np.asarray(theta, dtype=float).reshape(-1)
        sk = state_slice(self.k, self.num_states)
        active_idx = list(range(sk.start, sk.stop))

        def _res(theta_vec: np.ndarray) -> np.ndarray:
            return self.residual(theta_vec)

        J = _finite_diff_jacobian(theta, _res, active_idx, eps=self.eps)
        return J

    def weight_chol(self) -> np.ndarray:
        std = float(self.std_bi)
        if std <= 0.0:
            return np.eye(3, dtype=float)
        inv_std = 1.0 / std
        return inv_std * np.eye(3, dtype=float)


# ============================================================
# 5) yaw-from-velocity 因子
# ============================================================


@dataclass
class YawFromVelFactor:
    """
    yaw-from-velocity 因子: 当 ENU 平面速度足够大时，用 DVL 速度构造“航向观测”.

    观测:
        z_yaw = atan2(Ve, Vn)
        残差:
        r = wrap(z_yaw - yaw_k) ∈ R^1
    """

    num_states: int
    k: int
    vel_enu: np.ndarray   # shape (3,), [Ve, Vn, Vu]
    std_yaw: float        # rad
    eps: float = 1e-6

    debug: bool = False
    _printed_once: bool = field(default=False, init=False, repr=False)

    def residual(self, theta: np.ndarray) -> np.ndarray:
        theta = np.asarray(theta, dtype=float).reshape(-1)

        if not (0 <= self.k < self.num_states):
            raise IndexError(f"YawFromVelFactor k={self.k} out of [0, {self.num_states})")

        ve = float(self.vel_enu.reshape(3)[0])
        vn = float(self.vel_enu.reshape(3)[1])

        yaw_meas = yaw_from_enu_velocity(ve, vn)  # (-pi, pi]

        sk = state_slice(self.k, self.num_states)
        xk = theta[sk]
        yaw_k = wrap_yaw(float(xk[6]))

        r = np.zeros(1, dtype=float)
        r[0] = wrap_yaw(yaw_meas - yaw_k)

        if self.debug and not self._printed_once:
            self._printed_once = True
            print(
                f"[FACTOR][YAW_DVL] k={self.k} "
                f"yaw_meas={yaw_meas:.3f}, yaw_state={yaw_k:.3f}, r={r[0]:.3e}"
            )

        return r

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        theta = np.asarray(theta, dtype=float).reshape(-1)
        sk = state_slice(self.k, self.num_states)
        idxs = list(range(sk.start, sk.stop))
        return _finite_diff_jacobian(theta, self.residual, idxs, eps=self.eps)

    def weight_chol(self) -> np.ndarray:
        std = float(self.std_yaw)
        inv_std = 1.0 / std if std > 0.0 else 0.0
        return np.array([[inv_std]], dtype=float)
