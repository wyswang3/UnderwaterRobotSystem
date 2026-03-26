# src/offnav/viz/plots.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation


from ..core.types import Trajectory


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _ensure_dir(path: str) -> str:
    path = os.path.abspath(path)
    os.makedirs(path, exist_ok=True)
    return path


def _finite_mask(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    return np.all(np.isfinite(a), axis=-1) if a.ndim > 1 else np.isfinite(a)


def _setup_matplotlib() -> None:
    """
    统一设置 matplotlib 风格：Times New Roman + 投稿级参数
    """
    plt.rcParams.update(
        {
            # 字体
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,

            # 线条 & 坐标轴
            "lines.linewidth": 1.5,
            "axes.linewidth": 1.0,

            # 刻度样式
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.major.size": 4,
            "ytick.major.size": 4,

            # 导出
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "figure.dpi": 100,
        }
    )


def _save_fig(fig: plt.Figure, out_png: str) -> None:
    """
    高分辨率保存并关闭
    """
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 轨迹与速度相关图
# ---------------------------------------------------------------------------

def save_plot_traj_en(out_png: str, traj: Trajectory,
                      src_used: Optional[np.ndarray] = None) -> None:
    """
    EN 平面轨迹图（主要用于展示路径形状）
    """
    _setup_matplotlib()

    t = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    p = np.asarray(traj.p_enu, dtype=np.float64)

    m = _finite_mask(p[:, :2]) & _finite_mask(t)
    E = p[m, 0]
    N = p[m, 1]

    fig, ax = plt.subplots(figsize=(5.5, 5.5))

    if E.size > 0:
        ax.plot(E, N, label="Trajectory", zorder=1)
        # 修正：起点 y 坐标应该是 N[0]，而不是 E[0*0]
        ax.scatter(E[0], N[0], marker="o", s=40, label="Start", zorder=3)
        ax.scatter(E[-1], N[-1], marker="s", s=40, label="End", zorder=3)

    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")
    ax.set_title("Planar Trajectory (ENU)")
    ax.set_aspect("equal", adjustable="box")

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    if E.size > 0:
        leg = ax.legend(frameon=False, loc="best")
        for lh in leg.legend_handles:
            lh.set_linewidth(1.5)

    _save_fig(fig, out_png)

def save_xy_traj_gif(
    out_dir: str,
    traj: Trajectory,
    filename: str = "traj_xy.gif",
    fps: int = 20,
    tail_window_s: float = 10.0,
    max_frames: int = 600,
) -> str:
    """
    在 EN 平面上把轨迹做成 GIF 动图。

    特点：
      - 以 ENU 全局坐标为平面（E 横轴，N 纵轴）；
      - 画“移动窗口尾迹”：每一帧只画最近 tail_window_s 时间内的轨迹段；
      - 预先固定坐标轴范围，避免画面一边放大一边移动；
      - 对长时间数据做下采样（最多 max_frames 帧），控制 GIF 体积。

    参数:
      out_dir       : 输出目录（通常是 run_dir）
      traj          : Trajectory，要求有 t_s, p_enu
      filename      : 输出 GIF 文件名
      fps           : 帧率
      tail_window_s : 每一帧显示的“尾迹长度”（秒）
      max_frames    : 最大帧数（> 轨迹长度时不做下采样）

    返回:
      gif_path: GIF 文件的绝对路径
    """
    _setup_matplotlib()

    out_dir = _ensure_dir(out_dir)
    gif_path = os.path.abspath(os.path.join(out_dir, filename))

    t = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    p = np.asarray(traj.p_enu, dtype=np.float64)

    if t.size == 0 or p.shape[0] == 0:
        raise ValueError("Trajectory is empty, cannot generate GIF")

    # 只用 EN 平面
    E = p[:, 0]
    N = p[:, 1]

    # 有效 mask（防 NaN/Inf）
    m = _finite_mask(E) & _finite_mask(N) & _finite_mask(t)
    t = t[m]
    E = E[m]
    N = N[m]

    if t.size == 0:
        raise ValueError("No finite samples in trajectory for GIF")

    # 归一化时间，从 0 开始，方便 tail_window_s 计算
    t0 = float(t[0])
    t_rel = t - t0

    # =============== 帧下采样 ===============
    # 如果样本点很多，则等间距抽样到 <= max_frames 帧
    K = t_rel.size
    if K > max_frames:
        idx = np.linspace(0, K - 1, num=max_frames, dtype=int)
        t_rel = t_rel[idx]
        E = E[idx]
        N = N[idx]

    # 轨迹整体范围，用来固定坐标轴比例
    margin = 0.1  # 10% 额外边界
    E_min, E_max = float(E.min()), float(E.max())
    N_min, N_max = float(N.min()), float(N.max())
    dE = E_max - E_min
    dN = N_max - N_min
    if dE <= 0.0:
        dE = 1.0
    if dN <= 0.0:
        dN = 1.0

    E_pad = margin * dE
    N_pad = margin * dN

    fig, ax = plt.subplots(figsize=(5.0, 5.0))
    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")
    ax.set_title("Planar Trajectory (ENU, animated)")

    ax.set_xlim(E_min - E_pad, E_max + E_pad)
    ax.set_ylim(N_min - N_pad, N_max + N_pad)
    ax.set_aspect("equal", adjustable="box")

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    # 整条路径的淡灰色背景，用于提供全局参考
    ax.plot(E, N, color="0.9", linewidth=1.0, zorder=0)

    # 动态尾迹和当前点
    line_tail, = ax.plot([], [], color="tab:blue", linewidth=1.8, zorder=2, label="Tail")
    point_cur = ax.scatter([], [], color="tab:red", s=35, zorder=3, label="Current")

    # 起点标记
    ax.scatter(E[0], N[0], color="tab:green", marker="o", s=40, zorder=3, label="Start")

    # 图例
    leg = ax.legend(frameon=False, loc="best")
    for lh in leg.legend_handles:
        try:
            lh.set_linewidth(1.5)
        except Exception:
            pass

    # =============== 动画更新函数 ===============
    def _init():
        line_tail.set_data([], [])
        # scatter 要用 set_offsets
        point_cur.set_offsets(np.empty((0, 2)))
        return line_tail, point_cur

    def _update(frame_idx: int):
        t_now = t_rel[frame_idx]
        t_begin = max(0.0, t_now - float(tail_window_s))

        # 在 [t_begin, t_now] 范围内选点
        mask_tail = (t_rel >= t_begin) & (t_rel <= t_now)
        E_tail = E[mask_tail]
        N_tail = N[mask_tail]

        if E_tail.size == 0:
            line_tail.set_data([], [])
            point_cur.set_offsets(np.empty((0, 2)))
        else:
            line_tail.set_data(E_tail, N_tail)
            # 当前点：最后一个点
            point_cur.set_offsets(np.array([[E_tail[-1], N_tail[-1]]], dtype=np.float64))

        return line_tail, point_cur

    # 创建动画
    anim = animation.FuncAnimation(
        fig,
        _update,
        init_func=_init,
        frames=t_rel.size,
        interval=1000.0 / float(max(fps, 1)),  # ms
        blit=True,
    )

    # 保存 GIF（使用 PillowWriter）
    try:
        writer = animation.PillowWriter(fps=fps)
        anim.save(gif_path, writer=writer)
    finally:
        plt.close(fig)

    return gif_path


def save_plot_up_vs_time(out_png: str, traj: Trajectory) -> None:
    """
    Up 分量随时间变化
    """
    _setup_matplotlib()

    t = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    p = np.asarray(traj.p_enu, dtype=np.float64)

    m = np.isfinite(t) & np.isfinite(p[:, 2])

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    ax.plot(t[m], p[m, 2])

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Up [m]")
    ax.set_title("Up Position vs Time")

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    _save_fig(fig, out_png)


def save_plot_speed_vs_time(out_png: str, traj: Trajectory,
                            src_used: Optional[np.ndarray] = None) -> None:
    """
    速度模随时间变化（带可选 BI/BE 标记）
    """
    _setup_matplotlib()

    t = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    v = np.asarray(traj.v_enu, dtype=np.float64)

    speed = np.linalg.norm(v, axis=1)
    m = np.isfinite(t) & np.isfinite(speed)

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    ax.plot(t[m], speed[m], label="Speed")

    # 保留原来的 BI/BE 标记能力
    if src_used is not None and src_used.shape[0] == t.shape[0]:
        be_idx = np.where((src_used == "BE") & m)[0]
        bi_idx = np.where((src_used == "BI") & m)[0]
        if be_idx.size > 0:
            ax.scatter(
                t[be_idx],
                speed[be_idx],
                marker="o",
                s=25,
                facecolors="none",
                edgecolors="tab:blue",
                label="BE",
            )
        if bi_idx.size > 0:
            ax.scatter(
                t[bi_idx],
                speed[bi_idx],
                marker="x",
                s=25,
                color="tab:green",
                label="BI",
            )

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Speed [m/s]")
    ax.set_title("Speed Magnitude vs Time")

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    leg = ax.legend(frameon=False, loc="best")
    for lh in leg.legend_handles:
        lh.set_linewidth(1.5)

    _save_fig(fig, out_png)


# ---------------------------------------------------------------------------
# 姿态相关图
# ---------------------------------------------------------------------------

def _extract_yaw_from_diag_for_plot(traj: Trajectory,
                                    diag: Dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """
    优先从 diag['attitude'] 里取 (t_s, yaw)；若不存在，则退回原先的 yaw_rad + traj 时间轴。
    返回: (t_plot, yaw_deg)
    """
    # 1) 优先使用全局姿态轨迹
    att = diag.get("attitude")
    if isinstance(att, dict) and ("t_s" in att) and ("yaw" in att):
        t_att = np.asarray(att["t_s"], dtype=np.float64).reshape(-1)
        yaw_rad = np.asarray(att["yaw"], dtype=np.float64).reshape(-1)
        n = min(t_att.size, yaw_rad.size)
        t_plot = t_att[:n]
        yaw_deg = np.rad2deg(yaw_rad[:n])
        return t_plot, yaw_deg

    # 2) 回退到旧的 diag['yaw_rad'] + traj.t_s 对齐
    yaw_rad = diag.get("yaw_rad", None)
    t_traj = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    n = t_traj.size

    if yaw_rad is None:
        yaw_deg = np.full((n,), np.nan, dtype=np.float64)
    else:
        yaw_rad = np.asarray(yaw_rad, dtype=np.float64).reshape(-1)
        if yaw_rad.size >= n:
            yaw_deg = np.rad2deg(yaw_rad[:n])
        else:
            yaw_deg = np.rad2deg(yaw_rad)
            yaw_deg = np.pad(
                yaw_deg,
                (0, n - yaw_deg.size),
                constant_values=np.nan,
            )

    return t_traj, yaw_deg


def save_plot_yaw_vs_time(out_png: str, traj: Trajectory,
                          diag: Dict[str, Any]) -> None:
    """
    航向角随时间变化：
      - 优先使用 attitude 模块积分出的 yaw；
      - 否则回退到旧的 yaw_rad。
    """
    _setup_matplotlib()

    t_plot, yaw_deg = _extract_yaw_from_diag_for_plot(traj, diag)

    t = np.asarray(t_plot, dtype=np.float64).reshape(-1)
    y = np.asarray(yaw_deg, dtype=np.float64).reshape(-1)
    n = min(t.size, y.size)
    t = t[:n]
    y = y[:n]

    m = np.isfinite(t) & np.isfinite(y)

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    ax.plot(t[m], y[m])

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Yaw [deg]")
    ax.set_title("Yaw Angle vs Time")

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    _save_fig(fig, out_png)


def save_plot_attitude_full(out_png: str, diag: Dict[str, Any]) -> bool:
    """
    若 diag 中存在全局 attitude，则画 yaw/pitch/roll 三联图；否则返回 False。
    """
    att = diag.get("attitude")
    if not isinstance(att, dict):
        return False
    if ("t_s" not in att) or ("yaw" not in att) or ("pitch" not in att) or ("roll" not in att):
        return False

    _setup_matplotlib()

    t = np.asarray(att["t_s"], dtype=np.float64).reshape(-1)
    yaw = np.asarray(att["yaw"], dtype=np.float64).reshape(-1)
    pitch = np.asarray(att["pitch"], dtype=np.float64).reshape(-1)
    roll = np.asarray(att["roll"], dtype=np.float64).reshape(-1)
    n = min(t.size, yaw.size, pitch.size, roll.size)

    t = t[:n]
    yaw = yaw[:n]
    pitch = pitch[:n]
    roll = roll[:n]

    yaw_deg = np.rad2deg(yaw)
    pitch_deg = np.rad2deg(pitch)
    roll_deg = np.rad2deg(roll)

    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(6.5, 6.0))

    axes[0].plot(t, yaw_deg, color="tab:red")
    axes[1].plot(t, pitch_deg, color="tab:blue")
    axes[2].plot(t, roll_deg, color="tab:green")

    axes[0].set_ylabel("Yaw [deg]")
    axes[1].set_ylabel("Pitch [deg]")
    axes[2].set_ylabel("Roll [deg]")

    axes[0].set_title("Attitude Evolution (ZYX Euler)")

    for i, ax in enumerate(axes):
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)
        if i < 2:
            ax.tick_params(labelbottom=False)

    axes[-1].set_xlabel("Time [s]")

    _save_fig(fig, out_png)
    return True


# ---------------------------------------------------------------------------
# 段级诊断图（仅 segment 模式有意义）
# ---------------------------------------------------------------------------

def save_plot_segment_diagnostics(out_png: str, diag: Dict[str, Any]) -> bool:
    """
    若 diag['segment'] 存在，则绘制：
      - 每段 Δt
      - 每段步长
      - 每段选用模型 A/B/C/ZERO
    否则返回 False。
    """
    seg = diag.get("segment")
    if seg is None:
        return False

    _setup_matplotlib()

    dvl_times = np.asarray(seg.get("dvl_times", []), dtype=np.float64)
    dt_s = np.asarray(seg.get("seg_dt_s", []), dtype=np.float64)
    seg_len = np.asarray(seg.get("seg_len_m", []), dtype=np.float64)
    model_chosen = np.asarray(seg.get("model_chosen", []), dtype=object)

    K1 = dt_s.shape[0]
    if K1 == 0:
        return False

    idx = np.arange(K1)

    model_map = {"A": 0, "B": 1, "C": 2, "ZERO": -1}
    model_codes = np.array([model_map.get(m, -2) for m in model_chosen[:K1]], dtype=float)

    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(6.5, 6.0))

    # Δt
    axes[0].plot(idx, dt_s[:K1], color="tab:blue")
    axes[0].set_ylabel("Δt [s]")
    axes[0].set_title("Segment Diagnostics")

    # 步长
    axes[1].plot(idx, seg_len[:K1], color="tab:green")
    axes[1].set_ylabel("Step len [m]")

    # 模型编号
    axes[2].step(idx, model_codes, where="mid", color="tab:red")
    axes[2].set_ylabel("Model")
    axes[2].set_xlabel("Segment index")
    axes[2].set_yticks([-1, 0, 1, 2])
    axes[2].set_yticklabels(["ZERO", "A", "B", "C"])

    for ax in axes:
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)

    _save_fig(fig, out_png)
    return True


# ---------------------------------------------------------------------------
# 对外统一入口
# ---------------------------------------------------------------------------

def save_all_plots(out_dir: str,
                   traj: Trajectory,
                   diag: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    保存所有关键图像到 out_dir/plots，并返回 {name: path} 字典。

    保持原有的四个 key：
      - trajectory_en
      - up_vs_time
      - speed_vs_time
      - yaw_vs_time

    若有全局姿态 / 段级诊断信息，则额外输出：
      - attitude_full
      - segment_diagnostics
    """
    diag = diag or {}
    plots_dir = _ensure_dir(os.path.join(out_dir, "plots"))

    # 轨迹长度，用来构造 src_used
    t = np.asarray(traj.t_s, dtype=np.float64).reshape(-1)
    n = t.shape[0]

    # 尝试保留原来的 src_used 用于速度图上的 BI/BE 标记
    src = diag.get("src_used", None)
    if src is None:
        src_used = np.array([""] * n, dtype=object)
    else:
        src = np.asarray(src, dtype=object).reshape(-1)
        if src.size >= n:
            src_used = src[:n]
        else:
            src_used = np.concatenate(
                [src, np.array([""] * (n - src.size), dtype=object)]
            )

    paths: Dict[str, str] = {}

    # 1) EN 轨迹
    p1 = os.path.join(plots_dir, "trajectory_en.png")
    save_plot_traj_en(p1, traj, src_used=src_used)
    paths["trajectory_en"] = p1

    # 2) Up vs time
    p2 = os.path.join(plots_dir, "up_vs_time.png")
    save_plot_up_vs_time(p2, traj)
    paths["up_vs_time"] = p2

    # 3) Speed vs time
    p3 = os.path.join(plots_dir, "speed_vs_time.png")
    save_plot_speed_vs_time(p3, traj, src_used=src_used)
    paths["speed_vs_time"] = p3

    # 4) Yaw vs time（优先 attitude，全局姿态轨迹）
    p4 = os.path.join(plots_dir, "yaw_vs_time.png")
    save_plot_yaw_vs_time(p4, traj, diag)
    paths["yaw_vs_time"] = p4

    # 5) 全姿态三联图（如果有）
    p5 = os.path.join(plots_dir, "attitude_full.png")
    if save_plot_attitude_full(p5, diag):
        paths["attitude_full"] = p5

    # 6) 段级诊断图（仅 segment 模式）
    p6 = os.path.join(plots_dir, "segment_diagnostics.png")
    if save_plot_segment_diagnostics(p6, diag):
        paths["segment_diagnostics"] = p6

    return paths


# ---------------------------------------------------------------------------
# Graph 多算法 XY 轨迹对比（graph_compare_variants 使用）
# ---------------------------------------------------------------------------

def save_xy_compare_plot(
    out_dir: str,
    variants: Dict[str, Dict[str, Any]],
    filename: str = "traj_xy_compare.png",
    title: str = "XY Trajectory Comparison (ENU, multiple graph variants)",
) -> str:
    """
    在 EN 平面上叠加多条轨迹，对比不同 graph 变体（不同 ZUPT 阈值、不同配置等）的效果。

    参数:
      out_dir : run_dir（由 cmd_run 传入）
      variants: 形如 {
                    "base": {
                        "traj": Trajectory,
                        "diag": {...},
                        "cfg": GraphModeConfig,
                    },
                    "no_zupt": {...},
                    "zupt_0p02": {...},
                  }
      filename: 输出文件名
      title   : 图标题

    返回:
      输出 PNG 的绝对路径
    """
    _setup_matplotlib()

    plots_dir = _ensure_dir(os.path.join(out_dir, "plots"))
    out_path = os.path.join(plots_dir, filename)

    if not variants:
        # 没有数据就直接返回一个空路径，避免抛异常卡主流程
        return out_path

    # 为了让 base 最醒目：base 最后画、线粗一些
    # 其他变体按照名字排序画
    names = sorted(variants.keys())
    if "base" in names:
        names.remove("base")
        names.append("base")

    fig, ax = plt.subplots(figsize=(6.0, 6.0))

    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", None)
    if not color_cycle:
        color_cycle = ["tab:blue", "tab:orange", "tab:green", "tab:red",
                       "tab:purple", "tab:brown", "tab:pink", "tab:gray"]

    for idx, name in enumerate(names):
        entry = variants[name]
        traj = entry.get("traj", None)
        if traj is None:
            continue

        p = np.asarray(traj.p_enu, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] < 2:
            continue

        mask = _finite_mask(p[:, :2])
        E = p[mask, 0]
        N = p[mask, 1]

        if E.size == 0:
            continue

        color = color_cycle[idx % len(color_cycle)]

        # 尝试从 cfg 里取 zupt 阈值，方便在图例中展示
        cfg = entry.get("cfg", None)
        zupt_eps_str = ""
        if cfg is not None and hasattr(cfg, "zupt_eps_speed"):
            try:
                eps = float(cfg.zupt_eps_speed)
                zupt_eps_str = f" (eps={eps:.3g} m/s)"
            except Exception:
                pass

        label = name + zupt_eps_str

        lw = 1.2
        alpha = 0.9
        zorder = 1
        if name == "base":
            lw = 1.8
            alpha = 1.0
            zorder = 3

        ax.plot(E, N, label=label, color=color, linewidth=lw, alpha=alpha, zorder=zorder)

        # 标记各自的起点/终点（可以略微区分一下 base 轨迹）
        if name == "base":
            ax.scatter(E[0], N[0], marker="o", s=35, color=color,
                       edgecolors="k", linewidths=0.6, zorder=4)
            ax.scatter(E[-1], N[-1], marker="s", s=35, color=color,
                       edgecolors="k", linewidths=0.6, zorder=4)

    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    leg = ax.legend(frameon=False, loc="best")
    for lh in leg.legend_handles:
        if hasattr(lh, "set_linewidth"):
            lh.set_linewidth(1.5)

    _save_fig(fig, out_path)
    return out_path


# ---------------------------------------------------------------------------
# 轨迹平滑效果对比（检查路段是否被“过度拉直”）
# ---------------------------------------------------------------------------

def _heading_from_vel(v_enu: np.ndarray, deg: bool = True, unwrap: bool = True) -> np.ndarray:
    """
    根据 ENU 速度计算航向角:
        yaw = atan2(v_y, v_x)

    参数:
      v_enu  : (..., 3) 或 (..., 2)，只取前两个分量作为 EN 平面速度
      deg    : True -> 输出单位为度；False -> 弧度
      unwrap : True -> 使用 np.unwrap 在时间轴上展开，避免 ±180° 折返

    返回:
      yaw_seq: (N,) 航向角序列
    """
    v = np.asarray(v_enu, dtype=np.float64)
    if v.ndim != 2 or v.shape[1] < 2:
        raise ValueError("v_enu must have shape (N, >=2)")
    vx = v[:, 0]
    vy = v[:, 1]

    yaw = np.arctan2(vy, vx)  # rad, [-pi, pi]

    if unwrap:
        yaw = np.unwrap(yaw)

    if deg:
        yaw = np.rad2deg(yaw)

    return yaw


def _segment_headings_from_pos(p_xy: np.ndarray, deg: bool = True, unwrap: bool = False) -> np.ndarray:
    """
    根据离散位置序列计算“每一段”的航向角:
        Δp_k = p_{k+1} - p_k
        heading_k = atan2(Δy_k, Δx_k)

    用于对比段级方向是否被“拉直”。

    返回:
      heading_seg: (K-1,) 每一段的航向角
    """
    p = np.asarray(p_xy, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] < 2:
        raise ValueError("p_xy must have shape (N, >=2)")

    dp = np.diff(p[:, :2], axis=0)  # (K-1, 2)
    dx = dp[:, 0]
    dy = dp[:, 1]

    heading = np.arctan2(dy, dx)  # rad

    if unwrap:
        heading = np.unwrap(heading)

    if deg:
        heading = np.rad2deg(heading)

    return heading


def plot_xy_raw_vs_smooth(
    traj_raw: Trajectory,
    traj_smooth: Trajectory,
    out_dir: str,
    filename: str = "traj_xy_raw_vs_smooth.png",
    title: str = "XY Trajectory: raw vs smoothed",
    show: bool = False,
) -> str:
    """
    在 EN 平面上对比原始段级轨迹与图平滑后的轨迹，直观查看是否被“过度拉直”。

    - traj_raw   : run_segment_path 输出的 Trajectory
    - traj_smooth: run_factor_graph_smoothing 输出的 Trajectory
    - out_dir    : 输出目录
    - filename   : 输出文件名
    - show       : 是否 plt.show()（一般离线画图可以设为 False）

    返回:
      保存的图像绝对路径
    """
    out_dir = _ensure_dir(out_dir)
    out_path = os.path.join(out_dir, filename)

    p_raw = np.asarray(traj_raw.p_enu, dtype=np.float64)
    p_smooth = np.asarray(traj_smooth.p_enu, dtype=np.float64)

    mask_raw = _finite_mask(p_raw[:, :2])
    mask_smooth = _finite_mask(p_smooth[:, :2])

    plt.figure(figsize=(8, 8))
    # 原始轨迹
    plt.plot(
        p_raw[mask_raw, 0],
        p_raw[mask_raw, 1],
        linestyle="-",
        linewidth=1.0,
        label="raw (segment)",
        alpha=0.8,
    )
    # 平滑轨迹
    plt.plot(
        p_smooth[mask_smooth, 0],
        p_smooth[mask_smooth, 1],
        linestyle="-",
        linewidth=1.5,
        label="smoothed (graph)",
        alpha=0.9,
    )

    plt.xlabel("E [m]")
    plt.ylabel("N [m]")
    plt.axis("equal")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.title(title)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    if show:
        plt.show()
    else:
        plt.close()

    return out_path


def plot_heading_from_vel_compare(
    traj_raw: Trajectory,
    traj_smooth: Trajectory,
    out_dir: str,
    filename: str = "heading_from_vel_raw_vs_smooth.png",
    title: str = "Heading from velocity: raw vs smoothed",
    show: bool = False,
) -> str:
    """
    使用 EN 速度计算“速度方向航向角”，对比平滑前后是否把掉头/转向行为压平。

    这里的航向角只从速度算，不依赖 IMU 姿态，
    适合回答：“图平滑有没有把原本的掉头给拉直”这一问题。

    - 横轴: 时间（DVL epoch t_s）
    - 纵轴: 速度航向角（deg, 经过 unwrap 展开）
    """
    out_dir = _ensure_dir(out_dir)
    out_path = os.path.join(out_dir, filename)

    t_raw = np.asarray(traj_raw.t_s, dtype=np.float64)
    t_smooth = np.asarray(traj_smooth.t_s, dtype=np.float64)

    v_raw = np.asarray(traj_raw.v_enu, dtype=np.float64)
    v_smooth = np.asarray(traj_smooth.v_enu, dtype=np.float64)

    yaw_raw = _heading_from_vel(v_raw, deg=True, unwrap=True)
    yaw_smooth = _heading_from_vel(v_smooth, deg=True, unwrap=True)

    mask_raw = _finite_mask(yaw_raw)
    mask_smooth = _finite_mask(yaw_smooth)

    plt.figure(figsize=(10, 5))
    plt.plot(
        t_raw[mask_raw] - t_raw[0],
        yaw_raw[mask_raw],
        linestyle="-",
        linewidth=1.0,
        label="raw heading from v",
        alpha=0.8,
    )
    plt.plot(
        t_smooth[mask_smooth] - t_smooth[0],
        yaw_smooth[mask_smooth],
        linestyle="-",
        linewidth=1.2,
        label="smoothed heading from v",
        alpha=0.9,
    )

    plt.xlabel("Time since start [s] (DVL epoch)")
    plt.ylabel("Heading from velocity [deg] (unwrapped)")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.title(title)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    if show:
        plt.show()
    else:
        plt.close()

    return out_path


def plot_segment_heading_compare(
    traj_raw: Trajectory,
    traj_smooth: Trajectory,
    out_dir: str,
    filename: str = "segment_heading_raw_vs_smooth.png",
    title: str = "Per-segment heading: raw vs smoothed",
    show: bool = False,
) -> str:
    """
    按“DVL 相邻 epoch 段”计算每一段的方向（Δp 的 atan2），对比：
      - raw 段级轨迹的方向变化
      - smooth 段级轨迹的方向变化
    """
    out_dir = _ensure_dir(out_dir)
    out_path = os.path.join(out_dir, filename)

    p_raw = np.asarray(traj_raw.p_enu, dtype=np.float64)
    p_smooth = np.asarray(traj_smooth.p_enu, dtype=np.float64)

    h_raw = _segment_headings_from_pos(p_raw[:, :2], deg=True, unwrap=False)
    h_smooth = _segment_headings_from_pos(p_smooth[:, :2], deg=True, unwrap=False)

    # 段索引 (0..K-2)
    idx = np.arange(h_raw.shape[0], dtype=np.int32)

    plt.figure(figsize=(10, 5))
    plt.plot(
        idx,
        h_raw,
        linestyle="-",
        marker="o",
        markersize=2,
        linewidth=0.8,
        label="raw segment heading",
        alpha=0.8,
    )
    plt.plot(
        idx,
        h_smooth,
        linestyle="-",
        marker="x",
        markersize=2,
        linewidth=0.8,
        label="smoothed segment heading",
        alpha=0.8,
    )

    plt.xlabel("Segment index (between DVL epochs)")
    plt.ylabel("Segment heading [deg] (atan2(Δy, Δx))")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.title(title)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    if show:
        plt.show()
    else:
        plt.close()

    return out_path
def save_xy_modes_compare(
    out_dir: str,
    trajectories: Dict[str, Trajectory],
    filename: str = "traj_xy_modes_compare.png",
    title: str = "XY Trajectory: multi-mode comparison",
    show: bool = False,
) -> str:
    """
    在 EN 平面上对比多个“滤波 / 轨迹解算模式”的结果。
    trajectories: {mode_name: Trajectory}

    典型用法：
      - {"baseline": traj_base, "segment": traj_seg, "graph": traj_graph}
    """
    _setup_matplotlib()
    out_dir = _ensure_dir(out_dir)
    out_path = os.path.join(out_dir, filename)

    fig, ax = plt.subplots(figsize=(6.5, 6.5))

    # 按固定顺序画，保证图例稳定
    mode_order = ["baseline", "segment", "graph"]
    for mode_name in mode_order:
        traj = trajectories.get(mode_name)
        if traj is None:
            continue
        p = np.asarray(traj.p_enu, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] < 2:
            continue

        m = _finite_mask(p[:, :2])
        if not np.any(m):
            continue

        E = p[m, 0]
        N = p[m, 1]

        # 让主模式（比如 graph）线条稍微显眼一点
        if mode_name == "graph":
            lw = 2.0
            alpha = 0.95
        else:
            lw = 1.2
            alpha = 0.8

        ax.plot(E, N, label=mode_name, linewidth=lw, alpha=alpha)

        # 可选：给每条曲线标一下起点 / 终点
        ax.scatter(E[0], N[0], s=25, marker="o", edgecolors="none", alpha=0.8)
        ax.scatter(E[-1], N[-1], s=25, marker="s", edgecolors="none", alpha=0.8)

    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")

    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    if ax.lines:
        leg = ax.legend(frameon=False, loc="best")
        for lh in leg.legend_handles:
            if hasattr(lh, "set_linewidth"):
                lh.set_linewidth(1.5)

    _save_fig(fig, out_path)

    if show:
        plt.show()

    return out_path

