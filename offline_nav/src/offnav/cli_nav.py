# src/offnav/cli_nav.py
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from offnav.core.nav_config import NavConfig, load_nav_config
from offnav.core.types import DvlRawData, ImuRawData
from offnav.io.dataset import DatasetIndex

# ------------------------------
# 导航管线导入
# ------------------------------

from offnav.algo.deadreckon import run_deadreckon_pipeline

# 直接使用已经成熟的 eskf_runner 管线，而不是 eskf_engine 封装
from offnav.algo.eskf_runner import (
    EskfInputs,
    EskfOutputs,
    build_eskf_timeline,
    run_eskf_pipeline,
)

# ESKF 诊断结构体
from offnav.models.eskf_state import EskfDiagnostics

from offnav.algo.eskf_audit import (
    print_audit_deep_diagnostics,
    print_audit_summary,
    print_frame_consistency_diagnostics,
)

from offnav.preprocess import load_imu_processed_csv
from offnav.viz.traj_basic import save_depth_ut, save_planar_en


# =============================================================================
# Argument parser
# =============================================================================


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="offnav-nav",
        description="Offline navigation pipelines (dead-reckon / ESKF)",
    )
    p.add_argument(
        "--dataset-config",
        type=str,
        default="configs/dataset.yaml",
        help="Path to dataset.yaml (run list and raw file layout)",
    )
    p.add_argument(
        "--nav-config",
        type=str,
        default="configs/nav.yaml",
        help="Navigation config YAML (deadreckon / eskf / frames / dvl_gate sections)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # --------------------------------------------------
    # offnav-nav deadreckon --run ... [--out-dir ...] [--proc-dir ...]
    # --------------------------------------------------
    p_dr = sub.add_parser("deadreckon", help="Run dead-reckon baseline pipeline")
    p_dr.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_dr.add_argument(
        "--out-dir",
        type=str,
        default="out/nav_deadreckon",
        help="Root directory to save outputs (default: out/nav_deadreckon)",
    )
    p_dr.add_argument(
        "--proc-dir",
        type=str,
        default="../out/proc",
        help=(
            "Root directory of preprocessed IMU/DVL (same as cli_proc --out-dir). "
            "Dead-reckon will look for *_imu_filtered.csv and DVL CSV under proc_dir/run_id. "
            "具体用 BI 还是 BE 取决于 deadreckon.mode："
            "IMU+DVL/IMU_only -> *_dvl_BI.csv；DVL_BE_only -> *_dvl_BE.csv。"
        ),
    )
    p_dr.add_argument(
        "--mode",
        type=str,
        choices=["IMU_only", "DVL_BE_only", "IMU+DVL"],
        help=(
            "Override deadreckon.mode in nav.yaml. "
            "IMU_only: 只用 IMU 惯导积分；"
            "DVL_BE_only: 只用 DVL_BE ENU 速度积分；"
            "IMU+DVL: IMU 姿态 + DVL 体速度（默认）。"
        ),
    )

    # --------------------------------------------------
    # offnav-nav eskf --run ... [--out-dir ...] [--proc-dir ...]
    # --------------------------------------------------
    p_eskf = sub.add_parser("eskf", help="Run ESKF-based navigation pipeline")
    p_eskf.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_eskf.add_argument(
        "--out-dir",
        type=str,
        default="out/nav_eskf",
        help="Root directory to save outputs (default: out/nav_eskf)",
    )
    p_eskf.add_argument(
        "--proc-dir",
        type=str,
        default="../out/proc",
        help=(
            "Root directory of preprocessed IMU/DVL (same as cli_proc --out-dir). "
            "ESKF will look for *_imu_filtered.csv and *_dvl_BE.csv (and optionally *_dvl_BI.csv) "
            "under proc_dir/run_id."
        ),
    )
    p_eskf.add_argument(
        "--mode",
        type=str,
        choices=["full_ins", "local_vel"],
        help=(
            "Override eskf.mode in nav.yaml. "
            "full_ins: global INS; "
            "local_vel: 局部速度 ESKF（速度强贴 DVL）。"
        ),
    )

    return p


# =============================================================================
# Helpers
# =============================================================================


def _dump_eskf_update_diag_if_any(
    diag: EskfDiagnostics, out_root: Path, run_id: str
) -> Path | None:
    """
    若 diag.updates 存在且非空，则写出 <run_id>_eskf_update_diag.csv 到 out_root。
    输出列：t_s, name, nis, r0..r5, S0..S5
    """
    if not hasattr(diag, "updates"):
        return None

    updates = getattr(diag, "updates")
    if not updates:
        return None

    rows = []
    for u in updates:
        name = getattr(u, "name", None)
        t_s = getattr(u, "t", None)
        nis = getattr(u, "nis", None)
        r = getattr(u, "r", None)
        sdiag = getattr(u, "S_diag", None)

        if name is None and isinstance(u, dict):
            name = u.get("name")
            t_s = u.get("t")
            nis = u.get("nis")
            r = u.get("r")
            sdiag = u.get("S_diag")

        if name is None or t_s is None:
            continue

        r = [] if r is None else list(pd.Series(r).astype(float))
        sdiag = [] if sdiag is None else list(pd.Series(sdiag).astype(float))

        r_pad = (r + [float("nan")] * 6)[:6]
        s_pad = (sdiag + [float("nan")] * 6)[:6]

        rows.append(
            [float(t_s), str(name), float(nis) if nis is not None else float("nan")]
            + r_pad
            + s_pad
        )

    if not rows:
        return None

    df = pd.DataFrame(
        rows,
        columns=[
            "t_s",
            "name",
            "nis",
            "r0",
            "r1",
            "r2",
            "r3",
            "r4",
            "r5",
            "S0",
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
        ],
    )

    out_path = out_root / f"{run_id}_eskf_update_diag.csv"
    df.to_csv(out_path, index=False)
    return out_path


# =============================================================================
# Main
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dataset_cfg = Path(args.dataset_config)
    idx = DatasetIndex(dataset_cfg)

    nav_cfg: NavConfig = load_nav_config(args.nav_config)

    # --------------------------------------------------
    # deadreckon pipeline
    # --------------------------------------------------
    if args.cmd == "deadreckon":
        run_id: str = args.run
        _ = idx.load_run(run_id)

        out_root = Path(args.out_dir) / run_id
        out_root.mkdir(parents=True, exist_ok=True)

        proc_root = Path(args.proc_dir)
        proc_dir = proc_root / run_id

        imu_csv = proc_dir / f"{run_id}_imu_filtered.csv"
        if not imu_csv.exists():
            raise FileNotFoundError(f"IMU processed CSV not found: {imu_csv}")

        dr_cfg = nav_cfg.deadreckon
        cli_mode = getattr(args, "mode", None)
        if cli_mode is not None:
            dr_cfg.mode = str(cli_mode)
            print(f"[DEADRECKON] Override mode from CLI: {dr_cfg.mode!r}")

        mode = getattr(dr_cfg, "mode", "IMU+DVL") or "IMU+DVL"
        dr_cfg.mode = mode
        mode_norm = str(mode).upper()
        print(f"[DEADRECKON] Running mode = {mode_norm!r}")

        # 选择 DVL CSV
        dvl_csv = None
        if mode_norm == "DVL_BE_ONLY":
            candidates = [
                proc_dir / f"{run_id}_dvl_BE.csv",
                proc_dir / f"{run_id}_dvl_filtered_BE.csv",
            ]
        elif mode_norm in ("IMU+DVL", "IMU_DVL", "IMU_PLUS_DVL"):
            candidates = [
                proc_dir / f"{run_id}_dvl_BI.csv",
                proc_dir / f"{run_id}_dvl_filtered_BI.csv",
            ]
        elif mode_norm == "IMU_ONLY":
            candidates = [
                proc_dir / f"{run_id}_dvl_BI.csv",
                proc_dir / f"{run_id}_dvl_filtered_BI.csv",
                proc_dir / f"{run_id}_dvl_BE.csv",
                proc_dir / f"{run_id}_dvl_filtered_BE.csv",
            ]
        else:
            print(
                f"[DEADRECKON][WARN] Unknown deadreckon.mode={mode!r}, "
                "fallback to 'IMU+DVL' (BI)."
            )
            dr_cfg.mode = "IMU+DVL"
            mode_norm = "IMU+DVL"
            candidates = [
                proc_dir / f"{run_id}_dvl_BI.csv",
                proc_dir / f"{run_id}_dvl_filtered_BI.csv",
            ]

        for c in candidates:
            if c.exists():
                dvl_csv = c
                break

        if dvl_csv is None:
            cand_str = ", ".join(str(p.name) for p in candidates)
            raise FileNotFoundError(
                f"DVL processed CSV not found for deadreckon.mode={mode!r} under {proc_dir}\n"
                f"  Tried: {cand_str}"
            )

        print(f"[DEADRECKON] Using DVL CSV: {dvl_csv.name}")

        df_imu = pd.read_csv(imu_csv, low_memory=False)
        df_dvl = pd.read_csv(dvl_csv, low_memory=False)

        imu_data = ImuRawData(df=df_imu, source_path=str(imu_csv))
        dvl_data = DvlRawData(df=df_dvl, source_path=str(dvl_csv))

        traj, diag = run_deadreckon_pipeline(imu_data, dvl_data, dr_cfg)

        suffix = mode_norm.replace("+", "plus")
        traj_path = out_root / f"{run_id}_traj_deadreckon_{suffix}.csv"
        traj.to_csv(traj_path, index=False)

        method_name = f"Dead-reckon-{mode_norm}"
        fig_en = save_planar_en(traj=traj, out_dir=out_root, run_id=run_id, method_name=method_name)
        fig_depth = save_depth_ut(traj=traj, out_dir=out_root, run_id=run_id, method_name=method_name)

        print(f"[DEADRECKON] Trajectory saved to: {traj_path}")
        print(f"[DEADRECKON] EN figure saved to:  {fig_en}")
        print(f"[DEADRECKON] Depth figure saved:  {fig_depth}")
        if hasattr(diag, "n_imu") and hasattr(diag, "n_dvl"):
            print(f"[DEADRECKON] n_imu={diag.n_imu}  n_dvl={diag.n_dvl}")
        return 0

    # --------------------------------------------------
    # ESKF pipeline
    # --------------------------------------------------
    if args.cmd == "eskf":
        run_id: str = args.run
        _ = idx.load_run(run_id)

        out_root = Path(args.out_dir) / run_id
        out_root.mkdir(parents=True, exist_ok=True)

        proc_root = Path(args.proc_dir)
        proc_dir = proc_root / run_id

        # IMU
        imu_csv = proc_dir / f"{run_id}_imu_filtered.csv"
        if not imu_csv.exists():
            raise FileNotFoundError(f"IMU processed CSV not found: {imu_csv}")
        imu_proc = load_imu_processed_csv(str(imu_csv))

        # DVL-BE
        dvl_be_csv = proc_dir / f"{run_id}_dvl_BE.csv"
        if not dvl_be_csv.exists():
            alt_be = proc_dir / f"{run_id}_dvl_filtered_BE.csv"
            if alt_be.exists():
                dvl_be_csv = alt_be
        if not dvl_be_csv.exists():
            raise FileNotFoundError(
                f"DVL BE processed CSV not found: {proc_dir}/{run_id}_dvl_BE.csv "
                f"(also tried {proc_dir}/{run_id}_dvl_filtered_BE.csv)"
            )
        df_dvl_be = pd.read_csv(dvl_be_csv, low_memory=False)

        # DVL-BI（可选）
        dvl_bi_csv = proc_dir / f"{run_id}_dvl_BI.csv"
        df_dvl_bi = None
        if not dvl_bi_csv.exists():
            alt_bi = proc_dir / f"{run_id}_dvl_filtered_BI.csv"
            if alt_bi.exists():
                dvl_bi_csv = alt_bi
        if dvl_bi_csv.exists():
            df_dvl_bi = pd.read_csv(dvl_bi_csv, low_memory=False)
            print(f"[ESKF] Using DVL BI CSV: {dvl_bi_csv.name}")
        else:
            print(
                "[ESKF] DVL BI CSV not found "
                f"({run_id}_dvl_BI[_filtered].csv), "
                "ESKF will fall back to BE velocities only for horizontals."
            )

        # 模式覆盖
        cfg_mode = getattr(nav_cfg.eskf, "mode", "full_ins")
        cli_mode = getattr(args, "mode", None)
        if cli_mode is not None:
            mode = str(cli_mode)
            setattr(nav_cfg.eskf, "mode", mode)
            print(f"[ESKF] Override mode from CLI: {mode!r}")
        else:
            mode = str(cfg_mode) if cfg_mode is not None else "full_ins"
        mode = mode.lower()
        if mode not in ("full_ins", "local_vel"):
            print(f"[ESKF] Unknown eskf.mode={mode!r} in config, fallback to 'full_ins'")
            mode = "full_ins"
            setattr(nav_cfg.eskf, "mode", mode)
        print(f"[ESKF] Running mode = {mode!r}")

        # 打印 ESKF 配置快照
        # eskf_cfg = nav_cfg.eskf
        # try:
        #     eskf_kwargs = eskf_cfg.to_eskf_kwargs()
        #     print("[ESKF][CFG] kwargs snapshot:")
        #     for k, v in eskf_kwargs.items():
        #         print(f"  {k}: {v}")
        # except Exception:
        #     print("[ESKF][CFG] (no to_eskf_kwargs, fallback to attributes)")
        #     print(f"  mode: {getattr(eskf_cfg, 'mode', None)!r}")
        #     imu_noise = getattr(eskf_cfg, "imu_noise", None)
        #     if imu_noise is not None:
        #         print(
        #             f"  imu_noise.sigma_acc_mps2: "
        #             f"{getattr(imu_noise, 'sigma_acc_mps2', None)}"
        #         )
        #         print(
        #             f"  imu_noise.sigma_gyro_rad_s: "
        #             f"{getattr(imu_noise, 'sigma_gyro_rad_s', None)}"
        #         )
        #     dvl_noise = getattr(eskf_cfg, "dvl_noise", None)
        #     if dvl_noise is not None:
        #         print(f"  dvl_noise.percent: {getattr(dvl_noise, 'percent', None)}")
        #         print(
        #             f"  dvl_noise.floor_bi_mps: "
        #             f"{getattr(dvl_noise, 'floor_bi_mps', None)}"
        #         )
        #         print(
        #             f"  dvl_noise.floor_be_mps: "
        #             f"{getattr(dvl_noise, 'floor_be_mps', None)}"
        #         )
        #         print(f"  dvl_noise.be_inflate: {getattr(dvl_noise, 'be_inflate', None)}")

        #     print(f"  sigma_dvl_xy_mps: {getattr(eskf_cfg, 'sigma_dvl_xy_mps', None)}")
        #     print(f"  sigma_dvl_z_mps:  {getattr(eskf_cfg, 'sigma_dvl_z_mps', None)}")
        #     print(f"  use_dvl_BI_vel: {getattr(eskf_cfg, 'use_dvl_BI_vel', None)}")
        #     print(f"  use_dvl_BE_vel: {getattr(eskf_cfg, 'use_dvl_BE_vel', None)}")
        #     print(
        #         f"  imu_yaw_source: "
        #         f"{getattr(eskf_cfg, 'imu_yaw_source', None)!r}"
        #     )
        #     print(
        #         f"  imu_rollpitch_source: "
        #         f"{getattr(eskf_cfg, 'imu_rollpitch_source', None)!r}"
        #     )
        #     print(
        #         f"  init_yaw_source: "
        #         f"{getattr(eskf_cfg, 'init_yaw_source', None)!r}"
        #     )
        #     print(
        #         f"  use_dvl_yaw_from_vel: "
        #         f"{getattr(eskf_cfg, 'use_dvl_yaw_from_vel', None)}"
        #     )

        # 构造 ESKF 输入 & 时间线（用 eskf_runner 的 build_eskf_timeline）
        eskf_inputs = EskfInputs(
            imu_proc=imu_proc,
            dvl_be_df=df_dvl_be,
            dvl_bi_df=df_dvl_bi,
        )
        timeline, rep = build_eskf_timeline(nav_cfg, eskf_inputs)

        # 运行 ESKF 管线（eskf_runner.run_eskf_pipeline）
        eskf_out: EskfOutputs = run_eskf_pipeline(nav_cfg, eskf_inputs, timeline)

        traj = eskf_out.traj_df
        diag = eskf_out.diag
        df_audit = eskf_out.audit_df

        suffix = f"eskf_{mode}"
        traj_path = out_root / f"{run_id}_traj_{suffix}.csv"
        traj.to_csv(traj_path, index=False)

        audit_path = out_root / f"{run_id}_{suffix}_update_audit.csv"
        df_audit.to_csv(audit_path, index=False)

        method_name = f"ESKF-{mode}"
        fig_en = save_planar_en(traj=traj, out_dir=out_root, run_id=run_id, method_name=method_name)
        fig_depth = save_depth_ut(traj=traj, out_dir=out_root, run_id=run_id, method_name=method_name)

        diag_csv_path = _dump_eskf_update_diag_if_any(diag, out_root, f"{run_id}_{mode}")

        # 文本诊断写入 txt
        diag_txt_path = out_root / f"{run_id}_{suffix}_diagnostics.txt"
        with open(diag_txt_path, "w", encoding="utf-8") as f:
            f.write(
                f"[TIME][IMU]      t0={rep.imu_t0:.6f}  "
                f"t1={rep.imu_t1:.6f}  N={rep.imu_n}\n"
            )
            f.write(
                f"[TIME][DVL-BE]   t0={rep.dvl_t0:.6f}  "
                f"t1={rep.dvl_t1:.6f}  N={rep.dvl_n}\n"
            )
            f.write(
                f"[TIME][IMU-DVL]  dt0={rep.dt0_imu_minus_dvl:+.6f}  "
                f"dt1={rep.dt1_imu_minus_dvl:+.6f}\n\n"
            )

            if hasattr(diag, "n_imu") and hasattr(diag, "n_dvl"):
                f.write(f"[ESKF] n_imu={diag.n_imu}  n_dvl={diag.n_dvl}\n")
            if hasattr(diag, "nav_started"):
                if getattr(diag, "nav_started"):
                    f.write(
                        "[ESKF][GATE] nav_started=1  "
                        f"t_start={getattr(diag, 'nav_start_t', 0.0):.3f}  "
                        f"reason={getattr(diag, 'nav_start_reason', '')}\n"
                    )
                else:
                    f.write("[ESKF][GATE] nav_started=0  (IMU-only integration disabled)\n")
            if hasattr(diag, "n_dt_guard_skip"):
                f.write(
                    "[ESKF][DT] n_dt_guard_skip="
                    f"{getattr(diag, 'n_dt_guard_skip', 0)}  "
                    f"max_gap_s={nav_cfg.eskf.max_gap_s:.3f}\n"
                )
            if hasattr(diag, "n_gyro_z_fallback"):
                f.write(
                    "[ESKF][GYROZ] n_fallback="
                    f"{getattr(diag, 'n_gyro_z_fallback', 0)}\n"
                )
            if hasattr(diag, "n_vu_pseudo"):
                f.write(
                    "[ESKF][VU-PSEUDO] n_apply="
                    f"{getattr(diag, 'n_vu_pseudo', 0)}\n"
                )
            if any(
                hasattr(diag, n)
                for n in ("n_dvl_used_vel_BE", "n_dvl_used_vel_BI", "n_dvl_used_yaw")
            ):
                f.write(
                    "[ESKF][DVL-USED] "
                    f"BE_vel={getattr(diag, 'n_dvl_used_vel_BE', 0)}  "
                    f"BI_vel={getattr(diag, 'n_dvl_used_vel_BI', 0)}  "
                    f"yaw_from_vel={getattr(diag, 'n_dvl_used_yaw', 0)}\n"
                )

            f.write("\n[ESKF][AUDIT]\n")
            if not df_audit.empty:
                with redirect_stdout(f):
                    print_audit_summary(df_audit)
                    print_audit_deep_diagnostics(
                        df_audit,
                        robust_expected=False,
                        gate_possible_expected=False,
                    )
                    print_frame_consistency_diagnostics(
                        df_audit,
                        speed_min_mps=0.05,
                        topk=10,
                    )

        print(f"[ESKF] Trajectory saved to:        {traj_path}")
        print(f"[ESKF] EN figure saved to:         {fig_en}")
        print(f"[ESKF] Depth figure saved to:      {fig_depth}")
        print(f"[ESKF] Update-audit saved to:      {audit_path}")
        if diag_csv_path is not None:
            print(f"[ESKF] Update-diagnostics CSV:    {diag_csv_path}")
        print(f"[ESKF] Text diagnostics saved to:  {diag_txt_path}")

        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
