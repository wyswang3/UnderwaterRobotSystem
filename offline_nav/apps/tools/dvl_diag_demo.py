#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apps/tools/dvl_diag_demo.py

DVL 数据质量评估 Demo（仿照 imu_diag_demo.py 输出风格）

输入（推荐使用 cli_proc 产物）：
  out/proc/<run_id>/
    <run_id>_dvl_stream_all.csv
    <run_id>_dvl_filtered_all.csv
    <run_id>_dvl_filtered_BI_all.csv
    <run_id>_dvl_filtered_BE_all.csv
    <run_id>_dvl_filtered_BI.csv
    <run_id>_dvl_filtered_BE.csv

核心输出：
  - mixed stream 的 Src 组成（TS/BS/BD/SA/+0/BI/BE...）
  - 速度帧 BI/BE 的样本数、时间范围、门控通过率、原因分布
  - 静态窗口（前 static_s 秒）内：速度/分量均值、方差、p95、max
  - 跳变统计（Δv axis / Δv xy）在全程的 p95/max
  - BE 的 Vu 统计（池测常见异常源）

用法示例：
  python -m apps.tools.dvl_diag_demo \
    --proc-dir ../out/proc/2026-01-10_pooltest01 \
    --run-id 2026-01-10_pooltest01 \
    --static-s 20 \
    --static-speed-eps 0.02
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd


# =============================================================================
# Utilities
# =============================================================================

_TIME_COL_PRIORITY = ("EstS", "MonoS", "EstNS", "MonoNS")


def _norm_src(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def _pick_time_s(df: pd.DataFrame) -> np.ndarray:
    """
    选择时间轴（秒），优先 EstS/MonoS，其次 NS*1e-9。
    """
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError(f"No time column found. Need one of: {_TIME_COL_PRIORITY}")


def _safe_read_csv(p: Path) -> pd.DataFrame:
    """
    规避 mixed-type DtypeWarning：low_memory=False，且对常见混合列做安全兜底。
    """
    df = pd.read_csv(p, low_memory=False)

    # 常见混合列：ValidFlag（可能是字符串/空/数值）
    if "ValidFlag" in df.columns:
        df["ValidFlag"] = df["ValidFlag"].astype(str)

    # 常见布尔列：Valid / IsWaterMass / SpeedOk / GateOk
    for c in ["Valid", "IsWaterMass", "SpeedOk", "GateOk"]:
        if c in df.columns:
            # 允许 True/False/0/1/"True"/"False"/空
            def _to_bool(x):
                if pd.isna(x):
                    return False
                if isinstance(x, bool):
                    return x
                if isinstance(x, (int, float)):
                    return bool(int(x))
                s = str(x).strip().lower()
                return s in ("1", "true", "yes", "y", "on")
            df[c] = df[c].map(_to_bool)

    # Src 统一大写
    if "Src" in df.columns:
        df["Src"] = _norm_src(df["Src"])

    return df


def _finite(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return x[np.isfinite(x)]


def _stats_1d(x: np.ndarray) -> Dict[str, float]:
    x = _finite(x)
    if x.size == 0:
        return {"mean": np.nan, "std": np.nan, "p95_abs": np.nan, "max_abs": np.nan}
    xa = np.abs(x)
    return {
        "mean": float(np.mean(x)),
        "std": float(np.std(x)),
        "p95_abs": float(np.percentile(xa, 95)),
        "max_abs": float(np.max(xa)),
    }


def _fmt_stats(name: str, st: Dict[str, float], unit: str = "") -> str:
    return (
        f"  {name:<14s} mean={st['mean']:+.4f}  std={st['std']:.4f}  "
        f"p95|x|={st['p95_abs']:.4f}  max|x|={st['max_abs']:.4f}"
        + (f" {unit}" if unit else "")
    )


def _diff_stats(v: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    v: (N,3)
    return:
      dv_axis = max(|dv_i|) per sample
      dv_xy   = sqrt(dv_x^2 + dv_y^2) per sample
    """
    v = np.asarray(v, dtype=float)
    if v.ndim != 2 or v.shape[1] != 3 or v.shape[0] < 2:
        return np.array([], dtype=float), np.array([], dtype=float)
    dv = np.zeros_like(v)
    dv[1:, :] = v[1:, :] - v[:-1, :]
    dv_axis = np.max(np.abs(dv), axis=1)
    dv_xy = np.sqrt(dv[:, 0] * dv[:, 0] + dv[:, 1] * dv[:, 1])
    return dv_axis, dv_xy


# =============================================================================
# Diagnostics
# =============================================================================

@dataclass
class DvlDiagConfig:
    static_s: float = 20.0
    static_speed_eps: float = 0.02  # m/s，判定“静止窗口内速度应接近 0”的参考
    speed_col: str = "Speed_body(m_s)"  # 兼容历史；你们现在 df_all 里 speed 实际等价 speed_mag
    use_gate_ok_only: bool = False      # 若 True，静态统计只看 GateOk=True


def _print_header(file: Path, t: np.ndarray) -> None:
    if t.size == 0:
        print(f"[DVL-DIAG] file={file}\n  (empty time axis)\n")
        return
    t0, t1 = float(np.nanmin(t)), float(np.nanmax(t))
    dur = t1 - t0
    print(f"[DVL-DIAG] file={file}")
    print(f"  t=[{t0:.3f}, {t1:.3f}]  duration={dur:.2f}s  N={len(t)}\n")


def _src_counts(df: pd.DataFrame) -> Dict[str, int]:
    if df.empty or "Src" not in df.columns:
        return {}
    vc = df["Src"].astype(str).value_counts(dropna=False)
    return {str(k): int(v) for k, v in vc.items()}


def _gate_summary(df_vel: pd.DataFrame) -> None:
    if df_vel.empty:
        print("== Gate summary ==\n  (empty)\n")
        return
    if "GateOk" not in df_vel.columns:
        print("== Gate summary ==\n  GateOk column missing.\n")
        return

    n = len(df_vel)
    ok = df_vel["GateOk"].astype(bool).to_numpy()
    n_ok = int(np.sum(ok))
    print("== Gate summary ==")
    print(f"  GateOk: {n_ok}/{n} ({(n_ok/n*100.0):.1f}%)")

    if "GateReason" in df_vel.columns:
        reasons = df_vel.loc[~df_vel["GateOk"].astype(bool), "GateReason"].astype(str)
        if len(reasons) > 0:
            vc = reasons.value_counts()
            top = vc.head(8)
            print("  Top GateReason (failed):")
            for k, v in top.items():
                print(f"    - {k}: {int(v)}")
    print("")


def _static_window_mask(t: np.ndarray, static_s: float) -> np.ndarray:
    if t.size == 0:
        return np.zeros((0,), dtype=bool)
    t0 = float(np.nanmin(t))
    return (t - t0) <= float(static_s)


def _diag_velocity_block(
    df: pd.DataFrame,
    label: str,
    cfg: DvlDiagConfig,
    kind: str,  # "BI" or "BE"
) -> None:
    """
    打印某个速度源的诊断（BI 用 body 三轴，BE 用 ENU 三轴）。
    """
    if df.empty:
        print(f"== {label} ==\n  (empty)\n")
        return

    # 选择时间轴
    t = _pick_time_s(df)
    t0, t1 = float(np.nanmin(t)), float(np.nanmax(t))
    print(f"== {label} ==")
    print(f"  t=[{t0:.3f}, {t1:.3f}]  N={len(df)}")

    # 可选：只看 GateOk=True
    df_use = df
    if cfg.use_gate_ok_only and "GateOk" in df.columns:
        df_use = df[df["GateOk"].astype(bool)].copy()

    # 静态窗口
    t_use = _pick_time_s(df_use) if len(df_use) > 0 else np.array([], dtype=float)
    m_static = _static_window_mask(t_use, cfg.static_s)
    df_static = df_use.iloc[np.nonzero(m_static)[0]].copy() if len(df_use) > 0 else df_use

    # speed
    if cfg.speed_col in df_use.columns:
        sp = df_use[cfg.speed_col].to_numpy(dtype=float)
        sp_st = _stats_1d(sp)
        print(_fmt_stats(f"Speed({cfg.speed_col})", sp_st, "m/s"))
    else:
        print(f"  Speed col missing: {cfg.speed_col}")

    # 三轴向量
    if kind == "BI":
        cols = ["Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"]
        names = ["Vx_body", "Vy_body", "Vz_body"]
    else:
        cols = ["Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"]
        names = ["Ve_enu", "Vn_enu", "Vu_enu"]

    if all(c in df_use.columns for c in cols):
        v = np.stack([df_use[c].to_numpy(dtype=float) for c in cols], axis=1)

        # 全程三轴统计
        for i in range(3):
            st = _stats_1d(v[:, i])
            print(_fmt_stats(names[i], st, "m/s"))

        # Δv 统计（全程）
        dv_axis, dv_xy = _diff_stats(v)
        if dv_axis.size > 0:
            print(f"  dv_axis: p95={float(np.percentile(dv_axis,95)):.4f}  max={float(np.max(dv_axis)):.4f} m/s")
            print(f"  dv_xy  : p95={float(np.percentile(dv_xy,95)):.4f}  max={float(np.max(dv_xy)):.4f} m/s")

        # 静态窗口统计（更关键：是否有“静止漂移/噪声”）
        if len(df_static) > 5 and all(c in df_static.columns for c in cols):
            v0 = np.stack([df_static[c].to_numpy(dtype=float) for c in cols], axis=1)
            print(f"\n  -- Static window: first {cfg.static_s:.1f}s, samples={len(df_static)} --")
            for i in range(3):
                st = _stats_1d(v0[:, i])
                print(_fmt_stats(names[i], st, "m/s"))

            # 静态速度是否过大（工程提示）
            if cfg.speed_col in df_static.columns:
                sp0 = df_static[cfg.speed_col].to_numpy(dtype=float)
                p95 = float(np.percentile(np.abs(_finite(sp0)), 95)) if _finite(sp0).size > 0 else np.nan
                if np.isfinite(p95) and p95 > cfg.static_speed_eps:
                    print(f"  [WARN] static p95|speed|={p95:.4f} > eps={cfg.static_speed_eps:.4f} m/s")

    else:
        missing = [c for c in cols if c not in df_use.columns]
        print(f"  Missing velocity cols: {missing}")

    # BE 特有：Vu 范围（池测常见问题）
    if kind == "BE" and "Vu_enu(m_s)" in df_use.columns:
        vu = df_use["Vu_enu(m_s)"].to_numpy(dtype=float)
        st = _stats_1d(vu)
        print("\n  -- BE Vu focus --")
        print(_fmt_stats("Vu_enu", st, "m/s"))

    print("")


def run_dvl_diag(proc_dir: Path, run_id: str, cfg: DvlDiagConfig) -> int:
    proc_dir = Path(proc_dir)

    p_stream = proc_dir / f"{run_id}_dvl_stream_all.csv"
    p_all = proc_dir / f"{run_id}_dvl_filtered_all.csv"
    p_bi_all = proc_dir / f"{run_id}_dvl_filtered_BI_all.csv"
    p_be_all = proc_dir / f"{run_id}_dvl_filtered_BE_all.csv"
    p_bi = proc_dir / f"{run_id}_dvl_filtered_BI.csv"
    p_be = proc_dir / f"{run_id}_dvl_filtered_BE.csv"

    # 必要文件检查（最少要有 filtered_all）
    if not p_all.exists():
        raise FileNotFoundError(f"DVL filtered_all not found: {p_all}")

    df_all = _safe_read_csv(p_all)
    t_all = _pick_time_s(df_all)
    _print_header(p_all, t_all)

    # stream（可选）
    if p_stream.exists():
        df_stream = _safe_read_csv(p_stream)
        t_stream = _pick_time_s(df_stream) if len(df_stream) > 0 else np.array([], dtype=float)
        print("== 0) Stream overview (mixed frames) ==")
        if len(df_stream) > 0:
            print(f"  stream_rows={len(df_stream)}  time_cols={[c for c in _TIME_COL_PRIORITY if c in df_stream.columns]}")
            sc = _src_counts(df_stream)
            if sc:
                top = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)[:12]
                print("  Src counts (top): " + ", ".join([f"{k}:{v}" for k, v in top]))
        print("")
    else:
        df_stream = None

    # 速度帧汇总（df_all）
    print("== 1) Velocity frames overview (BI+BE) ==")
    sc_all = _src_counts(df_all)
    if sc_all:
        print("  Src counts: " + ", ".join([f"{k}:{v}" for k, v in sorted(sc_all.items())]))
    _gate_summary(df_all)

    # 读取 BI/BE（gated）
    if p_bi.exists():
        df_bi = _safe_read_csv(p_bi)
    else:
        df_bi = df_all[df_all.get("Src", "").astype(str).str.upper() == "BI"].copy()

    if p_be.exists():
        df_be = _safe_read_csv(p_be)
    else:
        df_be = df_all[df_all.get("Src", "").astype(str).str.upper() == "BE"].copy()

    # 读取 BI/BE（all，ungated）
    df_bi_all = _safe_read_csv(p_bi_all) if p_bi_all.exists() else df_bi.copy()
    df_be_all = _safe_read_csv(p_be_all) if p_be_all.exists() else df_be.copy()

    # 诊断：先看全量（含静止段）→ 再看 gated（下游输入）
    print("== 2) BI/BE diagnostics (ALL, ungated; includes static segment) ==")
    _diag_velocity_block(df_bi_all, "BI_all (ungated)", cfg, kind="BI")
    _diag_velocity_block(df_be_all, "BE_all (ungated)", cfg, kind="BE")

    print("== 3) BI/BE diagnostics (GATED; downstream input) ==")
    _diag_velocity_block(df_bi, "BI (GateOk=True)", cfg, kind="BI")
    _diag_velocity_block(df_be, "BE (GateOk=True)", cfg, kind="BE")

    # 工程建议（基于简单规则）
    rec: List[str] = []
    if "GateOk" in df_all.columns:
        ok_rate = float(np.mean(df_all["GateOk"].astype(bool).to_numpy())) if len(df_all) > 0 else 0.0
        if ok_rate < 0.6:
            rec.append(f"GateOk 通过率偏低（{ok_rate*100:.1f}%），建议检查 dv 门控阈值 / 原始 DVL 串口解析稳定性。")

    if cfg.speed_col in df_be_all.columns:
        sp = _finite(df_be_all[cfg.speed_col].to_numpy(dtype=float))
        if sp.size > 0 and float(np.percentile(sp, 99)) > 1.0:
            rec.append("BE 速度存在较大尖峰（p99>1m/s 级别），池测通常不合理；建议加强 BE 的 dv/vu 门控或仅在水体跟踪稳定时使用。")

    if rec:
        print("== 4) Recommendations ==")
        for r in rec:
            print(f"  - {r}")
        print("")

    return 0


# =============================================================================
# CLI
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvl-diag-demo", description="DVL data quality diagnostics demo")
    p.add_argument("--proc-dir", type=str, required=True, help="Processed run directory: out/proc/<run_id>/")
    p.add_argument("--run-id", type=str, required=True, help="run_id prefix of processed CSV files")
    p.add_argument("--static-s", type=float, default=20.0, help="Static window length in seconds (default 20)")
    p.add_argument("--static-speed-eps", type=float, default=0.02, help="Warn if static p95|speed| > eps (m/s)")
    p.add_argument("--speed-col", type=str, default="Speed_body(m_s)", help="Speed column name to use (default Speed_body(m_s))")
    p.add_argument("--gate-only", action="store_true", help="If set, static stats use GateOk=True only")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = DvlDiagConfig(
        static_s=float(args.static_s),
        static_speed_eps=float(args.static_speed_eps),
        speed_col=str(args.speed_col),
        use_gate_ok_only=bool(args.gate_only),
    )
    return run_dvl_diag(Path(args.proc_dir), str(args.run_id), cfg)


if __name__ == "__main__":
    raise SystemExit(main())
