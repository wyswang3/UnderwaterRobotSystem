# offline_nav/src/offnav/preprocess/diagnostics/imu_diag.py
from __future__ import annotations

import numpy as np

from offnav.core.types import ImuRawData
from offnav.preprocess.imu_processing import ImuProcessedData, ImuPreprocessConfig
from .types import DtStats, VecStats, ImuDiagReport


def _dt_stats(t_s: np.ndarray) -> DtStats:
    if t_s.size < 2:
        return DtStats(median=float("nan"), p95=float("nan"), min=float("nan"), max=float("nan"), bad_ratio=float("nan"))
    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return DtStats(median=float("nan"), p95=float("nan"), min=float("nan"), max=float("nan"), bad_ratio=float("nan"))

    med = float(np.median(dt))
    p95 = float(np.percentile(dt, 95))
    mn = float(np.min(dt))
    mx = float(np.max(dt))

    # outlier definition: very practical, easy to interpret
    bad = (dt > 3.0 * med) | (dt < 0.5 * med)
    bad_ratio = float(np.mean(bad)) if bad.size else 0.0
    return DtStats(median=med, p95=p95, min=mn, max=mx, bad_ratio=bad_ratio)


def _vec_stats(x: np.ndarray) -> VecStats:
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] != 3:
        raise ValueError(f"expect (N,3), got {x.shape}")
    m = np.nanmean(x, axis=0)
    s = np.nanstd(x, axis=0)
    p95 = np.nanpercentile(np.abs(x), 95, axis=0)
    nm = float(np.linalg.norm(m))
    return VecStats(mean=m, std=s, p95_abs=p95, norm_mean=nm)


def _bias_mask(t_s: np.ndarray, duration_s: float) -> np.ndarray:
    if t_s.size == 0:
        return np.array([], dtype=bool)
    t0 = float(t_s[0])
    t1 = t0 + float(duration_s)
    m = (t_s >= t0) & (t_s <= t1)
    if not np.any(m):
        m = np.ones_like(t_s, dtype=bool)
    return m


def diagnose_imu(
    imu_raw: ImuRawData,
    imu_proc: ImuProcessedData,
    cfg: ImuPreprocessConfig,
) -> ImuDiagReport:
    """
    Pure diagnostics:
      - never modifies imu_proc
      - returns structured report for printing / json
    """
    notes: list[str] = []

    t = np.asarray(imu_proc.t_s, dtype=float).reshape(-1)
    dt = _dt_stats(t)
    fs = float(imu_proc.fs_hz)

    bw = _bias_mask(t, cfg.bias_duration_s)

    # required
    gyro_in = np.asarray(imu_proc.gyro_in_rad_s, dtype=float)
    gyro_in_bw = _vec_stats(gyro_in[bw])

    gyro_out_bw = None
    gyro_out_zero_ratio = None
    if getattr(imu_proc, "gyro_out_rad_s", None) is not None:
        gyro_out = np.asarray(imu_proc.gyro_out_rad_s, dtype=float)
        gyro_out_bw = _vec_stats(gyro_out[bw])
        zr = (
            float(np.mean(np.abs(gyro_out[:, 0]) < 1e-12)),
            float(np.mean(np.abs(gyro_out[:, 1]) < 1e-12)),
            float(np.mean(np.abs(gyro_out[:, 2]) < 1e-12)),
        )
        gyro_out_zero_ratio = zr
        if zr[2] > 0.2:
            notes.append(f"gyro_out Z-axis zero_ratio={zr[2]:.2%} is high; threshold may be too aggressive.")

    gyro_diff = None
    if getattr(imu_proc, "gyro_out_rad_s", None) is not None:
        d = np.asarray(imu_proc.gyro_in_rad_s, dtype=float) - np.asarray(imu_proc.gyro_out_rad_s, dtype=float)
        gyro_diff = _vec_stats(d[bw])

    # acc raw + gravity
    if imu_proc.acc_raw_mps2 is None:
        notes.append("acc_raw_mps2 missing: cannot validate gravity / mapping via raw-vs-g checks.")
        acc_raw_bw = _vec_stats(np.asarray(imu_proc.acc_mps2, dtype=float)[bw])  # fallback
    else:
        acc_raw = np.asarray(imu_proc.acc_raw_mps2, dtype=float)
        acc_raw_bw = _vec_stats(acc_raw[bw])

    g_body_bw = None
    residual_bw = None
    if imu_proc.g_body_mps2 is not None and imu_proc.acc_raw_mps2 is not None:
        g_body = np.asarray(imu_proc.g_body_mps2, dtype=float)
        g_body_bw = _vec_stats(g_body[bw])

        # For "acc = a + g" 模型，静止时 acc_raw ≈ g_body，残差 = acc_raw - g_body
        residual = np.asarray(imu_proc.acc_raw_mps2, dtype=float) - g_body
        residual_bw = _vec_stats(residual[bw])

        # sanity checks
        g_expect = float(cfg.g_to_mps2)
        if abs(acc_raw_bw.norm_mean - g_expect) > 0.3:
            notes.append(
                f"|acc_raw_mean|={acc_raw_bw.norm_mean:.3f} differs from g≈{g_expect:.2f}; "
                "check units / mapping / acc_model."
            )
    else:
        if imu_proc.g_body_mps2 is None:
            notes.append("g_body_mps2 missing: cannot validate gravity projection.")
        if imu_proc.acc_raw_mps2 is None:
            notes.append("acc_raw_mps2 missing: cannot validate raw-vs-gravity residual.")

    # linear acc in bias window
    acc_lin_bw = None
    if getattr(imu_proc, "acc_mps2", None) is not None:
        acc_lin = np.asarray(imu_proc.acc_mps2, dtype=float)
        acc_lin_bw = _vec_stats(acc_lin[bw])
        if acc_lin_bw.norm_mean > 0.05:
            notes.append(f"acc_lin_mean norm={acc_lin_bw.norm_mean:.3f} m/s^2 in bias-window; bias/gravity comp may be off.")

    mr, mp, my = cfg.mount_rpy_rad
    mount_deg = (float(np.rad2deg(mr)), float(np.rad2deg(mp)), float(np.rad2deg(my)))

    return ImuDiagReport(
        fs_hz=fs,
        sensor_to_body_map=str(cfg.sensor_to_body_map),
        mount_rpy_deg=mount_deg,

        dt=dt,

        acc_raw_bw=acc_raw_bw,
        g_body_bw=g_body_bw,
        residual_bw=residual_bw,

        acc_lin_bw=acc_lin_bw,

        gyro_in_bw=gyro_in_bw,
        gyro_out_bw=gyro_out_bw,
        gyro_diff=gyro_diff,

        gyro_out_zero_ratio=gyro_out_zero_ratio,
        notes=notes,
    )
def _fmt3(v: np.ndarray | tuple[float, float, float] | None, prec: int = 4) -> str:
    if v is None:
        return "(?, ?, ?)"
    a = np.asarray(v, dtype=float).reshape(-1)
    if a.size != 3:
        return "(?, ?, ?)"
    return f"({a[0]:+.{prec}f},{a[1]:+.{prec}f},{a[2]:+.{prec}f})"


def print_imu_diag(report: ImuDiagReport) -> None:
    """
    把结构化的 ImuDiagReport 打印成若干 [IMU][...] 行，供 CLI 使用。
    不做任何计算，只是 view 层。
    """
    # 基本信息
    r = report
    mr, mp, my = r.mount_rpy_deg
    print(
        f"[IMU][DIAG] fs_hz={r.fs_hz:.3f}  "
        f"sensor_to_body_map={r.sensor_to_body_map}  "
        f"mount_rpy_deg={mr:.1f},{mp:.1f},{my:.1f}"
    )

    # dt 统计
    dt = r.dt
    print(
        "[IMU][DT] dt_s: "
        f"median={dt.median:.6f}  p95={dt.p95:.6f}  "
        f"min={dt.min:.6f}  max={dt.max:.6f}  bad_ratio={dt.bad_ratio:.3%}"
    )

    # acc raw / g / residual / lin acc（bias 窗）
    print(f"[IMU][BW] acc_raw_mean/std/p95|x|={_fmt3(r.acc_raw_bw.mean,4)} / "
          f"{_fmt3(r.acc_raw_bw.std,4)} / {_fmt3(r.acc_raw_bw.p95_abs,4)}")

    if r.g_body_bw is not None:
        print(f"[IMU][BW] g_body_mean/std/p95|x|={_fmt3(r.g_body_bw.mean,4)} / "
              f"{_fmt3(r.g_body_bw.std,4)} / {_fmt3(r.g_body_bw.p95_abs,4)}")

    if r.residual_bw is not None:
        print(f"[IMU][BW] residual(raw-g)_mean/std/p95|x|={_fmt3(r.residual_bw.mean,4)} / "
              f"{_fmt3(r.residual_bw.std,4)} / {_fmt3(r.residual_bw.p95_abs,4)}")

    if r.acc_lin_bw is not None:
        print(f"[IMU][BW] acc_lin_mean/std/p95|x|={_fmt3(r.acc_lin_bw.mean,4)} / "
              f"{_fmt3(r.acc_lin_bw.std,4)} / {_fmt3(r.acc_lin_bw.p95_abs,4)}  "
              f"||acc_lin_mean||={r.acc_lin_bw.norm_mean:.4f} m/s^2")

    # gyro in/out / diff（bias 窗）
    print(f"[IMU][BW] gyro_in_mean/std/p95|x|={_fmt3(r.gyro_in_bw.mean,6)} / "
          f"{_fmt3(r.gyro_in_bw.std,6)} / {_fmt3(r.gyro_in_bw.p95_abs,6)}")

    if r.gyro_out_bw is not None:
        print(f"[IMU][BW] gyro_out_mean/std/p95|x|={_fmt3(r.gyro_out_bw.mean,6)} / "
              f"{_fmt3(r.gyro_out_bw.std,6)} / {_fmt3(r.gyro_out_bw.p95_abs,6)}")

    if r.gyro_diff is not None:
        print(f"[IMU][AUDIT] (gyro_in - gyro_out)_mean/std/p95|x|="
              f"{_fmt3(r.gyro_diff.mean,6)} / "
              f"{_fmt3(r.gyro_diff.std,6)} / {_fmt3(r.gyro_diff.p95_abs,6)}")

    if r.gyro_out_zero_ratio is not None:
        zr = r.gyro_out_zero_ratio
        print(f"[IMU][BW] gyro_out_zero_ratio(x,y,z)=({_fmt3(zr,3)})")

    # notes
    for note in r.notes:
        print(f"[IMU][NOTE] {note}")