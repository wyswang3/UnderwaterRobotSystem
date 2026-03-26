#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apps/tools/imu_diag_demo.py

对 cli_proc 输出的 *_imu_filtered.csv 做“误差归因”诊断（工程版）：
核心修复点：
- gyro 诊断优先 Gyro*_in_rad_s（不要被阈值后的 *_out 清零误导）
- 重力一致性按 specific-force 模型检查：AccRaw + G - BiasAcc ≈ 0
- yaw 自动检测固定偏置（0/±90/180），输出最佳 offset 建议
- 输出“风险结论 + 建议动作”，不是只给统计

用法示例（从 offline_nav/src 执行）：
(offnav_env) python ../apps/tools/imu_diag_demo.py \
  --imu-csv ../out/proc/2026-01-10_pooltest02/2026-01-10_pooltest02_imu_filtered.csv \
  --out-dir ../out/diag_imu \
  --bias-duration-s 20
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# headless safe
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# =============================================================================
# Utilities
# =============================================================================

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def _finite(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    return np.isfinite(a)

def _wrap_deg_180(x_deg: np.ndarray) -> np.ndarray:
    """Wrap degrees to [-180,180)."""
    x = np.asarray(x_deg, dtype=float)
    return (x + 180.0) % 360.0 - 180.0

def _wrap_rad_pi(x_rad: np.ndarray) -> np.ndarray:
    """Wrap radians to [-pi,pi)."""
    x = np.asarray(x_rad, dtype=float)
    return (x + np.pi) % (2.0 * np.pi) - np.pi

def _robust_slope(t: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope k for y = k*t + b ignoring NaN/Inf."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    m = _finite(t) & _finite(y)
    if int(m.sum()) < 10:
        return float("nan")
    tt = t[m]
    yy = y[m]
    tt = tt - float(np.mean(tt))
    denom = float(np.dot(tt, tt))
    if denom <= 0:
        return float("nan")
    k = float(np.dot(tt, yy - float(np.mean(yy))) / denom)
    return k

def _stats(x: np.ndarray) -> Dict[str, float]:
    x = np.asarray(x, dtype=float)
    m = _finite(x)
    if int(m.sum()) == 0:
        return {"mean": np.nan, "std": np.nan, "p95": np.nan, "maxabs": np.nan, "rms": np.nan}
    xx = x[m]
    return {
        "mean": float(np.mean(xx)),
        "std": float(np.std(xx)),
        "p95": float(np.percentile(np.abs(xx), 95)),
        "maxabs": float(np.max(np.abs(xx))),
        "rms": float(np.sqrt(np.mean(xx * xx))),
    }

def _pick_first(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def _pick_cols(df: pd.DataFrame, cols: List[str]) -> List[str]:
    return [c for c in cols if c in df.columns]

def _estimate_fs(t_s: np.ndarray) -> float:
    t_s = np.asarray(t_s, dtype=float)
    if t_s.size < 2:
        return float("nan")
    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return float("nan")
    return 1.0 / float(np.median(dt))

def _circle_mean_deg(x_deg: np.ndarray) -> float:
    """Circular mean in degrees for wrapped angle [-180,180)."""
    x = np.asarray(x_deg, dtype=float)
    m = _finite(x)
    if int(m.sum()) == 0:
        return float("nan")
    rad = np.deg2rad(_wrap_deg_180(x[m]))
    s = float(np.mean(np.sin(rad)))
    c = float(np.mean(np.cos(rad)))
    if abs(s) < 1e-12 and abs(c) < 1e-12:
        return float("nan")
    return float(np.rad2deg(np.arctan2(s, c)))

def _best_yaw_offset_deg(diff_deg: np.ndarray, candidates: List[float]) -> Tuple[float, float]:
    """
    Given raw diff = yawA - yawB (deg), find offset in candidates that minimizes RMS of wrapped residual.
    Return (best_offset, best_rms).
    """
    best_off = float("nan")
    best_rms = float("inf")
    for off in candidates:
        r = _wrap_deg_180(diff_deg - off)
        s = _stats(r)
        if np.isfinite(s["rms"]) and s["rms"] < best_rms:
            best_rms = s["rms"]
            best_off = float(off)
    return best_off, best_rms


# =============================================================================
# Plot helpers
# =============================================================================

def _save_plot_series(
    t: np.ndarray,
    df: pd.DataFrame,
    cols: List[str],
    out_path: Path,
    title: str,
    span: Optional[Tuple[float, float]] = None,
) -> None:
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return
    plt.figure()
    for c in cols:
        plt.plot(t, df[c].to_numpy(dtype=float), label=c)
    if span is not None:
        plt.axvspan(span[0], span[1], alpha=0.2)
    plt.xlabel("t_s")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()

def _save_plot_hist(
    x: np.ndarray,
    out_path: Path,
    title: str,
    xlabel: str,
) -> None:
    x = np.asarray(x, dtype=float)
    m = _finite(x)
    if int(m.sum()) < 10:
        return
    plt.figure()
    plt.hist(x[m], bins=80)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


# =============================================================================
# Core diagnostics
# =============================================================================

def analyze_imu_csv(
    imu_csv: Path,
    out_dir: Path,
    bias_duration_s: float = 20.0,
    make_plots: bool = True,
    auto_yaw_offset: bool = True,
) -> int:
    imu_csv = Path(imu_csv)
    out_dir = _ensure_dir(Path(out_dir))

    df = pd.read_csv(imu_csv)
    if df is None or df.empty:
        raise RuntimeError(f"Empty IMU CSV: {imu_csv}")

    if "t_s" not in df.columns:
        raise KeyError("CSV missing required column: t_s")

    t = df["t_s"].to_numpy(dtype=float)
    if t.size < 10:
        raise ValueError("Too few samples in IMU CSV")

    t0 = float(np.nanmin(t))
    t1 = float(np.nanmax(t))
    dur = float(t1 - t0)
    fs = _estimate_fs(t)

    # bias window: first bias_duration_s seconds
    bias_mask = (t >= t0) & (t <= (t0 + float(bias_duration_s)))
    if int(np.sum(bias_mask)) < 10:
        bias_mask[:] = True

    span_bias = (t0, t0 + float(bias_duration_s))

    # column groups
    acc_lin_cols = _pick_cols(df, ["AccX_mps2", "AccY_mps2", "AccZ_mps2"])

    gyro_in_cols = _pick_cols(df, ["GyroX_in_rad_s", "GyroY_in_rad_s", "GyroZ_in_rad_s"])
    gyro_out_cols = _pick_cols(df, ["GyroX_out_rad_s", "GyroY_out_rad_s", "GyroZ_out_rad_s"])
    gyro_legacy_cols = _pick_cols(df, ["GyroX_rad_s", "GyroY_rad_s", "GyroZ_rad_s"])

    acc_raw_cols = _pick_cols(df, ["AccXraw_mps2", "AccYraw_mps2", "AccZraw_mps2"])
    g_cols = _pick_cols(df, ["Gx_mps2", "Gy_mps2", "Gz_mps2"])
    bias_acc_cols = _pick_cols(df, ["BiasAccX_mps2", "BiasAccY_mps2", "BiasAccZ_mps2"])
    bias_gyro_cols = _pick_cols(df, ["BiasGyroX_rad_s", "BiasGyroY_rad_s", "BiasGyroZ_rad_s"])

    # yaw candidates
    yaw_est_col = _pick_first(df, ["YawEst_unwrapped_deg", "YawEst_deg"])
    yaw_dev_col = _pick_first(df, ["YawDev_deg"])
    angz_col = _pick_first(df, ["AngZ_deg"])
    yaw_nav_col = _pick_first(df, ["yaw_nav_rad"])        # rad
    yaw_dev_rad_col = _pick_first(df, ["yaw_device_rad"]) # rad

    # report
    lines: List[str] = []
    lines.append(f"[IMU-DIAG] file={imu_csv}")
    lines.append(f"  t=[{t0:.3f}, {t1:.3f}]  duration={dur:.2f}s  N={int(t.size)}  fs~{fs:.2f}Hz")
    lines.append(f"  bias_window: first {bias_duration_s:.1f}s  samples={int(np.sum(bias_mask))}")
    lines.append("")

    # ------------------------------------------------------------
    # 0) Column health & warnings
    # ------------------------------------------------------------
    lines.append("== 0) Column health / which signals are trustworthy for what ==")
    if gyro_in_cols:
        lines.append("  gyro_for_eskf: Gyro*_in_rad_s (OK)")
    else:
        lines.append("  gyro_for_eskf: MISSING Gyro*_in_rad_s  (HIGH RISK: do not run ESKF with thresholded gyro)")

    if gyro_out_cols:
        # estimate zeroed ratio as a hint for thresholding
        zratio = []
        for c in gyro_out_cols:
            x = df[c].to_numpy(dtype=float)
            m = _finite(x)
            if int(m.sum()) == 0:
                zratio.append(float("nan"))
            else:
                zratio.append(float(np.mean(np.abs(x[m]) < 1e-12)))
        lines.append(f"  gyro_out: present (likely thresholded); zero_ratio={dict(zip(gyro_out_cols, [f'{r*100:.1f}%' if np.isfinite(r) else 'nan' for r in zratio]))}")
    elif gyro_legacy_cols:
        lines.append("  gyro_out: not found; using Gyro*_rad_s as legacy (check whether it is thresholded in your exporter)")
    else:
        lines.append("  gyro_out: MISSING")

    # gravity check availability
    if acc_raw_cols and g_cols:
        lines.append("  gravity_check: Acc*raw_mps2 + G*_mps2 available (OK)")
    else:
        lines.append("  gravity_check: missing Acc*raw_mps2 or G*_mps2 (cannot do specific-force consistency)")

    # yaw availability
    yaw_sources = []
    if yaw_est_col: yaw_sources.append(yaw_est_col)
    if yaw_dev_col: yaw_sources.append(yaw_dev_col)
    if angz_col: yaw_sources.append(angz_col)
    if yaw_nav_col: yaw_sources.append(yaw_nav_col)
    if yaw_dev_rad_col: yaw_sources.append(yaw_dev_rad_col)
    lines.append(f"  yaw_sources: {yaw_sources if yaw_sources else '(none)'}")
    lines.append("")

    # ------------------------------------------------------------
    # 1) Bias-window check: linear acc & gyro (use gyro_in!)
    # ------------------------------------------------------------
    lines.append("== 1) Bias-window check (should be near 0 for linear acc / gyro_in) ==")
    if acc_lin_cols:
        for c in acc_lin_cols:
            s = _stats(df[c].to_numpy(dtype=float)[bias_mask])
            lines.append(f"  {c:14s} mean={s['mean']:+.4f}  std={s['std']:.4f}  p95|x|={s['p95']:.4f}  max|x|={s['maxabs']:.4f}")
    else:
        lines.append("  (missing Acc*_mps2 columns)")

    if gyro_in_cols:
        for c in gyro_in_cols:
            s = _stats(df[c].to_numpy(dtype=float)[bias_mask])
            lines.append(f"  {c:14s} mean={s['mean']:+.6f}  std={s['std']:.6f}  p95|x|={s['p95']:.6f}  max|x|={s['maxabs']:.6f}")
    else:
        lines.append("  (missing Gyro*_in_rad_s columns)")
    lines.append("")

    # ------------------------------------------------------------
    # 2) Bias terms summary
    # ------------------------------------------------------------
    lines.append("== 2) Bias terms (from CSV, if exported) ==")
    if bias_acc_cols:
        vals = [float(np.nanmean(df[c].to_numpy(dtype=float)[bias_mask])) for c in bias_acc_cols]
        lines.append(f"  BiasAcc mean(bias window): {dict(zip(bias_acc_cols, [f'{v:+.4f}' for v in vals]))}")
    else:
        lines.append("  (missing BiasAcc*_mps2)")

    if bias_gyro_cols:
        vals = [float(np.nanmean(df[c].to_numpy(dtype=float)[bias_mask])) for c in bias_gyro_cols]
        lines.append(f"  BiasGyro mean(bias window): {dict(zip(bias_gyro_cols, [f'{v:+.6f}' for v in vals]))}")
    else:
        lines.append("  (missing BiasGyro*_rad_s)")
    lines.append("")

    # ------------------------------------------------------------
    # 3) Specific-force gravity consistency
    #    Correct check: r_sf = AccRaw + G - BiasAcc ≈ 0 in bias window
    # ------------------------------------------------------------
    lines.append("== 3) Specific-force consistency (static window) ==")
    r_sf = None
    if acc_raw_cols and g_cols and len(acc_raw_cols) == 3 and len(g_cols) == 3:
        acc_raw = df[acc_raw_cols].to_numpy(dtype=float)
        g_vec = df[g_cols].to_numpy(dtype=float)

        if bias_acc_cols and len(bias_acc_cols) == 3:
            b_acc = df[bias_acc_cols].to_numpy(dtype=float)
        else:
            # if BiasAcc not exported, approximate using mean(AccRaw + G) in bias window (consistent with your preprocess definition)
            b0 = np.nanmean((acc_raw + g_vec)[bias_mask, :], axis=0)
            b_acc = np.tile(b0.reshape(1, 3), (acc_raw.shape[0], 1))
            lines.append("  [WARN] BiasAcc not found; using b_acc ≈ mean(AccRaw+G) over bias window (approx).")

        r_sf = acc_raw + g_vec - b_acc  # should be ~0 at rest if bias window is truly static
        r_sf_b = r_sf[bias_mask, :]

        for i, ax in enumerate(["X", "Y", "Z"]):
            s = _stats(r_sf_b[:, i])
            lines.append(f"  r_sf_{ax}: mean={s['mean']:+.4f} std={s['std']:.4f} p95|x|={s['p95']:.4f} rms={s['rms']:.4f}")
        rms_all = float(np.sqrt(np.nanmean(r_sf_b ** 2)))
        lines.append(f"  r_sf_rms(all axes) = {rms_all:.4f} m/s^2  (target: small, e.g. <0.1~0.2 for good static window)")
    else:
        lines.append("  (need Acc*raw_mps2 + G*_mps2 to evaluate)")
    lines.append("")

    # ------------------------------------------------------------
    # 4) Yaw consistency & drift + auto offset suggestion
    # ------------------------------------------------------------
    lines.append("== 4) Yaw consistency / drift ==")
    # choose yaw_est series in deg (prefer unwrapped)
    if yaw_est_col is not None:
        yaw_est = df[yaw_est_col].to_numpy(dtype=float)
        k = _robust_slope(t, yaw_est)
        lines.append(f"  {yaw_est_col}: drift_slope ~ {k:+.6f} deg/s (~{k*60:+.3f} deg/min)")

        # compare with AngZ_deg
        if angz_col is not None:
            angz = df[angz_col].to_numpy(dtype=float)
            diff = _wrap_deg_180(yaw_est - angz)
            s = _stats(diff[bias_mask])
            cm = _circle_mean_deg(diff[bias_mask])
            lines.append(f"  diff({yaw_est_col} - {angz_col}) bias window: circ_mean={cm:+.3f}deg  std={s['std']:.3f}deg  p95|x|={s['p95']:.3f}")

            if auto_yaw_offset:
                cand = [0.0, 90.0, -90.0, 180.0, -180.0]
                best_off, best_rms = _best_yaw_offset_deg(diff[bias_mask], cand)
                # note: residual after applying best offset
                resid = _wrap_deg_180(diff[bias_mask] - best_off)
                s2 = _stats(resid)
                lines.append(f"  [SUGGEST] best fixed offset among {cand} is {best_off:+.1f} deg (resid_rms={best_rms:.3f}deg, resid_std={s2['std']:.3f}deg)")
                if abs(best_off) in (90.0, 180.0) and best_rms < 5.0:
                    lines.append("            This strongly indicates a frame/axis yaw semantic mismatch (e.g., RFU->FRD swap).")
                    lines.append("            Try yaw_offset_rad = deg2rad(best_off) in preprocess, then re-run ESKF and check DVL NIS.")
        else:
            lines.append("  (AngZ_deg missing; cannot compare with device yaw)")
    else:
        # alternatively compare yaw_nav_rad vs yaw_device_rad if exported in rad
        if yaw_nav_col is not None and yaw_dev_rad_col is not None:
            yaw_nav = df[yaw_nav_col].to_numpy(dtype=float)
            yaw_dev = df[yaw_dev_rad_col].to_numpy(dtype=float)
            diff_rad = _wrap_rad_pi(yaw_nav - yaw_dev)
            diff_deg = np.rad2deg(diff_rad)
            s = _stats(diff_deg[bias_mask])
            cm = _circle_mean_deg(diff_deg[bias_mask])
            lines.append(f"  diff({yaw_nav_col} - {yaw_dev_rad_col}) bias window: circ_mean={cm:+.3f}deg  std={s['std']:.3f}deg p95|x|={s['p95']:.3f}")
            if auto_yaw_offset:
                cand = [0.0, 90.0, -90.0, 180.0, -180.0]
                best_off, best_rms = _best_yaw_offset_deg(diff_deg[bias_mask], cand)
                resid = _wrap_deg_180(diff_deg[bias_mask] - best_off)
                s2 = _stats(resid)
                lines.append(f"  [SUGGEST] best fixed offset among {cand} is {best_off:+.1f} deg (resid_rms={best_rms:.3f}deg, resid_std={s2['std']:.3f}deg)")
        else:
            lines.append("  (missing yaw series; cannot diagnose yaw drift/offset)")
    lines.append("")

    # ------------------------------------------------------------
    # 5) Magnitude check: residual linear acc -> displacement inflation
    # ------------------------------------------------------------
    lines.append("== 5) Magnitude check: residual linear acceleration -> displacement inflation ==")
    if acc_lin_cols and len(acc_lin_cols) == 3:
        mu = np.array([float(np.nanmean(df[c].to_numpy(dtype=float)[bias_mask])) for c in acc_lin_cols], dtype=float)
        s_est = 0.5 * mu * (dur ** 2)
        lines.append(f"  mean(Acc_lin) in bias window [m/s^2] = {mu}")
        lines.append(f"  0.5*a*T^2 over T={dur:.1f}s -> {s_est} m (axis-wise)")
        lines.append("  Note: if this is small but 2D drift is huge, culprit is likely yaw/gyro/velocity-frame mismatch (not DC acc).")
    else:
        lines.append("  (missing Acc*_mps2)")
    lines.append("")

    # ------------------------------------------------------------
    # 6) Risk summary & next actions
    # ------------------------------------------------------------
    lines.append("== 6) Risk summary / recommended next actions ==")
    if not gyro_in_cols:
        lines.append("  [HIGH] Missing Gyro*_in_rad_s. Ensure imu_processing exports gyro_in and cli_proc writes it.")
    else:
        lines.append("  [OK] Gyro*_in_rad_s present; use it for ESKF propagation (do NOT use gyro_out).")

    if r_sf is not None:
        r_b = r_sf[bias_mask, :]
        rms_all = float(np.sqrt(np.nanmean(r_b ** 2)))
        if np.isfinite(rms_all) and rms_all > 0.5:
            lines.append(f"  [WARN] specific-force residual RMS={rms_all:.3f} m/s^2 is large for a static window. Verify your bias window is truly static.")
        else:
            lines.append("  [OK] specific-force consistency looks reasonable (static window).")

    if yaw_est_col is not None and angz_col is not None and auto_yaw_offset:
        # re-evaluate best offset quickly for summary
        diff = _wrap_deg_180(df[yaw_est_col].to_numpy(dtype=float) - df[angz_col].to_numpy(dtype=float))
        best_off, best_rms = _best_yaw_offset_deg(diff[bias_mask], [0.0, 90.0, -90.0, 180.0, -180.0])
        if np.isfinite(best_off) and abs(best_off) >= 89.0 and best_rms < 5.0:
            lines.append(f"  [HIGH] Detected near-constant yaw offset ~ {best_off:+.1f} deg (resid_rms={best_rms:.2f}deg).")
            lines.append("        This will rotate horizontal velocity/acc directions and can make DVL updates ineffective.")
            lines.append("        Action: add yaw_offset_rad=deg2rad(best_off) in preprocess, re-run ESKF, compare DVL NIS distribution.")
    lines.append("")

    # save report
    report_path = out_dir / f"{imu_csv.stem}_diag_report.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[IMU-DIAG] report saved: {report_path}")

    # plots
    if make_plots:
        run_out = _ensure_dir(out_dir / imu_csv.stem)

        # 1) linear acceleration
        _save_plot_series(
            t, df,
            ["AccX_mps2", "AccY_mps2", "AccZ_mps2"],
            run_out / "01_acc_linear.png",
            "Linear Acc (m/s^2) [body FRD]",
            span=span_bias,
        )

        # 2) gyro_in vs gyro_out (if present)
        if gyro_in_cols:
            _save_plot_series(
                t, df, gyro_in_cols,
                run_out / "02_gyro_in.png",
                "Gyro IN (rad/s) [for ESKF propagation]",
                span=span_bias,
            )
        if gyro_out_cols:
            _save_plot_series(
                t, df, gyro_out_cols,
                run_out / "03_gyro_out.png",
                "Gyro OUT (rad/s) [thresholded; for plots only]",
                span=span_bias,
            )
        elif gyro_legacy_cols:
            _save_plot_series(
                t, df, gyro_legacy_cols,
                run_out / "03_gyro_legacy.png",
                "Gyro legacy (rad/s) [check if thresholded!]",
                span=span_bias,
            )

        # 3) specific-force residual
        if r_sf is not None:
            # export residual columns to a temp df for plotting (avoid mutating original)
            tmp = pd.DataFrame({"t_s": t})
            tmp["r_sf_x"] = r_sf[:, 0]
            tmp["r_sf_y"] = r_sf[:, 1]
            tmp["r_sf_z"] = r_sf[:, 2]
            _save_plot_series(
                t, tmp, ["r_sf_x", "r_sf_y", "r_sf_z"],
                run_out / "04_specific_force_resid.png",
                "Specific-force residual: AccRaw + G - BiasAcc (m/s^2) [should ~0 in static window]",
                span=span_bias,
            )
            _save_plot_hist(
                r_sf[bias_mask, :].reshape(-1),
                run_out / "04b_specific_force_resid_hist.png",
                "Specific-force residual histogram (bias window)",
                "m/s^2",
            )

        # 4) yaw comparison (deg)
        yaw_cols = []
        if "YawEst_unwrapped_deg" in df.columns: yaw_cols.append("YawEst_unwrapped_deg")
        if "YawEst_deg" in df.columns: yaw_cols.append("YawEst_deg")
        if "YawDev_deg" in df.columns: yaw_cols.append("YawDev_deg")
        if "AngZ_deg" in df.columns: yaw_cols.append("AngZ_deg")
        if yaw_cols:
            _save_plot_series(
                t, df, yaw_cols,
                run_out / "05_yaw_compare.png",
                "Yaw series comparison (deg)",
                span=span_bias,
            )

        # 5) bias terms
        bt_cols = []
        bt_cols += bias_acc_cols
        bt_cols += bias_gyro_cols
        if bt_cols:
            _save_plot_series(
                t, df, bt_cols,
                run_out / "06_bias_terms.png",
                "Bias terms (exported)",
                span=span_bias,
            )

        print(f"[IMU-DIAG] plots saved under: {run_out}")

    return 0


# =============================================================================
# CLI
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="imu-diag-demo", description="IMU processed CSV diagnostic (engineering)")
    p.add_argument("--imu-csv", required=True, type=str, help="Path to <run_id>_imu_filtered.csv")
    p.add_argument("--out-dir", default="out/diag_imu", type=str, help="Directory to save report/plots")
    p.add_argument("--bias-duration-s", default=20.0, type=float, help="Bias window duration (s)")
    p.add_argument("--no-plots", action="store_true", help="Disable plots (only txt report)")
    p.add_argument("--no-auto-yaw-offset", action="store_true", help="Disable auto yaw offset suggestion")
    return p

def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return analyze_imu_csv(
        imu_csv=Path(args.imu_csv),
        out_dir=Path(args.out_dir),
        bias_duration_s=float(args.bias_duration_s),
        make_plots=(not bool(args.no_plots)),
        auto_yaw_offset=(not bool(args.no_auto_yaw_offset)),
    )

if __name__ == "__main__":
    raise SystemExit(main())
