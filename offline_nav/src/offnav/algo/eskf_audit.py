from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Dict, Any, List

import numpy as np
import pandas as pd


# =============================================================================
# Time alignment (keep interface)
# =============================================================================

@dataclass
class TimeSpan:
    name: str
    t0: float
    t1: float
    n: int


def print_time_alignment(
    imu_t: np.ndarray,
    dvl_be_t: np.ndarray,
    dvl_bi_t: Optional[np.ndarray] = None,
) -> None:
    imu_t = np.asarray(imu_t, dtype=float)
    dvl_be_t = np.asarray(dvl_be_t, dtype=float)

    def _span(name: str, t: np.ndarray) -> TimeSpan:
        t = np.asarray(t, dtype=float)
        t = t[np.isfinite(t)]
        if t.size == 0:
            return TimeSpan(name=name, t0=float("nan"), t1=float("nan"), n=0)
        return TimeSpan(name=name, t0=float(t[0]), t1=float(t[-1]), n=int(t.size))

    s_imu = _span("IMU", imu_t)
    s_be = _span("DVL-BE", dvl_be_t)

    if s_imu.n == 0:
        print("[TIME][IMU] empty")
        return
    if s_be.n == 0:
        print("[TIME][DVL-BE] empty")
        return

    print(f"[TIME][IMU]      t0={s_imu.t0:.6f}  t1={s_imu.t1:.6f}  N={s_imu.n}")
    print(f"[TIME][DVL-BE]   t0={s_be.t0:.6f}  t1={s_be.t1:.6f}  N={s_be.n}")
    # IMPORTANT: this is (BE - IMU), not dt_match_s in audit rows
    print(f"[TIME][IMU vs BE] (BE-IMU) dt0={(s_be.t0 - s_imu.t0):+.6f}  dt1={(s_be.t1 - s_imu.t1):+.6f}")

    if dvl_bi_t is not None:
        dvl_bi_t = np.asarray(dvl_bi_t, dtype=float)
        s_bi = _span("DVL-BI", dvl_bi_t)
        if s_bi.n == 0:
            print("[TIME][DVL-BI] empty")
        else:
            print(f"[TIME][DVL-BI]   t0={s_bi.t0:.6f}  t1={s_bi.t1:.6f}  N={s_bi.n}")
            print(f"[TIME][IMU vs BI] (BI-IMU) dt0={(s_bi.t0 - s_imu.t0):+.6f}  dt1={(s_bi.t1 - s_imu.t1):+.6f}")


# =============================================================================
# Audit dataframe (keep interface)
# =============================================================================

def audit_dataframe(rows: Sequence[Dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


# =============================================================================
# Utilities
# =============================================================================

def _safe_numeric(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)


def _wrap_pm_pi(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return (a + np.pi) % (2.0 * np.pi) - np.pi


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if np.sum(m) < 3:
        return float("nan")
    aa = a[m] - np.mean(a[m])
    bb = b[m] - np.mean(b[m])
    denom = float(np.sqrt(np.sum(aa * aa) * np.sum(bb * bb)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(aa * bb) / denom)


def _ensure_cols(df: pd.DataFrame, cols: Sequence[str]) -> None:
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan


def _pct(arr: np.ndarray, p: float) -> float:
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    return float(np.percentile(arr, p))


# =============================================================================
# Lightweight summary (keep interface, but focus on main signals)
# =============================================================================

def print_audit_summary(df_a: pd.DataFrame) -> None:
    if df_a is None or df_a.empty:
        print("[ESKF][AUDIT] empty")
        return

    # Only the most load-bearing stats
    if "nis" in df_a.columns:
        nis = _safe_numeric(df_a["nis"])
        nis = nis[np.isfinite(nis)]
        if nis.size > 0:
            print(
                f"[ESKF][AUDIT] NIS: mean={float(np.mean(nis)):.3f} "
                f"p95={float(np.percentile(nis, 95)):.3f} "
                f"p99={float(np.percentile(nis, 99)):.3f}"
            )

    if "dt_match_s" in df_a.columns:
        dtm = _safe_numeric(df_a["dt_match_s"])
        dtm = dtm[np.isfinite(dtm)]
        if dtm.size > 0:
            print(
                f"[ESKF][AUDIT] dt_match_s: mean={float(np.mean(dtm)):.6f} "
                f"std={float(np.std(dtm)):.6f} "
                f"max={float(np.max(dtm)):.6f}"
            )

    # If dv is available, show update magnitude (helps judge "over-trusting DVL")
    if all(c in df_a.columns for c in ("dvE", "dvN", "dvU")):
        dv = np.vstack([
            _safe_numeric(df_a["dvE"]),
            _safe_numeric(df_a["dvN"]),
            _safe_numeric(df_a["dvU"]),
        ]).T
        m = np.isfinite(dv).all(axis=1)
        if np.any(m):
            dvn = np.linalg.norm(dv[m], axis=1)
            print(
                f"[ESKF][AUDIT] |dv|: mean={float(np.mean(dvn)):.6f} "
                f"p95={float(np.percentile(dvn, 95)):.6f} "
                f"max={float(np.max(dvn)):.6f}"
            )


# =============================================================================
# Core diagnostics: ONLY main problems
# =============================================================================

def print_frame_consistency_diagnostics(
    df_a: pd.DataFrame,
    speed_min_mps: float = 0.05,
    topk: int = 10,
) -> None:
    """
    Focused diagnosis:
      1) v_pre vs v_meas semantic/scale sanity (MOST IMPORTANT)
      2) horizontal frame hints (EN swap, 180 flip)
      3) vertical sign hint (Vu up/down)
      4) time-lag hint (corr(dt_match_s, nis))
    """
    if df_a is None or df_a.empty:
        print("[ESKF][FRAME] empty")
        return

    need = [
        "vE", "vN", "speed_h",
        "vE_pre", "vN_pre",
        "dt_match_s", "nis",
        "t_imu_s", "t_dvl_s",
    ]
    _ensure_cols(df_a, need)

    vE = _safe_numeric(df_a["vE"])
    vN = _safe_numeric(df_a["vN"])
    sp = _safe_numeric(df_a["speed_h"])
    vE_pre = _safe_numeric(df_a["vE_pre"])
    vN_pre = _safe_numeric(df_a["vN_pre"])

    m = (
        np.isfinite(vE) & np.isfinite(vN)
        & np.isfinite(vE_pre) & np.isfinite(vN_pre)
        & np.isfinite(sp)
        & (sp >= float(speed_min_mps))
    )

    if int(np.sum(m)) < 20:
        print(f"[ESKF][FRAME] insufficient valid rows: n={int(np.sum(m))} (need >=20).")
        return

    # ---------- 1) Scale / semantic sanity (primary) ----------
    sp_meas = np.sqrt(vE[m] ** 2 + vN[m] ** 2)
    sp_pre = np.sqrt(vE_pre[m] ** 2 + vN_pre[m] ** 2)

    ratio = sp_pre / np.maximum(sp_meas, 1e-9)
    p50 = _pct(ratio, 50)
    p95 = _pct(ratio, 95)
    p99 = _pct(ratio, 99)

    print("[ESKF][FRAME] ===== primary sanity =====")
    print(f"[ESKF][FRAME] |v_pre| p95={_pct(sp_pre,95):.3f}  p99={_pct(sp_pre,99):.3f}  (m/s)")
    print(f"[ESKF][FRAME] |v_pre|/|v_meas| p50={p50:.3f}  p95={p95:.3f}  p99={p99:.3f}")

    if np.isfinite(p50) and p50 > 3.0:
        print("[ESKF][FRAME][HINT] 预测速度量级显著大于测量：优先检查 vE_pre/vN_pre 的生成语义与单位，"
              "以及 dt / 重力扣除 / 积分链路是否导致速度发散。")
    if np.isfinite(p95) and p95 > 20.0:
        print("[ESKF][FRAME][HINT] 比值 p95 极端偏大：高概率是字段含义/单位错误（不是简单调 R 能解决）。")
    if np.isfinite(_pct(sp_pre, 99)) and _pct(sp_pre, 99) > 5.0:
        print("[ESKF][FRAME][HINT] |v_pre| p99 > 5 m/s：对池试 ROV 通常不合理，疑似预测侧发散或字段写错。")

    # ---------- 2) Horizontal axis/sign hints ----------
    corr_E = _corr(vE_pre[m], vE[m])
    corr_N = _corr(vN_pre[m], vN[m])
    corr_E_to_N = _corr(vE_pre[m], vN[m])
    corr_N_to_E = _corr(vN_pre[m], vE[m])

    print("[ESKF][FRAME] ===== horizontal correlation =====")
    print(f"[ESKF][FRAME] corr(vE_pre, vE)={corr_E:.3f}  corr(vN_pre, vN)={corr_N:.3f}")
    print(f"[ESKF][FRAME] corr(vE_pre, vN)={corr_E_to_N:.3f}  corr(vN_pre, vE)={corr_N_to_E:.3f}")

    if np.isfinite(corr_E_to_N) and np.isfinite(corr_N_to_E) and (corr_E_to_N > 0.8 and corr_N_to_E > 0.8):
        print("[ESKF][FRAME][HINT] 水平 E/N 疑似互换（axis_map 错或旋转矩阵构造错误）。")
    if np.isfinite(corr_E) and np.isfinite(corr_N) and (corr_E < -0.8 and corr_N < -0.8):
        print("[ESKF][FRAME][HINT] v_pre ≈ -v_meas：疑似整体 180° 翻号（坐标系符号约定不一致）。")

    # ---------- 3) Vertical sign hint (optional, only if present) ----------
    if all(c in df_a.columns for c in ("vU", "vU_pre")):
        vU = _safe_numeric(df_a["vU"])
        vU_pre = _safe_numeric(df_a["vU_pre"])
        mU = np.isfinite(vU) & np.isfinite(vU_pre)
        if np.sum(mU) >= 20:
            corr_U = _corr(vU_pre[mU], vU[mU])
            print("[ESKF][FRAME] ===== vertical =====")
            print(f"[ESKF][FRAME] corr(vU_pre, vU)={corr_U:.3f}")
            if np.isfinite(corr_U) and corr_U < -0.5:
                print("[ESKF][FRAME][HINT] 垂向速度预测与观测明显反向：疑似 Vu Up/Down 符号翻转（ENU 约定未统一）。")

    # ---------- 4) Time-lag hint ----------
    dtm = _safe_numeric(df_a["dt_match_s"])
    nis = _safe_numeric(df_a["nis"])
    c_dt_nis = _corr(dtm[m], nis[m]) if ("nis" in df_a.columns) else float("nan")
    print("[ESKF][FRAME] ===== time-lag =====")
    print(f"[ESKF][FRAME] corr(dt_match_s, nis)={c_dt_nis:.3f}")
    if np.isfinite(c_dt_nis) and abs(c_dt_nis) > 0.3:
        print("[ESKF][FRAME][HINT] NIS 与 dt_match_s 相关性较强：疑似时间对齐/匹配窗口存在系统性问题。")

    # ---------- Top-K NIS for manual inspect (kept, but minimal) ----------
    if "nis" in df_a.columns:
        df2 = df_a.copy()
        df2["nis_num"] = pd.to_numeric(df2["nis"], errors="coerce")
        df2 = df2[np.isfinite(df2["nis_num"])]
        if len(df2) > 0:
            show_cols = [c for c in ["t_imu_s","t_dvl_s","dt_match_s","vE","vN","vE_pre","vN_pre","speed_h","nis"] if c in df2.columns]
            top = df2.sort_values("nis_num", ascending=False).head(int(max(1, topk)))
            print("[ESKF][FRAME] ===== top-NIS rows =====")
            for i, r in enumerate(top[show_cols].to_dict(orient="records")):
                print(f"[ESKF][FRAME] top{i+1}: {r}")


def print_audit_deep_diagnostics(
    df_a: pd.DataFrame,
    robust_expected: bool,
    gate_possible_expected: bool,
    speed_bins: Optional[Sequence[float]] = None,
) -> None:
    """
    Keep the function name/signature for compatibility, but focus on:
      - Missing audit fields (gate/robust/thr)
      - NIS too large/small quick hint
      - Dominant component hint if residual fields exist
      - Call frame_consistency_diagnostics at end
    """
    if df_a is None or df_a.empty:
        print("[ESKF][AUDIT-DEEP] empty")
        return

    # Ensure critical columns exist
    for c in ("nis", "nis_thr", "gate_possible", "robust_enabled", "robust_inflate", "nis2", "nis_gate_drop"):
        if c not in df_a.columns:
            df_a[c] = np.nan

    nis = _safe_numeric(df_a["nis"])
    thr = _safe_numeric(df_a["nis_thr"])
    thr_median = float(np.nanmedian(thr)) if np.isfinite(thr).any() else float("nan")

    print("[ESKF][AUDIT-DEEP] ===== pipeline fields =====")
    print(f"[ESKF][AUDIT-DEEP] rows={len(df_a)}  nis_thr(median)={thr_median:.6g}")

    # Hard warnings for missing fields
    if not np.isfinite(thr).any():
        print("[ESKF][AUDIT-DEEP][WARN] nis_thr 全缺失：当前无法判断 NIS 门控是否生效。请在 engine 写入 row['nis_thr']。")

    gp = df_a["gate_possible"]
    re = df_a["robust_enabled"]
    if gp.isna().all():
        print("[ESKF][AUDIT-DEEP][WARN] gate_possible 全缺失：无法判断 gate 是否具备条件/是否启用。请写 row['gate_possible']。")
    if re.isna().all():
        print("[ESKF][AUDIT-DEEP][WARN] robust_enabled 全缺失：无法判断 robust 是否启用。请写 row['robust_enabled'] / row['robust_inflate'] / row['nis2']。")

    # NIS hint (only)
    nis_f = nis[np.isfinite(nis)]
    if nis_f.size > 0:
        mean_nis = float(np.mean(nis_f))
        p95_nis = float(np.percentile(nis_f, 95))
        dof = 3.0
        print("[ESKF][AUDIT-DEEP] ===== NIS quick check =====")
        print(f"[ESKF][AUDIT-DEEP] nis: mean={mean_nis:.3f}  p95={p95_nis:.3f}")
        if mean_nis > dof * 2.0:
            print("[ESKF][AUDIT-DEEP][HINT] NIS 均值偏大：DVL 观测噪声 R 可能偏小（权重过大）或存在系统性不一致（更常见）。")
        if p95_nis > dof * 6.0:
            print("[ESKF][AUDIT-DEEP][HINT] NIS p95 很高：存在强离群观测，若 gate/robust 字段缺失请先补齐审计字段再判断策略效果。")

    # Dominant component hint if residual diag exists
    if all(c in df_a.columns for c in ("r0","r1","r2","S0","S1","S2","nis")):
        r0 = _safe_numeric(df_a["r0"]); r1 = _safe_numeric(df_a["r1"]); r2 = _safe_numeric(df_a["r2"])
        S0 = _safe_numeric(df_a["S0"]); S1 = _safe_numeric(df_a["S1"]); S2 = _safe_numeric(df_a["S2"])
        m = np.isfinite(r0)&np.isfinite(r1)&np.isfinite(r2)&np.isfinite(S0)&np.isfinite(S1)&np.isfinite(S2)&np.isfinite(nis)
        if np.sum(m) > 200:
            thr_top = float(np.percentile(nis[m], 99))
            sel = m & (nis >= thr_top)
            if np.any(sel):
                c0 = (r0[sel]**2)/np.maximum(S0[sel],1e-12)
                c1 = (r1[sel]**2)/np.maximum(S1[sel],1e-12)
                c2 = (r2[sel]**2)/np.maximum(S2[sel],1e-12)
                cmean = np.array([float(np.mean(c0)), float(np.mean(c1)), float(np.mean(c2))], dtype=float)
                axis = ["E","N","U"][int(np.argmax(cmean))]
                print("[ESKF][AUDIT-DEEP] ===== residual dominance (top1% NIS) =====")
                print(f"[ESKF][AUDIT-DEEP][HINT] Top1% NIS 主要由 {axis} 分量贡献（mean r^2/S 最大）。优先检查该轴的 sign/axis_map/观测来源(BI/BE)。")

    # Final: frame checks (most actionable)
    print("[ESKF][AUDIT-DEEP] ===== frame/axis sanity =====")
    print_frame_consistency_diagnostics(df_a, speed_min_mps=0.05, topk=10)


# =============================================================================
# High-level orchestrator (keep interface)
# =============================================================================

def run_eskf_audit(
    df_a: pd.DataFrame,
    robust_expected: bool,
    gate_possible_expected: bool,
    speed_min_mps: float = 0.05,
    speed_bins: Optional[Sequence[float]] = None,
    topk: int = 10,
) -> Dict[str, Any]:
    """
    Keeps signature & basic output contract.
    Returns a concise summary dict with only primary issues.
    """
    print_audit_summary(df_a)
    print_audit_deep_diagnostics(
        df_a,
        robust_expected=robust_expected,
        gate_possible_expected=gate_possible_expected,
        speed_bins=speed_bins,
    )

    summary: Dict[str, Any] = {}
    if df_a is None or df_a.empty:
        return {"empty": True, "issues": ["no_data"]}

    issues: List[str] = []
    summary["empty"] = False

    # --- Primary: semantic/scale mismatch ---
    for c in ("vE","vN","vE_pre","vN_pre","speed_h"):
        if c not in df_a.columns:
            df_a[c] = np.nan

    vE = _safe_numeric(df_a["vE"])
    vN = _safe_numeric(df_a["vN"])
    vE_pre = _safe_numeric(df_a["vE_pre"])
    vN_pre = _safe_numeric(df_a["vN_pre"])
    sp = _safe_numeric(df_a["speed_h"])

    m = np.isfinite(vE)&np.isfinite(vN)&np.isfinite(vE_pre)&np.isfinite(vN_pre)&np.isfinite(sp)&(sp >= float(speed_min_mps))
    if np.sum(m) >= 20:
        sp_meas = np.sqrt(vE[m]**2 + vN[m]**2)
        sp_pre = np.sqrt(vE_pre[m]**2 + vN_pre[m]**2)
        ratio = sp_pre / np.maximum(sp_meas, 1e-9)
        p50 = _pct(ratio, 50)
        p95 = _pct(ratio, 95)
        summary["v_ratio_p50"] = p50
        summary["v_ratio_p95"] = p95
        summary["v_pre_p99_mps"] = _pct(sp_pre, 99)

        if np.isfinite(p95) and p95 > 20.0:
            issues.append("semantic_or_unit_mismatch_v_pre_vs_meas")
        elif np.isfinite(p50) and p50 > 3.0:
            issues.append("scale_mismatch_v_pre_gt_meas")

        if np.isfinite(summary["v_pre_p99_mps"]) and summary["v_pre_p99_mps"] > 5.0:
            issues.append("v_pre_physically_unreasonable_maybe_diverged")

        # axis hints
        cee = _corr(vE_pre[m], vE[m])
        cnn = _corr(vN_pre[m], vN[m])
        cen = _corr(vE_pre[m], vN[m])
        cne = _corr(vN_pre[m], vE[m])
        summary["corr_vE_pre_E"] = cee
        summary["corr_vN_pre_N"] = cnn
        summary["corr_vE_pre_N"] = cen
        summary["corr_vN_pre_E"] = cne

        if np.isfinite(cen) and np.isfinite(cne) and (cen > 0.8 and cne > 0.8):
            issues.append("horizontal_axes_swapped_EN")
        if np.isfinite(cee) and np.isfinite(cnn) and (cee < -0.8 and cnn < -0.8):
            issues.append("horizontal_axes_flipped_180deg")

    # --- NIS quick flags (secondary, after semantic) ---
    if "nis" in df_a.columns:
        nis = _safe_numeric(df_a["nis"])
        nis_f = nis[np.isfinite(nis)]
        if nis_f.size > 0:
            summary["nis_mean"] = float(np.mean(nis_f))
            summary["nis_p95"] = float(np.percentile(nis_f, 95))
            dof = 3.0
            if summary["nis_mean"] > dof * 2.0:
                issues.append("nis_too_large_maybe_R_too_small_or_systematic_mismatch")
            if summary["nis_p95"] > dof * 6.0:
                issues.append("nis_p95_very_large_outliers_exist")

    # --- dt vs nis correlation (tertiary) ---
    if "dt_match_s" in df_a.columns and "nis" in df_a.columns:
        dtm = _safe_numeric(df_a["dt_match_s"])
        nis = _safe_numeric(df_a["nis"])
        c = _corr(dtm, nis)
        summary["corr_dt_match_nis"] = c
        if np.isfinite(c) and abs(c) > 0.3:
            issues.append("time_alignment_or_latency_suspected")

    # --- Missing audit fields (very actionable) ---
    if "nis_thr" not in df_a.columns or not np.isfinite(_safe_numeric(df_a["nis_thr"])).any():
        issues.append("audit_missing_nis_thr_gate_unverifiable")
    if "gate_possible" not in df_a.columns or pd.Series(df_a["gate_possible"]).isna().all():
        issues.append("audit_missing_gate_possible")
    if "robust_enabled" not in df_a.columns or pd.Series(df_a["robust_enabled"]).isna().all():
        issues.append("audit_missing_robust_fields")

    summary["issues"] = issues
    return summary
