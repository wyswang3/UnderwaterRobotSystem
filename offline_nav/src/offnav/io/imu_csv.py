# src/offnav/io/imu_csv.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Union

import pandas as pd

from offnav.core.types import ImuRawData

PathLike = Union[str, Path]

# 你刚给出的 IMU 列字段：
REQUIRED_COLUMNS_IMU = [
    "MonoNS", "EstNS", "MonoS", "EstS",
    "AccX", "AccY", "AccZ",
    "GyroX", "GyroY", "GyroZ",
    "YawDeg", "AngX", "AngY", "AngZ",
]


def _check_required_columns(df: pd.DataFrame, required: Iterable[str], path: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"IMU CSV {path} missing required columns: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )


def load_imu_csv(path: PathLike, encoding: str = "utf-8") -> ImuRawData:
    """
    加载单个 IMU CSV 文件，返回 ImuRawData.

    - 按当前约定检查字段：
      MonoNS, EstNS, MonoS, EstS,
      AccX, AccY, AccZ,
      GyroX, GyroY, GyroZ,
      YawDeg, AngX, AngY, AngZ
    - 将空字符串视为缺失值（NaN），例如 YawDeg 为空的情况
    - 暂不做单位转换（Acc 仍是 g，Gyro/角度仍是 deg），
      后续统一在 preprocess 层转换。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"IMU CSV not found: {p}")

    df = pd.read_csv(
        p,
        encoding=encoding,
        na_values=["", "NaN", "nan"],
        keep_default_na=True,
    )

    _check_required_columns(df, REQUIRED_COLUMNS_IMU, p)

    return ImuRawData(df=df, source_path=p)
