# src/offnav/paths.py
from __future__ import annotations
import glob
import os
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ExpPaths:
    exp_root: str
    dvl_csv: str
    imu_csv: str

def _pick_latest(glob_pattern: str) -> str:
    files = sorted(glob.glob(glob_pattern))
    if not files:
        raise FileNotFoundError(f"No files matched: {glob_pattern}")
    return files[-1]

def resolve_paths(exp_root: str, dvl_glob: str, imu_glob: str,
                  dvl_csv: Optional[str] = None,
                  imu_csv: Optional[str] = None) -> ExpPaths:
    exp_root = os.path.abspath(exp_root)
    if dvl_csv is None:
        dvl_csv = _pick_latest(os.path.join(exp_root, dvl_glob))
    else:
        dvl_csv = os.path.join(exp_root, dvl_csv) if not os.path.isabs(dvl_csv) else dvl_csv

    if imu_csv is None:
        imu_csv = _pick_latest(os.path.join(exp_root, imu_glob))
    else:
        imu_csv = os.path.join(exp_root, imu_csv) if not os.path.isabs(imu_csv) else imu_csv

    return ExpPaths(exp_root=exp_root, dvl_csv=os.path.abspath(dvl_csv), imu_csv=os.path.abspath(imu_csv))
