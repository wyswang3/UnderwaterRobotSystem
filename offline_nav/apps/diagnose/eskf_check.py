#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apps/diagnose/eskf_check.py

Audit DVL data quality vs ESKF update diagnostics.

Inputs (auto-discovered under proc_dir):
  - <run_id>_dvl_filtered_BE.csv        (GateOk=True)
  - <run_id>_dvl_filtered_BE_all.csv    (ungated)
  - <run_id>_dvl_stream_all.csv         (raw stream, mixed frames)
  - <run_id>_eskf_update_diag.csv       (ESKF update diagnostics; prefer proc_dir, can override)

Key goal:
  Locate time windows where ESKF DVL updates are inconsistent (high NIS),
  then explain whether it is caused by DVL quality/source switch, gating failure,
  watermass mixing, or speed validity flags.

This script is read-only: it does NOT modify any data.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ------------------------------
# Helpers
# ------------------------------
def _load_csv(p: Path) -> pd.DataFrame:
    if not p.exists():
        raise FileNotFoundError(p)
    df = pd.read_csv(p)
    if df is None or df.empty:
        raise RuntimeError(f"Empty CSV: {p}")
    # clean column names (strip BOM/spaces)
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
    return df


def _pick_time_s(df: pd.DataFrame) -> np.ndarray:
    for c in ("t_s", "EstS", "MonoS"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
    for c in ("EstNS", "MonoNS"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) * 1e-9
    raise KeyError("No time column among t_s/EstS/MonoS/EstNS/MonoNS")


def _optional_col(df: pd.DataFrame, cands: List[str]) -> Optional[str]:
    for c in cands:
        if c in df.columns:
            return c
    return None


def _to_num(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def _boolish_series(df: pd.DataFrame, col: str) -> pd.Series:
    """
    Convert typical CSV boolean-ish columns (True/False, 0/1, strings) to {0,1} with NaN allowed.
    """
    s = df[col]
    if s.dtype == bool:
        return s.astype(float)
    # common text forms
    if s.dtype == object:
        ss = s.astype(str).str.strip().str.lower()
        mapped = ss.map({"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0, "nan": np.nan})
        # if mapping fails for many rows, fallback to numeric coercion
        if mapped.notna().mean() < 0.5:
            return pd.to_numeric(s, errors="coerce")
        return mapped
    return pd.to_numeric(s, errors="coerce")


def _infer_update_dim(df: pd.DataFrame) -> pd.DataFrame:
    """
    Update diag format in your project:
      t_s,name,nis,r0..r5,S0..S5 (some empty)
    r_dim may be absent; infer per-row as count of non-NaN residuals.
    """
    df = df.copy()
    need = {"t_s", "name", "nis"}
    missing = need - set(df.columns)
    if missing:
        raise KeyError(f"update_diag missing {missing}, actual={list(df.columns)}")

    # coerce numeric
    r_cols = [c for c in df.columns if c.startswith("r") and c[1:].isdigit()]
    s_cols = [c for c in df.columns if c.startswith("S") and c[1:].isdigit()]
    _to_num(df, ["t_s", "nis"] + r_cols + s_cols)

    if "r_dim" not in df.columns:
        if not r_cols:
            raise KeyError("update_diag has no r0..rK columns to infer r_dim")
        df["r_dim"] = df[r_cols].notna().sum(axis=1).astype(int)

    return df


@dataclass
class Window:
    t0: float
    t1: float
    label: str


def _make_windows_from_update_diag(
    upd: pd.DataFrame,
    name: str = "dvl_be_vel",
    win_s: float = 30.0,
    nis_hi_quantile: float = 0.95,
    min_rows: int = 50,
) -> Tuple[pd.DataFrame, List[Window]]:
    """
    Produce window table and select 'bad' windows by NIS thresholding.
    Robust to NaN NIS.
    """
    df = upd[upd["name"].astype(str) == name].copy()
    if df.empty:
        raise RuntimeError(f"No update rows with name={name}")

    t = pd.to_numeric(df["t_s"], errors="coerce").to_numpy(float)
    nis = pd.to_numeric(df["nis"], errors="coerce").to_numpy(float)

    m = np.isfinite(t)
    t = t[m]
    nis = nis[m]

    if t.size < min_rows:
        raise RuntimeError(f"Too few update rows after cleaning: {t.size}")

    # bin windows
    t0 = float(np.min(t))
    bins = np.floor((t - t0) / win_s).astype(int)

    rows = []
    for b in np.unique(bins):
        mb = bins == b
        if int(np.sum(mb)) < min_rows:
            continue
        nis_b = nis[mb]
        rows.append(
            {
                "t_start": float(np.min(t[mb])),
                "t_end": float(np.max(t[mb])),
                "n": int(np.sum(mb)),
                "nis_mean": float(np.nanmean(nis_b)),
                "nis_p95": float(np.nanquantile(nis_b, 0.95)),
                "nis_p99": float(np.nanquantile(nis_b, 0.99)),
                "nis_nan_rate": float(np.mean(~np.isfinite(nis_b))),
            }
        )
    wdf = pd.DataFrame(rows).sort_values("t_start").reset_index(drop=True)

    # select bad windows by high quantile of nis_mean (ignore NaN means)
    nis_mean = wdf["nis_mean"].to_numpy(float)
    good = np.isfinite(nis_mean)
    if np.sum(good) < 3:
        # fallback: use nis_p95
        thr = float(np.nanquantile(wdf["nis_p95"].to_numpy(float), nis_hi_quantile))
        score_col = "nis_p95"
    else:
        thr = float(np.nanquantile(nis_mean[good], nis_hi_quantile))
        score_col = "nis_mean"

    wdf["is_bad"] = wdf[score_col] >= thr
    wdf["bad_score_col"] = score_col
    wdf["bad_threshold"] = thr

    bad_windows: List[Window] = []
    for i, r in wdf[wdf["is_bad"]].iterrows():
        bad_windows.append(Window(float(r["t_start"]), float(r["t_end"]), f"bad_win_{i}"))

    return wdf, bad_windows


def _subset_time(df: pd.DataFrame, t_col: str, t0: float, t1: float) -> pd.DataFrame:
    t = pd.to_numeric(df[t_col], errors="coerce")
    return df[(t >= t0) & (t <= t1)].copy()


def _summarize_flags(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Summarize common quality flags and meta fields if present.
    """
    out: Dict[str, Any] = {"n": int(len(df))}
    if df.empty:
        return out

    # flags
    for col in ("GateOk", "SpeedOk", "Valid", "IsWaterMass"):
        if col in df.columns:
            s = _boolish_series(df, col)
            out[f"{col}_rate1"] = float(np.nanmean(s))  # fraction of 1's
            out[f"{col}_nan_rate"] = float(np.mean(~np.isfinite(s.to_numpy(float))))

    # categorical distribution (top-k)
    for col in ("Src", "Speed_mag_src", "ValidFlag"):
        if col in df.columns:
            vc = df[col].astype(str).value_counts(dropna=False).head(5)
            out[f"{col}_top5"] = "; ".join([f"{k}:{int(v)}" for k, v in vc.items()])

    # speed magnitude (if exists)
    sp = _optional_col(df, ["Speed_mag(m_s)", "Speed_mag", "speed_mag", "Speed_body(m_s)"])
    if sp is not None:
        s = pd.to_numeric(df[sp], errors="coerce").to_numpy(float)
        out["speed_mag_min"] = float(np.nanmin(s))
        out["speed_mag_med"] = float(np.nanmedian(s))
        out["speed_mag_p95"] = float(np.nanquantile(s, 0.95))
        out["speed_mag_max"] = float(np.nanmax(s))

    return out


def _summarize_velocity_enu(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Summarize ENU velocity stats if columns exist.
    """
    out: Dict[str, Any] = {}
    ce = _optional_col(df, ["Ve_enu(m_s)", "Ve_enu", "Vx_enu(m_s)", "Vx_enu"])
    cn = _optional_col(df, ["Vn_enu(m_s)", "Vn_enu", "Vy_enu(m_s)", "Vy_enu"])
    cu = _optional_col(df, ["Vu_enu(m_s)", "Vu_enu", "Vz_enu(m_s)", "Vz_enu"])
    if not (ce and cn and cu):
        return out

    v = df[[ce, cn, cu]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    vn = v[:, 1]
    out["vn_mean"] = float(np.nanmean(vn))
    out["vn_std"] = float(np.nanstd(vn))
    out["vn_p95_abs"] = float(np.nanquantile(np.abs(vn), 0.95))
    out["vn_max_abs"] = float(np.nanmax(np.abs(vn)))
    return out


def run_audit(run_id: str, proc_dir: Path, out_dir: Path, updates_csv: Optional[Path] = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # locate files
    be_gated = proc_dir / f"{run_id}_dvl_filtered_BE.csv"
    be_all = proc_dir / f"{run_id}_dvl_filtered_BE_all.csv"
    stream_all = proc_dir / f"{run_id}_dvl_stream_all.csv"
    if updates_csv is None:
        cand = proc_dir / f"{run_id}_eskf_update_diag.csv"
        if cand.exists():
            updates_csv = cand
        else:
            raise FileNotFoundError(
                f"Cannot find updates csv at {cand}. "
                "Pass --updates explicitly."
            )

    # load
    upd = _infer_update_dim(_load_csv(updates_csv))
    dvl_be_g = _load_csv(be_gated) if be_gated.exists() else None
    dvl_be_a = _load_csv(be_all) if be_all.exists() else None
    dvl_stream = _load_csv(stream_all) if stream_all.exists() else None

    if dvl_be_g is None:
        raise FileNotFoundError(be_gated)
    if dvl_be_a is None:
        raise FileNotFoundError(be_all)
    if dvl_stream is None:
        # not fatal, but helpful
        print(f"[WARN] stream_all not found: {stream_all}")

    # standardize time column for each
    dvl_be_g["t_s"] = _pick_time_s(dvl_be_g)
    dvl_be_a["t_s"] = _pick_time_s(dvl_be_a)
    if dvl_stream is not None:
        dvl_stream["t_s"] = _pick_time_s(dvl_stream)

    # choose bad windows from update diag
    win_table, bad_windows = _make_windows_from_update_diag(
        upd,
        name="dvl_be_vel",
        win_s=30.0,
        nis_hi_quantile=0.90,  # slightly more sensitive; adjust if too many
        min_rows=50,
    )

    win_csv = out_dir / "bad_windows.csv"
    win_table.to_csv(win_csv, index=False)

    # window-by-window comparisons
    rows = []
    for w in bad_windows:
        g = _subset_time(dvl_be_g, "t_s", w.t0, w.t1)
        a = _subset_time(dvl_be_a, "t_s", w.t0, w.t1)
        s = _subset_time(dvl_stream, "t_s", w.t0, w.t1) if dvl_stream is not None else pd.DataFrame()

        base = {"run_id": run_id, "window": w.label, "t_start": w.t0, "t_end": w.t1}

        # gated stats
        sg = _summarize_flags(g)
        vg = _summarize_velocity_enu(g)
        for k, v in {**sg, **vg}.items():
            base[f"g_{k}"] = v

        # all stats
        sa = _summarize_flags(a)
        va = _summarize_velocity_enu(a)
        for k, v in {**sa, **va}.items():
            base[f"a_{k}"] = v

        # stream stats (if present)
        if dvl_stream is not None and not s.empty:
            ss = _summarize_flags(s)
            for k, v in ss.items():
                base[f"s_{k}"] = v

        # “gate effectiveness” proxy: how much bad sources/flags remain in gated vs all
        # (only if the columns exist)
        for col in ("IsWaterMass", "SpeedOk", "Valid"):
            if col in a.columns and col in g.columns:
                a_rate = float(np.nanmean(_boolish_series(a, col)))
                g_rate = float(np.nanmean(_boolish_series(g, col)))
                base[f"delta_{col}_rate1_(g-a)"] = g_rate - a_rate

        rows.append(base)

    comp = pd.DataFrame(rows).sort_values(["t_start", "window"]).reset_index(drop=True)
    comp_csv = out_dir / "window_comparison_BE.csv"
    comp.to_csv(comp_csv, index=False)

    # quick plots: NIS over time (from update diag), and Vn_enu for gated/all
    # (No seaborn, no fixed colors.)
    upd_be = upd[upd["name"].astype(str) == "dvl_be_vel"].copy()
    t_u = pd.to_numeric(upd_be["t_s"], errors="coerce").to_numpy(float)
    nis = pd.to_numeric(upd_be["nis"], errors="coerce").to_numpy(float)
    m = np.isfinite(t_u) & np.isfinite(nis)

    if np.sum(m) > 10:
        plt.figure()
        plt.plot(t_u[m], nis[m], linewidth=0.7)
        plt.xlabel("t_s")
        plt.ylabel("NIS (dvl_be_vel)")
        plt.title("ESKF update NIS over time")
        plt.grid(True)
        p = out_dir / "nis_by_time.png"
        plt.savefig(p, dpi=150, bbox_inches="tight")
        plt.close()

    # Vn ENU time series for gated/all
    def _plot_vn(df: pd.DataFrame, title: str, out_name: str) -> None:
        cn = _optional_col(df, ["Vn_enu(m_s)", "Vn_enu", "Vy_enu(m_s)", "Vy_enu"])
        if cn is None:
            return
        t = df["t_s"].to_numpy(float)
        vn = pd.to_numeric(df[cn], errors="coerce").to_numpy(float)
        mm = np.isfinite(t) & np.isfinite(vn)
        if np.sum(mm) < 10:
            return
        plt.figure()
        plt.plot(t[mm], vn[mm], linewidth=0.7)
        plt.xlabel("t_s")
        plt.ylabel("Vn_enu (m/s)")
        plt.title(title)
        plt.grid(True)
        p = out_dir / out_name
        plt.savefig(p, dpi=150, bbox_inches="tight")
        plt.close()

    _plot_vn(dvl_be_g, "DVL BE gated: Vn_enu(t)", "vn_enu_gated.png")
    _plot_vn(dvl_be_a, "DVL BE all: Vn_enu(t)", "vn_enu_all.png")

    # markdown report (avoid tabulate dependency; use to_string)
    rep = out_dir / "dvl_audit_report.md"
    lines = []
    lines.append(f"# DVL vs ESKF Update Audit - {run_id}\n\n")
    lines.append("## Inputs\n")
    lines.append(f"- proc_dir: `{proc_dir}`\n")
    lines.append(f"- updates: `{updates_csv}`\n")
    lines.append(f"- BE gated: `{be_gated}`\n")
    lines.append(f"- BE all: `{be_all}`\n")
    if dvl_stream is not None:
        lines.append(f"- stream_all: `{stream_all}`\n")
    lines.append("\n")

    lines.append("## 1) Bad windows detected from ESKF update diag (dvl_be_vel)\n")
    lines.append(f"- saved: `{win_csv.name}`\n\n")
    # show top 12 windows by nis_mean
    show = win_table.copy()
    show = show[np.isfinite(show["nis_mean"])].sort_values("nis_mean", ascending=False).head(12)
    if not show.empty:
        lines.append("Top windows by NIS mean:\n\n")
        lines.append("```\n")
        lines.append(show.to_string(index=False))
        lines.append("\n```\n\n")
    else:
        lines.append("No finite NIS mean windows (NIS may be NaN). Check update_diag numeric parsing.\n\n")

    lines.append("## 2) Window comparison (BE gated vs BE all)\n")
    lines.append(f"- saved: `{comp_csv.name}`\n\n")
    if not comp.empty:
        # only show a few key columns
        key_cols = [c for c in comp.columns if c in (
            "window","t_start","t_end",
            "g_n","a_n",
            "g_IsWaterMass_rate1","a_IsWaterMass_rate1",
            "g_SpeedOk_rate1","a_SpeedOk_rate1",
            "g_Valid_rate1","a_Valid_rate1",
            "g_vn_mean","a_vn_mean",
            "g_vn_max_abs","a_vn_max_abs",
            "g_Src_top5","a_Src_top5",
            "g_Speed_mag_src_top5","a_Speed_mag_src_top5",
        )]
        # some columns might not exist depending on data
        key_cols = [c for c in key_cols if c in comp.columns]
        lines.append("Key fields preview:\n\n")
        lines.append("```\n")
        lines.append(comp[key_cols].head(12).to_string(index=False))
        lines.append("\n```\n\n")

    lines.append("## 3) Figures\n")
    for fn in ("nis_by_time.png", "vn_enu_gated.png", "vn_enu_all.png"):
        p = out_dir / fn
        if p.exists():
            lines.append(f"- `{fn}`\n")
    lines.append("\n")

    lines.append("## 4) How to interpret quickly\n")
    lines.append(
        "- If **BE_all shows IsWaterMass_rate1>0** or Src switches, but **BE_gated still keeps them**, your Gate is too weak.\n"
        "- If **BE_gated is clean** but ESKF NIS still explodes, then investigate **timebase alignment (IMU vs DVL)** or **frame mapping**.\n"
        "- If **vn_mean drifts** with long positive bias in bad windows, it will integrate into **N overshoot**.\n"
    )

    rep.write_text("".join(lines), encoding="utf-8")

    print(f"[AUDIT] bad windows: {win_csv}")
    print(f"[AUDIT] window comparison: {comp_csv}")
    print(f"[AUDIT] report: {rep}")
    print(f"[AUDIT] figures in: {out_dir}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser("eskf_dvl_audit")
    ap.add_argument("--run", required=True, type=str, help="run_id, e.g. 2026-01-10_pooltest01")
    ap.add_argument(
        "--proc-dir",
        required=True,
        type=str,
        help="Directory containing processed DVL CSVs (the run folder), e.g. offline_nav/out/proc/<run_id>",
    )
    ap.add_argument(
        "--updates",
        default=None,
        type=str,
        help="Optional: eskf_update_diag.csv path. If omitted, use <proc-dir>/<run_id>_eskf_update_diag.csv",
    )
    ap.add_argument(
        "--out-dir",
        required=True,
        type=str,
        help="Output directory for audit results, e.g. offline_nav/out/diag_eskf/<run_id>",
    )
    args = ap.parse_args(argv)

    run_audit(
        run_id=args.run,
        proc_dir=Path(args.proc_dir),
        out_dir=Path(args.out_dir),
        updates_csv=Path(args.updates) if args.updates else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
