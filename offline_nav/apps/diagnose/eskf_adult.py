#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apps/diagnose/eskf_check.py

ESKF diagnostic (read-only):
- Trajectory: *_traj_eskf.csv
- Update diag: *_eskf_update_diag.csv

Your actual update_diag format:
t_s,name,nis,r0,r1,r2,r3,r4,r5,S0,S1,S2,S3,S4,S5
(many fields may be empty)

Focus: why N axis is too large.

Outputs:
- Figures: N(t), r1(t), NIS(t), whitened e1(t), optional vN(t), optional N vs integral(vN)
- Markdown report with key stats + 30s window localization tables

Run (recommended from offline_nav/src):
python ../apps/diagnose/eskf_check.py \
  --run 2026-01-10_pooltest01 \
  --traj    ../out/nav_eskf/2026-01-10_pooltest01/2026-01-10_pooltest01_traj_eskf.csv \
  --updates ../out/nav_eskf/2026-01-10_pooltest01/2026-01-10_pooltest01_eskf_update_diag.csv \
  --out-dir ../out/diag_eskf/2026-01-10_pooltest01
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -----------------------------------------------------------------------------
# Chi-square 95% thresholds (avoid scipy dependency)
#   chi2.ppf(0.95, dof)
# -----------------------------------------------------------------------------
CHI2_95: Dict[int, float] = {
    1: 3.841458820694124,
    2: 5.991464547107979,
    3: 7.814727903251179,
    4: 9.487729036781154,
    5: 11.070497693516351,
    6: 12.591587243743977,
}


# -----------------------------------------------------------------------------
# IO helpers
# -----------------------------------------------------------------------------
def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    if df is None or df.empty:
        raise RuntimeError(f"Empty CSV: {path}")
    return df


def _find_cols_by_prefix(df: pd.DataFrame, prefix: str, max_k: int = 6) -> List[str]:
    cols = []
    for k in range(max_k):
        c = f"{prefix}{k}"
        if c in df.columns:
            cols.append(c)
    return cols


def normalize_update_diag(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Normalize update_diag to be robust to:
    - BOM / spaces in headers
    - empty fields (',,,') -> NaN
    - missing r_dim: infer from non-NaN r0..r5 count

    Returns:
      df_norm, r_cols, s_cols
    """
    df = df.copy()
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]

    need = {"t_s", "name", "nis"}
    missing = need - set(df.columns)
    if missing:
        raise KeyError(f"update_diag missing columns {missing}. actual={list(df.columns)}")

    r_cols = _find_cols_by_prefix(df, "r", max_k=6)
    s_cols = _find_cols_by_prefix(df, "S", max_k=6)

    if not r_cols:
        raise KeyError(
            "update_diag has no residual columns r0..r5. "
            f"actual columns={list(df.columns)[:40]}"
        )

    # Force numeric conversion (empty -> NaN)
    for c in ["t_s", "nis"] + r_cols + s_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Infer r_dim / S_dim if absent
    if "r_dim" not in df.columns:
        df["r_dim"] = df[r_cols].notna().sum(axis=1).astype(int)
    else:
        df["r_dim"] = pd.to_numeric(df["r_dim"], errors="coerce").fillna(0).astype(int)

    if "S_dim" not in df.columns:
        df["S_dim"] = df[s_cols].notna().sum(axis=1).astype(int) if s_cols else 0
    else:
        df["S_dim"] = pd.to_numeric(df["S_dim"], errors="coerce").fillna(0).astype(int)

    # Clean name
    df["name"] = df["name"].astype(str)

    return df, r_cols, s_cols


# -----------------------------------------------------------------------------
# Stats helpers
# -----------------------------------------------------------------------------
def _rolling_mean(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1:
        return x
    s = pd.Series(x)
    return s.rolling(win, min_periods=max(1, win // 3), center=True).mean().to_numpy()


def _time_window_stats(t: np.ndarray, x: np.ndarray, win_s: float = 30.0) -> pd.DataFrame:
    """Compute per-window mean/std/p95_abs for x over fixed window length in seconds."""
    if t.size == 0:
        return pd.DataFrame(columns=["t_start", "t_end", "n", "mean", "std", "p95_abs"])

    t0 = float(np.min(t))
    bins = np.floor((t - t0) / win_s).astype(int)
    out = []
    for b in np.unique(bins):
        m = bins == b
        if int(np.sum(m)) < 3:
            continue
        xx = x[m]
        out.append(
            {
                "t_start": float(np.min(t[m])),
                "t_end": float(np.max(t[m])),
                "n": int(np.sum(m)),
                "mean": float(np.mean(xx)),
                "std": float(np.std(xx)),
                "p95_abs": float(np.quantile(np.abs(xx), 0.95)),
            }
        )
    return pd.DataFrame(out)


def _weighted_mean_by_dt(t: np.ndarray, x: np.ndarray) -> float:
    """Time-weighted mean using dt between samples (robust to nonuniform sampling)."""
    if t.size < 2:
        return float(np.mean(x)) if t.size == 1 else float("nan")
    idx = np.argsort(t)
    t = t[idx]
    x = x[idx]
    dt = np.diff(t)
    dt = np.maximum(dt, 0.0)
    # use mid-point weights for x
    w = dt
    xm = 0.5 * (x[:-1] + x[1:])
    denom = float(np.sum(w))
    if denom <= 0.0:
        return float(np.mean(x))
    return float(np.sum(xm * w) / denom)


def _safe_dt_median(t: np.ndarray, default_dt: float = 0.1) -> float:
    if t.size < 3:
        return default_dt
    t = np.sort(t)
    d = np.diff(t)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return default_dt
    # ignore zeros (duplicate timestamps)
    d_pos = d[d > 0.0]
    if d_pos.size == 0:
        return default_dt
    return float(np.median(d_pos))


# -----------------------------------------------------------------------------
# Core diagnose
# -----------------------------------------------------------------------------
def _aggregate_by_time(be: pd.DataFrame) -> pd.DataFrame:
    """
    Many logs may contain multiple updates with the same t_s.
    This aggregation stabilizes stats and avoids rolling/integration artifacts.

    Strategy:
      - nis: max
      - r*: mean
      - S*: mean
      - r_dim: max (should be stable per name)
    """
    # Choose existing columns
    agg: Dict[str, str] = {"nis": "max", "r_dim": "max"}
    for k in range(6):
        rk = f"r{k}"
        sk = f"S{k}"
        if rk in be.columns:
            agg[rk] = "mean"
        if sk in be.columns:
            agg[sk] = "mean"

    out = be.groupby("t_s", as_index=False).agg(agg)
    out = out.sort_values("t_s").reset_index(drop=True)
    return out


def _plot_line(x: np.ndarray, y: np.ndarray, xlabel: str, ylabel: str, title: str, out_path: Path) -> None:
    plt.figure()
    plt.plot(x, y, linewidth=1.0)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()


def diagnose(traj_csv: Path, upd_csv: Path, out_dir: Path, run_id: Optional[str] = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------
    # 1) Load trajectory
    # -----------------------
    traj = _load_csv(traj_csv)
    traj.columns = [c.strip().lstrip("\ufeff") for c in traj.columns]

    required_traj_cols = {"t_s", "E", "N", "U"}
    if not required_traj_cols.issubset(set(traj.columns)):
        raise KeyError(f"traj missing columns {required_traj_cols - set(traj.columns)}")

    t_traj = traj["t_s"].to_numpy(dtype=float)
    E = traj["E"].to_numpy(dtype=float)
    Nn = traj["N"].to_numpy(dtype=float)
    U = traj["U"].to_numpy(dtype=float)

    # vN optional
    vN = None
    for c in ("vN", "vN_mps", "Vn", "Vn_enu(m_s)"):
        if c in traj.columns:
            vN = traj[c].to_numpy(dtype=float)
            break

    # basic N range
    N_min, N_max = float(np.nanmin(Nn)), float(np.nanmax(Nn))
    N_span = N_max - N_min

    # -----------------------
    # 2) Load update diag (normalized)
    # -----------------------
    upd_raw = _load_csv(upd_csv)
    upd, r_cols, s_cols = normalize_update_diag(upd_raw)

    # filter dvl_be_vel updates
    be = upd[upd["name"].astype(str).eq("dvl_be_vel")].copy()
    if be.empty:
        # provide a helpful hint
        names = sorted(set(upd["name"].astype(str).tolist()))[:30]
        raise RuntimeError(
            "No rows with name == 'dvl_be_vel' found in update_diag.csv. "
            f"Available names (first 30)={names}"
        )

    # Aggregate per t_s to avoid duplicate timestamp artifacts
    be = _aggregate_by_time(be)

    # Ensure r0,r1,r2 and S0,S1,S2 exist (for BE vel 3D update)
    need_cols = {"t_s", "nis", "r_dim", "r0", "r1", "r2", "S0", "S1", "S2"}
    missing = need_cols - set(be.columns)
    if missing:
        raise KeyError(
            f"update_diag (after filter+agg) missing columns {missing}. "
            f"actual={list(be.columns)}"
        )

    t_be = be["t_s"].to_numpy(dtype=float)
    nis = be["nis"].to_numpy(dtype=float)
    r_dim = be["r_dim"].to_numpy(dtype=int)

    r0 = be["r0"].to_numpy(dtype=float)
    r1 = be["r1"].to_numpy(dtype=float)  # likely Vn residual
    r2 = be["r2"].to_numpy(dtype=float)

    S0 = be["S0"].to_numpy(dtype=float)
    S1 = be["S1"].to_numpy(dtype=float)
    S2 = be["S2"].to_numpy(dtype=float)

    # Guard S (avoid divide-by-zero / negative)
    eps = 1e-12
    S0g = np.maximum(S0, eps)
    S1g = np.maximum(S1, eps)
    S2g = np.maximum(S2, eps)

    e0 = r0 / np.sqrt(S0g)
    e1 = r1 / np.sqrt(S1g)
    e2 = r2 / np.sqrt(S2g)

    # -----------------------
    # 3) NIS gating stats (95%)
    # -----------------------
    # Map each row to dof threshold; if dof not in table, fallback to dof=3
    th = np.array([CHI2_95.get(int(d), CHI2_95[3]) for d in r_dim], dtype=float)
    exceed = nis > th

    nis_mean = float(np.mean(nis))
    nis_p95 = float(np.quantile(nis, 0.95))
    nis_p99 = float(np.quantile(nis, 0.99))
    nis_exceed_rate = float(np.mean(exceed))

    # Residual stats
    r1_mean = float(np.mean(r1))
    r1_std = float(np.std(r1))
    r1_wmean = _weighted_mean_by_dt(t_be, r1)

    e1_mean = float(np.mean(e1))
    e1_var = float(np.var(e1))
    e1_p95 = float(np.quantile(np.abs(e1), 0.95))

    # Integrated mismatch proxy (meters)
    # (sort already ensured by _aggregate_by_time)
    drift_N_from_r1 = float(np.trapz(r1, t_be))
    drift_N_abs = float(np.trapz(np.abs(r1), t_be))

    # Window localization
    win_be_r1 = _time_window_stats(t_be, r1, win_s=30.0)
    win_be_nis = _time_window_stats(t_be, nis, win_s=30.0)
    win_be_e1 = _time_window_stats(t_be, e1, win_s=30.0)

    # S sanity (to ensure S is indeed innovation covariance scale)
    S1_min, S1_med, S1_max = float(np.nanmin(S1)), float(np.nanmedian(S1)), float(np.nanmax(S1))

    # -----------------------
    # 4) Plots
    # -----------------------
    tag = run_id or "run"

    figN = out_dir / f"{tag}_N_t.png"
    _plot_line(t_traj, Nn, "t_s", "N (m)", "ESKF trajectory N(t)", figN)

    # r1(t) with safe rolling mean (~1s window)
    dt_med = _safe_dt_median(t_be, default_dt=0.1)
    win = max(5, int(round(1.0 / max(dt_med, 1e-3))))
    r1_rm = _rolling_mean(r1, win=win)

    plt.figure()
    plt.plot(t_be, r1, linewidth=0.8)
    plt.plot(t_be, r1_rm, linewidth=2.0)
    plt.xlabel("t_s")
    plt.ylabel("r1 (m/s)  (likely Vn residual)")
    plt.title(f"DVL BE residual on N-axis (r1), rolling~1s (win={win})")
    plt.grid(True)
    figr1 = out_dir / f"{tag}_r1_t.png"
    plt.savefig(figr1, dpi=150, bbox_inches="tight")
    plt.close()

    # NIS(t) with thresholds (row-wise) + constant dof=3 line
    plt.figure()
    plt.plot(t_be, nis, linewidth=0.8)
    plt.plot(t_be, th, linewidth=1.2)  # row-wise threshold
    plt.axhline(CHI2_95[3], linestyle="--", linewidth=1.0)
    plt.xlabel("t_s")
    plt.ylabel("NIS")
    plt.title("DVL BE update NIS(t) with chi2 95% thresholds")
    plt.grid(True)
    fignis = out_dir / f"{tag}_nis_t.png"
    plt.savefig(fignis, dpi=150, bbox_inches="tight")
    plt.close()

    # whitened e1(t)
    plt.figure()
    plt.plot(t_be, e1, linewidth=0.8)
    plt.axhline(0.0, linestyle="--", linewidth=1.0)
    plt.axhline(2.0, linestyle="--", linewidth=1.0)
    plt.axhline(-2.0, linestyle="--", linewidth=1.0)
    plt.xlabel("t_s")
    plt.ylabel("e1 = r1/sqrt(S1)")
    plt.title("Whitened residual on N-axis (target ~ N(0,1))")
    plt.grid(True)
    fige1 = out_dir / f"{tag}_e1_t.png"
    plt.savefig(fige1, dpi=150, bbox_inches="tight")
    plt.close()

    figvN = None
    if vN is not None:
        figvN = out_dir / f"{tag}_vN_t.png"
        _plot_line(t_traj, vN, "t_s", "vN (m/s)", "ESKF vN(t)", figvN)

        # N consistency: N vs integral(vN)
        # Align by sorting (just in case)
        idx = np.argsort(t_traj)
        tt = t_traj[idx]
        NN = Nn[idx]
        vN_s = vN[idx]
        N_from_vN = np.zeros_like(NN)
        if tt.size >= 2:
            N_from_vN = np.concatenate([[0.0], np.cumsum(0.5 * (vN_s[:-1] + vN_s[1:]) * np.diff(tt))])
        # Compare relative displacement
        plt.figure()
        plt.plot(tt, NN - NN[0], linewidth=1.0, label="N - N0")
        plt.plot(tt, N_from_vN, linewidth=1.0, label="∫ vN dt (relative)")
        plt.xlabel("t_s")
        plt.ylabel("relative N (m)")
        plt.title("Consistency check: N vs integral(vN)")
        plt.grid(True)
        plt.legend()
        figNv = out_dir / f"{tag}_N_vs_int_vN.png"
        plt.savefig(figNv, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        figNv = None

    # -----------------------
    # 5) Report (Markdown)
    # -----------------------
    report_md = out_dir / f"{tag}_eskf_check_report.md"

    lines: List[str] = []
    lines.append(f"# ESKF Diagnostic Report - {tag}\n\n")
    lines.append("## Files\n")
    lines.append(f"- traj: `{traj_csv}`\n")
    lines.append(f"- updates: `{upd_csv}`\n\n")

    lines.append("## 1) Trajectory sanity\n")
    lines.append(f"- N_min = {N_min:.3f} m\n")
    lines.append(f"- N_max = {N_max:.3f} m\n")
    lines.append(f"- N_span = {N_span:.3f} m\n\n")

    lines.append("## 2) DVL BE update consistency (name=dvl_be_vel)\n")
    lines.append(f"- Updates (after per-t aggregation) = {len(be)}\n")
    # r_dim distribution
    rd_vals, rd_cnts = np.unique(r_dim, return_counts=True)
    rd_str = ", ".join([f"{int(v)}:{int(c)}" for v, c in zip(rd_vals, rd_cnts)])
    lines.append(f"- r_dim distribution = {rd_str}\n")
    lines.append(f"- NIS mean = {nis_mean:.3f}\n")
    lines.append(f"- NIS p95  = {nis_p95:.3f}\n")
    lines.append(f"- NIS p99  = {nis_p99:.3f}\n")
    lines.append(f"- NIS exceed rate (chi2 95%, row-wise dof) = {nis_exceed_rate*100:.2f}%\n\n")

    lines.append("## 3) N-axis residual (r1) and whiteness\n")
    lines.append(f"- r1 mean (simple) = {r1_mean:+.6f} m/s\n")
    lines.append(f"- r1 mean (time-weighted) = {r1_wmean:+.6f} m/s\n")
    lines.append(f"- r1 std  = {r1_std:.6f} m/s\n\n")

    lines.append("### 3.1) Whitened residual e1 = r1/sqrt(S1)\n")
    lines.append(f"- S1 min/med/max = {S1_min:.6e} / {S1_med:.6e} / {S1_max:.6e}\n")
    lines.append(f"- e1 mean = {e1_mean:+.3f}\n")
    lines.append(f"- e1 var  = {e1_var:.3f}  (target ~ 1.0)\n")
    lines.append(f"- |e1| p95 = {e1_p95:.3f}  (rule-of-thumb: <= ~2)\n\n")

    lines.append("### 3.2) Integrated mismatch magnitude (position-scale proxy)\n")
    lines.append(f"- ∫ r1 dt = {drift_N_from_r1:+.3f} m\n")
    lines.append(f"- ∫ |r1| dt = {drift_N_abs:.3f} m\n\n")

    lines.append("## 4) Time-window localization (30s windows)\n")
    lines.append("### r1 window stats\n")
    lines.append(win_be_r1.to_markdown(index=False) if not win_be_r1.empty else "(insufficient data)")
    lines.append("\n\n### NIS window stats\n")
    lines.append(win_be_nis.to_markdown(index=False) if not win_be_nis.empty else "(insufficient data)")
    lines.append("\n\n### e1 window stats\n")
    lines.append(win_be_e1.to_markdown(index=False) if not win_be_e1.empty else "(insufficient data)")
    lines.append("\n\n")

    lines.append("## 5) Figures\n")
    lines.append(f"- N(t): `{figN.name}`\n")
    lines.append(f"- r1(t): `{figr1.name}`\n")
    lines.append(f"- NIS(t): `{fignis.name}`\n")
    lines.append(f"- e1(t): `{fige1.name}`\n")
    if figvN is not None:
        lines.append(f"- vN(t): `{figvN.name}`\n")
    if figNv is not None:
        lines.append(f"- N vs ∫vNdt: `{figNv.name}`\n")
    lines.append("\n")

    # Actionable rules
    lines.append("## 6) Actionable interpretation rules\n")
    # Rule 1: bias -> drift
    if abs(r1_wmean) > 0.01:
        lines.append(
            "- **Strong indicator: persistent N-axis velocity mismatch.** "
            f"Time-weighted r1 mean is {r1_wmean:+.4f} m/s. "
            "As a rule-of-thumb, 0.01 m/s over 500 s can cause ~5 m drift. "
            "Check DVL time alignment, ENU mapping, yaw_sign, and whether you are double-consuming DVL rows.\n"
        )
    else:
        lines.append(
            "- r1 time-weighted mean is small (<0.01 m/s). "
            "N overshoot is less likely caused by a constant Vn bias alone; focus on segment-wise biases, yaw drift, and Q/R tuning.\n"
        )

    # Rule 2: whiteness variance
    if e1_var > 1.5:
        lines.append(
            "- **e1 variance >> 1**: innovations are under-modeled (R too small) or there is a frame/time mismatch. "
            "If NIS exceed rate is also high, prioritize fixing timebase/frame/sign issues before tuning.\n"
        )
    elif e1_var < 0.5:
        lines.append(
            "- **e1 variance << 1**: DVL updates may be too weak (R too large) or the filter is over-confident from process model mismatch. "
            "Consider reducing DVL R or increasing process noise (sigma_acc / bias RW) to make updates more effective.\n"
        )
    else:
        lines.append(
            "- e1 variance is in a reasonable band (~0.5..1.5). Use window stats to localize problematic segments.\n"
        )

    # Rule 3: NIS exceed
    if nis_exceed_rate > 0.10:
        lines.append(
            "- **NIS exceed rate > 10%**: frequent inconsistency. Common causes: timestamp mismatch (IMU vs DVL), wrong velocity column usage, "
            "frame sign errors, or mixing watermass/bottom-track.\n"
        )

    if N_span > 20.0:
        lines.append(
            "- **N_span exceeds pool scale**: strongly suspect timebase mismatch or systematic velocity bias. "
            "Use the 30s window tables to pinpoint intervals with biased r1 or high NIS.\n"
        )

    report_md.write_text("".join(lines), encoding="utf-8")

    print(f"[DIAG] Report: {report_md}")
    print(f"[DIAG] Figures dir: {out_dir}")
    print(
        "[DIAG] Key numbers: "
        f"N_span={N_span:.3f} m, "
        f"r1_wmean={r1_wmean:+.6f} m/s, "
        f"∫r1dt={drift_N_from_r1:+.3f} m, "
        f"NIS_p95={nis_p95:.3f}, "
        f"NIS_exceed_rate={nis_exceed_rate*100:.2f}%"
    )


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="eskf_check", description="Diagnose ESKF trajectory + update diagnostics.")
    ap.add_argument("--traj", required=True, type=str, help="Path to *_traj_eskf.csv")
    ap.add_argument("--updates", required=True, type=str, help="Path to *_eskf_update_diag.csv")
    ap.add_argument("--out-dir", required=True, type=str, help="Output directory for figures/report")
    ap.add_argument("--run", default=None, type=str, help="run_id for naming (optional)")
    args = ap.parse_args(argv)

    diagnose(
        traj_csv=Path(args.traj),
        upd_csv=Path(args.updates),
        out_dir=Path(args.out_dir),
        run_id=args.run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
