# src/offnav/cli_raw.py
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from offnav.io.dataset import DatasetIndex
from offnav.viz import save_imu_raw_9axis, save_dvl_raw_velocity


# ------------------------------
# helpers
# ------------------------------
_TIME_COL_CANDIDATES = ("EstS", "MonoS", "EstNS", "MonoNS")


def _pick_time_s(df: pd.DataFrame) -> tuple[np.ndarray, str]:
    """Pick time column and return (t_s, colname). Raises if none found."""
    for c in _TIME_COL_CANDIDATES:
        if c in df.columns:
            t = df[c].to_numpy(dtype=float)
            if c.endswith("NS"):
                t = t * 1e-9
            return t, c
    raise KeyError(f"No time column found. Need one of: {_TIME_COL_CANDIDATES}")


def _estimate_fs(t_s: np.ndarray) -> float:
    if t_s is None or len(t_s) < 2:
        return float("nan")
    dt = np.diff(t_s)
    dt = dt[np.isfinite(dt)]
    dt = dt[dt > 0]
    if len(dt) == 0:
        return float("nan")
    return 1.0 / float(np.median(dt))


def _time_window_mask(t_s: np.ndarray, t0: float | None, t1: float | None) -> np.ndarray:
    """Return boolean mask for [t0, t1] in absolute time coordinates."""
    mask = np.ones_like(t_s, dtype=bool)
    if t0 is not None:
        mask &= (t_s >= t0)
    if t1 is not None:
        mask &= (t_s <= t1)
    return mask


def _downsample_indices(n: int, max_points: int) -> np.ndarray:
    """Uniformly pick indices to cap points."""
    if max_points <= 0 or n <= max_points:
        return np.arange(n, dtype=int)
    # linspace ensures include endpoints, stable visualization
    idx = np.linspace(0, n - 1, num=max_points, dtype=int)
    return idx


def _slice_raw_obj(raw_obj, mask: np.ndarray, max_points: int | None):
    """
    Slice a raw data object by boolean mask on its df, and optional downsample.
    Works by cloning object and replacing df with sliced df.
    Assumes raw_obj has attributes: df, source_path (optional), and __len__ uses df length.
    """
    df = raw_obj.df
    df2 = df.loc[mask].copy()

    if max_points is not None and max_points > 0 and len(df2) > max_points:
        idx = _downsample_indices(len(df2), max_points)
        df2 = df2.iloc[idx].copy()

    # shallow clone: create a new object of same class without re-reading file
    # safest approach: try to use dataclass replace-like pattern if exists,
    # else fallback to copy and assign .df
    try:
        new_obj = raw_obj.__class__(df=df2, source_path=getattr(raw_obj, "source_path", None))
        return new_obj
    except Exception:
        # generic fallback: copy object then set df
        import copy
        new_obj = copy.copy(raw_obj)
        new_obj.df = df2
        return new_obj


# ------------------------------
# cli
# ------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="offnav-raw",
        description="Offline navigation toolkit - RAW data CLI",
    )
    p.add_argument(
        "--dataset-config",
        type=str,
        default="config/dataset.yaml",
        help="Path to dataset.yaml",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # offnav-raw list
    sub.add_parser("list", help="List available runs")

    # offnav-raw show --run ...
    p_show = sub.add_parser("show", help="Show basic info of one run")
    p_show.add_argument("--run", required=True, help="run_id defined in dataset.yaml")

    # offnav-raw plot-raw --run ...
    p_plot_raw = sub.add_parser("plot-raw", help="Plot raw IMU/DVL data for one run")
    p_plot_raw.add_argument("--run", required=True, help="run_id defined in dataset.yaml")
    p_plot_raw.add_argument(
        "--out-dir",
        type=str,
        default="out/plots_raw",
        help="Root directory to save plots (default: out/plots_raw)",
    )

    # --- new options: time window / downsample / toggles
    p_plot_raw.add_argument(
        "--t0",
        type=float,
        default=None,
        help="Start time (seconds, absolute in the chosen time column units).",
    )
    p_plot_raw.add_argument(
        "--t1",
        type=float,
        default=None,
        help="End time (seconds, absolute).",
    )
    p_plot_raw.add_argument(
        "--max-points",
        type=int,
        default=0,
        help="Cap number of points for plotting (0 means no cap). Recommended for IMU.",
    )
    p_plot_raw.add_argument(
        "--no-imu",
        action="store_true",
        help="Skip IMU raw plot",
    )
    p_plot_raw.add_argument(
        "--no-dvl",
        action="store_true",
        help="Skip DVL raw plot",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cfg_path = Path(args.dataset_config)
    idx = DatasetIndex(cfg_path)

    if args.cmd == "list":
        for spec in idx.list_runs():
            print(
                f"- {spec.run_id}  "
                f"date={spec.date}  "
                f"path={spec.path}  "
                f"note={spec.note}"
            )
        return 0

    if args.cmd == "show":
        run = idx.load_run(args.run)

        # --- IMU summary
        imu_df = run.imu.df
        imu_cols = list(imu_df.columns)
        imu_t_s, imu_tcol = _pick_time_s(imu_df)
        imu_fs = _estimate_fs(imu_t_s)
        imu_dt = np.diff(imu_t_s)
        imu_dt = imu_dt[np.isfinite(imu_dt)]
        imu_dt_pos = imu_dt[imu_dt > 0]

        print(f"Run: {run.run_id}")
        print(f"  IMU: {len(run.imu)} samples, file={run.imu.source_path}")
        print(f"       time_col={imu_tcol}, t0={float(imu_t_s[0]):.6f}, t1={float(imu_t_s[-1]):.6f}, fs_est={imu_fs:.3f} Hz")
        if len(imu_dt_pos) > 0:
            print(
                "       dt(s): "
                f"min={float(np.min(imu_dt_pos)):.6f}, "
                f"med={float(np.median(imu_dt_pos)):.6f}, "
                f"max={float(np.max(imu_dt_pos)):.6f}"
            )
        print(f"       n_cols={len(imu_cols)} first_cols={imu_cols[:20]}")

        # --- DVL summary
        dvl_df = run.dvl.df
        dvl_cols = list(dvl_df.columns)
        dvl_t_s, dvl_tcol = _pick_time_s(dvl_df)
        dvl_rate = _estimate_fs(dvl_t_s)  # for low-rate sensors, this is "rate_est"
        print(f"  DVL: {len(run.dvl)} samples, file={run.dvl.source_path}")
        print(f"       time_col={dvl_tcol}, t0={float(dvl_t_s[0]):.6f}, t1={float(dvl_t_s[-1]):.6f}, rate_est={dvl_rate:.3f} Hz")
        print(f"       n_cols={len(dvl_cols)} first_cols={dvl_cols[:20]}")

        print(f"  Meta: date={run.meta.date}, note={run.meta.note}")
        return 0

    if args.cmd == "plot-raw":
        run = idx.load_run(args.run)
        out_root = Path(args.out_dir)
        run_out = out_root / run.run_id
        run_out.mkdir(parents=True, exist_ok=True)

        # time window is applied in absolute time coordinates, using each sensor's own time column
        imu_obj = run.imu
        dvl_obj = run.dvl

        if args.t0 is not None or args.t1 is not None or (args.max_points and args.max_points > 0):
            # IMU slice
            imu_t_s, _ = _pick_time_s(imu_obj.df)
            imu_mask = _time_window_mask(imu_t_s, args.t0, args.t1)
            imu_obj = _slice_raw_obj(imu_obj, imu_mask, args.max_points if args.max_points > 0 else None)

            # DVL slice (no need to downsample usually, but keep consistent)
            dvl_t_s, _ = _pick_time_s(dvl_obj.df)
            dvl_mask = _time_window_mask(dvl_t_s, args.t0, args.t1)
            dvl_obj = _slice_raw_obj(dvl_obj, dvl_mask, None)

        imu_fig = None
        dvl_fig = None

        if not args.no_imu:
            imu_fig = save_imu_raw_9axis(imu_obj, run_out, run_id=run.run_id)
            print(f"[plot-raw] IMU figure saved to: {imu_fig}")
        else:
            print("[plot-raw] IMU plot skipped (--no-imu)")

        if not args.no_dvl:
            dvl_fig = save_dvl_raw_velocity(dvl_obj, run_out, run_id=run.run_id)
            print(f"[plot-raw] DVL figure saved to: {dvl_fig}")
        else:
            print("[plot-raw] DVL plot skipped (--no-dvl)")

        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
