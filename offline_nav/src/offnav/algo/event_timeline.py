# src/offnav/algo/event_timeline.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


# =============================================================================
# Event definition
# =============================================================================

class EventKind(str, Enum):
    IMU = "imu"
    DVL_BE = "dvl_be"
    DVL_BI = "dvl_bi"


class UseReason(str, Enum):
    USED_OK = "USED_OK"
    DROP_TOO_OLD = "DROP_TOO_OLD"            # too old w.r.t IMU start
    DROP_OUT_OF_WINDOW = "DROP_OUT_OF_WINDOW"
    DROP_INVALID = "DROP_INVALID"            # DVL quality flag rejects, etc.


@dataclass(frozen=True)
class TimelineEvent:
    kind: EventKind
    t_s: float

    # For IMU event
    imu_k: Optional[int] = None

    # For DVL event
    dvl_j: Optional[int] = None
    imu_anchor_k: Optional[int] = None        # which IMU sample we will update after
    dt_imu_minus_dvl_s: Optional[float] = None

    used: bool = True
    used_reason: str = UseReason.USED_OK


def _as_bool(val: Any, default: bool = False) -> bool:
    """
    Parse common "bool-like" values robustly:
      - bool / np.bool_
      - numeric (0 -> False, nonzero -> True)
      - strings: true/t/1/yes/y/ok ; false/f/0/no/n/nan/""
    """
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if val is None:
        return default
    if isinstance(val, (int, float, np.integer, np.floating)):
        if not np.isfinite(val):
            return default
        return bool(val != 0)
    s = str(val).strip().lower()
    if s in ("true", "t", "1", "yes", "y", "ok"):
        return True
    if s in ("false", "f", "0", "no", "n", "nan", ""):
        return False
    return default

def extract_time_s(df: pd.DataFrame) -> np.ndarray:
    return _extract_time_s(df)


# =============================================================================
# CSV loading helpers (moved out of runner)
# =============================================================================

_TIME_COL_CANDS_S = ("t_s", "EstS", "MonoS")
_TIME_COL_CANDS_NS = ("EstNS", "MonoNS")


def _extract_time_s(df: pd.DataFrame) -> np.ndarray:
    for c in _TIME_COL_CANDS_S:
        if c in df.columns:
            return df[c].to_numpy(dtype=float)
    for c in _TIME_COL_CANDS_NS:
        if c in df.columns:
            return df[c].to_numpy(dtype=float) * 1e-9
    raise KeyError("No time column among t_s/EstS/MonoS/EstNS/MonoNS")


def _optional_any(df: pd.DataFrame, cands: Iterable[str]) -> Optional[str]:
    for c in cands:
        if c in df.columns:
            return c
    return None


def extract_dvl_be_vel_enu(df: pd.DataFrame) -> np.ndarray:
    col_e = _optional_any(df, ("Ve_enu(m_s)", "Ve_enu", "VelE", "E_vel", "Ve"))
    col_n = _optional_any(df, ("Vn_enu(m_s)", "Vn_enu", "VelN", "N_vel", "Vn"))
    col_u = _optional_any(df, ("Vu_enu(m_s)", "Vu_enu", "VelU", "U_vel", "Vu"))
    if not (col_e and col_n and col_u):
        raise KeyError(
            f"Cannot find DVL-BE ENU vel columns. columns[:40]={list(df.columns)[:40]}"
        )
    return df[[col_e, col_n, col_u]].to_numpy(dtype=float)


def extract_dvl_bi_vel_body_frd(df: pd.DataFrame) -> np.ndarray:
    col_x = _optional_any(df, ("Vx_body(m_s)", "Vx_body", "Vx_frd(m_s)", "Vx_frd", "Vx"))
    col_y = _optional_any(df, ("Vy_body(m_s)", "Vy_body", "Vy_frd(m_s)", "Vy_frd", "Vy"))
    col_z = _optional_any(df, ("Vz_body(m_s)", "Vz_body", "Vz_frd(m_s)", "Vz_frd", "Vz"))
    if not (col_x and col_y and col_z):
        raise KeyError(
            f"Cannot find DVL-BI body vel columns. columns[:40]={list(df.columns)[:40]}"
        )
    return df[[col_x, col_y, col_z]].to_numpy(dtype=float)


def load_csv_sorted(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    if df is None or df.empty:
        raise RuntimeError(f"CSV is empty: {path}")
    if "Src" in df.columns:
        df["Src"] = df["Src"].astype(str)
    t = _extract_time_s(df)
    idx = np.argsort(t)
    return df.iloc[idx].reset_index(drop=True)


def extract_dvl_quality_row(df: pd.DataFrame, idx: int) -> Dict[str, Any]:
    """
    Extract a small set of "audit columns" if present.
    This is intentionally tolerant: missing columns are ignored.
    """
    out: Dict[str, Any] = {}

    def get(name: str) -> Any:
        return df.at[idx, name] if name in df.columns else np.nan

    # keep compatibility with your audit columns
    cols = (
        "Frame",
        "Src",
        "SpeedOk",
        "Valid",
        "ValidFlag",
        "IsWaterMass",
        "GateOk",
        "Speed_mag(m_s)",
        "Speed_mag_src",
        "Speed(m_s)",
    )

    for c in cols:
        if c in df.columns:
            out[c] = get(c)
            continue

        # alias handling
        if c == "Speed_mag(m_s)" and "Speed_mag" in df.columns:
            out[c] = get("Speed_mag")
            continue

    return out


# =============================================================================
# Timeline builder
# =============================================================================

@dataclass(frozen=True)
class TimelineConfig:
    # DVL -> IMU anchor matching
    match_policy: str = "anchor_next"   # anchor_next | nearest
    match_window_s: float = 0.05        # max allowed |imu_t - dvl_t|
    drop_older_than_s: float = 0.5      # if dvl_t < imu_t0 - drop_older_than_s => DROP_TOO_OLD

    # Optional: apply DVL quality gate here (kept simple; you can extend)
    require_gate_ok: bool = True
    require_speed_ok: bool = True
    require_valid: bool = False         # many logs have Valid empty; keep False unless confirmed


@dataclass(frozen=True)
class TimeAlignmentReport:
    # raw coverage
    imu_t0: float
    imu_t1: float
    imu_n: int
    dvl_t0: float
    dvl_t1: float
    dvl_n: int
    dt0_imu_minus_dvl: float
    dt1_imu_minus_dvl: float

    # navigation start (first USED DVL anchor) - may be None/NaN if no used
    nav_k0: int
    nav_t0: float
    n_dvl_used: int


def _find_anchor_k(imu_t: np.ndarray, t_meas: float, policy: str) -> Optional[int]:
    n = int(imu_t.size)
    if n == 0:
        return None

    if policy == "anchor_next":
        k = int(np.searchsorted(imu_t, t_meas, side="left"))
        return None if k >= n else k

    if policy == "nearest":
        k = int(np.searchsorted(imu_t, t_meas, side="left"))
        if k <= 0:
            return 0
        if k >= n:
            return n - 1
        # choose closer
        return k if abs(imu_t[k] - t_meas) <= abs(imu_t[k - 1] - t_meas) else (k - 1)

    raise ValueError(f"Unknown match_policy: {policy}")


def build_dvl_be_events(
    imu_t: np.ndarray,
    dvl_df: pd.DataFrame,
    cfg: TimelineConfig,
) -> Tuple[List[TimelineEvent], TimeAlignmentReport]:
    """
    Build DVL-BE events with per-row gating and IMU anchoring.

    Notes:
      - This function DOES NOT build IMU events nor merge timeline.
      - It also computes a TimeAlignmentReport including nav start (first USED event).
    """
    t_dvl = _extract_time_s(dvl_df)
    n_dvl = int(t_dvl.size)

    imu_n = int(imu_t.size)
    if imu_n == 0 or n_dvl == 0:
        rep = TimeAlignmentReport(
            imu_t0=float(imu_t[0]) if imu_n else np.nan,
            imu_t1=float(imu_t[-1]) if imu_n else np.nan,
            imu_n=imu_n,
            dvl_t0=float(t_dvl[0]) if n_dvl else np.nan,
            dvl_t1=float(t_dvl[-1]) if n_dvl else np.nan,
            dvl_n=n_dvl,
            dt0_imu_minus_dvl=np.nan,
            dt1_imu_minus_dvl=np.nan,
            nav_k0=0,
            nav_t0=float(imu_t[0]) if imu_n else np.nan,
            n_dvl_used=0,
        )
        return [], rep

    imu_t0 = float(imu_t[0])
    imu_t1 = float(imu_t[-1])
    dvl_t0 = float(t_dvl[0])
    dvl_t1 = float(t_dvl[-1])

    events: List[TimelineEvent] = []
    n_used = 0

    for j in range(n_dvl):
        tm = float(t_dvl[j])

        # 1) Strict: drop anything earlier than IMU start
        if tm < imu_t0:
            events.append(
                TimelineEvent(
                    kind=EventKind.DVL_BE,
                    t_s=tm,
                    dvl_j=j,
                    imu_anchor_k=None,
                    dt_imu_minus_dvl_s=None,
                    used=False,
                    used_reason=UseReason.DROP_TOO_OLD,
                )
            )
            continue

        # 2) Quality gates (conservative, only applied if column exists)
        if cfg.require_gate_ok and ("GateOk" in dvl_df.columns):
            if not _as_bool(dvl_df.at[j, "GateOk"], default=False):
                events.append(
                    TimelineEvent(
                        kind=EventKind.DVL_BE,
                        t_s=tm,
                        dvl_j=j,
                        used=False,
                        used_reason=UseReason.DROP_INVALID,
                    )
                )
                continue

        if cfg.require_speed_ok and ("SpeedOk" in dvl_df.columns):
            if not _as_bool(dvl_df.at[j, "SpeedOk"], default=False):
                events.append(
                    TimelineEvent(
                        kind=EventKind.DVL_BE,
                        t_s=tm,
                        dvl_j=j,
                        used=False,
                        used_reason=UseReason.DROP_INVALID,
                    )
                )
                continue

        if cfg.require_valid and ("Valid" in dvl_df.columns):
            if not _as_bool(dvl_df.at[j, "Valid"], default=False):
                events.append(
                    TimelineEvent(
                        kind=EventKind.DVL_BE,
                        t_s=tm,
                        dvl_j=j,
                        used=False,
                        used_reason=UseReason.DROP_INVALID,
                    )
                )
                continue

        # 3) Find anchor IMU sample
        k = _find_anchor_k(imu_t, tm, cfg.match_policy)
        if k is None:
            events.append(
                TimelineEvent(
                    kind=EventKind.DVL_BE,
                    t_s=tm,
                    dvl_j=j,
                    used=False,
                    used_reason=UseReason.DROP_OUT_OF_WINDOW,
                )
            )
            continue

        dt = float(imu_t[k] - tm)
        if abs(dt) > cfg.match_window_s:
            events.append(
                TimelineEvent(
                    kind=EventKind.DVL_BE,
                    t_s=tm,
                    dvl_j=j,
                    imu_anchor_k=k,
                    dt_imu_minus_dvl_s=dt,
                    used=False,
                    used_reason=UseReason.DROP_OUT_OF_WINDOW,
                )
            )
            continue

        events.append(
            TimelineEvent(
                kind=EventKind.DVL_BE,
                t_s=tm,
                dvl_j=j,
                imu_anchor_k=k,
                dt_imu_minus_dvl_s=dt,
                used=True,
                used_reason=UseReason.USED_OK,
            )
        )
        n_used += 1

    # Sort by anchor IMU index primarily, then by time
    events.sort(
        key=lambda e: (e.imu_anchor_k if e.imu_anchor_k is not None else 10**18, e.t_s)
    )

    # nav start = first USED event's anchor (if any)
    nav_k0 = 0
    nav_t0 = imu_t0
    for e in events:
        if e.used and (e.imu_anchor_k is not None):
            nav_k0 = int(e.imu_anchor_k)
            nav_t0 = float(imu_t[nav_k0])
            break

    rep = TimeAlignmentReport(
        imu_t0=imu_t0,
        imu_t1=imu_t1,
        imu_n=imu_n,
        dvl_t0=dvl_t0,
        dvl_t1=dvl_t1,
        dvl_n=n_dvl,
        dt0_imu_minus_dvl=imu_t0 - dvl_t0,
        dt1_imu_minus_dvl=imu_t1 - dvl_t1,
        nav_k0=nav_k0,
        nav_t0=nav_t0,
        n_dvl_used=int(n_used),
    )

    return events, rep


def build_imu_events(imu_t: np.ndarray, *, k0: int = 0) -> List[TimelineEvent]:
    """
    Build IMU events from imu_t[k0:].

    This is intentionally a separate knob so that the ESKF timeline can be
    strictly started from the first USED DVL anchor (nav_k0).
    """
    n = int(imu_t.size)
    k0i = int(k0)
    if n <= 0:
        return []
    if k0i < 0:
        k0i = 0
    if k0i >= n:
        return []
    return [
        TimelineEvent(kind=EventKind.IMU, t_s=float(imu_t[k]), imu_k=k)
        for k in range(k0i, n)
    ]


def merge_timeline(
    imu_events: List[TimelineEvent],
    dvl_events: List[TimelineEvent],
) -> List[TimelineEvent]:
    """
    Merge strategy:
      - For each IMU event (k), output it first,
        then output all DVL events anchored to that k (used or not), sorted by time.

    DVL events with imu_anchor_k=None are ignored here (they should remain auditable
    elsewhere via explicit logging/rep if needed).
    """
    by_anchor: Dict[int, List[TimelineEvent]] = {}
    for e in dvl_events:
        if e.imu_anchor_k is None:
            continue
        by_anchor.setdefault(int(e.imu_anchor_k), []).append(e)

    out: List[TimelineEvent] = []
    for imu_ev in imu_events:
        out.append(imu_ev)
        k = int(imu_ev.imu_k) if imu_ev.imu_k is not None else None
        if k is None:
            continue
        if k in by_anchor:
            out.extend(sorted(by_anchor[k], key=lambda x: x.t_s))

    return out
