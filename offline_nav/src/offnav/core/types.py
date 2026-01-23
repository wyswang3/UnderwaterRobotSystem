# src/offnav/core/types.py
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


# =========================
#  IMU 原始数据 / 样本类型
# =========================

@dataclass
class ImuRawData:
    """
    原始 IMU 数据容器

    约定字段（来自日志）：
      - MonoNS, EstNS, MonoS, EstS
      - AccX, AccY, AccZ
      - GyroX, GyroY, GyroZ
      - YawDeg, AngX, AngY, AngZ
    """
    df: pd.DataFrame
    source_path: Path

    def __len__(self) -> int:
        return len(self.df)

    @property
    def has_est_ns(self) -> bool:
        return "EstNS" in self.df.columns

    @property
    def t_ns(self) -> np.ndarray:
        """
        推荐统一使用 EstNS 作为“估计时间基”的 ns 时间戳。
        如果没有 EstNS，也可以退回 MonoNS（后续再细化策略）。
        """
        if "EstNS" in self.df.columns:
            return self.df["EstNS"].to_numpy(dtype=np.int64)
        elif "MonoNS" in self.df.columns:
            return self.df["MonoNS"].to_numpy(dtype=np.int64)
        else:
            raise KeyError("IMU df has neither EstNS nor MonoNS")

    @property
    def acc_xyz(self) -> np.ndarray:
        """返回 (N,3)，单位目前仍保持日志原始单位（看起来是 g）。"""
        return self.df[["AccX", "AccY", "AccZ"]].to_numpy(dtype=float)

    @property
    def gyro_xyz(self) -> np.ndarray:
        """返回 (N,3)，目前单位保持原始（多半是 deg/s，后续在 preprocess 转 rad/s）。"""
        return self.df[["GyroX", "GyroY", "GyroZ"]].to_numpy(dtype=float)


@dataclass
class ImuSample:
    """
    单帧 IMU 样本（用于某些工具函数 / 积分接口）。
    现在我们更多地直接用向量/数组，但保留这个类型，
    方便已有代码正常 import。
    """
    t_s: float                  # 时间戳（秒）
    acc_body: np.ndarray        # (3,) 体坐标线加速度
    gyro_body: np.ndarray       # (3,) 体坐标角速度
    roll: float                 # roll [rad]
    pitch: float                # pitch [rad]
    yaw: float | None = None    # yaw [rad]（有些场景可选）


# =========================
#  DVL 原始数据 / 样本类型
# =========================

@dataclass
class DvlRawData:
    df: pd.DataFrame
    source_path: Path

    def __len__(self) -> int:
        return len(self.df)


@dataclass
class DvlSample:
    """
    单帧 DVL 样本（供 segment_estimator 等模块使用的兼容结构）。

    这里先给出一个“常见字段超集”，后续如果发现某处
    需要更多字段，可以再迭代扩展：
      - t_s      : 时间戳（秒）
      - vel_body : 体坐标速度 (Vx, Vy, Vz) [m/s]
      - vel_enu  : ENU 速度 (Ve, Vn, Vu) [m/s]（若有）
      - depth    : 深度 [m]（若有）
      - speed    : 速度模长 |v| [m/s]（若有）
      - src      : 源标记（BI / BE / 其它）
      - valid    : 该帧是否认为是有效观测
    """
    t_s: float
    vel_body: np.ndarray                 # (3,) Vx_body, Vy_body, Vz_body
    vel_enu: np.ndarray | None = None    # (3,) Ve, Vn, Vu
    depth: float | None = None
    speed: float | None = None
    src: str | None = None
    valid: bool | None = None


# =========================
#  Run 元信息 / 打包结构
# =========================

@dataclass
class RunMeta:
    run_id: str
    date: Optional[str] = None
    note: Optional[str] = None
    extra: Dict[str, Any] = None


@dataclass
class RawRunData:
    run_id: str
    imu: ImuRawData
    dvl: DvlRawData
    meta: RunMeta

# =========================
#  轨迹类型（Deadreckon / ESKF 输出共用）
# =========================
@dataclass
class Trajectory:
    """
    离线轨迹结果（deadreckon / ESKF 等管线的公共输出格式）。

    约定：
      - t_s     : 时间轴 [s]，长度 N
      - E, N, U : ENU 位置 [m]，长度 N
      - yaw_rad : 航向角 [rad]（可选），长度 N 或 None

    后续如果需要，也可以扩展 roll/pitch、速度等字段，
    但目前先保持简单，够用即可。
    """
    t_s: np.ndarray
    E: np.ndarray
    N: np.ndarray
    U: np.ndarray
    yaw_rad: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.t_s)

    def as_dataframe(self) -> pd.DataFrame:
        """
        转成 DataFrame，列名统一为：
          t_s, E, N, U, yaw_rad(可选), yaw_deg(可选)
        """
        t_s = np.asarray(self.t_s, dtype=float)
        E   = np.asarray(self.E,   dtype=float)
        N   = np.asarray(self.N,   dtype=float)
        U   = np.asarray(self.U,   dtype=float)

        data: dict[str, np.ndarray] = {
            "t_s": t_s,
            "E":   E,
            "N":   N,
            "U":   U,
        }

        if self.yaw_rad is not None:
            yaw_rad = np.asarray(self.yaw_rad, dtype=float)
            data["yaw_rad"] = yaw_rad
            # 方便人眼看：同时导出度
            data["yaw_deg"] = np.rad2deg(yaw_rad)

        return pd.DataFrame(data)

    def to_csv(self, path: Path | str) -> None:
        """
        保存到 CSV，便于后续 MATLAB / Python 画图或对比。
        """
        df = self.as_dataframe()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)

    @staticmethod
    def from_dataframe(df: pd.DataFrame) -> "Trajectory":
        """
        从 DataFrame 恢复 Trajectory（例如从 CSV 读回来）。

        优先使用 yaw_rad；如果没有 yaw_rad 但有 yaw_deg，
        则用 yaw_deg 反推 yaw_rad。
        """
        t_s = df["t_s"].to_numpy(dtype=float)
        E   = df["E"].to_numpy(dtype=float)
        N   = df["N"].to_numpy(dtype=float)
        U   = df["U"].to_numpy(dtype=float)

        yaw_rad: np.ndarray | None
        if "yaw_rad" in df.columns:
            yaw_rad = df["yaw_rad"].to_numpy(dtype=float)
        elif "yaw_deg" in df.columns:
            yaw_rad = np.deg2rad(df["yaw_deg"].to_numpy(dtype=float))
        else:
            yaw_rad = None

        return Trajectory(t_s=t_s, E=E, N=N, U=U, yaw_rad=yaw_rad)

    @staticmethod
    def from_csv(path: Path | str) -> "Trajectory":
        df = pd.read_csv(path)
        return Trajectory.from_dataframe(df)

