from __future__ import annotations

"""
Factor-graph based offline navigation pipeline (IMU + DVL, LV1 bias model).

本模块提供与 eskf_runner.py 类似的“离线轨迹求解主入口”，但使用的是
因子图 + Gauss-Newton 平滑，而不是在线 ESKF。

LV1 版主要思路：
- 以 IMU 时间轴为基础，先对每个 IMU 样本做粗略 dead-reckon 得到 states_full；
- 在 Graph 管线里按 stride + max_nodes 从 IMU 时间轴选出关键帧：
    * 关键帧索引数组 kfs （指向 IMU 全时间轴）
    * 节点时间轴 t_nodes = t_imu[kfs]
    * 图中节点状态列表 states_init = [states_full[k] for k in kfs]
- 因子构图：
    * 先验因子：约束第一个关键帧 + 全局 bias
    * IMU 过程因子：仅在相邻关键帧 i -> i+1 之间建边（LV1 简化）
    * DVL BE 速度因子：约束对应关键帧的 v_k (ENU)
    * DVL BI 速度因子：约束 v_k + yaw_k 经 R_bn 投影到体坐标
    * yaw-from-vel 因子：用 DVL ENU 速度构造“航向角”观测约束 yaw_k
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np

from offnav.core.types import ImuRawData, DvlRawData, Trajectory
from offnav.core.nav_config import GraphConfig
from offnav.graph.states import (
    GraphState,
    BiasState,
    pack_theta,
    unpack_theta,
    wrap_yaw,
)
from offnav.graph.factors import (
    PriorStateBiasFactor,
    ImuProcessFactor,
    DvlBEVelFactor,
    DvlBIVelFactor,
    YawFromVelFactor,
)
from offnav.graph.smoothing import gauss_newton_solve, GaussNewtonStats
from offnav.models.attitude import AttitudeRPY, rpy_to_R_nb
from offnav.preprocess.imu_processing import (
    ImuProcessedData,
    load_imu_processed_csv,
)
from offnav.preprocess.dvl_processing import (
    DvlProcessedData,
    load_dvl_processed_csv,
)


# ============================================================
# 时间轴工具（与 eskf_runner 保持一致）
# ============================================================


def _get_time_s_from_imu(imu: ImuRawData) -> np.ndarray:
    df = imu.df
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    elif "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    elif "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    elif "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    else:
        raise KeyError("IMU df has no EstS/MonoS/EstNS/MonoNS time column.")


def _get_time_s_from_dvl_df(df) -> np.ndarray:
    if "EstS" in df.columns:
        return df["EstS"].to_numpy(dtype=float)
    elif "MonoS" in df.columns:
        return df["MonoS"].to_numpy(dtype=float)
    elif "EstNS" in df.columns:
        return df["EstNS"].to_numpy(dtype=float) * 1e-9
    elif "MonoNS" in df.columns:
        return df["MonoNS"].to_numpy(dtype=float) * 1e-9
    else:
        raise KeyError("DVL df has no EstS/MonoS/EstNS/MonoNS time column.")


def _find_nearest_index(
    t_array: np.ndarray,
    t_q: float,
    max_gap_s: float,
) -> Optional[int]:
    """
    在给定时间轴 t_array 上找到与 t_q 最近的索引 k，
    如果最近时间差 > max_gap_s 则返回 None。
    """
    n = t_array.shape[0]
    if n == 0:
        return None

    idx = np.searchsorted(t_array, t_q)
    candidates: List[int] = []
    if 0 <= idx < n:
        candidates.append(idx)
    if 0 <= idx - 1 < n:
        candidates.append(idx - 1)
    if not candidates:
        return None

    best_k: Optional[int] = None
    best_dt: Optional[float] = None
    for k in candidates:
        dt = abs(float(t_array[k]) - t_q)
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best_k = k

    if best_dt is not None and best_dt <= max_gap_s:
        return best_k
    return None


def _select_keyframe_indices(
    t_imu: np.ndarray,
    *,
    keyframe_stride: int,
    max_nodes: int | None,
) -> np.ndarray:
    """
    根据 stride + max_nodes 从 IMU 时间轴里选出关键帧索引。
    例如：
        keyframe_stride=10 => 每 10 帧取一帧；
        max_nodes=1000     => 最多取前 1000 个关键帧。
    """
    n_imu = t_imu.shape[0]
    if n_imu == 0:
        return np.zeros((0,), dtype=int)

    stride = max(1, int(keyframe_stride))
    idx = np.arange(n_imu, dtype=int)[::stride]
    if max_nodes is not None and idx.shape[0] > max_nodes:
        idx = idx[:max_nodes]
    return idx


# ============================================================
# Graph 诊断信息
# ============================================================


@dataclass
class GraphDiagnostics:
    n_imu: int                 # 使用的 IMU 样本数（可被 max_imu_samples 裁剪）
    n_dvl_all: int             # 使用的 DVL 样本数
    n_states: int              # 因子图中状态节点数（关键帧数量）

    n_factors_total: int
    n_factors_prior: int
    n_factors_imu: int
    n_factors_dvl_be: int
    n_factors_dvl_bi: int
    n_factors_yaw: int

    gn_converged: bool
    gn_iters: int
    gn_initial_cost: float
    gn_final_cost: float


# ============================================================
# 初始状态构造：基于 IMU 的粗略 dead-reckon（每帧一个）
# ============================================================


def _build_initial_guess(
    imu_raw: ImuRawData,
    cfg: GraphConfig,
    proc_dir: Optional[Path],
    run_id: Optional[str],
) -> Tuple[List[GraphState], BiasState, np.ndarray]:
    """
    基于 IMU 做一个简单 dead-reckon，构造“每一帧 IMU”的 GraphState 序列
    和全局 BiasState 初值。

    - 支持通过 cfg.max_imu_samples 对 IMU 进行前缀裁剪；
    - yaw 初值来自 cfg.init_yaw_rad 或 IMU AngZ[0]；
    - p, v 初值从 0 开始，使用简化的欧拉积分：
        v_{k+1} = v_k + a_n * dt
        p_{k+1} = p_k + v_k * dt + 0.5 * a_n * dt^2
    - bias 初值设为 0（后续由先验因子收紧）
    """
    # ---------- 0) 读取完整 IMU DataFrame + 时间轴 ----------
    df_imu_full = imu_raw.df
    t_imu_full = _get_time_s_from_imu(imu_raw)
    n_imu_full = len(df_imu_full)
    if n_imu_full < 2:
        raise ValueError("IMU 数据过短，无法构造初始状态")

    # ---------- 1) 可选：按 max_imu_samples 裁剪前缀 ----------
    max_imu_samples = int(getattr(cfg, "max_imu_samples", 0) or 0)
    if max_imu_samples > 0 and n_imu_full > max_imu_samples:
        df_imu = df_imu_full.iloc[:max_imu_samples].reset_index(drop=True)
        t_imu = t_imu_full[:max_imu_samples]
        if getattr(cfg, "verbose", False):
            print(
                f"[GRAPH] _build_initial_guess: crop IMU from "
                f"{n_imu_full} to {len(df_imu)} samples (max_imu_samples={max_imu_samples})"
            )
    else:
        df_imu = df_imu_full
        t_imu = t_imu_full

    n_imu = len(df_imu)
    if n_imu < 2:
        raise ValueError("裁剪后 IMU 数据过短，无法构造初始状态")

    # ---------- 2) 是否使用 processed IMU ----------
    imu_proc: ImuProcessedData | None = None
    if getattr(cfg, "use_processed_imu", False):
        if proc_dir is None or run_id is None:
            raise ValueError("GraphConfig.use_processed_imu=True，但未提供 proc_dir/run_id")
        imu_proc_path = proc_dir / f"{run_id}_imu_filtered.csv"
        imu_proc = load_imu_processed_csv(imu_proc_path)

        # 确保 processed 长度与裁剪后的 IMU 对齐
        n_proc = imu_proc.acc_mps2.shape[0]
        if n_proc != n_imu:
            n_common = min(n_imu, n_proc)
            if getattr(cfg, "verbose", False):
                print(
                    f"[GRAPH] imu_proc length ({n_proc}) != n_imu ({n_imu}), "
                    f"crop to {n_common}"
                )
            df_imu = df_imu.iloc[:n_common].reset_index(drop=True)
            t_imu = t_imu[:n_common]
            imu_proc.acc_mps2 = imu_proc.acc_mps2[:n_common, :]
            imu_proc.gyro_rad_s = imu_proc.gyro_rad_s[:n_common, :]
            n_imu = n_common

    # ---------- 3) 常数 ----------
    g_val = float(getattr(cfg, "gravity", 9.78))
    g_n = np.array([0.0, 0.0, -g_val], dtype=float)
    g_to_mps2_raw = float(getattr(cfg, "imu_raw_g_to_mps2", 9.78))

    # ---------- 4) 初始姿态 yaw0 ----------
    if hasattr(cfg, "init_yaw_rad"):
        yaw0 = float(cfg.init_yaw_rad)
    elif "AngZ" in df_imu.columns:
        yaw0 = np.deg2rad(float(df_imu["AngZ"].iloc[0]))
    else:
        yaw0 = 0.0
    yaw0 = wrap_yaw(yaw0)

    roll0 = np.deg2rad(float(df_imu["AngX"].iloc[0]))
    pitch0 = np.deg2rad(float(df_imu["AngY"].iloc[0]))
    _ = roll0  # 当前未直接使用，预留

    # ---------- 5) 初始 p, v ----------
    p = np.array([0.0, 0.0, 0.0], dtype=float)
    v = np.zeros(3, dtype=float)
    yaw = yaw0

    states: List[GraphState] = []
    # k=0
    states.append(
        GraphState(
            t_s=float(t_imu[0]),
            p=p.copy(),
            v=v.copy(),
            yaw=yaw,
        )
    )

    # ---------- 6) 主循环：粗略 dead-reckon ----------
    for k in range(1, n_imu):
        t_prev = float(t_imu[k - 1])
        t_curr = float(t_imu[k])
        dt = t_curr - t_prev
        if dt <= 0.0:
            # 时间轴异常时，保持上一状态
            states.append(
                GraphState(
                    t_s=t_curr,
                    p=p.copy(),
                    v=v.copy(),
                    yaw=yaw,
                )
            )
            continue

        # roll/pitch：仍用原始 IMU
        roll = np.deg2rad(float(df_imu["AngX"].iloc[k]))
        pitch = np.deg2rad(float(df_imu["AngY"].iloc[k]))

        # 加速度/角速度：processed or raw
        if imu_proc is not None:
            acc_body = imu_proc.acc_mps2[k, :].reshape(3)
            gyro_body = imu_proc.gyro_rad_s[k, :].reshape(3)
        else:
            ax = float(df_imu["AccX"].iloc[k])
            ay = float(df_imu["AccY"].iloc[k])
            az = float(df_imu["AccZ"].iloc[k])
            acc_body = np.array([ax, ay, az], dtype=float) * g_to_mps2_raw

            gx = float(df_imu["GyroX"].iloc[k])
            gy = float(df_imu["GyroY"].iloc[k])
            gz = float(df_imu["GyroZ"].iloc[k])
            gyro_body = np.deg2rad(np.array([gx, gy, gz], dtype=float))

        yaw_rate = float(gyro_body[2])

        att = AttitudeRPY(
            roll=roll,
            pitch=pitch,
            yaw=yaw,
        )
        R_nb = rpy_to_R_nb(att)
        a_n = R_nb @ acc_body + g_n

        v = v + a_n * dt
        p = p + v * dt + 0.5 * a_n * dt * dt
        yaw = wrap_yaw(yaw + yaw_rate * dt)

        states.append(
            GraphState(
                t_s=t_curr,
                p=p.copy(),
                v=v.copy(),
                yaw=yaw,
            )
        )

    # ---------- 7) 全局 bias 初值 ----------
    bias = BiasState(
        ba=np.zeros(3, dtype=float),
        bgz=0.0,
    )

    return states, bias, t_imu

# ============================================================
# 主管线：构图 + GN 平滑（关键帧 LV1 版）
# ============================================================
def run_graph_pipeline(
    imu_raw: ImuRawData,
    dvl_raw: DvlRawData,
    cfg: GraphConfig,
    proc_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> Tuple[Trajectory, GraphDiagnostics]:
    """
    因子图导航离线轨迹求解主入口（关键帧 LV1 版）.
    """
    df_imu = imu_raw.df
    df_dvl_raw = dvl_raw.df

    # ---------- 1) 构造“每帧 IMU”的初始状态与 bias（内部可裁剪 IMU） ----------
    states_full, bias_init, t_imu = _build_initial_guess(imu_raw, cfg, proc_dir, run_id)
    n_imu = len(states_full)
    if n_imu < 2:
        raise ValueError("IMU 数据过短，无法运行 Graph 管线")

    # ---------- 1.1 关键帧下采样 ----------
    keyframe_stride = int(getattr(cfg, "keyframe_stride", 10))
    max_nodes = getattr(cfg, "max_nodes", 1000)

    kfs = _select_keyframe_indices(
        t_imu,
        keyframe_stride=keyframe_stride,
        max_nodes=max_nodes,
    )
    if kfs.size < 2:
        raise ValueError(
            f"关键帧数量过少：{kfs.size} (< 2)，请检查 keyframe_stride/max_nodes 或 IMU 数据长度"
        )

    # 关键帧状态列表 + 节点时间轴（图中的真实节点）
    states_init: List[GraphState] = [states_full[int(k)] for k in kfs]
    t_nodes = t_imu[kfs]
    n_states = len(states_init)

    # ---------- 2) 载入/统一 DVL 源 ----------
    dvl_proc: DvlProcessedData | None = None
    use_dvl_proc = getattr(cfg, "use_processed_dvl", False)
    if use_dvl_proc:
        if proc_dir is None or run_id is None:
            raise ValueError("GraphConfig.use_processed_dvl=True，但未提供 proc_dir/run_id")
        dvl_proc = load_dvl_processed_csv(proc_dir, run_id)

    if dvl_proc is not None:
        df_dvl = dvl_proc.df_all
    else:
        df_dvl = df_dvl_raw

    t_dvl = _get_time_s_from_dvl_df(df_dvl)
    n_dvl_all = len(df_dvl)

    # ---------- 3) pack θ 初值（只针对关键帧节点） ----------
    theta0 = pack_theta(states_init, bias_init)
    D = theta0.size

    # ---------- 4) 构造因子列表 ----------
    factors: List[object] = []  # 每个元素需实现 Factor 协议

    # 4.1 先验因子（第一个关键帧 + bias）
    prior_p_std = float(getattr(cfg, "prior_p_std", 0.10))  # m
    prior_v_std = float(getattr(cfg, "prior_v_std", 0.10))  # m/s
    prior_yaw_std = float(getattr(cfg, "prior_yaw_std", np.deg2rad(10.0)))  # rad
    prior_ba_std = float(getattr(cfg, "prior_ba_std", 1.0e-2))  # m/s^2
    prior_bgz_std = float(getattr(cfg, "prior_bgz_std", np.deg2rad(1.0)))  # rad/s

    p0_mean = states_init[0].p.copy()
    v0_mean = states_init[0].v.copy()
    yaw0_mean = states_init[0].yaw
    ba_mean = bias_init.ba.copy()
    bgz_mean = bias_init.bgz

    factors.append(
        PriorStateBiasFactor(
            num_states=n_states,
            p0_mean=p0_mean,
            v0_mean=v0_mean,
            yaw0_mean=yaw0_mean,
            ba_mean=ba_mean,
            bgz_mean=bgz_mean,
            prior_p_std=prior_p_std,
            prior_v_std=prior_v_std,
            prior_yaw_std=prior_yaw_std,
            prior_ba_std=prior_ba_std,
            prior_bgz_std=prior_bgz_std,
        )
    )
    n_f_prior = 1

    # 4.2 IMU 过程因子（仅在相邻关键帧之间建边，LV1 模型）
    g_val = float(getattr(cfg, "gravity", 9.78))
    g_to_mps2_raw = float(getattr(cfg, "imu_raw_g_to_mps2", 9.78))

    proc_pos_std = float(getattr(cfg, "proc_pos_std", 1.0e-3))
    proc_vel_std = float(getattr(cfg, "proc_vel_std", 1.0e-2))
    proc_yaw_std = float(getattr(cfg, "proc_yaw_std", np.deg2rad(1.0)))

    imu_proc: ImuProcessedData | None = None
    if getattr(cfg, "use_processed_imu", False):
        if proc_dir is None or run_id is None:
            raise ValueError("GraphConfig.use_processed_imu=True，但未提供 proc_dir/run_id")
        imu_proc_path = proc_dir / f"{run_id}_imu_filtered.csv"
        imu_proc = load_imu_processed_csv(imu_proc_path)

    n_f_imu = 0

    # ★ 这里加开关：先用 False 测试“纯 DVL”效果
    if getattr(cfg, "enable_imu_factor", False):
        for i in range(n_states - 1):
            k0 = int(kfs[i])       # 对应原始 IMU 索引
            k1 = int(kfs[i + 1])

            t_prev = float(t_imu[k0])
            t_curr = float(t_imu[k1])
            dt = t_curr - t_prev
            if dt <= 0.0:
                continue

            # roll/pitch 取起点关键帧的 IMU 姿态（LV1 简化）
            roll = np.deg2rad(float(df_imu["AngX"].iloc[k0]))
            pitch = np.deg2rad(float(df_imu["AngY"].iloc[k0]))

            if imu_proc is not None:
                acc_body = imu_proc.acc_mps2[k0, :].reshape(3)
                gyro_body = imu_proc.gyro_rad_s[k0, :].reshape(3)
            else:
                ax = float(df_imu["AccX"].iloc[k0])
                ay = float(df_imu["AccY"].iloc[k0])
                az = float(df_imu["AccZ"].iloc[k0])
                acc_body = np.array([ax, ay, az], dtype=float) * g_to_mps2_raw

                gx = float(df_imu["GyroX"].iloc[k0])
                gy = float(df_imu["GyroY"].iloc[k0])
                gz = float(df_imu["GyroZ"].iloc[k0])
                gyro_body = np.deg2rad(np.array([gx, gy, gz], dtype=float))

            factors.append(
                ImuProcessFactor(
                    num_states=n_states,   # 图中节点数
                    k=i,                   # 节点索引 i -> i+1
                    dt=dt,
                    acc_body=acc_body,
                    gyro_body=gyro_body,
                    roll_rad=roll,
                    pitch_rad=pitch,
                    g_val=g_val,
                    std_pos=proc_pos_std,
                    std_vel=proc_vel_std,
                    std_yaw=proc_yaw_std,
                )
            )
            n_f_imu += 1
    else:
        # 不用 IMU 因子时，n_f_imu 保持 0 即可
        n_f_imu = 0

    # 4.3 DVL 因子（对齐到关键帧时间轴 t_nodes）
    use_dvl_BI_vel = bool(getattr(cfg, "use_dvl_BI_vel", True))
    use_dvl_BE_vel = bool(getattr(cfg, "use_dvl_BE_vel", True))
    use_dvl_yaw_from_vel = bool(getattr(cfg, "use_dvl_yaw_from_vel", True))

    dvl_bi_std = float(getattr(cfg, "r_dvl_BI_vel", 5.0e-3))
    dvl_be_std = float(getattr(cfg, "r_dvl_BE_vel", 5.0e-3))
    dvl_yaw_std = float(getattr(cfg, "r_dvl_yaw", np.deg2rad(2.0)))
    min_speed_for_yaw_dvl = float(getattr(cfg, "min_speed_for_yaw_dvl", 0.10))
    max_gap_s = float(getattr(cfg, "max_gap_s", 0.05))

    n_f_dvl_be = 0
    n_f_dvl_bi = 0
    n_f_yaw = 0

    for j in range(n_dvl_all):
        t_d = float(t_dvl[j])
        # 在关键帧时间轴上找最近节点
        k_state = _find_nearest_index(t_nodes, t_d, max_gap_s)
        if k_state is None:
            continue

        row = df_dvl.iloc[j]
        src = str(row.get("Src", "")).upper()

        # BI: 体速度观测
        if use_dvl_BI_vel and src == "BI":
            try:
                vx_b = float(row["Vx_body(m_s)"])
                vy_b = float(row["Vy_body(m_s)"])
                vz_b = float(row["Vz_body(m_s)"])
            except KeyError:
                # 列名缺失时跳过
                pass
            else:
                # roll/pitch ：使用对应关键帧的原始 IMU 姿态
                k_imu_idx = int(kfs[k_state])  # 映射回原始 IMU 索引
                roll = np.deg2rad(float(df_imu["AngX"].iloc[k_imu_idx]))
                pitch = np.deg2rad(float(df_imu["AngY"].iloc[k_imu_idx]))
                vel_body = np.array([vx_b, vy_b, vz_b], dtype=float)

                factors.append(
                    DvlBIVelFactor(
                        num_states=n_states,
                        k=k_state,
                        vel_body=vel_body,
                        roll_rad=roll,
                        pitch_rad=pitch,
                        std_bi=dvl_bi_std,
                    )
                )
                n_f_dvl_bi += 1

        # BE: ENU 速度 + yaw-from-vel
        if (use_dvl_BE_vel or use_dvl_yaw_from_vel) and src == "BE":
            try:
                ve = float(row["Ve_enu(m_s)"])
                vn = float(row["Vn_enu(m_s)"])
                vu = float(row["Vu_enu(m_s)"])
            except KeyError:
                pass
            else:
                vel_enu = np.array([ve, vn, vu], dtype=float)

                if use_dvl_BE_vel:
                    factors.append(
                        DvlBEVelFactor(
                            num_states=n_states,
                            k=k_state,
                            vel_enu=vel_enu,
                            std_be=dvl_be_std,
                        )
                    )
                    n_f_dvl_be += 1

                if use_dvl_yaw_from_vel:
                    speed_xy = float(np.hypot(ve, vn))
                    if speed_xy >= min_speed_for_yaw_dvl:
                        factors.append(
                            YawFromVelFactor(
                                num_states=n_states,
                                k=k_state,
                                vel_enu=vel_enu,
                                std_yaw=dvl_yaw_std,
                            )
                        )
                        n_f_yaw += 1

    n_f_total = len(factors)

    # 调试输出：当前问题规模
    print(
        f"[GRAPH] n_imu={n_imu}  n_states={n_states}  "
        f"dim(theta)={D}  n_factors={n_f_total}"
    )

    # ---------- 5) Gauss-Newton 平滑 ----------
    max_iters = int(getattr(cfg, "max_iterations", 20))
    use_robust_loss = bool(getattr(cfg, "use_robust_loss", True))
    robust_param = float(getattr(cfg, "robust_loss_param", 1.0))

    robust_loss_type = "huber" if use_robust_loss else None

    theta_opt, gn_stats = gauss_newton_solve(
        factors=factors,
        theta0=theta0,
        max_iters=max_iters,
        tol_step=float(getattr(cfg, "tol_step", 1e-6)),
        tol_cost_rel=float(getattr(cfg, "tol_cost_rel", 1e-6)),
        robust_loss=robust_loss_type,
        robust_param=robust_param,
        verbose=bool(getattr(cfg, "verbose", False)),
    )

    # ---------- 6) 解包 θ -> states + bias ----------
    # 注意：这里用的是关键帧时间轴 t_nodes
    states_opt, bias_opt = unpack_theta(theta_opt, t_nodes)
    _ = bias_opt  # 当前仅做调试，可在后续扩展输出

    # ---------- 7) 打包 Trajectory ----------
    t_arr = np.asarray([st.t_s for st in states_opt], dtype=float)
    E_arr = np.asarray([st.p[0] for st in states_opt], dtype=float)
    N_arr = np.asarray([st.p[1] for st in states_opt], dtype=float)
    U_arr = np.asarray([st.p[2] for st in states_opt], dtype=float)
    yaw_arr = np.asarray([st.yaw for st in states_opt], dtype=float)

    traj = Trajectory(
        t_s=t_arr,
        E=E_arr,
        N=N_arr,
        U=U_arr,
        yaw_rad=yaw_arr,
    )

    # ---------- 8) 诊断信息 ----------
    diag = GraphDiagnostics(
        n_imu=n_imu,
        n_dvl_all=n_dvl_all,
        n_states=n_states,
        n_factors_total=n_f_total,
        n_factors_prior=n_f_prior,
        n_factors_imu=n_f_imu,
        n_factors_dvl_be=n_f_dvl_be,
        n_factors_dvl_bi=n_f_dvl_bi,
        n_factors_yaw=n_f_yaw,
        gn_converged=gn_stats.converged,
        gn_iters=gn_stats.num_iters,
        gn_initial_cost=gn_stats.initial_cost,
        gn_final_cost=gn_stats.final_cost,
    )

    return traj, diag
