# src/offnav/cli_dvl.py
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, Set, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from offnav.io.dataset import DatasetIndex
from offnav.core.types import DvlRawData


# 合法模式：SA（姿态）、TS（时间戳）、BI/BS（体坐标速度）、BE（ENU 速度）、BD（ENU 距离）
_VALID_SRC: Set[str] = {"SA", "TS", "BI", "BS", "BE", "BD"}


# =============================================================================
# 读取 + 清洗 dvl_parsed/nav_state CSV
# =============================================================================

def load_and_clean_dvl_parsed_csv(path: Path) -> pd.DataFrame:
    """
    读取 dvl_parsed_*.csv 或 dvl_nav_state_tb_*.csv，并做几件事：
      1) 使用首行作为表头（Timestamp(s), SensorID, Src, ...）
      2) 只保留 DVL_H1000 + Src ∈ {SA,TS,BI,BS,BE,BD} 的行
      3) 数值列统一 to_numeric，异常值裁剪为 0：
         - 速度：|v| > 5 m/s 或 5000 mm/s → 0
         - 距离/深度：|x| > 100 m（泳池尺度，可按需调）→ 0
      4) NaN 统一填 0，占位但不污染积分
      5) 生成统一时间列 t_s（从 0 开始的相对时间），优先使用 EstS / MonoS / Timestamp(s)

    返回：干净的 DataFrame，至少包含：
      - 'Src'：模式大写（SA/TS/BI/BS/BE/BD）
      - 't_s'：相对时间 [s]
      - 若原文件有：Vx_body(m_s)/Ve_enu(m_s)/De_enu(m)/Depth(m) 等则统一转成 float
    """
    path = Path(path)
    print(f"[DVL] load_and_clean_dvl_parsed_csv: {path}")

    # 先按“无表头”读入，然后第一行当表头
    df_raw = pd.read_csv(path, header=None)
    if df_raw.empty:
        raise RuntimeError(f"DVL parsed CSV is empty: {path}")

    header = df_raw.iloc[0].tolist()
    df = df_raw.iloc[1:].copy()
    df.columns = header

    # 只保留 DVL_H1000
    if "SensorID" in df.columns:
        df = df[df["SensorID"] == "DVL_H1000"].copy()

    if df.empty:
        print("[DVL] after SensorID=DVL_H1000 filter -> empty")
        return df.reset_index(drop=True)

    # 规范化 Src
    if "Src" not in df.columns:
        raise KeyError(f"[DVL] CSV has no 'Src' column: {path}")

    df["Src"] = df["Src"].astype(str).str.strip().str.upper()
    df = df[df["Src"].isin(_VALID_SRC)].copy()

    if df.empty:
        print("[DVL] after Src ∈ {SA,TS,BI,BS,BE,BD} filter -> empty")
        return df.reset_index(drop=True)

    # ---- 构造时间列 t_s_raw ----
    t_raw = None
    for c in ("EstS", "MonoS", "Timestamp(s)"):
        if c in df.columns:
            t_raw = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
            if np.isfinite(t_raw).any():
                df["t_s_raw"] = t_raw
                break

    if "t_s_raw" not in df.columns:
        raise KeyError(
            f"[DVL] cannot find usable time column (EstS/MonoS/Timestamp(s)): {path}"
        )

    t0 = float(np.nanmin(df["t_s_raw"].to_numpy(dtype=float)))
    df["t_s"] = df["t_s_raw"] - t0

    # ---- 数值列统一转 float + 裁剪异常值 ----
    num_cols: List[str] = [
        c for c in df.columns
        if any(x in c for x in ("(mm_s)", "(m_s)", "(m)"))
    ]

    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    vel_m_cols = [c for c in num_cols if c.endswith("(m_s)")]
    vel_mm_cols = [c for c in num_cols if c.endswith("(mm_s)")]
    dist_cols = [c for c in num_cols if c.endswith("(m)")]

    # 速度阈值
    for c in vel_m_cols:
        mask_bad = df[c].abs() > 5.0
        if mask_bad.any():
            df.loc[mask_bad, c] = 0.0

    for c in vel_mm_cols:
        mask_bad = df[c].abs() > 5000.0
        if mask_bad.any():
            df.loc[mask_bad, c] = 0.0

    # 距离 / 深度阈值
    for c in dist_cols:
        mask_bad = df[c].abs() > 100.0   # 泳池可用，海试再调大
        if mask_bad.any():
            df.loc[mask_bad, c] = 0.0

    # 剩余 NaN 一律填 0
    if num_cols:
        df[num_cols] = df[num_cols].fillna(0.0)

    return df.reset_index(drop=True)


# =============================================================================
# 解析参数
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="offnav-dvl",
        description="DVL 数据离线分析 / 可视化工具（按 BI/BS/BE/BD 拆分）",
    )
    p.add_argument(
        "--dataset-config",
        type=str,
        default="configs/dataset.yaml",
        help="dataset.yaml 路径（定义 data_root 与 runs 列表）",
    )
    p.add_argument(
        "--run",
        type=str,
        required=True,
        help="run_id（必须在 dataset.yaml 的 runs 中存在）",
    )
    p.add_argument(
        "--out-dir",
        type=str,
        default="out/dvl_analysis",
        help="输出图像和统计的目录（默认：out/dvl_analysis）",
    )
    p.add_argument(
        "--dvl-csv",
        type=str,
        default="",
        help=(
            "可选：显式指定 DVL CSV 路径（若不指定，则使用 dataset.yaml 中的 dvl_glob 解析结果）"
        ),
    )
    return p


# =============================================================================
# 帮助函数：根据 dataset.yaml 找到 DVL 文件
# =============================================================================

def _load_dvl_via_dataset(idx: DatasetIndex, run_id: str) -> Path:
    """
    根据 dataset.yaml 找到 DVL 的 CSV 路径。

    - 若 run.dvl 是 DvlRawData：优先使用其 source_path；
    - 否则假定 run.dvl 是相对路径字符串（例如 "dvl/dvl_nav_state_tb_....csv"），
      使用 data_root / run.path / run.dvl 拼出完整路径。
    """
    run = idx.load_run(run_id)
    dvl_meta = run.dvl

    # 情况 1：DvlRawData（某些 DatasetIndex 实现可能会这么返回）
    if isinstance(dvl_meta, DvlRawData):
        sp = getattr(dvl_meta, "source_path", None)
        if sp is None:
            raise RuntimeError(
                f"run.dvl is DvlRawData but has no source_path: {dvl_meta!r}"
            )
        dvl_path = Path(sp)
        print(f"[DVL] Using DvlRawData.source_path: {dvl_path}")
        return dvl_path

    # 情况 2：str / Path
    if isinstance(dvl_meta, (str, Path)):
        data_root = Path(idx.data_root)
        run_dir = data_root / run.path
        dvl_path = (run_dir / dvl_meta).resolve()
        print(f"[DVL] Using dataset.yaml path: {dvl_path}")
        return dvl_path

    raise TypeError(f"Unsupported run.dvl type: {type(dvl_meta)} ({dvl_meta!r})")


# =============================================================================
# 拆分 / 统计
# =============================================================================

def _split_by_src(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for mode in ("SA", "TS", "BI", "BS", "BE", "BD"):
        m = df["Src"] == mode
        if not m.any():
            continue
        sub = df.loc[m].copy()
        sub = sub.sort_values("t_s").reset_index(drop=True)
        out[mode] = sub
    return out


def _print_mode_stats(mode: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"[DVL][{mode}] N=0 (empty)")
        return

    t = df["t_s"].to_numpy(dtype=float)
    t0 = float(np.nanmin(t))
    t1 = float(np.nanmax(t))
    duration = t1 - t0 if np.isfinite(t0) and np.isfinite(t1) else float("nan")
    n = len(df)
    fs = n / duration if duration > 0 else float("nan")

    print(f"[DVL][{mode}] t=[{t0:.3f}, {t1:.3f}]  dur={duration:.3f}s  N={n}  fs≈{fs:.2f} Hz")

    # 速度统计
    if mode in ("BI", "BS"):
        cols = [c for c in ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)") if c in df.columns]
        if len(cols) == 3:
            v = df[cols].to_numpy(dtype=float)
            speed = np.linalg.norm(v, axis=1)
            print(
                f"  Body speed: min={np.nanmin(speed):.4f}  "
                f"mean={np.nanmean(speed):.4f}  "
                f"p95={np.nanpercentile(speed, 95):.4f}  "
                f"max={np.nanmax(speed):.4f}"
            )

    if mode == "BE":
        cols = [c for c in ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)") if c in df.columns]
        if len(cols) == 3:
            v = df[cols].to_numpy(dtype=float)
            speed = np.linalg.norm(v, axis=1)
            print(
                f"  ENU speed:  min={np.nanmin(speed):.4f}  "
                f"mean={np.nanmean(speed):.4f}  "
                f"p95={np.nanpercentile(speed, 95):.4f}  "
                f"max={np.nanmax(speed):.4f}"
            )

    if mode == "BD":
        for c in ("De_enu(m)", "Dn_enu(m)", "Du_enu(m)", "Depth(m)", "E(m)", "N(m)", "U(m)"):
            if c in df.columns:
                x = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
                if np.any(np.isfinite(x)):
                    print(
                        f"  {c}: min={np.nanmin(x):.3f}  "
                        f"max={np.nanmax(x):.3f}  "
                        f"Δ={np.nanmax(x)-np.nanmin(x):.3f}"
                    )


# =============================================================================
# 绘图：BI/BS/BE/BD
# =============================================================================

def _ensure_out_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _plot_bi_bs(df_bi: pd.DataFrame, df_bs: pd.DataFrame, out_dir: Path, run_id: str) -> Path | None:
    if df_bi.empty and df_bs.empty:
        return None

    fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
    ax_vx, ax_vy, ax_vz, ax_speed = axes

    # BI
    if not df_bi.empty:
        t_bi = df_bi["t_s"].to_numpy(dtype=float)
        for col, ax in zip(("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"), (ax_vx, ax_vy, ax_vz)):
            if col in df_bi.columns:
                ax.plot(t_bi, df_bi[col].to_numpy(dtype=float), label="BI")
        cols = [c for c in ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)") if c in df_bi.columns]
        if len(cols) == 3:
            v = df_bi[cols].to_numpy(dtype=float)
            speed = np.linalg.norm(v, axis=1)
            ax_speed.plot(t_bi, speed, label="BI")

    # BS
    if not df_bs.empty:
        t_bs = df_bs["t_s"].to_numpy(dtype=float)
        for col, ax in zip(("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"), (ax_vx, ax_vy, ax_vz)):
            if col in df_bs.columns:
                ax.plot(t_bs, df_bs[col].to_numpy(dtype=float), linestyle="--", label="BS")
        cols = [c for c in ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)") if c in df_bs.columns]
        if len(cols) == 3:
            v = df_bs[cols].to_numpy(dtype=float)
            speed = np.linalg.norm(v, axis=1)
            ax_speed.plot(t_bs, speed, linestyle="--", label="BS")

    ax_vx.set_ylabel("Vx_body [m/s]")
    ax_vy.set_ylabel("Vy_body [m/s]")
    ax_vz.set_ylabel("Vz_body [m/s]")
    ax_speed.set_ylabel("|v_body| [m/s]")
    ax_speed.set_xlabel("t [s] (relative)")

    for ax in axes:
        ax.grid(True)
        ax.legend(loc="best")

    fig.suptitle(f"DVL Body-frame Velocities (BI/BS) - {run_id}")
    out_path = out_dir / f"{run_id}_dvl_body_vel_BI_BS.png"
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[DVL-PLOT] BI/BS body velocities saved: {out_path}")
    return out_path


def _plot_be(df_be: pd.DataFrame, out_dir: Path, run_id: str) -> Path | None:
    if df_be.empty:
        return None

    fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
    ax_ve, ax_vn, ax_vu, ax_speed = axes

    t = df_be["t_s"].to_numpy(dtype=float)
    for col, ax in zip(("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"), (ax_ve, ax_vn, ax_vu)):
        if col in df_be.columns:
            ax.plot(t, df_be[col].to_numpy(dtype=float), label=col)
            ax.set_ylabel(col)
            ax.grid(True)
            ax.legend(loc="best")

    cols = [c for c in ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)") if c in df_be.columns]
    if len(cols) == 3:
        v = df_be[cols].to_numpy(dtype=float)
        speed = np.linalg.norm(v, axis=1)
        ax_speed.plot(t, speed, label="|v_enu|")
        ax_speed.set_ylabel("|v_enu| [m/s]")
        ax_speed.grid(True)
        ax_speed.legend(loc="best")

    ax_speed.set_xlabel("t [s] (relative)")

    fig.suptitle(f"DVL ENU-frame Velocities (BE) - {run_id}")
    out_path = out_dir / f"{run_id}_dvl_enu_vel_BE.png"
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[DVL-PLOT] BE ENU velocities saved: {out_path}")
    return out_path


def _plot_bd(df_bd: pd.DataFrame, out_dir: Path, run_id: str) -> Path | None:
    if df_bd.empty:
        return None

    fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
    ax_de, ax_dn, ax_du, ax_depth = axes

    t = df_bd["t_s"].to_numpy(dtype=float)

    if "De_enu(m)" in df_bd.columns:
        ax_de.plot(t, df_bd["De_enu(m)"].to_numpy(dtype=float), label="De_enu(m)")
        ax_de.set_ylabel("De [m]")
        ax_de.grid(True)
        ax_de.legend(loc="best")
    if "Dn_enu(m)" in df_bd.columns:
        ax_dn.plot(t, df_bd["Dn_enu(m)"].to_numpy(dtype=float), label="Dn_enu(m)")
        ax_dn.set_ylabel("Dn [m]")
        ax_dn.grid(True)
        ax_dn.legend(loc="best")
    if "Du_enu(m)" in df_bd.columns:
        ax_du.plot(t, df_bd["Du_enu(m)"].to_numpy(dtype=float), label="Du_enu(m)")
        ax_du.set_ylabel("Du [m]")
        ax_du.grid(True)
        ax_du.legend(loc="best")

    if "Depth(m)" in df_bd.columns:
        ax_depth.plot(t, df_bd["Depth(m)"].to_numpy(dtype=float), label="Depth(m)")
    if "U(m)" in df_bd.columns:
        ax_depth.plot(t, df_bd["U(m)"].to_numpy(dtype=float), label="U(m)")
    ax_depth.set_ylabel("Depth / U [m]")
    ax_depth.grid(True)
    ax_depth.legend(loc="best")
    ax_depth.set_xlabel("t [s] (relative)")

    fig.suptitle(f"DVL ENU Displacements / Depth (BD) - {run_id}")
    out_path = out_dir / f"{run_id}_dvl_enu_disp_depth_BD.png"
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[DVL-PLOT] BD ENU displacement / depth saved: {out_path}")
    return out_path


# =============================================================================
# Main
# =============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dataset_cfg = Path(args.dataset_config)
    idx = DatasetIndex(dataset_cfg)

    # -------- 解析 DVL 文件路径 --------
    if args.dvl_csv:
        dvl_csv = Path(args.dvl_csv).resolve()
        if not dvl_csv.exists():
            raise FileNotFoundError(f"[DVL] --dvl-csv not found: {dvl_csv}")
        print(f"[DVL] Using explicit --dvl-csv: {dvl_csv}")
    else:
        dvl_csv = _load_dvl_via_dataset(idx, args.run)

    out_root = _ensure_out_dir(Path(args.out_dir) / args.run)

    # -------- 读取 + 清洗 + 拆分 --------
    df = load_and_clean_dvl_parsed_csv(dvl_csv)
    if df.empty:
        print("[DVL] cleaned DVL dataframe is empty, nothing to analyze.")
        return 0

    modes = _split_by_src(df)
    print(f"[DVL] total rows={len(df)}; modes present={list(modes.keys())}")

    for mode, sub in modes.items():
        _print_mode_stats(mode, sub)

    # -------- 绘图：BI/BS/BE/BD --------
    df_bi = modes.get("BI", pd.DataFrame())
    df_bs = modes.get("BS", pd.DataFrame())
    df_be = modes.get("BE", pd.DataFrame())
    df_bd = modes.get("BD", pd.DataFrame())

    _plot_bi_bs(df_bi, df_bs, out_root, args.run)
    _plot_be(df_be, out_root, args.run)
    _plot_bd(df_bd, out_root, args.run)

    print(f"[DVL] Analysis finished. Output dir: {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
