# src/offnav/cli_proc.py
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, List

import numpy as np
import pandas as pd

from offnav.io.dataset import DatasetIndex
from offnav.preprocess import (
    # IMU
    ImuPreprocessConfig,
    preprocess_imu_simple,
    # DVL
    DvlPreprocessConfig,
    preprocess_dvl_simple,
)
from offnav.viz.imu_processed import save_imu_filtered_9axis
from offnav.viz.dvl_processed import save_dvl_filtered_velocity
from offnav.preprocess.diagnostics.imu_diag import diagnose_imu, print_imu_diag
from offnav.preprocess.diagnostics.dvl_diag import (
    DvlDiagConfig,
    diagnose_dvl_from_proc_dir,
    print_dvl_diag,
)

# =============================================================================
# CLI
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="offnav-proc",
        description="Offline navigation toolkit - IMU/DVL preprocess & diagnostics CLI",
    )
    p.add_argument(
        "--dataset-config",
        type=str,
        default="config/dataset.yaml",
        help="Path to dataset.yaml (default: config/dataset.yaml)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # 1) IMU only: preprocess + CSV + figure + diagnostics
    p_imu = sub.add_parser(
        "preprocess-imu",
        help="Preprocess IMU (bias, gravity, filter) and export filtered CSV / plot / diagnostics",
    )
    p_imu.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_imu.add_argument(
        "--out-dir",
        type=str,
        default="out/proc",
        help="Root dir to save processed data (default: out/proc)",
    )
    p_imu.add_argument(
        "--imu-sensor-to-body-map",
        type=str,
        default="rfu_to_frd",
        choices=["rfu_to_frd", "wit_rfu_to_frd", "identity"],
        help=(
            "Axis-map from IMU sensor frame (RFU) to body(FRD). "
            "rfu_to_frd / wit_rfu_to_frd: vendor RFU -> project FRD; "
            "identity: assume sensor frame already equals body frame."
        ),
    )
    p_imu.add_argument(
        "--imu-mount-rpy-deg",
        type=str,
        default="0,0,0",
        help="Extra fixed mount rotation (sensor->body) in ZYX degrees: 'roll,pitch,yaw'. Default: 0,0,0",
    )
    p_imu.add_argument(
        "--skip-imu-diag",
        action="store_true",
        help="Skip IMU diagnostics (only do preprocess + CSV + plot).",
    )

    # 2) DVL only: preprocess + CSV + figure + diagnostics
    p_dvl = sub.add_parser(
        "preprocess-dvl",
        help="Preprocess DVL (gate + split BI/BE) and export CSV / plot / diagnostics",
    )
    p_dvl.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_dvl.add_argument(
        "--out-dir",
        type=str,
        default="out/proc",
        help="Root dir to save processed data (default: out/proc)",
    )
    p_dvl.add_argument(
        "--skip-dvl-diag",
        action="store_true",
        help="Skip DVL diagnostics (only do preprocess + CSV + plot).",
    )

    # 3) IMU + DVL (推荐终端用户入口：一条命令跑完)
    p_all = sub.add_parser(
        "preprocess-all",
        help="Preprocess BOTH IMU and DVL; save all CSVs + plots + diagnostics under out/proc/<run_id>/",
    )
    p_all.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_all.add_argument(
        "--out-dir",
        type=str,
        default="out/proc",
        help="Root dir to save processed data (default: out/proc)",
    )
    p_all.add_argument(
        "--imu-sensor-to-body-map",
        type=str,
        default="rfu_to_frd",
        choices=["rfu_to_frd", "wit_rfu_to_frd", "identity"],
        help=(
            "Axis-map from IMU sensor frame (RFU) to body(FRD). "
            "rfu_to_frd / wit_rfu_to_frd: vendor RFU -> project FRD; "
            "identity: assume sensor frame already equals body frame."
        ),
    )
    p_all.add_argument(
        "--imu-mount-rpy-deg",
        type=str,
        default="0,0,0",
        help="Extra fixed mount rotation (sensor->body) in ZYX degrees: 'roll,pitch,yaw'. Default: 0,0,0",
    )
    p_all.add_argument(
        "--skip-imu-diag",
        action="store_true",
        help="Skip IMU diagnostics (only do preprocess + CSV + plot).",
    )
    p_all.add_argument(
        "--skip-dvl-diag",
        action="store_true",
        help="Skip DVL diagnostics (only do preprocess + CSV + plot).",
    )

    # 4) 只做 DVL 诊断（使用 preprocess 导出的 CSV）
    p_dvl_diag = sub.add_parser(
        "diag-dvl",
        help="Diagnose DVL data quality from out/proc/<run_id>/ CSVs",
    )
    p_dvl_diag.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_dvl_diag.add_argument(
        "--out-dir",
        type=str,
        default="out/proc",
        help="Root dir for processed data (default: out/proc)",
    )

    return p


# =============================================================================
# Helpers
# =============================================================================


def _parse_rpy_deg_csv(s: str) -> tuple[float, float, float]:
    """
    Parse 'roll,pitch,yaw' (degrees) -> (roll,pitch,yaw) (radians).
    """
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) != 3:
        raise ValueError(f"Invalid --imu-mount-rpy-deg={s!r}. Expected 'roll,pitch,yaw'.")
    r_deg, p_deg, y_deg = float(parts[0]), float(parts[1]), float(parts[2])
    return tuple(float(np.deg2rad(v)) for v in (r_deg, p_deg, y_deg))  # type: ignore[return-value]


def _as_n3(x, n: int, name: str) -> Optional[np.ndarray]:
    """
    Read an attribute that is expected to be (n,3). Return None if x is None.
    """
    if x is None:
        return None
    a = np.asarray(x, dtype=float)
    if a.shape != (n, 3):
        raise ValueError(f"{name} shape mismatch: expected ({n},3), got {a.shape}")
    return a


def _imu_processed_to_dataframe(imu_proc) -> pd.DataFrame:
    """
    把 ImuProcessedData 打包成 CSV（下游 ESKF / Graph / 可视化都用这一份）。

    约定：
      - acc_mps2: 重力已经补偿后的线性加速度（body=FRD）
      - gyro_in_rad_s: 低通但不阈值（ESKF 输入）
      - gyro_out_rad_s: 低通+阈值（用于图更干净）

    CSV 核心列：
      - t_s
      - AccX/Y/Z_mps2
      - GyroX/Y/Z_rad_s            (别名：gyro_out)
      - GyroX/Y/Z_out_rad_s        (显式 gyro_out)
      - GyroX/Y/Z_in_rad_s         (ESKF 应使用)
      - roll_rad / pitch_rad / yaw_nav_rad（body 语义的姿态，rad）
      - yaw_device_rad（若存在：设备原始 yaw，rad）
    """
    t = np.asarray(getattr(imu_proc, "t_s"), dtype=float).reshape(-1)
    n = len(t)

    acc = _as_n3(getattr(imu_proc, "acc_mps2", None), n, "acc_mps2")
    if acc is None:
        raise RuntimeError("imu_proc.acc_mps2 is required but missing")

    gyro_out = getattr(imu_proc, "gyro_out_rad_s", None)
    if gyro_out is None:
        gyro_out = getattr(imu_proc, "gyro_in_rad_s", None)
        if gyro_out is not None:
            print(
                "[IMU][WARN] imu_proc.gyro_out_rad_s missing; "
                "fall back to gyro_in_rad_s for Gyro*_rad_s columns."
            )
    gyro_out = _as_n3(gyro_out, n, "gyro_out_rad_s|gyro_in_rad_s")
    if gyro_out is None:
        raise RuntimeError("imu_proc.gyro_out_rad_s / gyro_in_rad_s both missing")

    gyro_in = getattr(imu_proc, "gyro_in_rad_s", None)
    if gyro_in is None:
        gyro_in = gyro_out
    gyro_in = _as_n3(gyro_in, n, "gyro_in_rad_s")

    data: dict[str, np.ndarray] = {
        "t_s": t,
        "AccX_mps2": acc[:, 0],
        "AccY_mps2": acc[:, 1],
        "AccZ_mps2": acc[:, 2],
        # legacy gyro columns = gyro_out
        "GyroX_rad_s": gyro_out[:, 0],
        "GyroY_rad_s": gyro_out[:, 1],
        "GyroZ_rad_s": gyro_out[:, 2],
        # explicit gyro_out
        "GyroX_out_rad_s": gyro_out[:, 0],
        "GyroY_out_rad_s": gyro_out[:, 1],
        "GyroZ_out_rad_s": gyro_out[:, 2],
        # gyro_in for ESKF
        "GyroX_in_rad_s": gyro_in[:, 0],
        "GyroY_in_rad_s": gyro_in[:, 1],
        "GyroZ_in_rad_s": gyro_in[:, 2],
    }

    # ---------------- 姿态：body 语义的 roll/pitch/yaw ----------------
    angle_est = getattr(imu_proc, "angle_est_rad", None)
    if angle_est is not None:
        a = np.asarray(angle_est, dtype=float)
        if a.shape == (n, 3):
            # rad 版（给 deadreckon / ESKF 用）
            data["roll_rad"] = a[:, 0]
            data["pitch_rad"] = a[:, 1]
            # 这里将 body-yaw 直接作为导航 yaw 使用
            data["yaw_nav_rad"] = a[:, 2]

            # deg 版（纯诊断 / 作图）
            deg = np.rad2deg(a)
            data["RollEst_deg"] = deg[:, 0]
            data["PitchEst_deg"] = deg[:, 1]
            data["YawEst_deg"] = deg[:, 2]
            try:
                yaw_unwrap = np.unwrap(a[:, 2])
                data["YawEst_unwrapped_deg"] = np.rad2deg(yaw_unwrap)
            except Exception:
                pass

    # 设备原始欧拉角（若保留）
    angle_dev = getattr(imu_proc, "angle_rad", None)
    if angle_dev is not None:
        a = np.asarray(angle_dev, dtype=float)
        if a.shape == (n, 3):
            deg = np.rad2deg(a)
            data["AngX_deg"] = deg[:, 0]
            data["AngY_deg"] = deg[:, 1]
            data["AngZ_deg"] = deg[:, 2]

    # 设备 yaw（rad），用于对比 / 诊断
    yaw_device = getattr(imu_proc, "yaw_device_rad", None)
    if yaw_device is not None:
        y = np.asarray(yaw_device, dtype=float).reshape(-1)
        if y.size == n:
            data["yaw_device_rad"] = y

    # 原始加速度 / 重力分量 / bias 等 debug
    acc_raw = getattr(imu_proc, "acc_raw_mps2", None)
    if acc_raw is not None:
        ar = np.asarray(acc_raw, dtype=float)
        if ar.shape == (n, 3):
            data["AccXraw_mps2"] = ar[:, 0]
            data["AccYraw_mps2"] = ar[:, 1]
            data["AccZraw_mps2"] = ar[:, 2]

    g_body = getattr(imu_proc, "g_body_mps2", None)
    if g_body is not None:
        gb = np.asarray(g_body, dtype=float)
        if gb.shape == (n, 3):
            data["Gx_mps2"] = gb[:, 0]
            data["Gy_mps2"] = gb[:, 1]
            data["Gz_mps2"] = gb[:, 2]

    bias_acc = getattr(imu_proc, "bias_acc_mps2", None)
    if bias_acc is not None:
        ba = np.asarray(bias_acc, dtype=float).reshape(-1)
        if ba.size == 3:
            data["BiasAccX_mps2"] = np.full(n, ba[0], dtype=float)
            data["BiasAccY_mps2"] = np.full(n, ba[1], dtype=float)
            data["BiasAccZ_mps2"] = np.full(n, ba[2], dtype=float)

    bias_gyro = getattr(imu_proc, "bias_gyro_rad_s", None)
    if bias_gyro is not None:
        bg = np.asarray(bias_gyro, dtype=float).reshape(-1)
        if bg.size == 3:
            data["BiasGyroX_rad_s"] = np.full(n, bg[0], dtype=float)
            data["BiasGyroY_rad_s"] = np.full(n, bg[1], dtype=float)
            data["BiasGyroZ_rad_s"] = np.full(n, bg[2], dtype=float)

    df_out = pd.DataFrame(data)

    preferred = [
        "t_s",
        "AccX_mps2",
        "AccY_mps2",
        "AccZ_mps2",
        "GyroX_rad_s",
        "GyroY_rad_s",
        "GyroZ_rad_s",
        "GyroX_in_rad_s",
        "GyroY_in_rad_s",
        "GyroZ_in_rad_s",
        # 姿态（rad）
        "roll_rad",
        "pitch_rad",
        "yaw_nav_rad",
        "yaw_device_rad",
        # 姿态（deg）
        "RollEst_deg",
        "PitchEst_deg",
        "YawEst_deg",
        "YawEst_unwrapped_deg",
        "AngX_deg",
        "AngY_deg",
        "AngZ_deg",
        # debug
        "AccXraw_mps2",
        "AccYraw_mps2",
        "AccZraw_mps2",
        "Gx_mps2",
        "Gy_mps2",
        "Gz_mps2",
        "BiasAccX_mps2",
        "BiasAccY_mps2",
        "BiasAccZ_mps2",
        "BiasGyroX_rad_s",
        "BiasGyroY_rad_s",
        "BiasGyroZ_rad_s",
    ]
    cols = [c for c in preferred if c in df_out.columns] + [
        c for c in df_out.columns if c not in preferred
    ]
    return df_out[cols]


def _get_time_s_from_df(df: pd.DataFrame) -> np.ndarray:
    """
    从 DVL DataFrame 中提取时间轴（秒）。
    按 EstS / MonoS / EstNS / MonoNS 的优先级顺序选择。
    """
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    if "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    if "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    if "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    raise KeyError("DVL df has no EstS/MonoS/EstNS/MonoNS time column.")


def _diagnose_dvl_events(dvl_proc, run_id: str) -> None:
    """
    对预处理后的 DVL 事件流做一个简要审查：
      - BI / BE 各自的时间范围、样本数、采样频率估计
      - 速度模值 Speed(m_s) 的统计（min/mean/std/p95/max）
    方便后面判断 DVL 观测是否健康，为 ESKF 做准备。
    """
    def _diag_one(name: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            print(f"[DVL-DIAG][{run_id}] {name}: EMPTY")
            return

        try:
            t = _get_time_s_from_df(df)
        except KeyError as e:
            print(f"[DVL-DIAG][{run_id}] {name}: no valid time column ({e})")
            return

        n = len(df)
        t0 = float(t[0])
        t1 = float(t[-1])
        duration = t1 - t0 if n >= 2 else 0.0

        # 采样频率估计
        if n >= 2:
            dt = np.diff(t)
            dt = dt[np.isfinite(dt) & (dt > 0)]
            fs = 1.0 / float(np.median(dt)) if dt.size > 0 else float("nan")
        else:
            fs = float("nan")

        # 速度模值
        if "Speed(m_s)" in df.columns:
            spd = df["Speed(m_s)"].to_numpy(dtype=float)
        else:
            # 尝试从 3 轴速度推导
            v_cols_candidates = [
                ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"),
                ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"),
            ]
            spd = None
            for vc in v_cols_candidates:
                if set(vc).issubset(df.columns):
                    v = df[list(vc)].to_numpy(dtype=float)
                    spd = np.sqrt(np.sum(v * v, axis=1))
                    break
            if spd is None:
                print(f"[DVL-DIAG][{run_id}] {name}: no Speed(m_s) or 3-axis velocity columns, skip speed stats")
                spd = None

        print(f"[DVL-DIAG][{run_id}] {name}:")
        print(f"  t=[{t0:.3f}, {t1:.3f}]  duration={duration:.2f}s  N={n}  fs≈{fs:.2f} Hz")

        if spd is not None and spd.size > 0:
            spd_f = spd[np.isfinite(spd)]
            if spd_f.size == 0:
                print("  Speed(m_s): all non-finite, skip stats")
            else:
                p95 = np.percentile(spd_f, 95)
                print(
                    "  Speed(m_s): "
                    f"min={spd_f.min():.4f}  mean={spd_f.mean():.4f}  "
                    f"std={spd_f.std():.4f}  p95={p95:.4f}  max={spd_f.max():.4f}"
                )

                # 如果能拿到 config.speed_max_m_s，可以顺带给一点对比
                if getattr(dvl_proc, "config", None) is not None:
                    cfg = dvl_proc.config
                    if hasattr(cfg, "speed_max_m_s"):
                        print(
                            f"  cfg.speed_max_m_s={cfg.speed_max_m_s:.3f} "
                            f"(p95/cfg≈{p95 / float(cfg.speed_max_m_s):.2f})"
                        )

        # 额外：如果有 ENU / body 3 轴，可以粗略看一下水平/垂向分量尺度
        v_en_cols = ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)")
        v_bd_cols = ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)")
        if set(v_en_cols).issubset(df.columns):
            v_en = df[list(v_en_cols)].to_numpy(dtype=float)
            ve, vn, vu = v_en[:, 0], v_en[:, 1], v_en[:, 2]
            ve_f = ve[np.isfinite(ve)]
            vn_f = vn[np.isfinite(vn)]
            vu_f = vu[np.isfinite(vu)]
            if ve_f.size and vn_f.size and vu_f.size:
                print(
                    "  ENU components (mean/std): "
                    f"Ve={ve_f.mean():.4f}/{ve_f.std():.4f}, "
                    f"Vn={vn_f.mean():.4f}/{vn_f.std():.4f}, "
                    f"Vu={vu_f.mean():.4f}/{vu_f.std():.4f}"
                )
        elif set(v_bd_cols).issubset(df.columns):
            v_bd = df[list(v_bd_cols)].to_numpy(dtype=float)
            vx, vy, vz = v_bd[:, 0], v_bd[:, 1], v_bd[:, 2]
            vx_f = vx[np.isfinite(vx)]
            vy_f = vy[np.isfinite(vy)]
            vz_f = vz[np.isfinite(vz)]
            if vx_f.size and vy_f.size and vz_f.size:
                print(
                    "  Body components (mean/std): "
                    f"Vx={vx_f.mean():.4f}/{vx_f.std():.4f}, "
                    f"Vy={vy_f.mean():.4f}/{vy_f.std():.4f}, "
                    f"Vz={vz_f.mean():.4f}/{vz_f.std():.4f}"
                )

    df_bi = dvl_proc.df_bi
    df_be = dvl_proc.df_be
    cfg = getattr(dvl_proc, "config", None)

    print(f"[DVL-DIAG][{run_id}] ===== DVL Events Diagnostics =====")

    # 打印关键预处理配置，方便后面看 gate 是否偏保守
    if cfg is not None:
        print(
            f"[DVL-DIAG][{run_id}] cfg: "
            f"time_col={getattr(cfg, 'time_col', 'EstS')}, "
            f"keep_first_s={getattr(cfg, 'keep_first_s', float('nan')):.1f}, "
            f"speed_min/max=({getattr(cfg, 'speed_min_m_s', float('nan')):.3f},"
            f"{getattr(cfg, 'speed_max_m_s', float('nan')):.3f}), "
            f"dv_axis_max={getattr(cfg, 'dv_axis_max_m_s', float('nan')):.3f}, "
            f"dv_xy_max={getattr(cfg, 'dv_xy_max_m_s', float('nan')):.3f}, "
            f"be_vu_abs_max={getattr(cfg, 'be_vu_abs_max_m_s', float('nan')):.3f}, "
            f"lowpass_window_s={getattr(cfg, 'lowpass_window_s', float('nan')):.2f}"
        )

    _diag_one("BI", df_bi)
    _diag_one("BE", df_be)
    print(f"[DVL-DIAG][{run_id}] ====================================")

# =============================================================================
# Pipelines
# =============================================================================


def _run_imu_preprocess(
    run,
    run_out: Path,
    imu_sensor_to_body_map: str,
    imu_mount_rpy_deg: str,
    skip_diag: bool = False,
) -> None:
    if run is None:
        raise RuntimeError("[IMU] run is None")
    if not hasattr(run, "run_id"):
        raise RuntimeError("[IMU] run has no attribute 'run_id'")
    if not hasattr(run, "imu") or run.imu is None:
        raise RuntimeError(f"[IMU][{run.run_id}] run.imu is None or missing")

    imu_raw = run.imu

    mount_rpy_rad = _parse_rpy_deg_csv(imu_mount_rpy_deg)
    imu_cfg = ImuPreprocessConfig(
        sensor_to_body_map=str(imu_sensor_to_body_map),
        mount_rpy_rad=mount_rpy_rad,
        nav_frame="ENU",
        keep_debug=True,
        keep_raw_df=True,
    )

    imu_proc = preprocess_imu_simple(imu_raw, imu_cfg)

    # 1) CSV 输出
    df_out = _imu_processed_to_dataframe(imu_proc)
    csv_path = run_out / f"{run.run_id}_imu_filtered.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"[IMU] Filtered IMU CSV saved to: {csv_path}")

    # 2) 图像输出（兼容旧版绘图接口）
    fig_path = None
    had_attr = hasattr(imu_proc, "gyro_rad_s")
    old_val = getattr(imu_proc, "gyro_rad_s", None) if had_attr else None
    try:
        if not had_attr:
            imu_proc.gyro_rad_s = imu_proc.gyro_out_rad_s  # type: ignore[attr-defined]
        fig_path = save_imu_filtered_9axis(imu_proc, run_out, run_id=run.run_id)
    finally:
        if not had_attr:
            del imu_proc.gyro_rad_s
        else:
            imu_proc.gyro_rad_s = old_val  # type: ignore[assignment]

    print(f"[IMU] Filtered IMU figure saved to: {fig_path}")

    # 3) 诊断（调用 diagnostics 模块，而不是在 CLI 内部写统计）
    if not skip_diag:
        try:
            report = diagnose_imu(imu_raw, imu_proc, imu_cfg)
            print_imu_diag(report)
            print(
                "[IMU][INFO] Use Gyro*_in_rad_s for ESKF; "
                "use Gyro*_rad_s / Gyro*_out_rad_s for plots."
            )
        except Exception as e:
            print(f"[IMU][WARN] imu diagnostics failed: {type(e).__name__}: {e}")


def _run_dvl_preprocess(
    run,
    run_out: Path,
    skip_diag: bool = False,
) -> None:
    if run is None:
        raise RuntimeError("[DVL] run is None")
    if not hasattr(run, "run_id"):
        raise RuntimeError("[DVL] run has no attribute 'run_id'")
    if not hasattr(run, "dvl") or run.dvl is None:
        raise RuntimeError(f"[DVL][run.run_id] run.dvl is None or missing")

    # 1) 预处理（事件流）
    dvl_cfg = DvlPreprocessConfig()  # alias of DvlEventsConfig
    dvl_ev = preprocess_dvl_simple(run.dvl, dvl_cfg)  # returns DvlEventsData / DvlProcessedData

    # 2) 保存 BI / BE CSV
    run_out.mkdir(parents=True, exist_ok=True)
    csv_bi = run_out / f"{run.run_id}_dvl_BI.csv"
    csv_be = run_out / f"{run.run_id}_dvl_BE.csv"
    dvl_ev.df_bi.to_csv(csv_bi, index=False)
    dvl_ev.df_be.to_csv(csv_be, index=False)
    print(f"[DVL][{run.run_id}] DVL BI CSV saved to: {csv_bi} (n={len(dvl_ev.df_bi)})")
    print(f"[DVL][{run.run_id}] DVL BE CSV saved to: {csv_be} (n={len(dvl_ev.df_be)})")

    # 3) 绘图：滤波后的 DVL 速度曲线（BI + BE）
    plots_dir = run_out / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    try:
        png_path = save_dvl_filtered_velocity(
            dvl_proc=dvl_ev,
            out_dir=plots_dir,
            run_id=run.run_id,
            subset="BI_BE",  # 目前参数仍保留兼容
        )
        print(f"[DVL][{run.run_id}] Filtered velocity plot saved to: {png_path}")
    except Exception as e:
        print(f"[DVL][{run.run_id}] Plotting failed: {e!r}")

    # 4) 审查 / diagnostics
    if not skip_diag:
        try:
            _diagnose_dvl_events(dvl_ev, run.run_id)
        except Exception as e:
            print(f"[DVL][{run.run_id}] Diagnostics failed: {e!r}")

# =============================================================================
# Main
# =============================================================================


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # diag-dvl 只依赖 out/proc 下已有 CSV，可不加载 dataset.yaml
    if args.cmd == "diag-dvl":
        run_id = args.run
        out_root = Path(args.out_dir)
        run_out = out_root / run_id
        rep = diagnose_dvl_from_proc_dir(run_out, run_id, cfg=DvlDiagConfig(static_s=20.0))
        print_dvl_diag(rep)
        return 0

    # 其他子命令需要 dataset.yaml / DatasetIndex
    cfg_path = Path(args.dataset_config)
    idx = DatasetIndex(cfg_path)

    run = idx.load_run(args.run)

    out_root = Path(args.out_dir)
    run_out = out_root / run.run_id
    run_out.mkdir(parents=True, exist_ok=True)

    if args.cmd == "preprocess-imu":
        _run_imu_preprocess(
            run,
            run_out,
            imu_sensor_to_body_map=str(args.imu_sensor_to_body_map),
            imu_mount_rpy_deg=str(args.imu_mount_rpy_deg),
            skip_diag=bool(getattr(args, "skip_imu_diag", False)),
        )
        return 0

    if args.cmd == "preprocess-dvl":
        _run_dvl_preprocess(
            run,
            run_out,
            skip_diag=bool(getattr(args, "skip_dvl_diag", False)),
        )
        return 0

    if args.cmd == "preprocess-all":
        _run_imu_preprocess(
            run,
            run_out,
            imu_sensor_to_body_map=str(args.imu_sensor_to_body_map),
            imu_mount_rpy_deg=str(args.imu_mount_rpy_deg),
            skip_diag=bool(getattr(args, "skip_imu_diag", False)),
        )
        _run_dvl_preprocess(
            run,
            run_out,
            skip_diag=bool(getattr(args, "skip_dvl_diag", False)),
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
