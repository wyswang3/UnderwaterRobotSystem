# src/offnav/io/dvl_csv.py
from pathlib import Path
from typing import Iterable, Union

import pandas as pd

from offnav.core.types import DvlRawData

PathLike = Union[str, Path]

REQUIRED_COLUMNS = [
    "MonoNS", "EstNS", "MonoS", "EstS",
    "SensorID", "Src",
    "Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)",
    "Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)",
    "De_enu(m)", "Dn_enu(m)", "Du_enu(m)",
    "Depth(m)", "E(m)", "N(m)", "U(m)",
    "Valid", "ValidFlag", "IsWaterMass",
]


def _check_required_columns(df: pd.DataFrame, required: Iterable[str], path: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"DVL CSV {path} missing required columns: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )


def load_dvl_csv(path: PathLike, encoding: str = "utf-8") -> DvlRawData:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"DVL CSV not found: {p}")

    df = pd.read_csv(p, encoding=encoding)
    _check_required_columns(df, REQUIRED_COLUMNS, p)

    return DvlRawData(df=df, source_path=p)
