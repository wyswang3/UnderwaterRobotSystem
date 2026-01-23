# src/offnav/nav/frames.py
from __future__ import annotations

import numpy as np


def rpy_deg_to_rotmat_enu(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
    """
    把 IMU 欧拉角 (roll, pitch, yaw, deg) 变成 ENU 中 body->ENU 的 3x3 旋转矩阵。

    约定：
      - roll: 绕 X 轴
      - pitch: 绕 Y 轴
      - yaw: 绕 Z 轴
      - 旋转顺序：Rz(yaw) * Ry(pitch) * Rx(roll) 之类（你可以明确写在注释中）
    """
    ...


def rotate_body_to_enu(
    rpy_deg: np.ndarray,       # (N,3) [roll_deg, pitch_deg, yaw_deg]
    v_body: np.ndarray,        # (N,3) [Vx_body, Vy_body, Vz_body]
) -> np.ndarray:
    """
    批量把 body 速度变换到 ENU：逐样本 R * v_body。
    """
    ...
