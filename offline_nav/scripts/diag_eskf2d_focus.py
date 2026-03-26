#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
diag_eskf2d_focus.py (UPGRADED)

针对 offline_nav/out/diag/*_eskf2d_focus.csv 的 ESKF 诊断脚本（新 schema 兼容版）：

新增支持（若列存在则启用）：
- 过程诊断：prop_ok, dt_prop_s
- 更新一致性：nis0, nis1, R_inflate, HPHt_over_R
- 白化残差：rwhiteE/rwhiteN/rwhite_norm
- 注入量：dx_norm, dx_v_h, dx_yaw, dx_bgz
- yaw 语义：yaw_state_rad, yaw_used_rad, yaw_err_rad
- 数值稳定性：Pcond, S_cond, R_cond 以及 traces
- 细粒度 HPHt 与 R（HPHt_E/HPHt_N/R_E/R_N）
- 仍保持老版本统计：kind/used/used_reason/triggered/dt_match/speeds/ratio/nis

输出：
1) 文本报告：<out>/eskf_diag_report.txt
2) 图：<out>/*.png
3) 异常行 CSV（可选）：<out>/anomalies.csv

使用示例：
python diag_eskf2d_focus.py \
  --csv offline_nav/out/diag/2026-01-10_pooltest02_eskf2d_focus.csv \
  --out offline_nav/out/diag_reports/2026-01-10_pooltest02 \
  --export_anomalies
"""

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -----------------------------
# helpers
# -----------------------------
def _mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_num(df: pd.DataFrame, col: str) -> None:
    """Convert column to numeric if exists."""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def _pct(frac: float) -> str:
    if not np.isfinite(frac):
        return "nan%"
    return f"{100.0 * float(frac):.2f}%"


def _finite(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return a[np.isfinite(a)]


def _quantiles(a: np.ndarray, qs=(0.5, 0.9, 0.95, 0.99)) -> dict:
    v = _finite(a)
    if v.size == 0:
        return {q: np.nan for q in qs}
    return {q: float(np.quantile(v, q)) for q in qs}


def _hist_save(values: np.ndarray, title: str, out_png: Path, xlabel: str, logy: bool = False) -> None:
    v = _finite(values)
    plt.figure()
    if v.size > 0:
        plt.hist(v, bins=120)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("count")
    if logy:
        plt.yscale("log")
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def _scatter_save(x: np.ndarray, y: np.ndarray, title: str, out_png: Path, xlabel: str, ylabel: str) -> None:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    plt.figure()
    if np.any(m):
        plt.scatter(x[m], y[m], s=6)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def _topk_rows(df: pd.DataFrame, key: str, k: int = 30, ascending: bool = False) -> pd.DataFrame:
    if key not in df.columns:
        return df.head(0)
    return df.sort_values(key, ascending=ascending).head(k)


def _colset(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns]


# -----------------------------
# main
# -----------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=str, help="path to *_eskf2d_focus.csv")
    ap.add_argument("--out", required=True, type=str, help="output directory for report/plots")

    # thresholds (keep old defaults but allow override)
    ap.add_argument("--dt_bad", type=float, default=0.05, help="|dt_match_s| bad threshold (s)")
    ap.add_argument("--nis_bad", type=float, default=80.0, help="NIS bad threshold (match new cfg focus_nis_warn style)")
    ap.add_argument("--nis0_bad", type=float, default=120.0, help="NIS0 bad threshold (pre-inflate / pre-gate)")
    ap.add_argument("--nis1_bad", type=float, default=120.0, help="NIS1 bad threshold (post-inflate)")
    ap.add_argument("--meas_speed_eps", type=float, default=1e-3, help="speed_meas_h considered ~0 threshold")

    ap.add_argument("--ratio_bad", type=float, default=10.0, help="ratio_pre_over_meas bad threshold")
    ap.add_argument("--rwhite_bad", type=float, default=6.0, help="whitened residual norm bad threshold (chi-ish)")
    ap.add_argument("--dx_norm_bad", type=float, default=0.5, help="dx_norm bad threshold (engineering)")

    ap.add_argument("--noeffect_vel_eps", type=float, default=1e-3, help="|v_post - v_pre| small => update ineffective")
    ap.add_argument("--noeffect_pos_eps", type=float, default=1e-4, help="|p_post - p_pre| small => update ineffective (m)")
    ap.add_argument("--export_anomalies", action="store_true", help="export anomalies.csv")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out)
    _mkdir(out_dir)

    df = pd.read_csv(csv_path)

    # -----------------------------
    # normalize numeric types (new schema + backward compatible)
    # -----------------------------
    numeric_candidates = [
        # base
        "used", "t_meas_s", "t_imu_s", "dt_match_s",
        "vE_pre", "vN_pre", "vU_pre", "vE_post", "vN_post", "vU_post",
        "vE_meas", "vN_meas", "vU_meas", "vU_be", "vU_ref_err",
        "speed_pre_h", "speed_post_h", "speed_meas_h", "ratio_pre_over_meas",
        "verrE", "verrN", "verrU", "verr_h",
        "nis", "triggered",
        "E_pre", "N_pre", "U_pre", "E_post", "N_post", "U_post",

        # new add-ons
        "nis0", "nis1", "R_inflate", "HPHt_over_R",
        "HPHt_E", "HPHt_N", "R_E", "R_N",
        "rwhiteE", "rwhiteN", "rwhite_norm",
        "dx_norm", "dx_v_h", "dx_yaw", "dx_bgz",
        "prop_ok", "dt_prop_s",
        "yaw_state_rad", "yaw_used_rad", "yaw_err_rad",
        "bgz_rad_s",
        "Pcond", "P_pos_tr", "P_vel_tr", "P_yaw", "P_bgz", "P_tr",
        "S_tr", "S_cond", "R_tr", "R_cond",
    ]
    for c in numeric_candidates:
        _safe_num(df, c)

    # -----------------------------
    # derived metrics (robust)
    # -----------------------------
    # dv norm
    if all(c in df.columns for c in ["vE_pre", "vN_pre", "vU_pre", "vE_post", "vN_post", "vU_post"]):
        dvE = df["vE_post"] - df["vE_pre"]
        dvN = df["vN_post"] - df["vN_pre"]
        dvU = df["vU_post"] - df["vU_pre"]
        df["_dv_norm"] = np.sqrt(dvE**2 + dvN**2 + dvU**2)
    elif all(c in df.columns for c in ["vE_pre", "vN_pre", "vE_post", "vN_post"]):
        dvE = df["vE_post"] - df["vE_pre"]
        dvN = df["vN_post"] - df["vN_pre"]
        df["_dv_norm"] = np.sqrt(dvE**2 + dvN**2)
    else:
        df["_dv_norm"] = np.nan

    # dp norm
    if all(c in df.columns for c in ["E_pre", "N_pre", "U_pre", "E_post", "N_post", "U_post"]):
        dE = df["E_post"] - df["E_pre"]
        dN = df["N_post"] - df["N_pre"]
        dU = df["U_post"] - df["U_pre"]
        df["_dp_norm"] = np.sqrt(dE**2 + dN**2 + dU**2)
    elif all(c in df.columns for c in ["E_pre", "N_pre", "E_post", "N_post"]):
        dE = df["E_post"] - df["E_pre"]
        dN = df["N_post"] - df["N_pre"]
        df["_dp_norm"] = np.sqrt(dE**2 + dN**2)
    else:
        df["_dp_norm"] = np.nan

    # yaw delta (state vs used)
    if "yaw_state_rad" in df.columns and "yaw_used_rad" in df.columns:
        df["_yaw_state_minus_used"] = df["yaw_state_rad"] - df["yaw_used_rad"]
    else:
        df["_yaw_state_minus_used"] = np.nan

    # ratio explosion (nan/inf or huge)
    if "ratio_pre_over_meas" in df.columns:
        ratio = df["ratio_pre_over_meas"].to_numpy(dtype=float)
        df["_ratio_bad"] = (~np.isfinite(ratio)) | (np.abs(ratio) > 1e3)
    else:
        df["_ratio_bad"] = False

    # used mask
    used = (df["used"] > 0.5) if "used" in df.columns else pd.Series([True] * len(df), index=df.index)

    # -----------------------------
    # anomaly masks
    # -----------------------------
    dt_bad = (df["dt_match_s"].abs() > args.dt_bad) if "dt_match_s" in df.columns else pd.Series([False] * len(df), index=df.index)

    nis_bad = (df["nis"] > args.nis_bad) if "nis" in df.columns else pd.Series([False] * len(df), index=df.index)
    nis0_bad = (df["nis0"] > args.nis0_bad) if "nis0" in df.columns else pd.Series([False] * len(df), index=df.index)
    nis1_bad = (df["nis1"] > args.nis1_bad) if "nis1" in df.columns else pd.Series([False] * len(df), index=df.index)

    meas_speed_zero = (df["speed_meas_h"].abs() < args.meas_speed_eps) if "speed_meas_h" in df.columns else pd.Series([False] * len(df), index=df.index)
    used_with_meas_zero = used & meas_speed_zero

    update_noeffect_vel = used & (df["_dv_norm"] < args.noeffect_vel_eps)
    update_noeffect_pos = used & (df["_dp_norm"] < args.noeffect_pos_eps)

    ratio_bad = pd.Series(df["_ratio_bad"].astype(bool), index=df.index) if "_ratio_bad" in df.columns else pd.Series([False] * len(df), index=df.index)
    ratio_soft_bad = (df["ratio_pre_over_meas"] > args.ratio_bad) if "ratio_pre_over_meas" in df.columns else pd.Series([False] * len(df), index=df.index)

    rwhite_bad = (df["rwhite_norm"] > args.rwhite_bad) if "rwhite_norm" in df.columns else pd.Series([False] * len(df), index=df.index)
    dx_norm_bad = (df["dx_norm"] > args.dx_norm_bad) if "dx_norm" in df.columns else pd.Series([False] * len(df), index=df.index)

    # conditioning flags (if present)
    Pcond_bad = (df["Pcond"] > 1e6) if "Pcond" in df.columns else pd.Series([False] * len(df), index=df.index)
    Scond_bad = (df["S_cond"] > 1e12) if "S_cond" in df.columns else pd.Series([False] * len(df), index=df.index)
    Rcond_bad = (df["R_cond"] > 1e12) if "R_cond" in df.columns else pd.Series([False] * len(df), index=df.index)

    # union anomalies (used rows focused)
    anomalies = (
        (used & dt_bad)
        | (used & nis_bad)
        | (used & nis0_bad)
        | (used & nis1_bad)
        | (used & ratio_bad)
        | (used & ratio_soft_bad)
        | (used & rwhite_bad)
        | (used & dx_norm_bad)
        | (used & Pcond_bad)
        | (used & Scond_bad)
        | (used & Rcond_bad)
    )

    # -----------------------------
    # report
    # -----------------------------
    rep: list[str] = []
    rep.append(f"CSV: {csv_path}\n")
    rep.append(f"Rows: {len(df)}\n\n")

    # schema peek
    rep.append("== schema summary ==\n")
    rep.append(f"columns={len(df.columns)}\n")
    rep.append("key columns present:\n")
    keys = [
        "kind","used","used_reason","triggered","t_meas_s","t_imu_s","dt_match_s",
        "speed_pre_h","speed_meas_h","ratio_pre_over_meas","nis","nis0","nis1","R_inflate",
        "rwhite_norm","dx_norm","prop_ok","dt_prop_s","yaw_state_rad","yaw_used_rad","yaw_err_rad",
        "Pcond","S_cond","R_cond"
    ]
    present = [k for k in keys if k in df.columns]
    missing = [k for k in keys if k not in df.columns]
    rep.append("  present: " + ", ".join(present) + "\n")
    rep.append("  missing: " + ", ".join(missing) + "\n\n")

    # distributions
    if "kind" in df.columns:
        rep.append("== kind distribution ==\n")
        rep.append(df["kind"].value_counts(dropna=False).to_string() + "\n\n")

    if "used" in df.columns:
        rep.append("== used distribution ==\n")
        rep.append(df["used"].value_counts(dropna=False).to_string() + "\n\n")

    if "used_reason" in df.columns:
        rep.append("== used_reason distribution (top40) ==\n")
        rep.append(df["used_reason"].value_counts(dropna=False).head(40).to_string() + "\n\n")

    if "triggered" in df.columns:
        rep.append("== triggered distribution ==\n")
        rep.append(df["triggered"].value_counts(dropna=False).to_string() + "\n\n")

    if "prop_ok" in df.columns:
        rep.append("== prop_ok distribution ==\n")
        rep.append(df["prop_ok"].value_counts(dropna=False).to_string() + "\n\n")

    # dt stats
    if "dt_match_s" in df.columns:
        dt = df["dt_match_s"].to_numpy(dtype=float)
        q = _quantiles(np.abs(dt))
        rep.append("== dt_match_s |abs| stats ==\n")
        rep.append(
            f"mean={np.nanmean(np.abs(dt)):.6f}  "
            f"median={q[0.5]:.6f}  p90={q[0.9]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n"
        )
        rep.append(f"bad(|dt|>{args.dt_bad}s) USED: {(used & dt_bad).mean():.6f} ({_pct((used & dt_bad).mean())})\n\n")

    if "dt_prop_s" in df.columns:
        dtp = df["dt_prop_s"].to_numpy(dtype=float)
        q = _quantiles(dtp)
        rep.append("== dt_prop_s stats ==\n")
        rep.append(
            f"mean={np.nanmean(dtp):.6f}  median={q[0.5]:.6f}  p90={q[0.9]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n\n"
        )

    # speed stats
    if "speed_meas_h" in df.columns:
        sm = df["speed_meas_h"].to_numpy(dtype=float)
        q = _quantiles(sm)
        rep.append("== speed_meas_h stats ==\n")
        rep.append(
            f"mean={np.nanmean(sm):.6f}  median={q[0.5]:.6f}  p90={q[0.9]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n"
        )
        rep.append(f"near-zero(|speed_meas_h|<{args.meas_speed_eps}): {meas_speed_zero.mean():.6f} ({_pct(meas_speed_zero.mean())})\n")
        rep.append(f"USED & near-zero meas speed: {used_with_meas_zero.mean():.6f} ({_pct(used_with_meas_zero.mean())})\n\n")

    if "speed_pre_h" in df.columns:
        sp = df["speed_pre_h"].to_numpy(dtype=float)
        q = _quantiles(sp)
        rep.append("== speed_pre_h stats ==\n")
        rep.append(
            f"mean={np.nanmean(sp):.6f}  median={q[0.5]:.6f}  p90={q[0.9]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n\n"
        )

    # ratio stats
    if "ratio_pre_over_meas" in df.columns:
        rr = df["ratio_pre_over_meas"].to_numpy(dtype=float)
        q = _quantiles(rr)
        rep.append("== ratio_pre_over_meas stats ==\n")
        rep.append(
            f"mean={np.nanmean(rr):.3f}  median={q[0.5]:.3f}  p90={q[0.9]:.3f}  p95={q[0.95]:.3f}  p99={q[0.99]:.3f}\n"
        )
        rep.append(f"ratio bad (nan/inf or |ratio|>1e3) USED: {(used & ratio_bad).mean():.6f} ({_pct((used & ratio_bad).mean())})\n")
        rep.append(f"ratio > {args.ratio_bad} USED: {(used & ratio_soft_bad).mean():.6f} ({_pct((used & ratio_soft_bad).mean())})\n\n")

    # NIS stats (nis / nis0 / nis1)
    if "nis" in df.columns:
        nis = df["nis"].to_numpy(dtype=float)
        q = _quantiles(nis)
        rep.append("== NIS stats ==\n")
        rep.append(
            f"mean={np.nanmean(nis):.3f}  median={q[0.5]:.3f}  p90={q[0.9]:.3f}  p95={q[0.95]:.3f}  p99={q[0.99]:.3f}\n"
        )
        rep.append(f"bad(NIS>{args.nis_bad}) USED: {(used & nis_bad).mean():.6f} ({_pct((used & nis_bad).mean())})\n\n")

    if "nis0" in df.columns:
        a = df["nis0"].to_numpy(dtype=float)
        q = _quantiles(a)
        rep.append("== NIS0 (pre-inflate) stats ==\n")
        rep.append(
            f"mean={np.nanmean(a):.3f}  median={q[0.5]:.3f}  p95={q[0.95]:.3f}  p99={q[0.99]:.3f}\n"
        )
        rep.append(f"bad(NIS0>{args.nis0_bad}) USED: {(used & nis0_bad).mean():.6f} ({_pct((used & nis0_bad).mean())})\n\n")

    if "nis1" in df.columns:
        a = df["nis1"].to_numpy(dtype=float)
        q = _quantiles(a)
        rep.append("== NIS1 (post-inflate) stats ==\n")
        rep.append(
            f"mean={np.nanmean(a):.3f}  median={q[0.5]:.3f}  p95={q[0.95]:.3f}  p99={q[0.99]:.3f}\n"
        )
        rep.append(f"bad(NIS1>{args.nis1_bad}) USED: {(used & nis1_bad).mean():.6f} ({_pct((used & nis1_bad).mean())})\n\n")

    # R inflation stats
    if "R_inflate" in df.columns:
        rin = df["R_inflate"].to_numpy(dtype=float)
        q = _quantiles(rin)
        rep.append("== R_inflate stats ==\n")
        rep.append(
            f"mean={np.nanmean(rin):.3f}  median={q[0.5]:.3f}  p90={q[0.9]:.3f}  p95={q[0.95]:.3f}  p99={q[0.99]:.3f}\n"
        )
        rep.append(f"R_inflate>1.0 USED: {(used & (df['R_inflate'] > 1.0)).mean():.6f} ({_pct((used & (df['R_inflate'] > 1.0)).mean())})\n\n")

    # whitened residual stats
    if "rwhite_norm" in df.columns:
        rw = df["rwhite_norm"].to_numpy(dtype=float)
        q = _quantiles(rw)
        rep.append("== whitened residual norm stats ==\n")
        rep.append(
            f"mean={np.nanmean(rw):.3f}  median={q[0.5]:.3f}  p90={q[0.9]:.3f}  p95={q[0.95]:.3f}  p99={q[0.99]:.3f}\n"
        )
        rep.append(f"bad(rwhite_norm>{args.rwhite_bad}) USED: {(used & rwhite_bad).mean():.6f} ({_pct((used & rwhite_bad).mean())})\n\n")

    # dx stats
    if "dx_norm" in df.columns:
        dxn = df["dx_norm"].to_numpy(dtype=float)
        q = _quantiles(dxn)
        rep.append("== dx_norm stats ==\n")
        rep.append(
            f"mean={np.nanmean(dxn):.6f}  median={q[0.5]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n"
        )
        rep.append(f"bad(dx_norm>{args.dx_norm_bad}) USED: {(used & dx_norm_bad).mean():.6f} ({_pct((used & dx_norm_bad).mean())})\n\n")

    # yaw sanity
    if "yaw_err_rad" in df.columns:
        ye = df["yaw_err_rad"].to_numpy(dtype=float)
        q = _quantiles(np.abs(ye))
        rep.append("== yaw_err_rad |abs| stats ==\n")
        rep.append(
            f"mean={np.nanmean(np.abs(ye)):.6f}  median={q[0.5]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n\n"
        )

    if "_yaw_state_minus_used" in df.columns:
        yd = df["_yaw_state_minus_used"].to_numpy(dtype=float)
        q = _quantiles(yd)
        rep.append("== yaw_state_rad - yaw_used_rad stats ==\n")
        rep.append(
            f"mean={np.nanmean(yd):.6f}  median={q[0.5]:.6f}  p95={q[0.95]:.6f}  p99={q[0.99]:.6f}\n\n"
        )

    # conditioning
    if "Pcond" in df.columns:
        pc = df["Pcond"].to_numpy(dtype=float)
        q = _quantiles(pc)
        rep.append("== Pcond stats ==\n")
        rep.append(
            f"mean={np.nanmean(pc):.3e}  median={q[0.5]:.3e}  p95={q[0.95]:.3e}  p99={q[0.99]:.3e}\n"
        )
        rep.append(f"Pcond>1e6 USED: {(used & Pcond_bad).mean():.6f} ({_pct((used & Pcond_bad).mean())})\n\n")

    if "S_cond" in df.columns:
        sc = df["S_cond"].to_numpy(dtype=float)
        q = _quantiles(sc)
        rep.append("== S_cond stats ==\n")
        rep.append(
            f"mean={np.nanmean(sc):.3e}  median={q[0.5]:.3e}  p95={q[0.95]:.3e}  p99={q[0.99]:.3e}\n"
        )
        rep.append(f"S_cond>1e12 USED: {(used & Scond_bad).mean():.6f} ({_pct((used & Scond_bad).mean())})\n\n")

    if "R_cond" in df.columns:
        rc = df["R_cond"].to_numpy(dtype=float)
        q = _quantiles(rc)
        rep.append("== R_cond stats ==\n")
        rep.append(
            f"mean={np.nanmean(rc):.3e}  median={q[0.5]:.3e}  p95={q[0.95]:.3e}  p99={q[0.99]:.3e}\n"
        )
        rep.append(f"R_cond>1e12 USED: {(used & Rcond_bad).mean():.6f} ({_pct((used & Rcond_bad).mean())})\n\n")

    # update effect
    rep.append("== update effect (used rows) ==\n")
    rep.append(f"no-effect velocity (|dv|<{args.noeffect_vel_eps}): {update_noeffect_vel.mean():.6f} ({_pct(update_noeffect_vel.mean())})\n")
    rep.append(f"no-effect position (|dp|<{args.noeffect_pos_eps}): {update_noeffect_pos.mean():.6f} ({_pct(update_noeffect_pos.mean())})\n\n")

    # anomaly union
    rep.append("== anomaly counts (union, used-focused) ==\n")
    rep.append(f"anomalies: {(anomalies).mean():.6f} ({_pct((anomalies).mean())})  total={int(anomalies.sum())}\n\n")

    # top offenders tables
    def _table(cols: list[str], title: str, sort_key: str, asc: bool = False) -> None:
        avail = _colset(df, cols)
        rep.append(f"== {title} ==\n")
        if not avail or sort_key not in df.columns:
            rep.append("(missing columns)\n\n")
            return
        tmp = _topk_rows(df[used], sort_key, k=25, ascending=asc)
        rep.append(tmp[avail].to_string(index=False) + "\n\n")

    _table(
        cols=["kind","used","used_reason","t_meas_s","t_imu_s","dt_match_s","speed_pre_h","speed_meas_h","ratio_pre_over_meas","nis","nis0","nis1","R_inflate","triggered"],
        title="top NIS rows (used)",
        sort_key="nis",
        asc=False,
    )

    if "dt_match_s" in df.columns:
        tmp = df[used].copy()
        tmp["_abs_dt"] = tmp["dt_match_s"].abs()
        avail = _colset(tmp, ["kind","used","used_reason","t_meas_s","t_imu_s","dt_match_s","_abs_dt","nis","nis0","nis1","triggered"])
        rep.append("== top |dt_match_s| rows (used) ==\n")
        rep.append(tmp.sort_values("_abs_dt", ascending=False).head(25)[avail].to_string(index=False) + "\n\n")

    _table(
        cols=["kind","used","used_reason","t_meas_s","dt_match_s","nis","nis0","nis1","R_inflate","rwhite_norm","dx_norm","triggered"],
        title="top whitened residual norm rows (used)",
        sort_key="rwhite_norm",
        asc=False,
    )

    _table(
        cols=["kind","used","used_reason","t_meas_s","dt_match_s","nis","R_inflate","dx_norm","dx_v_h","dx_yaw","dx_bgz","triggered"],
        title="top dx_norm rows (used)",
        sort_key="dx_norm",
        asc=False,
    )

    # write report
    rep_path = out_dir / "eskf_diag_report.txt"
    rep_path.write_text("".join(rep), encoding="utf-8")

    # -----------------------------
    # plots (only if columns exist)
    # -----------------------------
    if "dt_match_s" in df.columns:
        _hist_save(np.abs(df["dt_match_s"].to_numpy()), "abs(dt_match_s) histogram", out_dir / "hist_abs_dt_match.png", "abs(dt_match_s) [s]", logy=True)

    if "dt_prop_s" in df.columns:
        _hist_save(df["dt_prop_s"].to_numpy(), "dt_prop_s histogram", out_dir / "hist_dt_prop.png", "dt_prop_s [s]", logy=True)

    if "nis" in df.columns:
        _hist_save(df["nis"].to_numpy(), "NIS histogram", out_dir / "hist_nis.png", "NIS", logy=True)

    if "nis0" in df.columns:
        _hist_save(df["nis0"].to_numpy(), "NIS0 histogram", out_dir / "hist_nis0.png", "NIS0", logy=True)

    if "nis1" in df.columns:
        _hist_save(df["nis1"].to_numpy(), "NIS1 histogram", out_dir / "hist_nis1.png", "NIS1", logy=True)

    if "R_inflate" in df.columns:
        _hist_save(df["R_inflate"].to_numpy(), "R_inflate histogram", out_dir / "hist_R_inflate.png", "R_inflate", logy=True)

    if "HPHt_over_R" in df.columns:
        _hist_save(df["HPHt_over_R"].to_numpy(), "HPHt_over_R histogram", out_dir / "hist_HPHt_over_R.png", "HPHt_over_R", logy=True)

    if "speed_meas_h" in df.columns:
        _hist_save(df["speed_meas_h"].to_numpy(), "speed_meas_h histogram", out_dir / "hist_speed_meas_h.png", "speed_meas_h [m/s]", logy=True)

    if "speed_pre_h" in df.columns:
        _hist_save(df["speed_pre_h"].to_numpy(), "speed_pre_h histogram", out_dir / "hist_speed_pre_h.png", "speed_pre_h [m/s]", logy=True)

    if "ratio_pre_over_meas" in df.columns:
        _hist_save(df["ratio_pre_over_meas"].to_numpy(), "ratio_pre_over_meas histogram", out_dir / "hist_ratio.png", "ratio_pre_over_meas", logy=True)

    if "_dv_norm" in df.columns:
        _hist_save(df["_dv_norm"].to_numpy(), "update |dv| histogram", out_dir / "hist_dv_norm.png", "|v_post - v_pre| [m/s]", logy=True)

    if "_dp_norm" in df.columns:
        _hist_save(df["_dp_norm"].to_numpy(), "update |dp| histogram", out_dir / "hist_dp_norm.png", "|p_post - p_pre| [m]", logy=True)

    if "rwhite_norm" in df.columns:
        _hist_save(df["rwhite_norm"].to_numpy(), "whitened residual norm histogram", out_dir / "hist_rwhite_norm.png", "rwhite_norm", logy=True)

    if "dx_norm" in df.columns:
        _hist_save(df["dx_norm"].to_numpy(), "dx_norm histogram", out_dir / "hist_dx_norm.png", "dx_norm", logy=True)

    if "Pcond" in df.columns:
        _hist_save(df["Pcond"].to_numpy(), "Pcond histogram", out_dir / "hist_Pcond.png", "Pcond", logy=True)

    if "S_cond" in df.columns:
        _hist_save(df["S_cond"].to_numpy(), "S_cond histogram", out_dir / "hist_Scond.png", "S_cond", logy=True)

    if "R_cond" in df.columns:
        _hist_save(df["R_cond"].to_numpy(), "R_cond histogram", out_dir / "hist_Rcond.png", "R_cond", logy=True)

    # yaw plots
    if "yaw_err_rad" in df.columns:
        _hist_save(np.abs(df["yaw_err_rad"].to_numpy()), "|yaw_err_rad| histogram", out_dir / "hist_abs_yaw_err.png", "|yaw_err_rad| [rad]", logy=True)

    if "_yaw_state_minus_used" in df.columns:
        _hist_save(df["_yaw_state_minus_used"].to_numpy(), "yaw_state - yaw_used histogram", out_dir / "hist_yaw_state_minus_used.png", "yaw_state - yaw_used [rad]", logy=True)

    # scatter correlations
    if "dt_match_s" in df.columns and "nis" in df.columns:
        _scatter_save(np.abs(df["dt_match_s"].to_numpy()), df["nis"].to_numpy(),
                      "NIS vs abs(dt_match_s)", out_dir / "scatter_nis_vs_absdt.png",
                      "abs(dt_match_s) [s]", "NIS")

    if "speed_meas_h" in df.columns and "nis" in df.columns:
        _scatter_save(df["speed_meas_h"].to_numpy(), df["nis"].to_numpy(),
                      "NIS vs speed_meas_h", out_dir / "scatter_nis_vs_speedmeas.png",
                      "speed_meas_h [m/s]", "NIS")

    if "ratio_pre_over_meas" in df.columns and "nis" in df.columns:
        _scatter_save(df["ratio_pre_over_meas"].to_numpy(), df["nis"].to_numpy(),
                      "NIS vs ratio_pre_over_meas", out_dir / "scatter_nis_vs_ratio.png",
                      "ratio_pre_over_meas", "NIS")

    if "R_inflate" in df.columns and "nis" in df.columns:
        _scatter_save(df["R_inflate"].to_numpy(), df["nis"].to_numpy(),
                      "NIS vs R_inflate", out_dir / "scatter_nis_vs_Rinflate.png",
                      "R_inflate", "NIS")

    if "rwhite_norm" in df.columns and "nis" in df.columns:
        _scatter_save(df["rwhite_norm"].to_numpy(), df["nis"].to_numpy(),
                      "NIS vs rwhite_norm", out_dir / "scatter_nis_vs_rwhite.png",
                      "rwhite_norm", "NIS")

    if "dx_norm" in df.columns and "nis" in df.columns:
        _scatter_save(df["dx_norm"].to_numpy(), df["nis"].to_numpy(),
                      "NIS vs dx_norm", out_dir / "scatter_nis_vs_dxnorm.png",
                      "dx_norm", "NIS")

    if "Pcond" in df.columns and "nis" in df.columns:
        _scatter_save(df["Pcond"].to_numpy(), df["nis"].to_numpy(),
                      "NIS vs Pcond", out_dir / "scatter_nis_vs_Pcond.png",
                      "Pcond", "NIS")

    # export anomalies
    if args.export_anomalies:
        out_csv = out_dir / "anomalies.csv"
        df.loc[anomalies].to_csv(out_csv, index=False)

    print(f"[OK] Report: {rep_path}")
    print(f"[OK] Plots  : {out_dir}/*.png")
    if args.export_anomalies:
        print(f"[OK] Anoms  : {out_dir/'anomalies.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
