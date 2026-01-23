# src/offnav/io/trajectory_io.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from ..core.types import Trajectory


def _yaw_deg_from_diag(diag: Dict[str, Any], n: int) -> np.ndarray:
    yaw_rad = diag.get("yaw_rad", None)
    if yaw_rad is None:
        return np.full((n,), np.nan, dtype=np.float64)
    yaw_rad = np.asarray(yaw_rad, dtype=np.float64).reshape(-1)
    if yaw_rad.size != n:
        # pad/trim defensively
        out = np.full((n,), np.nan, dtype=np.float64)
        m = min(n, yaw_rad.size)
        out[:m] = yaw_rad[:m]
        return np.rad2deg(out)
    return np.rad2deg(yaw_rad)


def _src_used_from_diag(diag: Dict[str, Any], n: int) -> np.ndarray:
    src = diag.get("src_used", None)
    if src is None:
        return np.array([""] * n, dtype=object)
    src = np.asarray(src, dtype=object).reshape(-1)
    if src.size != n:
        out = np.array([""] * n, dtype=object)
        m = min(n, src.size)
        out[:m] = src[:m]
        return out
    return src


def trajectory_to_dataframe(traj: Trajectory, diag: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """
    Convert trajectory to a DataFrame with standard columns:
      t_s, E, N, U, vE, vN, vU, yaw_deg, src_used
    """
    t = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    p = np.asarray(traj.p_enu, dtype=np.float64)
    v = np.asarray(traj.v_enu, dtype=np.float64)

    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError(f"traj.p_enu must be (K,3), got {p.shape}")
    if v.ndim != 2 or v.shape[1] != 3:
        raise ValueError(f"traj.v_enu must be (K,3), got {v.shape}")
    if t.shape[0] != p.shape[0] or t.shape[0] != v.shape[0]:
        raise ValueError(f"traj length mismatch: t={t.shape}, p={p.shape}, v={v.shape}")

    n = t.shape[0]
    diag = diag or {}

    yaw_deg = _yaw_deg_from_diag(diag, n)
    src_used = _src_used_from_diag(diag, n)

    df = pd.DataFrame({
        "t_s": t,
        "E_m": p[:, 0],
        "N_m": p[:, 1],
        "U_m": p[:, 2],
        "vE_mps": v[:, 0],
        "vN_mps": v[:, 1],
        "vU_mps": v[:, 2],
        "yaw_deg": yaw_deg,
        "src_used": src_used,
    })
    return df


def save_trajectory_csv(out_path: str, traj: Trajectory, diag: Optional[Dict[str, Any]] = None) -> str:
    """
    Save trajectory CSV and return absolute path.
    """
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    df = trajectory_to_dataframe(traj, diag)
    df.to_csv(out_path, index=False)
    return out_path
