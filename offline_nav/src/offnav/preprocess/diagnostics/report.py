# offline_nav/src/offnav/preprocess/diagnostics/report.py
from __future__ import annotations
import numpy as np
from .types import ImuDiagReport,DvlDiagReport, DvlFrameSummary

def _fmt3(x: np.ndarray, a: int = 4) -> str:
    x = np.asarray(x, dtype=float).reshape(-1)
    return f"({x[0]:+.{a}f},{x[1]:+.{a}f},{x[2]:+.{a}f})"

def render_imu_report(r: ImuDiagReport) -> str:
    lines: list[str] = []
    lines.append(f"[IMU][DIAG] fs_hz={r.fs_hz:.3f}  sensor_to_body_map={r.sensor_to_body_map}  mount_rpy_deg={r.mount_rpy_deg[0]:.0f},{r.mount_rpy_deg[1]:.0f},{r.mount_rpy_deg[2]:.0f}")
    lines.append(f"[IMU][DT] dt_s: median={r.dt.median:.6f}  p95={r.dt.p95:.6f}  min={r.dt.min:.6f}  max={r.dt.max:.6f}  bad_ratio={r.dt.bad_ratio:.2%}")

    a = r.acc_raw_bw
    lines.append(f"[IMU][BW] acc_raw_mean(mps2)={_fmt3(a.mean,4)}  acc_raw_std={_fmt3(a.std,4)}")
    lines.append(f"[IMU][BW] |acc_raw_mean|={a.norm_mean:.4f}")

    if r.g_body_bw is not None:
        g = r.g_body_bw
        lines.append(f"[IMU][BW] g_body_mean(mps2)={_fmt3(g.mean,4)}  g_body_std={_fmt3(g.std,4)}")
    if r.residual_bw is not None:
        rs = r.residual_bw
        lines.append(f"[IMU][BW] residual(acc_raw+g_body)_mean={_fmt3(rs.mean,4)}  std={_fmt3(rs.std,4)}")

    if r.acc_lin_bw is not None:
        al = r.acc_lin_bw
        lines.append(f"[IMU][BW] acc_lin_mean(mps2)={_fmt3(al.mean,4)}  std={_fmt3(al.std,4)}  p95|x|={_fmt3(al.p95_abs,4)}")

    gi = r.gyro_in_bw
    lines.append(f"[IMU][BW] gyro_in_mean(rad/s)={_fmt3(gi.mean,6)}  std={_fmt3(gi.std,6)}")

    if r.gyro_out_bw is not None:
        go = r.gyro_out_bw
        lines.append(f"[IMU][BW] gyro_out_mean(rad/s)={_fmt3(go.mean,6)}  std={_fmt3(go.std,6)}")
    if r.gyro_out_zero_ratio is not None:
        zr = r.gyro_out_zero_ratio
        lines.append(f"[IMU][BW] gyro_out_zero_ratio(x,y,z)=({zr[0]:+.3f},{zr[1]:+.3f},{zr[2]:+.3f})")

    if r.gyro_diff is not None:
        gd = r.gyro_diff
        lines.append(f"[IMU][AUDIT] |gyro_in-gyro_out| p95={_fmt3(gd.p95_abs,6)}  max~={_fmt3(np.maximum(gd.p95_abs, gd.std*5),6)}")

    for n in r.notes:
        lines.append(f"[IMU][NOTE] {n}")

    return "\n".join(lines)
def _fmt3(x: np.ndarray, a: int = 4) -> str:
    x = np.asarray(x, dtype=float).reshape(-1)
    return f"({x[0]:+.{a}f},{x[1]:+.{a}f},{x[2]:+.{a}f})"

def _render_frame(f: DvlFrameSummary) -> list[str]:
    lines: list[str] = []
    lines.append(f"[DVL][{f.name}] n_all={f.n_all}  n_gate_ok={f.n_gate_ok}  pass_ratio={f.pass_ratio:.2%}")
    lines.append(f"[DVL][{f.name}] t=[{f.t_min:.3f}, {f.t_max:.3f}]  dt_med={f.dt_median:.6f}  dt_p95={f.dt_p95:.6f}")
    if f.gate_reason_counts:
        top = sorted(f.gate_reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        reason_str = ", ".join([f"{k}:{v}" for k, v in top])
        lines.append(f"[DVL][{f.name}] gate_fail_reasons(top)={reason_str}")
    lines.append(f"[DVL][{f.name}][STATIC] v_mean(m/s)={_fmt3(f.v_mean,4)}  v_std={_fmt3(f.v_std,4)}  p95|v|={_fmt3(f.v_p95_abs,4)}  max|v|={_fmt3(f.v_max_abs,4)}")
    lines.append(f"[DVL][{f.name}][JUMP]  p95|dv|={_fmt3(f.dv_p95_abs,4)}  max|dv|={_fmt3(f.dv_max_abs,4)}  dvxy_p95={f.dvxy_p95:.4f}  dvxy_max={f.dvxy_max:.4f}")
    if f.vu_stats is not None and f.name.upper() == "BE":
        s = f.vu_stats
        lines.append(f"[DVL][BE][VU] mean={s.mean:+.4f}  std={s.std:.4f}  p95|.|={s.p95_abs:.4f}  max|.|={s.max_abs:.4f}")
    return lines

def render_dvl_report(r: DvlDiagReport) -> str:
    lines: list[str] = []
    lines.append(f"[DVL][DIAG] run_id={r.run_id}  static_s={r.static_s:.1f}")
    if r.stream_src_counts:
        top = sorted(r.stream_src_counts.items(), key=lambda kv: kv[1], reverse=True)
        s = ", ".join([f"{k}:{v}" for k, v in top[:12]])
        lines.append(f"[DVL][STREAM] Src composition(top)={s}")
    else:
        lines.append("[DVL][STREAM] Src composition: (not available)")

    if r.BI is not None:
        lines.extend(_render_frame(r.BI))
    else:
        lines.append("[DVL][BI] missing")

    if r.BE is not None:
        lines.extend(_render_frame(r.BE))
    else:
        lines.append("[DVL][BE] missing")

    for n in r.notes:
        lines.append(f"[DVL][NOTE] {n}")
    return "\n".join(lines)