#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/make_traj_gif.py

使用 meta.yaml -> trajectory.csv -> 生成 XY 轨迹 GIF。
"""

from __future__ import annotations

import argparse
import os

import yaml

from offnav.io.trajectory_io import load_trajectory_csv
from offnav.viz.anim import save_xy_traj_gif


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir",
        required=True,
        help="offnav run 输出的目录（包含 meta.yaml 和 trajectory.csv）",
    )
    ap.add_argument(
        "--fps",
        type=int,
        default=20,
        help="GIF 帧率 (default: 20)",
    )
    ap.add_argument(
        "--tail-sec",
        type=float,
        default=10.0,
        help="尾迹时间窗口长度（秒），默认 10s；设为 0 或负数则从起点画到当前。",
    )
    args = ap.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    meta_path = os.path.join(run_dir, "meta.yaml")
    if not os.path.exists(meta_path):
        raise SystemExit(f"meta.yaml not found in {run_dir}")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    traj_csv = meta["outputs"]["trajectory_csv"]
    traj, diag = load_trajectory_csv(traj_csv)  # 按你现有的接口来

    gif_path = save_xy_traj_gif(
        out_dir=run_dir,
        traj=traj,
        filename="traj_xy.gif",
        fps=args.fps,
        tail_window_s=args.tail_sec,
    )

    print(f"[gif] saved to: {gif_path}")


if __name__ == "__main__":
    main()
