# src/offnav/preprocess/dvl_processing.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Literal, List

import numpy as np
import pandas as pd

from offnav.core.types import DvlRawData


# =============================================================================
# Contract
# =============================================================================
"""
We treat DVL raw stream as a mixed-frame event log.

Required columns (from your example):
  MonoNS,EstNS,MonoS,EstS,SensorID,Src,
  Vx_body(m_s),Vy_body(m_s),Vz_body(m_s),
  Ve_enu(m_s),Vn_enu(m_s),Vu_enu(m_s),
  Valid,ValidFlag,IsWaterMass, ...

Goal output:
  - One BI velocity event stream (body frame, units m/s)
  - One BE velocity event stream (ENU frame, units m/s)
  - Minimal columns only
  - Keep original timestamps (we keep EstS + EstNS + MonoS + MonoNS if present)
"""


# =============================================================================
# Data structures (NEW)
# =============================================================================

@dataclass
class DvlEventsConfig:
    # which time axis to use as primary
    time_col: Literal["EstS", "MonoS"] = "EstS"   # keep raw; no re-timing here

    # keep first N seconds even if gating says "bad" (static window support)
    keep_first_s: float = 20.0

    # validity: if Valid exists, require it True; otherwise ignore
    require_valid: bool = False

    # optional bottom-track constraint (if IsWaterMass exists)
    require_bottom_track: bool = False

    # speed range gate (applied after outlier + dv gate)
    speed_min_m_s: float = 0.0
    speed_max_m_s: float = 2.0

    # jump gate (per-sample)
    dv_axis_max_m_s: float = 0.20
    dv_xy_max_m_s: float = 0.25

    # BE special gate: |Vu| limit (ENU Up)
    be_vu_abs_max_m_s: float = 0.30

    # outlier removal
    # if enabled, remove points whose |v| deviates from rolling median by > k * rolling MAD
    enable_rolling_outlier: bool = True
    outlier_window_s: float = 2.0
    outlier_k: float = 8.0
    outlier_min_points: int = 15

    # low-pass
    enable_lowpass: bool = True
    lowpass_window_s: float = 0.50

    # output columns
    keep_id_cols: bool = True   # keep SensorID, Src


@dataclass
class DvlEventsData:
    df_bi: pd.DataFrame
    df_be: pd.DataFrame
    config: Optional[DvlEventsConfig] = None


# =============================================================================
# Backward-compatible aliases (IMPORTANT)
# =============================================================================
# Old code expects these names
DvlPreprocessConfig = DvlEventsConfig
DvlProcessedData = DvlEventsData


# =============================================================================
# Helpers
# =============================================================================

def _norm_src(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def _to_bool_series(x: pd.Series) -> pd.Series:
    if x.dtype == bool:
        return x
    s = x.astype(str).str.strip().str.lower()
    true_set = {"1", "true", "t", "yes", "y", "on"}
    false_set = {"0", "false", "f", "no", "n", "off", "", "nan", "none"}
    out = s.map(lambda v: True if v in true_set else (False if v in false_set else False))
    return out.astype(bool)


def _pick_time(df: pd.DataFrame, cfg: DvlEventsConfig) -> np.ndarray:
    if cfg.time_col in df.columns:
        return df[cfg.time_col].to_numpy(dtype=float)
    # fallback
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError("DVL df has no EstS/MonoS/EstNS/MonoNS time column.")


def _estimate_fs_hz(t_s: np.ndarray) -> float:
    if t_s.size < 2:
        return float("nan")
    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return float("nan")
    return 1.0 / float(np.median(dt))


def _moving_average(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1:
        return x.astype(float, copy=True)
    kernel = np.ones(win, dtype=float) / float(win)
    y = np.empty_like(x, dtype=float)
    for i in range(x.shape[1]):
        y[:, i] = np.convolve(x[:, i], kernel, mode="same")
    return y


def _speed(v: np.ndarray) -> np.ndarray:
    return np.sqrt(np.sum(v * v, axis=1))


def _rolling_median_mad(x: np.ndarray, win: int) -> Tuple[np.ndarray, np.ndarray]:
    # simple pandas-based implementation for stability
    s = pd.Series(x)
    med = s.rolling(win, center=True, min_periods=max(3, win // 3)).median().to_numpy(dtype=float)
    mad = (s - pd.Series(med)).abs().rolling(win, center=True, min_periods=max(3, win // 3)).median().to_numpy(dtype=float)
    return med, mad


def _gate_common(
    df: pd.DataFrame,
    t_s: np.ndarray,
    v: np.ndarray,
    cfg: DvlEventsConfig,
    *,
    kind: Literal["BI", "BE"],
) -> Tuple[np.ndarray, List[str]]:
    """
    Returns keep_mask and reasons (len=N, '' if kept).
    keep_mask is after all gating, BUT we will force-keep keep_first_s.
    """
    n = df.shape[0]
    keep = np.ones(n, dtype=bool)
    reason = [""] * n

    # validity
    if cfg.require_valid and "Valid" in df.columns:
        ok = _to_bool_series(df["Valid"]).to_numpy(dtype=bool)
        bad = ~ok
        for i in np.nonzero(bad)[0]:
            keep[i] = False
            reason[i] = (reason[i] + ";valid") if reason[i] else "valid"

    # bottom track
    if cfg.require_bottom_track and "IsWaterMass" in df.columns:
        ok = (~_to_bool_series(df["IsWaterMass"])).to_numpy(dtype=bool)
        bad = ~ok
        for i in np.nonzero(bad)[0]:
            keep[i] = False
            reason[i] = (reason[i] + ";water_mass") if reason[i] else "water_mass"

    # dv gate
    dv = np.zeros_like(v)
    dv[1:, :] = v[1:, :] - v[:-1, :]
    dv_axis = np.max(np.abs(dv), axis=1)
    dv_xy = np.sqrt(dv[:, 0] * dv[:, 0] + dv[:, 1] * dv[:, 1])
    bad = (dv_axis > float(cfg.dv_axis_max_m_s)) | (dv_xy > float(cfg.dv_xy_max_m_s))
    bad[0] = False
    for i in np.nonzero(bad)[0]:
        keep[i] = False
        reason[i] = (reason[i] + ";dv_jump") if reason[i] else "dv_jump"

    # BE Vu gate
    if kind == "BE":
        vu = v[:, 2]  # ENU: (E,N,U)
        bad2 = np.abs(vu) > float(cfg.be_vu_abs_max_m_s)
        bad2[0] = False
        for i in np.nonzero(bad2)[0]:
            keep[i] = False
            reason[i] = (reason[i] + ";vu_abs") if reason[i] else "vu_abs"

    # outlier gate on speed (rolling median/MAD)
    if cfg.enable_rolling_outlier:
        fs = _estimate_fs_hz(t_s)
        if np.isfinite(fs) and fs > 0:
            win = max(3, int(round(float(cfg.outlier_window_s) * fs)))
            spd = _speed(v)
            med, mad = _rolling_median_mad(spd, win)
            # robust z: |x-med| / (1.4826*mad)
            denom = 1.4826 * mad
            z = np.zeros_like(spd)
            m = np.isfinite(denom) & (denom > 1e-9) & np.isfinite(med)
            z[m] = np.abs(spd[m] - med[m]) / denom[m]
            bad3 = z > float(cfg.outlier_k)
            # avoid gating if too few points overall
            if n >= int(cfg.outlier_min_points):
                for i in np.nonzero(bad3)[0]:
                    keep[i] = False
                    reason[i] = (reason[i] + ";outlier") if reason[i] else "outlier"

    # speed range gate
    spd = _speed(v)
    bad4 = (spd < float(cfg.speed_min_m_s)) | (spd > float(cfg.speed_max_m_s))
    for i in np.nonzero(bad4)[0]:
        keep[i] = False
        reason[i] = (reason[i] + ";speed_range") if reason[i] else "speed_range"

    # force keep static window
    if n > 0 and float(cfg.keep_first_s) > 0:
        t0 = float(t_s[0])
        force = (t_s - t0) <= float(cfg.keep_first_s)
        for i in np.nonzero(force)[0]:
            keep[i] = True
            reason[i] = ""  # explicitly clear, because this part is used for bias/statistics

    return keep, reason


def _post_filter_velocity(
    t_s: np.ndarray,
    v: np.ndarray,
    cfg: DvlEventsConfig,
) -> np.ndarray:
    if (not cfg.enable_lowpass) or v.size == 0:
        return v
    fs = _estimate_fs_hz(t_s)
    if np.isfinite(fs) and fs > 0:
        win = max(1, int(round(float(cfg.lowpass_window_s) * fs)))
    else:
        win = 5
    return _moving_average(v, win)


def _minimal_cols(df: pd.DataFrame) -> List[str]:
    cols = []
    for c in ["MonoNS", "EstNS", "MonoS", "EstS"]:
        if c in df.columns:
            cols.append(c)
    for c in ["SensorID", "Src"]:
        if c in df.columns:
            cols.append(c)
    return cols


# =============================================================================
# Public API (NEW)
# =============================================================================

def preprocess_dvl_events(
    dvl: DvlRawData,
    cfg: Optional[DvlEventsConfig] = None,
) -> DvlEventsData:
    if cfg is None:
        cfg = DvlEventsConfig()

    df0 = dvl.df
    if df0 is None or df0.empty:
        return DvlEventsData(df_bi=pd.DataFrame(), df_be=pd.DataFrame(), config=cfg)

    df = df0.copy()
    if "Src" not in df.columns:
        raise KeyError("DVL df missing 'Src' column.")
    df["Src"] = _norm_src(df["Src"])

    # split BI/BE rows
    df_bi0 = df[df["Src"] == "BI"].copy()
    df_be0 = df[df["Src"] == "BE"].copy()

    # sort by chosen time
    def _sort_inplace(d: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        if d.empty:
            return d, np.array([], dtype=float)
        t = _pick_time(d, cfg)
        d["_t_s"] = t
        d.sort_values("_t_s", inplace=True, kind="mergesort")
        d.drop(columns=["_t_s"], inplace=True, errors="ignore")
        d.reset_index(drop=True, inplace=True)
        return d, _pick_time(d, cfg)

    df_bi0, t_bi = _sort_inplace(df_bi0)
    df_be0, t_be = _sort_inplace(df_be0)

    # build velocities
    # BI: body velocities
    if not df_bi0.empty:
        for c in ["Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"]:
            if c not in df_bi0.columns:
                raise KeyError(f"DVL BI missing {c!r}")
        v_bi_raw = df_bi0[["Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"]].to_numpy(dtype=float)
    else:
        v_bi_raw = np.zeros((0, 3), dtype=float)

    # BE: ENU velocities
    if not df_be0.empty:
        for c in ["Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"]:
            if c not in df_be0.columns:
                raise KeyError(f"DVL BE missing {c!r}")
        v_be_raw = df_be0[["Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"]].to_numpy(dtype=float)
    else:
        v_be_raw = np.zeros((0, 3), dtype=float)

    # gating (on raw)
    if df_bi0.empty:
        keep_bi = np.array([], dtype=bool)
        reason_bi = []
    else:
        keep_bi, reason_bi = _gate_common(df_bi0, t_bi, v_bi_raw, cfg, kind="BI")

    if df_be0.empty:
        keep_be = np.array([], dtype=bool)
        reason_be = []
    else:
        keep_be, reason_be = _gate_common(df_be0, t_be, v_be_raw, cfg, kind="BE")

    # apply gate
    df_bi1 = df_bi0.loc[keep_bi].copy() if df_bi0.shape[0] else df_bi0.copy()
    df_be1 = df_be0.loc[keep_be].copy() if df_be0.shape[0] else df_be0.copy()
    t_bi1 = t_bi[keep_bi] if t_bi.size else t_bi
    t_be1 = t_be[keep_be] if t_be.size else t_be

    v_bi1 = v_bi_raw[keep_bi] if v_bi_raw.shape[0] else v_bi_raw
    v_be1 = v_be_raw[keep_be] if v_be_raw.shape[0] else v_be_raw

    # low-pass (after gating)
    v_bi_lp = _post_filter_velocity(t_bi1, v_bi1, cfg)
    v_be_lp = _post_filter_velocity(t_be1, v_be1, cfg)

    # output minimal columns + filtered velocities + speed
    base_cols_bi = _minimal_cols(df_bi1) if cfg.keep_id_cols else [c for c in _minimal_cols(df_bi1) if c not in ("SensorID", "Src")]
    base_cols_be = _minimal_cols(df_be1) if cfg.keep_id_cols else [c for c in _minimal_cols(df_be1) if c not in ("SensorID", "Src")]

    out_bi = df_bi1[base_cols_bi].copy() if not df_bi1.empty else pd.DataFrame(columns=base_cols_bi)
    out_be = df_be1[base_cols_be].copy() if not df_be1.empty else pd.DataFrame(columns=base_cols_be)

    if v_bi_lp.size:
        out_bi["Vx_body(m_s)"] = v_bi_lp[:, 0]
        out_bi["Vy_body(m_s)"] = v_bi_lp[:, 1]
        out_bi["Vz_body(m_s)"] = v_bi_lp[:, 2]
        out_bi["Speed(m_s)"] = _speed(v_bi_lp)

    if v_be_lp.size:
        out_be["Ve_enu(m_s)"] = v_be_lp[:, 0]
        out_be["Vn_enu(m_s)"] = v_be_lp[:, 1]
        out_be["Vu_enu(m_s)"] = v_be_lp[:, 2]
        out_be["Speed(m_s)"] = _speed(v_be_lp)

    # keep a compact "why dropped" audit if you want: export separately in cli, not in main CSV
    # (we intentionally do NOT attach reasons into the main output to keep it clean)

    return DvlEventsData(df_bi=out_bi, df_be=out_be, config=cfg)


def save_dvl_events_csv(
    out: DvlEventsData,
    out_dir: Path,
    run_id: str,
) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p_bi = out_dir / f"{run_id}_dvl_BI.csv"
    p_be = out_dir / f"{run_id}_dvl_BE.csv"
    out.df_bi.to_csv(p_bi, index=False)
    out.df_be.to_csv(p_be, index=False)
    return p_bi, p_be


def load_dvl_events_csv(proc_dir: Path, run_id: str) -> DvlEventsData:
    proc_dir = Path(proc_dir)
    p_bi = proc_dir / f"{run_id}_dvl_BI.csv"
    p_be = proc_dir / f"{run_id}_dvl_BE.csv"
    if not p_bi.exists() and not p_be.exists():
        raise FileNotFoundError(f"DVL BI/BE CSV not found in {proc_dir} for run_id={run_id}")
    df_bi = pd.read_csv(p_bi) if p_bi.exists() else pd.DataFrame()
    df_be = pd.read_csv(p_be) if p_be.exists() else pd.DataFrame()
    return DvlEventsData(df_bi=df_bi, df_be=df_be, config=None)


# =============================================================================
# Backward-compatible names (so cli_proc.py / __init__.py won't explode)
# =============================================================================

def preprocess_dvl_simple(dvl: DvlRawData, cfg: Optional[DvlPreprocessConfig] = None) -> DvlProcessedData:
    return preprocess_dvl_events(dvl, cfg)


def load_dvl_processed_csv(proc_dir: Path, run_id: str) -> DvlProcessedData:
    return load_dvl_events_csv(proc_dir, run_id)
