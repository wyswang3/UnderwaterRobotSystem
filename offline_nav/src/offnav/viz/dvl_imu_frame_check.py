# src/offnav/viz/dvl_imu_frame_check.py
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd


# =============================================================================
# 小工具
# =============================================================================

_TIME_COL_CANDIDATES = ("t_s", "EstS", "MonoS", "EstNS", "MonoNS")


def _wrap_pm_pi(a: np.ndarray) -> np.ndarray:
    """把角度 wrap 到 (-pi, pi]."""
    return (a + np.pi) % (2.0 * np.pi) - np.pi


def _pick_time_s(df: pd.DataFrame, src: str) -> np.ndarray:
    """从 DataFrame 中挑一个时间列，返回 float 秒数组。"""
    for c in _TIME_COL_CANDIDATES:
        if c in df.columns:
            t = df[c].to_numpy(dtype=float)
            # 如果是 ns，转成 s
            if c.endswith("NS"):
                t = t * 1e-9
            print(f"[{src}] 使用时间列: {c}, t=[{t[0]:.3f}, {t[-1]:.3f}], N={len(t)}")
            return t
    raise RuntimeError(f"[{src}] 找不到时间列，已尝试: {_TIME_COL_CANDIDATES}")


def _pick_yaw_from_imu(df_imu: pd.DataFrame) -> Tuple[np.ndarray, str]:
    """
    从 IMU 预处理 CSV 中挑一个 yaw 序列（单位 rad），并做 unwrap。
    优先级：
      1) yaw_nav_rad
      2) yaw_device_rad
      3) YawEst_unwrapped_deg
      4) YawEst_deg
      5) AngZ_deg / YawDeg
    """
    # 1) 直接 rad 列
    for col in ("yaw_nav_rad", "yaw_device_rad", "yaw_rad"):
        if col in df_imu.columns:
            yaw = df_imu[col].to_numpy(dtype=float)
            # 做一次 unwrap，避免跨 ±pi 的断裂
            yaw_un = np.unwrap(yaw)
            print(f"[IMU] 使用 yaw 列( rad ): {col}")
            return yaw_un, col

    # 2) 角度制（已经去掉跳变）
    if "YawEst_unwrapped_deg" in df_imu.columns:
        yaw_deg = df_imu["YawEst_unwrapped_deg"].to_numpy(dtype=float)
        yaw_un = np.deg2rad(yaw_deg)
        print("[IMU] 使用 yaw 列( deg ): YawEst_unwrapped_deg")
        return yaw_un, "YawEst_unwrapped_deg"

    # 3) 普通角度制（未 unwrap）
    for col in ("YawEst_deg", "AngZ_deg", "YawDeg"):
        if col in df_imu.columns:
            yaw_deg = df_imu[col].to_numpy(dtype=float)
            yaw_rad = np.deg2rad(yaw_deg)
            yaw_un = np.unwrap(yaw_rad)
            print(f"[IMU] 使用 yaw 列( deg ): {col}，内部已 unwrap")
            return yaw_un, col

    raise RuntimeError("[IMU] 找不到合适的 yaw 列，请检查 imu_filtered.csv 的表头。")


def _extract_be_vel_enu(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    从 DVL BE CSV 中提取 ENU 速度分量 (Ve, Vn, Vu)，返回三个等长 1D ndarray。
    尝试若干常见列名组合：VelE_mps / VelN_mps / VelU_mps 等。
    """
    candidates = [
        ("VelE_mps", "VelN_mps", "VelU_mps"),
        ("vE", "vN", "vU"),
        ("E_mps", "N_mps", "U_mps"),
        ("Ve", "Vn", "Vu"),
        # ★ 新增一组：和你现在的 dvl_BE 表头匹配
        ("Ve_enu(m_s)", "Vn_enu(m_s)", "Vu_enu(m_s)"),
    ]

    for cols in candidates:
        if all(c in df.columns for c in cols):
            Ve = df[cols[0]].to_numpy(dtype=float)
            Vn = df[cols[1]].to_numpy(dtype=float)
            Vu = df[cols[2]].to_numpy(dtype=float)
            print(f"[DVL-BE] 使用速度列: {cols}")
            return Ve, Vn, Vu

    # 如果没找到，打印表头帮助排查
    print("[DVL-BE][ERROR] 找不到 ENU 速度列，当前列名如下：")
    print(list(df.columns))
    raise RuntimeError("[DVL-BE] 无法识别 ENU 速度列，请在脚本中补充列名组合。")



def _extract_bi_vel_body(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    从 DVL BI CSV 中提取设备/体坐标系速度分量 (Vx, Vy, Vz)。
    """
    candidates = [
        ("VelBx_mps", "VelBy_mps", "VelBz_mps"),
        ("Vx_body_mps", "Vy_body_mps", "Vz_body_mps"),
        ("Vx", "Vy", "Vz"),
        # ★ 新增一组：和你现在的 dvl_BE 表头匹配
        ("Vx_body(m_s)", "Vy_body(m_s)", "Vz_body(m_s)"),
    ]

    for cols in candidates:
        if all(c in df.columns for c in cols):
            Vx = df[cols[0]].to_numpy(dtype=float)
            Vy = df[cols[1]].to_numpy(dtype=float)
            Vz = df[cols[2]].to_numpy(dtype=float)
            print(f"[DVL-BI] 使用速度列: {cols}")
            return Vx, Vy, Vz

    print("[DVL-BI][ERROR] 找不到体坐标速度列，当前列名如下：")
    print(list(df.columns))
    raise RuntimeError("[DVL-BI] 无法识别 BI 速度列，请在脚本中补充列名组合。")


def _apply_quality_mask(df: pd.DataFrame) -> np.ndarray:
    """
    基于 GateOk / SpeedOk / Valid 等字段生成质量 mask。
    字段缺失时不强制过滤。
    """
    mask = np.ones(len(df), dtype=bool)

    for col in ("GateOk", "SpeedOk", "Valid"):
        if col in df.columns:
            # 约定：1 / True 表示 OK
            v = df[col].to_numpy()
            if v.dtype == bool:
                mask &= v
            else:
                mask &= (v.astype(float) > 0.5)

    return mask


# =============================================================================
# 诊断 1：DVL BE vs DVL BI 帧关系（纯 DVL 视角）
# =============================================================================

def dvl_be_bi_frame_check(
    df_be: pd.DataFrame,
    df_bi: pd.DataFrame,
    speed_min: float = 0.05,
) -> None:
    """
    用最小二乘拟合一个 2x2 线性映射 M，使得：
        [Ve; Vn] ≈ M @ [Vx; Vy]
    并做极分解，估计旋转角和尺度因子，帮助理解 DVL 内部 BE / BI 帧关系。
    """
    print("\n[CHECK-1] DVL BE vs BI 帧关系诊断（纯 DVL）")

    # 时间与速度
    t_be = _pick_time_s(df_be, "DVL-BE")
    Ve, Vn, Vu = _extract_be_vel_enu(df_be)
    t_bi = _pick_time_s(df_bi, "DVL-BI")
    Vx, Vy, Vz = _extract_bi_vel_body(df_bi)

    # 质量过滤
    mask_be = _apply_quality_mask(df_be)
    mask_bi = _apply_quality_mask(df_bi)

    # 统一到 BE 时间轴上，在 BI 时间轴上插值 (Vx, Vy)
    # 只关心水平速度
    speed_be_h = np.hypot(Ve, Vn)
    mask_speed = speed_be_h >= speed_min

    # 可用样本：BE 有效 & BI 插值范围内 & 质量 OK
    t_min_bi, t_max_bi = float(t_bi[0]), float(t_bi[-1])
    mask_time = (t_be >= t_min_bi) & (t_be <= t_max_bi)

    mask = mask_be & mask_bi[np.clip(
        np.searchsorted(t_bi, t_be, side="left"), 0, len(t_bi)-1
    )] & mask_speed & mask_time

    if np.count_nonzero(mask) < 100:
        print(f"[CHECK-1][WARN] 可用样本太少(N={np.count_nonzero(mask)}), 结果可能不稳定。")

    t_use = t_be[mask]
    Ve_use = Ve[mask]
    Vn_use = Vn[mask]

    # 在 BI 时间轴插值 Vx, Vy
    Vx_interp = np.interp(t_use, t_bi, Vx)
    Vy_interp = np.interp(t_use, t_bi, Vy)

    # 构造最小二乘问题：Y ≈ X @ M^T
    # X: (N,2) = [Vx, Vy]，Y: (N,2) = [Ve, Vn]
    X = np.stack([Vx_interp, Vy_interp], axis=1)
    Y = np.stack([Ve_use, Vn_use], axis=1)

    # 只用有限值
    finite_mask = np.isfinite(X).all(axis=1) & np.isfinite(Y).all(axis=1)
    X = X[finite_mask]
    Y = Y[finite_mask]

    N = X.shape[0]
    print(f"[CHECK-1] 可用于拟合的样本数 N={N}")
    if N < 10:
        print("[CHECK-1][ERROR] 可用样本数太少，无法可靠估计 M。")
        return

    # 最小二乘求解 M
    # 我们希望 Y ≈ X @ M^T => 对每个维度单独做 lstsq
    M = np.zeros((2, 2), dtype=float)
    for i in range(2):
        # 解 X @ m_i ≈ Y[:, i]
        mi, *_ = np.linalg.lstsq(X, Y[:, i], rcond=None)
        M[i, :] = mi

    print("[CHECK-1] 最小二乘线性映射 M (使 [Ve,Vn]^T ≈ M @ [Vx,Vy]^T)：")
    print(f"  M =\n    [{M[0,0]: .4f}  {M[0,1]: .4f}]\n    [{M[1,0]: .4f}  {M[1,1]: .4f}]")

    # 极分解（正交矩阵 R + 对称正定矩阵 S）
    U, s, Vt = np.linalg.svd(M)
    R = U @ Vt
    # 确保 R 为“旋转或反射”，调整 det 符号
    det_R = float(np.linalg.det(R))
    if det_R < 0:
        U[:, -1] *= -1
        R = U @ Vt
        det_R = float(np.linalg.det(R))

    # 对应旋转角（右手系 ENU）
    rot_rad = np.arctan2(R[1, 0], R[0, 0])
    rot_deg = float(np.rad2deg(rot_rad))

    print("\n[CHECK-1] 极分解结果：")
    print(f"  R (近似旋转矩阵) =\n"
          f"    [{R[0,0]: .4f}  {R[0,1]: .4f}]\n"
          f"    [{R[1,0]: .4f}  {R[1,1]: .4f}]")
    print(f"  det(R)       = {det_R: .4f}")
    print(f"  rotation_deg = {rot_deg: .2f} deg  (BE 与 BI 水平平面的相对旋转)")
    print(f"  singular s   = [{s[0]: .4f}, {s[1]: .4f}] (尺度因子)")

    print("\n[CHECK-1][HINT]")
    print("  - 若 det(R)≈+1 且 rotation_deg≈某个常数(如 +θ)，说明 BE 与 BI 主要是旋转 + 尺度；")
    print("  - 若 det(R)≈-1，说明存在反射（例如某个轴取负、或交换轴后再取负）；")
    print("  - s 接近 1 表示速度尺度一致，远离 1 表示 DVL 内部对 BE/BI 的标度不一致或我们列名选错。")


# =============================================================================
# 诊断 2：DVL BE 速度方向 vs IMU yaw 对齐情况
# =============================================================================
def be_vs_imu_yaw_check(
    df_be: pd.DataFrame,
    df_imu: pd.DataFrame,
    speed_min: float = 0.05,
) -> None:
    """
    在纯传感器层面检查：
        yaw_imu(t)  vs  yaw_dvl(t)

    这里我们约定：
      - DVL BE 提供 ENU 速度 (Ve, Vn, Vu)，单位 m/s；
      - IMU 预处理提供 yaw_nav_rad（或 yaw_device_rad / yaw_rad），单位 rad；
      - DVL 方向 yaw_dvl 采用和 deadreckon / ESKF 一致的定义：
            yaw_dvl = atan2(Ve, Vn)
        即：yaw=0 对应“正北( +N )”，yaw>0 顺时针/逆时针取决于你的 R_nb 约定，
        但我们只关心 yaw_imu - yaw_dvl 的差值分布。

    注意：本检查完全绕开 ESKF，仅用原始预处理 CSV。
    """
    print("\n[CHECK-2] DVL BE 速度方向 vs IMU yaw 诊断（纯传感器）")

    # ------------------------------------------------------------------
    # 1) DVL-BE 时间 & 速度
    # ------------------------------------------------------------------
    t_be = _pick_time_s(df_be, "DVL-BE")        # 形如 EstS
    Ve, Vn, Vu = _extract_be_vel_enu(df_be)
    speed_be_h = np.hypot(Ve, Vn)

    N_be = len(t_be)
    print(f"[CHECK-2][DVL-BE] t=[{t_be.min():.3f}, {t_be.max():.3f}], N={N_be}")
    print("[CHECK-2][DVL-BE] 使用列: Ve_enu/Vn_enu/Vu_enu (m/s)")

    # 质量门控（GateOk/SpeedOk/Valid 等），如果没有合适列，就退化为全 True
    mask_quality = _apply_quality_mask(df_be)
    mask_quality = np.asarray(mask_quality, dtype=bool)
    if mask_quality.shape[0] != N_be:
        raise RuntimeError(f"[CHECK-2][ERROR] mask_quality 长度 {mask_quality.shape[0]} != N_be {N_be}")

    # 速度门限
    mask_speed = speed_be_h >= float(speed_min)

    # ------------------------------------------------------------------
    # 2) IMU 时间 & yaw（注意处理 NaN）
    # ------------------------------------------------------------------
    t_imu = _pick_time_s(df_imu, "IMU")         # 形如 t_s
    yaw_unwrapped, yaw_col = _pick_yaw_from_imu(df_imu)

    # 过滤掉 NaN，避免 t_max_imu 变成 nan
    imu_finite_mask = np.isfinite(t_imu)
    if not np.any(imu_finite_mask):
        print("[CHECK-2][ERROR] IMU 时间列全是 NaN，无法进行检查。")
        return

    t_imu_finite = t_imu[imu_finite_mask]
    t_min_imu = float(t_imu_finite.min())
    t_max_imu = float(t_imu_finite.max())

    print(f"[CHECK-2][IMU]    t=[{t_min_imu:.3f}, {t_max_imu:.3f}], "
          f"N={len(t_imu)} (finite={imu_finite_mask.sum()})")
    print(f"[CHECK-2][IMU]    使用 yaw 列( rad ): {yaw_col}")

    # 只保留落在 IMU 有效时间覆盖区间内的 DVL 样本
    mask_time = (t_be >= t_min_imu) & (t_be <= t_max_imu)

    # ------------------------------------------------------------------
    # 3) 统计每层 mask 的通过数量，检查“是哪里把样本杀完了”
    # ------------------------------------------------------------------
    n_quality = int(mask_quality.sum())
    n_speed   = int(mask_speed.sum())
    n_time    = int(mask_time.sum())

    mask_all = mask_quality & mask_speed & mask_time
    n_all    = int(mask_all.sum())

    print(f"[CHECK-2][MASK] 质量通过 N_quality = {n_quality}/{N_be}")
    print(f"[CHECK-2][MASK] 速度通过 N_speed   = {n_speed}/{N_be} (speed_min={speed_min} m/s)")
    print(f"[CHECK-2][MASK] 时间重叠 N_time    = {n_time}/{N_be} (与 IMU t_s 区间交集)")
    print(f"[CHECK-2][MASK] 全部通过 N_all     = {n_all}/{N_be}")

    if n_all == 0:
        print("[CHECK-2][WARN] N_all==0，无法进行 yaw_imu vs yaw_dvl 分析。")
        print("                 请检查：")
        print("                 1) DVL 质量标志列是否过于严格（_apply_quality_mask 的逻辑）；")
        print("                 2) speed_min 是否设得太高（可尝试 0.0 或 0.02 再看）；")
        print("                 3) IMU t_s 与 DVL EstS 的重叠时段是否充足。")
        return

    if n_all < 100:
        print(f"[CHECK-2][WARN] 可用样本较少 (N_all={n_all})，统计结果可能不稳定。")

    # 选出通过全部 mask 的样本
    t_use   = t_be[mask_all]
    Ve_use  = Ve[mask_all]
    Vn_use  = Vn[mask_all]
    # Vu_use = Vu[mask_all]  # 当前不使用垂向分量

    # ------------------------------------------------------------------
    # 4) 在 IMU 时间轴上插值 yaw_unwrapped，再 wrap 回 [-pi,pi]
    # ------------------------------------------------------------------
    yaw_interp_un = np.interp(t_use, t_imu, yaw_unwrapped)
    yaw_imu = _wrap_pm_pi(yaw_interp_un)

    print(f"[CHECK-2] 使用 IMU yaw 列: {yaw_col}")
    print(f"[CHECK-2] 最终可用样本数 N={len(t_use)}")

    # ------------------------------------------------------------------
    # 5) 候选的 (Ve,Vn) 帧变换，与 eskf_frame_check 保持一致
    # ------------------------------------------------------------------
    def cand_T0(vE, vN):  # 原始 ENU
        return vE, vN

    def cand_T1(vE, vN):  # swap
        return vN, vE

    def cand_T2(vE, vN):  # -E
        return -vE, vN

    def cand_T3(vE, vN):  # -N
        return vE, -vN

    def cand_T4(vE, vN):  # 180deg
        return -vE, -vN

    def cand_T5(vE, vN):  # rot +90
        return -vN, vE

    def cand_T6(vE, vN):  # rot -90
        return vN, -vE

    candidates: Dict[str, callable] = {
        "T0_orig":   cand_T0,
        "T1_swap":   cand_T1,
        "T2_negE":   cand_T2,
        "T3_negN":   cand_T3,
        "T4_180":    cand_T4,
        "T5_rot+90": cand_T5,
        "T6_rot-90": cand_T6,
    }

    # 常数偏置候选（考虑 IMU yaw 与 DVL 方向可能有固定安装角）
    offsets_deg = [0.0, 90.0, -90.0, 180.0, -180.0]

    summary_rows = []

    for key, fn in candidates.items():
        vE_c, vN_c = fn(Ve_use, Vn_use)

        # ★ 关键：这里采用 yaw_dvl = atan2(Ve, Vn)，与 deadreckon / ESKF 保持一致
        yaw_dvl = np.arctan2(vE_c, vN_c)

        dyaw = _wrap_pm_pi(yaw_imu - yaw_dvl)
        dyaw_deg = np.rad2deg(dyaw)

        # N 小时 nanpercentile 也安全，min(N,4)=N
        mean0 = float(np.nanmean(dyaw_deg))
        std0  = float(np.nanstd(dyaw_deg))
        p50, p90, p95, p99 = np.nanpercentile(dyaw_deg, [50.0, 90.0, 95.0, 99.0])

        print(f"\n[CHECK-2] Candidate {key}:")
        print("  Basic stats (no offset):")
        print(f"    mean(dyaw_deg) = {mean0: .3f}")
        print(f"    std(dyaw_deg)  = {std0: .3f}")
        print(f"    p50/p90/p95/p99 = {p50: .2f} / {p90: .2f} / {p95: .2f} / {p99: .2f}")

        # 常数 yaw 偏置扫描
        best_std = std0
        best_off = 0.0
        for off_deg in offsets_deg:
            off_rad = np.deg2rad(off_deg)
            dyaw_off = _wrap_pm_pi(dyaw - off_rad)
            dyaw_off_deg = np.rad2deg(dyaw_off)
            std_off  = float(np.nanstd(dyaw_off_deg))
            mean_off = float(np.nanmean(dyaw_off_deg))
            print(f"    offset = {off_deg:6.1f} deg -> std={std_off: .3f} deg, mean={mean_off: .3f} deg")
            if std_off < best_std:
                best_std = std_off
                best_off = off_deg

        summary_rows.append((key, len(dyaw_deg), std0, mean0, best_off, best_std))

    # ------------------------------------------------------------------
    # 6) 汇总排序
    # ------------------------------------------------------------------
    summary_rows.sort(key=lambda r: r[5])  # 按 best_std 排序

    print("\n[CHECK-2] Candidate summary (按最佳常数偏置后的 std 排序):")
    print("  key        | N      | std0(deg) | mean0(deg) | best_off(deg) | best_std(deg)")
    for key, N_c, std0, mean0, best_off, best_std in summary_rows:
        print(
            f"  {key:10s} | {N_c:6d} | {std0:9.3f} | {mean0:10.3f} |"
            f" {best_off:12.1f} | {best_std:13.3f}"
        )

    print("\n[CHECK-2][HINT]")
    print("  - 理想情况下，应该存在某个候选(轴交换/取负/±90°旋转) + 某个常数偏置，")
    print("    使得 best_std 降到 10°~20° 量级，这说明 IMU yaw ↔ DVL 方向几何关系是自洽的；")
    print("  - 若所有候选的 best_std 都 >60°，说明 DVL BE 的方向定义或 IMU yaw 与我们假设的 ENU/安装关系严重不一致；")
    print("  - 该检查完全基于原始 IMU yaw 与 DVL BE 速度，与 ESKF 状态建模、噪声矩阵无关。")

# =============================================================================
# CLI
# =============================================================================

def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="DVL/IMU 原始数据帧检查工具（脱离 ESKF，仅看传感器几何）"
    )
    ap.add_argument(
        "--imu-csv",
        required=True,
        help="IMU 预处理 CSV 路径（例如 out/proc/..._imu_filtered.csv）",
    )
    ap.add_argument(
        "--dvl-be-csv",
        required=True,
        help="DVL BE 预处理 CSV 路径（例如 out/proc/..._dvl_BE.csv）",
    )
    ap.add_argument(
        "--dvl-bi-csv",
        required=False,
        help="DVL BI 预处理 CSV 路径（例如 out/proc/..._dvl_BI.csv），若给出则做 BE vs BI 帧检查",
    )
    ap.add_argument(
        "--speed-min",
        type=float,
        default=0.05,
        help="用于统计/拟合的最小水平速度阈值（m/s），默认 0.05",
    )

    args = ap.parse_args(argv)

    imu_path = Path(args.imu_csv)
    be_path = Path(args.dvl_be_csv)
    bi_path = Path(args.dvl_bi_csv) if args.dvl_bi_csv else None

    print(f"[ARGS] IMU CSV    : {imu_path}")
    print(f"[ARGS] DVL BE CSV : {be_path}")
    if bi_path is not None:
        print(f"[ARGS] DVL BI CSV : {bi_path}")
    print(f"[ARGS] speed_min  : {args.speed_min} m/s")

    if not imu_path.is_file():
        raise FileNotFoundError(f"IMU CSV 不存在: {imu_path}")
    if not be_path.is_file():
        raise FileNotFoundError(f"DVL BE CSV 不存在: {be_path}")
    if bi_path is not None and not bi_path.is_file():
        raise FileNotFoundError(f"DVL BI CSV 不存在: {bi_path}")

    # 读取 CSV
    df_imu = pd.read_csv(imu_path)
    df_be = pd.read_csv(be_path)
    df_bi = pd.read_csv(bi_path) if bi_path is not None else None

    # 诊断 1：BE vs BI（若有 BI）
    if df_bi is not None:
        dvl_be_bi_frame_check(df_be, df_bi, speed_min=args.speed_min)
    else:
        print("\n[CHECK-1] 未提供 DVL BI CSV，跳过 BE vs BI 帧检查。")

    # 诊断 2：BE vs IMU yaw
    be_vs_imu_yaw_check(df_be, df_imu, speed_min=args.speed_min)

    print("\n[DVL-IMU-FRAME-CHECK] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
