#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
offnav.viz.eskf_frame_check

离线检查 ESKF 与 DVL 速度帧的一致性：

- 读取 ESKF update-audit CSV（*_eskf_update_audit.csv）；
- 过滤出 BE 速度更新、有效更新、速度足够大的样本；
- 计算 “yaw_pre - yaw_meas(由 DVL 速度方向给出)” 的统计量；
- 尝试一组候选的 DVL 帧变换（E/N 互换 & 取负 & ±90° 等），
  对每个候选，计算：
    * dyaw 的统计（mean/std/p50/p90/p95/p99）
    * v_pre ≈ M @ v_meas 的最小二乘线性映射 M
    * M 的极分解：最近正交矩阵 R（含 det/旋转角）、尺度因子 s

使用示例：
  python -m offnav.viz.eskf_frame_check \
      --audit-csv ../out/nav_eskf/2026-01-10_pooltest01/2026-01-10_pooltest01_eskf_update_audit.csv \
      --speed-min 0.10

"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple, Dict, Any, List

import numpy as np
import pandas as pd

from offnav.models.attitude import wrap_angle_pm_pi


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------


def _finite(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return np.isfinite(a)


def _wrap_deg_pm180(a_deg: np.ndarray) -> np.ndarray:
    a_deg = np.asarray(a_deg, dtype=float)
    return (a_deg + 180.0) % 360.0 - 180.0


@dataclass
class FrameCandidate:
    key: str
    description: str


# 预定义一组 DVL vEN 帧变换候选：
# 输入: (vE, vN) -> 输出: (vE', vN')
FRAME_CANDIDATES: Dict[str, FrameCandidate] = {
    "T0_orig": FrameCandidate("T0_orig", "no change (vE,vN)"),
    "T1_swap": FrameCandidate("T1_swap", "swap E/N: (vN, vE)"),
    "T2_negE": FrameCandidate("T2_negE", "flip E: (-vE, vN)"),
    "T3_negN": FrameCandidate("T3_negN", "flip N: (vE, -vN)"),
    "T4_180": FrameCandidate("T4_180", "flip both: (-vE, -vN) ~ +180°"),
    "T5_rot+90": FrameCandidate("T5_rot+90", "rotate +90°: (-vN, vE)"),
    "T6_rot-90": FrameCandidate("T6_rot-90", "rotate -90°: (vN, -vE)"),
}


def _apply_frame_transform(key: str, vE: np.ndarray, vN: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    根据 key 对 (vE,vN) 进行简单线性变换，用于枚举 ENU/NED/符号/互换等假设。
    """
    vE = np.asarray(vE, dtype=float)
    vN = np.asarray(vN, dtype=float)

    if key == "T0_orig":
        return vE, vN
    if key == "T1_swap":
        return vN, vE
    if key == "T2_negE":
        return -vE, vN
    if key == "T3_negN":
        return vE, -vN
    if key == "T4_180":
        return -vE, -vN
    if key == "T5_rot+90":
        # (vE',vN') = (-vN, vE)
        return -vN, vE
    if key == "T6_rot-90":
        # (vE',vN') = (vN, -vE)
        return vN, -vE

    # 默认回退：不变
    return vE, vN


@dataclass
class DyawStats:
    N: int
    mean_deg: float
    std_deg: float
    p50_deg: float
    p90_deg: float
    p95_deg: float
    p99_deg: float


def _compute_dyaw_stats(
    yaw_pre_rad: np.ndarray,
    yaw_meas_rad: np.ndarray,
    const_offset_deg: float = 0.0,
) -> DyawStats:
    """
    计算 dyaw = wrap( yaw_pre - (yaw_meas + const_offset) ) 的统计量（单位 deg）。
    """
    yaw_pre_rad = np.asarray(yaw_pre_rad, dtype=float)
    yaw_meas_rad = np.asarray(yaw_meas_rad, dtype=float)

    mask = _finite(yaw_pre_rad) & _finite(yaw_meas_rad)
    if not np.any(mask):
        return DyawStats(0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan)

    yp = yaw_pre_rad[mask]
    ym = yaw_meas_rad[mask]

    if const_offset_deg != 0.0:
        ym = ym + np.deg2rad(const_offset_deg)

    dyaw = wrap_angle_pm_pi(yp - ym)
    dyaw_deg = np.rad2deg(dyaw)

    return DyawStats(
        N=int(dyaw_deg.size),
        mean_deg=float(np.nanmean(dyaw_deg)),
        std_deg=float(np.nanstd(dyaw_deg)),
        p50_deg=float(np.nanpercentile(dyaw_deg, 50.0)),
        p90_deg=float(np.nanpercentile(dyaw_deg, 90.0)),
        p95_deg=float(np.nanpercentile(dyaw_deg, 95.0)),
        p99_deg=float(np.nanpercentile(dyaw_deg, 99.0)),
    )


@dataclass
class LinearMapResult:
    ok: bool
    M: np.ndarray       # 2x2
    R: np.ndarray       # 2x2 最近正交矩阵
    det_R: float
    rot_deg: float      # 从 R 提取的旋转角（右手，ENU，deg）
    svals: np.ndarray   # 奇异值（尺度因子）
    cond_BBT: float     # B B^T 的条件数


def _estimate_linear_map(vE_pre: np.ndarray, vN_pre: np.ndarray,
                         vE_meas: np.ndarray, vN_meas: np.ndarray) -> LinearMapResult:
    """
    拟合线性映射 M，使得 v_pre ≈ M @ v_meas：
      - v_pre  = [vE_pre; vN_pre] ∈ R^{2×N}
      - v_meas = [vE_meas; vN_meas] ∈ R^{2×N}

    然后对 M 做极分解，得到最近正交矩阵 R 及尺度因子 svals。
    """
    vE_pre = np.asarray(vE_pre, dtype=float)
    vN_pre = np.asarray(vN_pre, dtype=float)
    vE_meas = np.asarray(vE_meas, dtype=float)
    vN_meas = np.asarray(vN_meas, dtype=float)

    # 过滤有限值 & 非零测量
    mask = (
        _finite(vE_pre)
        & _finite(vN_pre)
        & _finite(vE_meas)
        & _finite(vN_meas)
    )
    # 至少需要若干点
    if np.count_nonzero(mask) < 10:
        return LinearMapResult(False, np.full((2, 2), np.nan), np.full((2, 2), np.nan),
                               np.nan, np.nan, np.full((2,), np.nan), np.nan)

    vp = np.vstack([vE_pre[mask], vN_pre[mask]])   # 2×N
    vm = np.vstack([vE_meas[mask], vN_meas[mask]])  # 2×N

    # BBT = vm vm^T
    BBT = vm @ vm.T  # 2x2
    # 数值稳定性检查
    eigvals = np.linalg.eigvalsh(BBT)
    if np.any(eigvals <= 0.0):
        cond = np.inf
    else:
        cond = float(np.max(eigvals) / np.min(eigvals))

    eps = 1e-12
    BBT_reg = BBT + eps * np.eye(2, dtype=float)

    try:
        BBT_inv = np.linalg.inv(BBT_reg)
    except np.linalg.LinAlgError:
        return LinearMapResult(False, np.full((2, 2), np.nan), np.full((2, 2), np.nan),
                               np.nan, np.nan, np.full((2,), np.nan), cond)

    # M = vp vm^T (vm vm^T)^-1
    M = vp @ vm.T @ BBT_inv  # 2x2

    # 极分解: M = R S, 其中 R 为正交矩阵，S 为对称正定
    U, svals, Vt = np.linalg.svd(M)
    R = U @ Vt
    det_R = float(np.linalg.det(R))

    # 从 R 提取旋转角：R = [[cosθ, -sinθ]; [sinθ, cosθ]] 或带反射
    # 即使 det<0，这个角也只是“伴随反射”的旋转部分，用于定性分析
    theta_rad = np.arctan2(R[1, 0], R[0, 0])
    rot_deg = float(np.rad2deg(theta_rad))

    return LinearMapResult(True, M, R, det_R, rot_deg, svals, cond)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def run_frame_check(
    audit_csv: Path,
    speed_min: float = 0.0,
    speed_max: float | None = None,
) -> None:
    print(f"[FRAME-CHECK] Loading audit CSV: {audit_csv}")
    df = pd.read_csv(audit_csv)

    # 1) 基本字段存在性检查
    required_cols = ["vE", "vN", "vE_pre", "vN_pre", "speed_h"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"audit CSV 缺少必要列：{missing}，请检查 eskf_runner 中的审计输出。")

    # 可选过滤：只看 BE 速度、只看 used==1
    if "src" in df.columns:
        df = df[df["src"].astype(str).str.upper() == "BE"]
    if "used" in df.columns:
        df = df[df["used"] > 0.5]

    # 速度筛选
    speed = df["speed_h"].to_numpy(dtype=float)
    mask = _finite(speed)
    if speed_min is not None and speed_min > 0.0:
        mask &= (speed >= speed_min)
    if speed_max is not None and np.isfinite(speed_max):
        mask &= (speed <= speed_max)

    df = df[mask].copy()
    print(f"[FRAME-CHECK] After BE/used/speed filter: N = {len(df)}")

    if len(df) == 0:
        print("[FRAME-CHECK] 没有符合条件的样本，无法分析。")
        return

    # 提取基础数组
    vE = df["vE"].to_numpy(dtype=float)
    vN = df["vN"].to_numpy(dtype=float)
    vE_pre = df["vE_pre"].to_numpy(dtype=float)
    vN_pre = df["vN_pre"].to_numpy(dtype=float)

    # 用速度方向构造“航向”（rad）
    yaw_meas_rad_base = np.arctan2(vN, vE)
    yaw_pre_rad_base = np.arctan2(vN_pre, vE_pre)

    # ----------------------------------------------------------------------
    # 0) 原始 dyaw 统计 + 常数 yaw 偏置试探
    # ----------------------------------------------------------------------
    stats0 = _compute_dyaw_stats(yaw_pre_rad_base, yaw_meas_rad_base, const_offset_deg=0.0)
    print("[FRAME-CHECK] Basic stats (no offset):")
    print(f"  N = {stats0.N}")
    print(f"  mean(dyaw_deg) = {stats0.mean_deg:.3f} deg")
    print(f"  std(dyaw_deg)  = {stats0.std_deg:.3f} deg")
    print(
        f"  p50/p90/p95/p99 = "
        f"{stats0.p50_deg:.2f} / {stats0.p90_deg:.2f} / {stats0.p95_deg:.2f} / {stats0.p99_deg:.2f} deg"
    )
    print()

    offsets = [0.0, 90.0, -90.0, 180.0, -180.0]
    print("[FRAME-CHECK] Try constant yaw offsets:")
    best_std = np.inf
    best_off = None
    for off in offsets:
        st = _compute_dyaw_stats(yaw_pre_rad_base, yaw_meas_rad_base, const_offset_deg=off)
        print(
            f"  offset = {off:6.1f} deg -> std={st.std_deg:7.3f} deg, mean={st.mean_deg:7.3f} deg"
        )
        if st.N > 0 and np.isfinite(st.std_deg) and st.std_deg < best_std:
            best_std = st.std_deg
            best_off = off
    print()
    if best_off is not None:
        print(
            f"[FRAME-CHECK] Best constant offset (among candidates) ≈ {best_off:+.1f} deg "
            f"with std ≈ {best_std:.3f} deg"
        )
    else:
        print("[FRAME-CHECK] 无法从常数偏置中找到合理的候选（全部 NaN）。")
    print()

    # ----------------------------------------------------------------------
    # 1) 对多种 DVL 帧变换做线性映射拟合 + dyaw 统计
    # ----------------------------------------------------------------------
    print("[FRAME-CHECK] Estimating linear maps for multiple DVL frame candidates...\n")

    results: List[Dict[str, Any]] = []

    for key, fc in FRAME_CANDIDATES.items():
        vE_m, vN_m = _apply_frame_transform(key, vE, vN)

        # 用变换后的 DVL 速度方向重新定义航向
        yaw_meas_rad = np.arctan2(vN_m, vE_m)
        yaw_pre_rad = yaw_pre_rad_base  # 仍然用 v_pre 的速度方向

        st = _compute_dyaw_stats(yaw_pre_rad, yaw_meas_rad, const_offset_deg=0.0)

        lm = _estimate_linear_map(vE_pre, vN_pre, vE_m, vN_m)

        res: Dict[str, Any] = {
            "key": key,
            "desc": fc.description,
            "N": st.N,
            "dyaw_std_deg": st.std_deg,
            "dyaw_mean_deg": st.mean_deg,
            "dyaw_p50_deg": st.p50_deg,
            "det_R": lm.det_R,
            "rot_deg": lm.rot_deg,
            "s1": np.nan,
            "s2": np.nan,
            "cond_BBT": lm.cond_BBT,
        }
        if lm.ok and lm.svals is not None and lm.svals.size >= 2:
            res["s1"] = float(lm.svals[0])
            res["s2"] = float(lm.svals[1])

        results.append(res)

    # 按 dyaw_std 排序打印
    results_sorted = sorted(results, key=lambda r: (np.isnan(r["dyaw_std_deg"]), r["dyaw_std_deg"]))

    print("[FRAME-CHECK] Candidate summary (sorted by dyaw_std_deg):")
    print(
        "  {key:10s} | {N:6s} | {dyaw_std:9s} | {dyaw_mean:9s} | {detR:7s} | {rot:9s} | {s1:8s} | {s2:8s}".format(
            key="key",
            N="N",
            dyaw_std="std(dyaw)",
            dyaw_mean="mean(dyaw)",
            detR="det(R)",
            rot="rot_deg",
            s1="s1",
            s2="s2",
        )
    )
    for r in results_sorted:
        print(
            "  {key:10s} | {N:6d} | {dyaw_std:9.3f} | {dyaw_mean:9.3f} | {detR:7.3f} | {rot:9.2f} | {s1:8.3f} | {s2:8.3f}".format(
                key=r["key"],
                N=r["N"],
                dyaw_std=r["dyaw_std_deg"],
                dyaw_mean=r["dyaw_mean_deg"],
                detR=r["det_R"],
                rot=r["rot_deg"],
                s1=r["s1"],
                s2=r["s2"],
            )
        )
    print()

    # 简单给一点文字层面的提示
    print("[FRAME-CHECK][HINT]")
    print("  - 对于一个“理想”的 ENU 帧对齐候选，我们期待：")
    print("      * dyaw_std_deg 较小（例如 < 20°~30°）；")
    print("      * det(R) ≈ +1（纯旋转，无反射）；")
    print("      * rot_deg ≈ 0°（或你已知的结构性偏角，比如 +90° 帧差）；")
    print("      * s1,s2 接近 1（速度尺度匹配良好）。")
    print("  - 如果所有候选 det(R) 都 ≈ -1，说明存在反射（某个轴取负/交换后再取负）；")
    print("  - 如果某个候选 dyaw_std 明显变小、det(R)→+1，基本就锁定了 DVL BE->nav 的帧映射。")
    print()
    print("[FRAME-CHECK] Done.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ESKF / DVL 帧一致性离线检查工具（eskf_frame_check）"
    )
    parser.add_argument(
        "--audit-csv",
        type=str,
        required=True,
        help="ESKF update-audit CSV 文件路径（如 *_eskf_update_audit.csv）",
    )
    parser.add_argument(
        "--speed-min",
        type=float,
        default=0.0,
        help="只分析水平速度模长 >= speed_min 的样本（m/s），默认 0.0",
    )
    parser.add_argument(
        "--speed-max",
        type=float,
        default=None,
        help="若指定，则只分析 |v_h| <= speed_max 的样本（m/s），默认不限制",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    audit_csv = Path(args.audit_csv)
    if not audit_csv.is_file():
        raise FileNotFoundError(f"audit CSV 不存在: {audit_csv}")

    run_frame_check(
        audit_csv=audit_csv,
        speed_min=float(args.speed_min),
        speed_max=float(args.speed_max) if args.speed_max is not None else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
