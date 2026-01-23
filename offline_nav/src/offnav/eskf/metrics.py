# offline_nav/src/offnav/eskf/metrics.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _safe_num(a: Any) -> np.ndarray:
    return pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)


def _finite(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return a[np.isfinite(a)]


def _rmse(x: np.ndarray) -> float:
    x = _finite(x)
    if x.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(x * x)))


def _p(x: np.ndarray, q: float) -> float:
    x = _finite(x)
    if x.size == 0:
        return float("nan")
    return float(np.percentile(x, q))


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if np.sum(m) < 5:
        return float("nan")
    aa = a[m] - np.mean(a[m])
    bb = b[m] - np.mean(b[m])
    denom = float(np.sqrt(np.sum(aa * aa) * np.sum(bb * bb)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(aa * bb) / denom)


@dataclass
class MetricsConfig:
    """
    指标口径配置。建议你固定口径，这样不同实验/不同参数可以横向对比。
    """
    speed_bin_edges: Tuple[float, ...] = (0.0, 0.02, 0.05, 0.10, 0.20, 0.50, 2.0)
    use_only_used_rows: bool = True
    kind_filter: Optional[str] = "BI"  # 默认只看 BI 更新（你 2D 的主观测）
    min_rows: int = 20


def load_focus_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def compute_focus_metrics(df: pd.DataFrame, cfg: MetricsConfig = MetricsConfig()) -> Dict[str, Any]:
    """
    输入：FocusMonitor CSV（或同结构 DataFrame）
    输出：可序列化 dict（你可以再落盘成 json/yaml，或打印一行摘要）
    """
    out: Dict[str, Any] = {
        "empty": True,
        "n_rows": 0,
        "n_used": 0,
        "kind": cfg.kind_filter,
    }
    if df is None or df.empty:
        out["issues"] = ["no_data"]
        return out

    d = df.copy()
    out["n_rows"] = int(len(d))

    # filter by kind
    if cfg.kind_filter is not None and "kind" in d.columns:
        d = d[d["kind"].astype(str) == str(cfg.kind_filter)]

    # filter used
    if cfg.use_only_used_rows and "used" in d.columns:
        used = _safe_num(d["used"])
        m = np.isfinite(used) & (used > 0.5)
        d = d[m]
    out["n_used"] = int(len(d))

    if len(d) < cfg.min_rows:
        out["empty"] = True
        out["issues"] = [f"too_few_rows<{cfg.min_rows}"]
        return out

    out["empty"] = False
    issues = []

    # core arrays
    verr_h = _safe_num(d["verr_h"]) if "verr_h" in d.columns else np.array([], dtype=float)
    ratio = _safe_num(d["ratio_pre_over_meas"]) if "ratio_pre_over_meas" in d.columns else np.array([], dtype=float)
    nis = _safe_num(d["nis"]) if "nis" in d.columns else np.array([], dtype=float)

    speed_meas_h = _safe_num(d["speed_meas_h"]) if "speed_meas_h" in d.columns else np.array([], dtype=float)
    speed_pre_h = _safe_num(d["speed_pre_h"]) if "speed_pre_h" in d.columns else np.array([], dtype=float)

    # headline metrics
    out["verr_h_rmse"] = _rmse(verr_h)
    out["verr_h_p95"] = _p(verr_h, 95)
    out["ratio_p50"] = _p(ratio, 50)
    out["ratio_p95"] = _p(ratio, 95)
    out["nis_mean"] = float(np.mean(_finite(nis))) if _finite(nis).size > 0 else float("nan")
    out["nis_p95"] = _p(nis, 95)

    # correlations (sanity)
    out["corr_speed_pre_vs_meas"] = _corr(speed_pre_h, speed_meas_h)

    # trigger ratio
    if "triggered" in d.columns:
        trig = _safe_num(d["triggered"])
        trig_f = trig[np.isfinite(trig)]
        out["trigger_ratio"] = float(np.mean(trig_f > 0.5)) if trig_f.size > 0 else float("nan")

    # per-speed-bin summary for verr_h
    bins = np.asarray(cfg.speed_bin_edges, dtype=float)
    bin_rows = []
    if speed_meas_h.size == len(d) and verr_h.size == len(d):
        m = np.isfinite(speed_meas_h) & np.isfinite(verr_h)
        for i in range(len(bins) - 1):
            lo, hi = float(bins[i]), float(bins[i + 1])
            sel = m & (speed_meas_h >= lo) & (speed_meas_h < hi)
            arr = verr_h[sel]
            if arr.size == 0:
                continue
            bin_rows.append(
                {
                    "bin_lo": lo,
                    "bin_hi": hi,
                    "n": int(arr.size),
                    "verr_h_rmse": _rmse(arr),
                    "verr_h_p95": _p(arr, 95),
                }
            )
    out["verr_h_by_speed_bins"] = bin_rows

    # heuristic issues
    if np.isfinite(out["ratio_p95"]) and out["ratio_p95"] > 10.0:
        issues.append("ratio_p95_too_large_semantic_or_units_problem_suspected")
    if np.isfinite(out["corr_speed_pre_vs_meas"]) and out["corr_speed_pre_vs_meas"] < 0.2:
        issues.append("speed_pre_vs_meas_correlation_low_possible_frame_or_pipeline_issue")
    if np.isfinite(out["verr_h_p95"]) and out["verr_h_p95"] > 0.5:
        issues.append("horizontal_velocity_error_large_need_tuning_or_model_fix")
    if np.isfinite(out["nis_p95"]) and out["nis_p95"] > 200.0:
        issues.append("nis_large_systematic_inconsistency_or_R_too_small_or_outliers")

    out["issues"] = issues
    return out


def metrics_to_flat_rows(metrics: Dict[str, Any]) -> pd.DataFrame:
    """
    把 summary dict 摊平成 1 行 DataFrame，方便你写到“实验对比表”里。
    """
    row: Dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, (dict, list)):
            continue
        row[k] = v
    return pd.DataFrame([row])
