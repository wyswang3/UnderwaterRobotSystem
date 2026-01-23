# src/offnav/graph/states.py
from __future__ import annotations

"""
Graph-level state representation for offline factor-graph navigation.

本模块定义“因子图导航”中的状态与参数向量 θ 之间的映射：
- 每个 IMU 时刻 k 有一个 7 维状态结点 x_k = [p(3), v(3), yaw(1)]
- 全局共享一个 4 维 bias 结点 b = [ba(3), bgz(1)]
- 参数向量 θ 的布局为: [x_0, x_1, ..., x_{N-1}, b]

注意：
- 这里只关心 ENU 位置/速度与 yaw，roll/pitch 仍由 IMU 姿态解算提供；
- 本文件假定 LV1 模型：bias 在整个轨迹上恒定。
"""

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


# 每个状态结点的维度: p(3) + v(3) + yaw(1)
STATE_SIZE: int = 7

# 全局 bias 结点维度: ba(3) + bgz(1)
BIAS_SIZE: int = 4


@dataclass
class GraphState:
    """
    单个时间结点的导航状态 (ENU + yaw).

    Attributes
    ----------
    t_s : float
        时间戳 [s]，通常来自 IMU 时间轴 (EstS / MonoS 等).
        注意 t_s 不会被编码进 θ，只用来还原输出轨迹。
    p : np.ndarray, shape (3,)
        ENU 位置 [m]，顺序为 [E, N, U].
    v : np.ndarray, shape (3,)
        ENU 速度 [m/s]，顺序为 [vE, vN, vU].
    yaw : float
        航向角 [rad]，绕 ENU 的 Up 轴，范围建议 wrap 到 (-pi, pi].
    """

    t_s: float
    p: np.ndarray
    v: np.ndarray
    yaw: float

    def copy(self) -> GraphState:
        """深拷贝，避免外部意外修改内部数组。"""
        return GraphState(
            t_s=float(self.t_s),
            p=np.asarray(self.p, dtype=float).reshape(3).copy(),
            v=np.asarray(self.v, dtype=float).reshape(3).copy(),
            yaw=float(self.yaw),
        )


@dataclass
class BiasState:
    """
    全局 IMU bias 结点 (LV1: 在整个轨迹中恒定).

    Attributes
    ----------
    ba : np.ndarray, shape (3,)
        IMU 体坐标下线加速度 bias [m/s^2]，顺序 [bax, bay, baz].
    bgz : float
        IMU 体坐标下 z 轴陀螺 bias [rad/s].
    """

    ba: np.ndarray
    bgz: float

    def copy(self) -> BiasState:
        return BiasState(
            ba=np.asarray(self.ba, dtype=float).reshape(3).copy(),
            bgz=float(self.bgz),
        )


# ------------------------------
# 角度 wrap 工具
# ------------------------------


def wrap_yaw(yaw: float) -> float:
    """
    把航向角 wrap 到 (-pi, pi].

    在更新 θ 或构造 GraphState 时，建议统一调用本函数，
    确保所有模块使用一致的角度范围约定。
    """
    return (yaw + np.pi) % (2.0 * np.pi) - np.pi


# ------------------------------
# θ 维度与索引工具
# ------------------------------


def theta_dim(num_states: int) -> int:
    """
    给定状态结点个数 N，返回参数向量 θ 的总维度 = 7N + 4.

    参数
    ----
    num_states : int
        轨迹中状态结点数 N，通常等于 IMU 样本数.

    返回
    ----
    int
        θ 的长度.
    """
    return num_states * STATE_SIZE + BIAS_SIZE


def state_slice(k: int, num_states: int) -> slice:
    """
    返回第 k 个状态结点 x_k 在 θ 中对应的切片 [start:end].

    约定布局:
        θ = [x_0 (7), x_1 (7), ..., x_{N-1} (7), ba(3), bgz(1)]

    参数
    ----
    k : int
        状态结点索引, 0 <= k < num_states.
    num_states : int
        总状态结点数 N.

    返回
    ----
    slice
        对应 x_k 的切片.
    """
    if not (0 <= k < num_states):
        raise IndexError(f"state index k={k} out of range [0, {num_states})")
    start = k * STATE_SIZE
    end = start + STATE_SIZE
    return slice(start, end)


def bias_slice(num_states: int) -> slice:
    """
    返回全局 bias 结点在 θ 中对应的切片 [start:end].

    对应顺序为:
        [ba_x, ba_y, ba_z, bgz]

    参数
    ----
    num_states : int
        总状态结点数 N.

    返回
    ----
    slice
        对应 bias 结点的切片.
    """
    start = num_states * STATE_SIZE
    end = start + BIAS_SIZE
    return slice(start, end)


# ------------------------------
# pack / unpack: 状态 <-> θ
# ------------------------------


def pack_theta(states: List[GraphState], bias: BiasState) -> np.ndarray:
    """
    将 N 个 GraphState + 一个 BiasState 打平成参数向量 θ.

    布局约定:
        θ = [p_0(3), v_0(3), yaw_0,
             p_1(3), v_1(3), yaw_1,
             ...
             p_{N-1}(3), v_{N-1}(3), yaw_{N-1},
             ba(3), bgz(1)]

    注意:
    - t_s 不编码进 θ，只存在于 GraphState 中.
    - yaw 在打包时会统一 wrap 到 (-pi, pi].

    参数
    ----
    states : List[GraphState]
        长度为 N 的状态结点列表.
    bias : BiasState
        全局 bias 结点.

    返回
    ----
    np.ndarray, shape (7N + 4,)
        参数向量 θ (float64).
    """
    num_states = len(states)
    if num_states <= 0:
        raise ValueError("pack_theta: states 列表不能为空")

    theta = np.zeros(theta_dim(num_states), dtype=float)

    # 逐结点写入 p, v, yaw
    for k, st in enumerate(states):
        s = state_slice(k, num_states)
        block = np.zeros(STATE_SIZE, dtype=float)

        p = np.asarray(st.p, dtype=float).reshape(3)
        v = np.asarray(st.v, dtype=float).reshape(3)
        yaw = wrap_yaw(float(st.yaw))

        block[0:3] = p
        block[3:6] = v
        block[6] = yaw

        theta[s] = block

    # 写入全局 bias
    bs = bias_slice(num_states)
    ba = np.asarray(bias.ba, dtype=float).reshape(3)
    bgz = float(bias.bgz)

    bias_block = np.zeros(BIAS_SIZE, dtype=float)
    bias_block[0:3] = ba
    bias_block[3] = bgz

    theta[bs] = bias_block

    return theta


def unpack_theta(theta: np.ndarray, t_imu: np.ndarray) -> Tuple[List[GraphState], BiasState]:
    """
    从参数向量 θ 还原出 N 个 GraphState + 一个 BiasState.

    θ 的长度必须满足:
        len(theta) == 7N + 4
    其中 N = len(t_imu).

    参数
    ----
    theta : np.ndarray, shape (7N + 4,)
        优化变量向量 θ.
    t_imu : np.ndarray, shape (N,)
        IMU 时间轴 [s]，用来给每个 GraphState 填充 t_s.

    返回
    ----
    states : List[GraphState]
        长度为 N 的状态结点列表.
    bias : BiasState
        全局 bias 结点.
    """
    theta = np.asarray(theta, dtype=float).reshape(-1)
    t_imu = np.asarray(t_imu, dtype=float).reshape(-1)

    num_states = int(t_imu.shape[0])
    expected_dim = theta_dim(num_states)
    if theta.shape[0] != expected_dim:
        raise ValueError(
            f"unpack_theta: theta 长度不匹配, "
            f"len(theta)={theta.shape[0]}, 期望={expected_dim} (N={num_states})"
        )

    states: List[GraphState] = []

    # 逐结点读取
    for k in range(num_states):
        s = state_slice(k, num_states)
        block = theta[s]

        p = block[0:3].copy()
        v = block[3:6].copy()
        yaw = wrap_yaw(float(block[6]))
        t_s = float(t_imu[k])

        states.append(
            GraphState(
                t_s=t_s,
                p=p,
                v=v,
                yaw=yaw,
            )
        )

    # 读取全局 bias
    bs = bias_slice(num_states)
    bias_block = theta[bs]

    ba = bias_block[0:3].copy()
    bgz = float(bias_block[3])

    bias = BiasState(ba=ba, bgz=bgz)

    return states, bias
