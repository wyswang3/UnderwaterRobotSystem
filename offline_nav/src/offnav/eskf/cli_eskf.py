from __future__ import annotations

import argparse
import math
from pathlib import Path

from .config import Eskf2DConfig
from .runner import run_eskf2d_from_csv


def _deg2rad(x: float) -> float:
    return float(x) * math.pi / 180.0


def main() -> int:
    ap = argparse.ArgumentParser("offnav.eskf2d")

    # required inputs
    ap.add_argument("--imu", required=True, help="imu_filtered.csv")
    ap.add_argument("--bi", required=True, help="dvl_BI.csv")
    ap.add_argument("--be", required=True, help="dvl_BE.csv")

    # outputs
    ap.add_argument("--out", default="out/nav/eskf2d_traj.csv", help="output trajectory csv")
    ap.add_argument("--focus-out", default=None, help="focus monitor csv (override cfg.focus_csv_path)")
    ap.add_argument("--no-focus", action="store_true", help="disable focus monitor")

    # minimal runtime knobs (only what you really need to touch during experiments)
    ap.add_argument("--acc-linear", action="store_true", help="IMU acc is linear (gravity already removed)")
    ap.add_argument("--acc-raw", action="store_true", help="IMU acc includes gravity (will subtract g)")
    ap.add_argument("--g", type=float, default=None, help="gravity m/s^2 (used only when --acc-raw)")

    ap.add_argument("--init-yaw-source", choices=["imu", "config"], default=None,
                    help="initial yaw source (override cfg.init_yaw_source)")
    ap.add_argument("--init-yaw-deg", type=float, default=None,
                    help="initial yaw in degrees when init-yaw-source=config (override cfg.init_yaw_rad)")
    ap.add_argument("--yaw-sign", type=float, default=None,
                    help="yaw_sign (override cfg.yaw_sign), usually +1 or -1")
    ap.add_argument("--yaw-offset-deg", type=float, default=None,
                    help="yaw_offset in degrees (override cfg.yaw_offset_rad), e.g. -90")

    args = ap.parse_args()

    # start from defaults in config.py (single source of truth)
    cfg = Eskf2DConfig()

    # --- overrides (only when user provides flags) ---
    # focus monitor
    if args.no_focus:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "focus_csv_path": None})  # frozen dataclass workaround
    if args.focus_out is not None:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "focus_csv_path": str(args.focus_out)})

    # acc semantic
    if args.acc_linear and args.acc_raw:
        raise SystemExit("Choose only one of --acc-linear or --acc-raw.")

    if args.acc_linear:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "imu_acc_is_linear": True})
    elif args.acc_raw:
        d = {**cfg.__dict__, "imu_acc_is_linear": False}
        if args.g is not None:
            d["gravity_mps2"] = float(args.g)
        cfg = Eskf2DConfig(**d)

    # yaw init knobs
    if args.init_yaw_source is not None:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "init_yaw_source": str(args.init_yaw_source)})

    if args.init_yaw_deg is not None:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "init_yaw_rad": _deg2rad(float(args.init_yaw_deg))})

    if args.yaw_sign is not None:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "yaw_sign": float(args.yaw_sign)})

    if args.yaw_offset_deg is not None:
        cfg = Eskf2DConfig(**{**cfg.__dict__, "yaw_offset_rad": _deg2rad(float(args.yaw_offset_deg))})

    # run
    run_eskf2d_from_csv(
        imu_csv=args.imu,
        dvl_bi_csv=args.bi,
        dvl_be_csv=args.be,
        out_traj_csv=args.out,
        cfg=cfg,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
