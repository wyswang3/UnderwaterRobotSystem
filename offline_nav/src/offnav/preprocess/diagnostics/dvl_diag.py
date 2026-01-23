from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import numpy as np
import pandas as pd

from .types import DvlDiagReport, DvlFrameSummary, ScalarStats


# =============================================================================
# Column helpers
# =============================================================================

def _require_any(df: pd.DataFrame, cands: list[str], field: str) -> str:
    for c in cands:
        if c in df.columns:
            return c
    raise KeyError(f"DVL CSV missing required field '{field}', tried: {cands}. Available(sample)={list(df.columns)[:40]}")

def _optional_any(df: pd.DataFrame, cands: list[str]) -> Optional[str]:
    for c in cands:
        if c in df.columns:
            return c
    return None

def _read_time_s(df: pd.DataFrame) -> np.ndarray:
    if "t_s" in df.columns:
        return df["t_s"].to_numpy(dtype=float)
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError("DVL CSV has no time column among t_s/EstS/MonoS/EstNS/MonoNS")

def _estimate_dt_stats(t: np.ndarray) -> Tuple[float, float]:
    if t.size < 2:
        return (float("nan"), float("nan"))
    dt = np.diff(t)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return (float("nan"), float("nan"))
    return (float(np.median(dt)), float(np.percentile(dt, 95)))

def _finite_rows(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    if a.ndim == 1:
        return np.isfinite(a)
    return np.all(np.isfinite(a), axis=1)

def _read_vel_xyz(df: pd.DataFrame) -> np.ndarray:
    """
    Try to read DVL velocity in m/s, returning (N,3) in some consistent frame.

    当前策略：
      1) 优先使用 body 速度: Vx_body(m_s), Vy_body(m_s), Vz_body(m_s)
      2) 若没有 body 速度，则尝试 ENU: Ve_enu(m_s), Vn_enu(m_s), Vu_enu(m_s)
      3) 再回退到通用命名: Vx/Vy/Vz, U/V/W, VelX/VelY/VelZ 等
    """
    # ---- 1) 先查 body-frame 速度 ----
    x = _optional_any(df, ["Vx_body(m_s)", "Vx_body", "Vx_body_m_s"])
    y = _optional_any(df, ["Vy_body(m_s)", "Vy_body", "Vy_body_m_s"])
    z = _optional_any(df, ["Vz_body(m_s)", "Vz_body", "Vz_body_m_s"])

    # ---- 2) 若 body 不存在，用 ENU 速度 ----
    if not (x and y and z):
        x = _optional_any(
            df,
            ["Ve_enu(m_s)", "Ve_enu", "VelE_mps", "VelE", "E_vel_mps"],
        )
        y = _optional_any(
            df,
            ["Vn_enu(m_s)", "Vn_enu", "VelN_mps", "VelN", "N_vel_mps"],
        )
        z = _optional_any(
            df,
            ["Vu_enu(m_s)", "Vu_enu", "VelU_mps", "VelU", "U_vel_mps"],
        )

    # ---- 3) 再不行，回退到旧的通用列名 ----
    if not (x and y and z):
        x = _optional_any(df, ["Vx_mps", "Vx", "U_mps", "U", "VelX", "vx", "u"])
        y = _optional_any(df, ["Vy_mps", "Vy", "V_mps", "V", "VelY", "vy", "v"])
        z = _optional_any(df, ["Vz_mps", "Vz", "W_mps", "W", "VelZ", "vz", "w"])

    if not (x and y and z):
        raise KeyError(
            "DVL velocity columns not found. Tried candidates among "
            "Vx_body/Vy_body/Vz_body, Ve_enu/Vn_enu/Vu_enu, "
            "Vx/Vy/Vz, U/V/W, VelX/VelY/VelZ (with optional units suffix)."
        )

    v = df[[x, y, z]].to_numpy(dtype=float)
    return v

def _read_gate_fields(df: pd.DataFrame) -> Tuple[Optional[np.ndarray], Optional[pd.Series]]:
    gate_ok_col = _optional_any(df, ["GateOk", "gate_ok", "is_gate_ok"])
    reason_col  = _optional_any(df, ["GateReason", "GateFailReason", "gate_reason", "reason"])
    gate_ok = None
    if gate_ok_col is not None:
        gate_ok = df[gate_ok_col].to_numpy()
        # normalize to bool
        if gate_ok.dtype != bool:
            gate_ok = np.asarray(gate_ok, dtype=int) != 0
    reason = df[reason_col].astype(str) if reason_col is not None else None
    return gate_ok, reason

def _scalar_stats(x: np.ndarray) -> ScalarStats:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return ScalarStats(mean=float("nan"), std=float("nan"), p95_abs=float("nan"), max_abs=float("nan"))
    return ScalarStats(
        mean=float(np.mean(x)),
        std=float(np.std(x)),
        p95_abs=float(np.percentile(np.abs(x), 95)),
        max_abs=float(np.max(np.abs(x))),
    )


# =============================================================================
# Core computations
# =============================================================================

def _summarize_frame(
    name: str,
    df_all: pd.DataFrame,
    df_gate: Optional[pd.DataFrame],
    static_s: float,
    notes: list[str],
) -> DvlFrameSummary:
    if df_all is None or df_all.empty:
        raise ValueError(f"{name}: df_all is empty")

    # time & vel
    t_all = _read_time_s(df_all)
    v_all = _read_vel_xyz(df_all)

    # sort by time (safety)
    idx = np.argsort(t_all)
    t_all = t_all[idx]
    v_all = v_all[idx]

    # gate stats
    gate_ok, reason = _read_gate_fields(df_all)
    n_all = int(len(df_all))
    if gate_ok is None:
        # if df_gate provided, infer pass ratio using time intersection size
        if df_gate is not None and not df_gate.empty:
            n_gate_ok = int(len(df_gate))
            pass_ratio = float(n_gate_ok / max(n_all, 1))
            notes.append(f"{name}: GateOk column missing; pass_ratio inferred from gated CSV size.")
            gate_reason_counts: dict[str, int] = {}
        else:
            n_gate_ok = 0
            pass_ratio = float("nan")
            gate_reason_counts = {}
            notes.append(f"{name}: GateOk column missing and gated CSV not available; cannot compute pass ratio.")
    else:
        n_gate_ok = int(np.sum(gate_ok))
        pass_ratio = float(n_gate_ok / max(n_all, 1))
        gate_reason_counts = {}
        if reason is not None:
            # reasons for failed samples only
            mask_fail = (~gate_ok) & reason.notna().to_numpy()
            if np.any(mask_fail):
                vc = reason[mask_fail].value_counts(dropna=True)
                gate_reason_counts = {str(k): int(v) for k, v in vc.items()}

    # time stats
    t_min = float(np.nanmin(t_all)) if t_all.size else float("nan")
    t_max = float(np.nanmax(t_all)) if t_all.size else float("nan")
    dt_med, dt_p95 = _estimate_dt_stats(t_all)

    # static window in first static_s seconds
    if t_all.size:
        t0 = float(t_all[0])
        bw = (t_all >= t0) & (t_all <= t0 + float(static_s))
        if not np.any(bw):
            bw = np.ones_like(t_all, dtype=bool)
            notes.append(f"{name}: static window empty; fallback to full-run stats.")
    else:
        bw = np.array([], dtype=bool)

    vb = v_all[bw] if bw.size else v_all
    vb = vb[_finite_rows(vb)]
    if vb.size == 0:
        v_mean = np.array([np.nan, np.nan, np.nan])
        v_std = v_mean.copy()
        v_p95 = v_mean.copy()
        v_max = v_mean.copy()
    else:
        v_mean = np.mean(vb, axis=0)
        v_std = np.std(vb, axis=0)
        v_p95 = np.percentile(np.abs(vb), 95, axis=0)
        v_max = np.max(np.abs(vb), axis=0)

    # jump stats on full run: consecutive diffs
    v_ok = v_all[_finite_rows(v_all)]
    if v_ok.shape[0] >= 2:
        dv = np.diff(v_ok, axis=0)
        dv_abs = np.abs(dv)
        dv_p95 = np.percentile(dv_abs, 95, axis=0)
        dv_max = np.max(dv_abs, axis=0)

        dvxy = np.sqrt(dv[:, 0] ** 2 + dv[:, 1] ** 2)
        dvxy_p95 = float(np.percentile(np.abs(dvxy), 95))
        dvxy_max = float(np.max(np.abs(dvxy)))
    else:
        dv_p95 = np.array([np.nan, np.nan, np.nan])
        dv_max = dv_p95.copy()
        dvxy_p95 = float("nan")
        dvxy_max = float("nan")

    # BE Vu stats (common pool anomaly source)
    vu_stats = None
    if name.upper() == "BE":
        vu_col = _optional_any(
            df_all,
            [
                "Vu_enu(m_s)",
                "Vu_enu",
                "Vu_mps",
                "Vu",
                "Vup_mps",
                "Vup",
                "VelUp",
                "vel_up",
            ],
        )
        if vu_col is not None:
            vu_stats = _scalar_stats(df_all[vu_col].to_numpy(dtype=float))
        else:
            # fallback: 用我们已经抽取的 z 分量（此时 z 可能是 body.z 或 ENU.u）
            vu_stats = _scalar_stats(v_all[:, 2])
            notes.append(
                "BE: Vu column missing; using Z velocity component as Vu proxy for stats (sign may differ)."
            )

    return DvlFrameSummary(
        name=name,
        n_all=n_all,
        n_gate_ok=n_gate_ok,
        pass_ratio=pass_ratio,
        t_min=t_min,
        t_max=t_max,
        dt_median=dt_med,
        dt_p95=dt_p95,
        gate_reason_counts=gate_reason_counts,

        v_mean=v_mean,
        v_std=v_std,
        v_p95_abs=v_p95,
        v_max_abs=v_max,

        dv_p95_abs=dv_p95,
        dv_max_abs=dv_max,

        dvxy_p95=dvxy_p95,
        dvxy_max=dvxy_max,

        vu_stats=vu_stats,
    )


# =============================================================================
# Public API
# =============================================================================

@dataclass
class DvlDiagConfig:
    static_s: float = 20.0


def diagnose_dvl_from_proc_dir(
    run_out_dir: Path,
    run_id: str,
    cfg: DvlDiagConfig | None = None,
) -> DvlDiagReport:
    """
    Entry point: read cli_proc outputs under out/proc/<run_id>/ and produce a structured report.
    """
    if cfg is None:
        cfg = DvlDiagConfig()

    run_out_dir = Path(run_out_dir)
    notes: list[str] = []

    def _load_csv(p: Path) -> Optional[pd.DataFrame]:
        if not p.exists():
            notes.append(f"missing file: {p.name}")
            return None
        try:
            df = pd.read_csv(p)
            if df.empty:
                notes.append(f"empty file: {p.name}")
            return df
        except Exception as e:
            notes.append(f"failed to read {p.name}: {type(e).__name__}: {e}")
            return None

    # 1) mixed stream composition
    stream_path = run_out_dir / f"{run_id}_dvl_stream_all.csv"
    df_stream = _load_csv(stream_path)
    stream_src_counts: dict[str, int] = {}
    if df_stream is not None and not df_stream.empty:
        src_col = _optional_any(df_stream, ["Src", "src", "Frame", "frame", "Type", "type"])
        if src_col is None:
            notes.append("stream_all: cannot find Src column; skip stream composition.")
        else:
            vc = df_stream[src_col].astype(str).value_counts(dropna=True)
            stream_src_counts = {str(k): int(v) for k, v in vc.items()}
    else:
        notes.append("stream_all not available; skip mixed stream composition.")

    # 2) BI/BE all + gated
    df_BI_all = _load_csv(run_out_dir / f"{run_id}_dvl_filtered_BI_all.csv")
    df_BE_all = _load_csv(run_out_dir / f"{run_id}_dvl_filtered_BE_all.csv")
    df_BI = _load_csv(run_out_dir / f"{run_id}_dvl_filtered_BI.csv")
    df_BE = _load_csv(run_out_dir / f"{run_id}_dvl_filtered_BE.csv")

    BI = None
    BE = None
    if df_BI_all is not None and not df_BI_all.empty:
        BI = _summarize_frame("BI", df_BI_all, df_BI, cfg.static_s, notes)
    else:
        notes.append("BI_all missing/empty: cannot summarize BI.")
    if df_BE_all is not None and not df_BE_all.empty:
        BE = _summarize_frame("BE", df_BE_all, df_BE, cfg.static_s, notes)
    else:
        notes.append("BE_all missing/empty: cannot summarize BE.")

    return DvlDiagReport(
        run_id=str(run_id),
        static_s=float(cfg.static_s),
        stream_src_counts=stream_src_counts,
        BI=BI,
        BE=BE,
        notes=notes,
    )
# =============================================================================
# Pretty print
# =============================================================================

def _fmt3(v: Optional[np.ndarray] | None, precision: int = 4) -> str:
    if v is None:
        return "(nan, nan, nan)"
    a = np.asarray(v, dtype=float).reshape(-1)
    if a.size != 3:
        return "(?, ?, ?)"
    return f"({a[0]:+.{precision}f}, {a[1]:+.{precision}f}, {a[2]:+.{precision}f})"


def _print_scalar_stats(tag: str, st: Optional[ScalarStats]) -> None:
    if st is None:
        print(f"  {tag}: <no data>")
        return
    print(
        f"  {tag}: mean={st.mean:+.4f}, std={st.std:.4f}, "
        f"p95|x|={st.p95_abs:.4f}, max|x|={st.max_abs:.4f}"
    )


def _print_frame_summary(fs: Optional[DvlFrameSummary]) -> None:
    if fs is None:
        print("  <no data>")
        return

    print(f"  samples: total={fs.n_all}  GateOk={fs.n_gate_ok}  pass_ratio={fs.pass_ratio:.2%}")
    print(
        f"  time: [{fs.t_min:.3f}, {fs.t_max:.3f}]  "
        f"dt_median={fs.dt_median:.4f}  dt_p95={fs.dt_p95:.4f}"
    )

    print("  static-window velocity (m/s):")
    print(f"    mean      = {_fmt3(fs.v_mean, 4)}")
    print(f"    std       = {_fmt3(fs.v_std, 4)}")
    print(f"    p95|v|    = {_fmt3(fs.v_p95_abs, 4)}")
    print(f"    max|v|    = {_fmt3(fs.v_max_abs, 4)}")

    print("  jump stats (full run):")
    print(f"    p95|Δv|   = {_fmt3(fs.dv_p95_abs, 4)}")
    print(f"    max|Δv|   = {_fmt3(fs.dv_max_abs, 4)}")
    print(f"    p95|Δv_xy|={fs.dvxy_p95:.4f}  max|Δv_xy|={fs.dvxy_max:.4f}")

    if fs.vu_stats is not None:
        print("  Vu stats (vertical / up component):")
        _print_scalar_stats("Vu", fs.vu_stats)

    if fs.gate_reason_counts:
        print("  gate fail reasons:")
        for k, v in fs.gate_reason_counts.items():
            print(f"    {k}: {v}")


def print_dvl_diag(rep: DvlDiagReport) -> None:
    """
    Console-friendly pretty print for DvlDiagReport
    """
    print(f"[DVL-DIAG] run_id={rep.run_id}  static_window={rep.static_s:.1f}s")

    # 1) mixed stream composition
    print("\n== 1) Mixed stream composition (stream_all) ==")
    if rep.stream_src_counts:
        for src, cnt in rep.stream_src_counts.items():
            print(f"  Src={src:>4}: {cnt}")
    else:
        print("  <no stream composition info>")

    # 2) BI summary
    print("\n== 2) BI frame summary ==")
    _print_frame_summary(rep.BI)

    # 3) BE summary
    print("\n== 3) BE frame summary ==")
    _print_frame_summary(rep.BE)

    # 4) notes / warnings
    print("\n== 4) Notes / warnings ==")
    if rep.notes:
        for s in rep.notes:
            print(f"  - {s}")
    else:
        print("  <no notes>")
