# offnav/algo/eskf_local.py

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque

import numpy as np

from offnav.models.eskf_state import EskfFilter
from offnav.core.nav_config import EskfConfig

@dataclass
class LocalVelPolicy:
    """
    局部 ESKF 运行策略（运行时用）：
      - alpha            : 速度收缩系数（0 => 贴 DVL，1 => 保持 INS）
      - keep_pos_from_imu: 是否继续信 IMU 的位置积分（目前仅做占位）
      - window_horizon_s : MHE 窗口长度（秒）
      - enable_mhe       : 是否启用窗口平均修正
    """
    alpha: float = 0.0
    keep_pos_from_imu: bool = False
    window_horizon_s: float = 5.0
    enable_mhe: bool = False

    @classmethod
    def from_eskf_cfg(cls, cfg: EskfConfig) -> "LocalVelPolicy":
        lv = cfg.local_vel
        return cls(
            alpha=float(lv.vel_trust_alpha),
            keep_pos_from_imu=bool(lv.keep_pos_from_imu),
            window_horizon_s=5.0,  # 先写死，之后你想开放到 YAML 再加字段
            enable_mhe=False,      # 同上，将来在 YAML 里加 enable_mhe 再接
        )

    def clamped_alpha(self) -> float:
        """把 alpha 限制到 [0,1] 区间。"""
        return float(min(1.0, max(0.0, self.alpha)))
    

def _get_v_enu(eskf: EskfFilter) -> np.ndarray:
    """
    从 EskfFilter 中读当前 ENU 速度。
    """
    return np.asarray(eskf.v_enu, dtype=float).reshape(3)


def _set_v_enu(eskf: EskfFilter, v_enu_new: np.ndarray) -> None:
    """
    把修正后的 ENU 速度写回 EskfFilter 内部状态。
    注意：这里只修改 state.v，不动 state.p / yaw 等其它量。
    """
    v_enu_new = np.asarray(v_enu_new, dtype=float).reshape(3)
    eskf.state.v = v_enu_new


def apply_local_vel_post_update(
    eskf: EskfFilter,
    v_dvl_enu: np.ndarray,
    policy: LocalVelPolicy,
) -> None:
    """
    在完成一次 DVL BE 观测更新后，对“当前滤波器内部速度”做局部收缩：
      v_new = (1 - alpha) * v_dvl + alpha * v_eskf

    假定：
      - eskf.v_enu / state.v 按约定是 ENU 速度；
      - v_dvl_enu 已经是 ENU 坐标系下的 DVL BE 速度。
    """
    alpha = policy.clamped_alpha()
    v_eskf = _get_v_enu(eskf)
    v_dvl = np.asarray(v_dvl_enu, dtype=float).reshape(3)

    v_new = (1.0 - alpha) * v_dvl + alpha * v_eskf
    _set_v_enu(eskf, v_new)


@dataclass
class WindowEvent:
    """
    一帧“DVL 更新时刻”的快照：
      - t_s       : 时间戳（秒）
      - v_eskf_enu: 当时 ESKF 内部的 ENU 速度（已经经过 BE 更新 + 局部收缩）
      - v_dvl_enu : 当时 DVL BE ENU 速度测量
    """
    t_s: float
    v_eskf_enu: np.ndarray
    v_dvl_enu: np.ndarray


WindowDeque = Deque[WindowEvent]

def append_window_event(
    window: WindowDeque,
    t_s: float,
    eskf: EskfFilter,
    v_dvl_enu: np.ndarray,
) -> None:
    """
    在每次 DVL 更新后调用，记录一条事件进入窗口。
    """
    v_eskf = _get_v_enu(eskf)
    v_dvl = np.asarray(v_dvl_enu, dtype=float).reshape(3)

    window.append(
        WindowEvent(
            t_s=float(t_s),
            v_eskf_enu=v_eskf,
            v_dvl_enu=v_dvl,
        )
    )

def shrink_window(
    window: WindowDeque,
    horizon_s: float,
    t_now_s: float,
) -> None:
    """
    把窗口中“太早”的事件丢掉，只保留最近 horizon_s 秒内的。
    """
    while window and (t_now_s - window[0].t_s > horizon_s):
        window.popleft()

def mhe_refine_velocity(
    window: WindowDeque,
    eskf: EskfFilter,
    policy: LocalVelPolicy,
) -> None:
    """
    利用最近窗口内的 (v_dvl - v_eskf) 平均值，修正当前速度：
        delta_v = mean_i (v_dvl_i - v_eskf_i)
        v_now   = v_now + delta_v

    当前版本：
      - 只有 policy.enable_mhe=True 时才启用；
      - 权重一视同仁，后续可以升级为带权平均 / LS。
    """
    if not policy.enable_mhe:
        return
    if not window:
        return

    diffs = [w.v_dvl_enu - w.v_eskf_enu for w in window]
    if not diffs:
        return

    delta_v = np.mean(np.stack(diffs, axis=0), axis=0)  # [3]
    v_now = _get_v_enu(eskf)
    _set_v_enu(eskf, v_now + delta_v)

