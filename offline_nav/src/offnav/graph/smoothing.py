# src/offnav/graph/smoothing.py
from __future__ import annotations

"""
Nonlinear least-squares smoothing (Gauss-Newton) for offline factor-graph navigation.

本模块提供一个简单的 Gauss-Newton 求解器:
- 输入: 因子列表 + 初始参数向量 θ0
- 输出: 优化后的 θ 以及迭代统计信息

特性:
- 支持任意实现 Factor 协议的因子 (see offnav.graph.factors)
- 每个因子提供 residual / jacobian / weight_chol
- 可选鲁棒核 (Huber / Cauchy 等，第一版实现 Huber)
"""

from dataclasses import dataclass
from typing import Sequence, Dict, Any, Optional, Tuple

import numpy as np
import time  # 新增：用于统计 wall-time

from offnav.graph.factors import Factor
from offnav.graph.states import STATE_SIZE, BIAS_SIZE, state_slice, wrap_yaw


@dataclass
class GaussNewtonStats:
    """
    Gauss-Newton 迭代统计信息.
    """

    num_iters: int
    converged: bool
    initial_cost: float
    final_cost: float
    final_step_norm: float
    final_cost_change: float
    elapsed_time_s: float  # 新增：总耗时（秒）


# ------------------------------
# 内部工具: yaw wrap
# ------------------------------


def _wrap_yaw_all_states(theta: np.ndarray) -> None:
    """
    将 θ 中所有状态结点的 yaw 分量 wrap 到 (-pi, pi].

    θ 布局:
        θ = [x_0(7), x_1(7), ..., x_{N-1}(7), ba(3), bgz(1)]
    """
    theta = np.asarray(theta, dtype=float)
    D = theta.shape[0]
    if D <= BIAS_SIZE:
        return

    num_states = (D - BIAS_SIZE) // STATE_SIZE
    if num_states <= 0:
        return

    for k in range(num_states):
        s = state_slice(k, num_states)
        idx_yaw = s.start + 6  # x_k 的第 7 维是 yaw
        theta[idx_yaw] = wrap_yaw(theta[idx_yaw])


# ------------------------------
# 内部工具: 鲁棒核
# ------------------------------
def _robust_weight(
    norm_r: float,
    loss_type: Optional[str],
    loss_param: float,
) -> float:
    """
    根据残差范数计算鲁棒核权重 w ∈ (0, 1].

    第一版实现 Huber:
        ρ(s) = { s                   , s <= δ^2
               { 2δ sqrt(s) - δ^2 , s > δ^2
        对应权重:
        w = dρ/ds / 2 ≈
          = 1,  s <= δ^2
          = δ / sqrt(s), s > δ^2

    这里我们用 s = ||r||^2,  δ = loss_param.

    若 loss_type 为 None 或未识别，则返回 1.0 (不使用鲁棒核).
    """
    if loss_type is None:
        return 1.0

    s = norm_r * norm_r
    delta = float(max(loss_param, 1e-6))

    if loss_type.lower() in ("huber", "h"):
        if s <= delta * delta:
            return 1.0
        else:
            # w = delta / sqrt(s)
            return delta / max(norm_r, 1e-6)

    # 可以在此扩展其他核 (Cauchy, Tukey 等)，暂不实现
    return 1.0
# ------------------------------
# 主入口: Gauss-Newton 求解
# ------------------------------
def gauss_newton_solve(
    factors: Sequence[Factor],
    theta0: np.ndarray,
    *,
    max_iters: int = 20,
    tol_step: float = 1e-6,
    tol_cost_rel: float = 1e-6,
    robust_loss: Optional[str] = None,
    robust_param: float = 1.0,
    verbose: bool = False,
) -> Tuple[np.ndarray, GaussNewtonStats]:
    """
    使用 Gauss-Newton 对给定的因子图进行非线性最小二乘优化.

    参数
    ----
    factors : Sequence[Factor]
        因子列表，每个因子实现 residual / jacobian / weight_chol.
    theta0 : np.ndarray, shape (D,)
        初始参数向量 θ0.
    max_iters : int
        最大迭代次数.
    tol_step : float
        迭代步长收敛阈值: 若 ||δ|| < tol_step，则认为收敛.
    tol_cost_rel : float
        相对 cost 变化阈值: 若 |cost_new - cost_old| / max(cost_old,1) < tol_cost_rel，则认为收敛.
    robust_loss : str or None
        鲁棒核类型，如 "huber" 或 None.
    robust_param : float
        鲁棒核参数 δ.
    verbose : bool
        若为 True，则在每次迭代打印 cost / step 等信息.

    返回
    ----
    theta_opt : np.ndarray
        优化后的 θ.
    stats : GaussNewtonStats
        迭代统计信息.
    """
    # ==== 计时开始 ====
    t_start = time.time()

    theta = np.asarray(theta0, dtype=float).reshape(-1)
    D = theta.shape[0]

    if len(factors) == 0:
        # 没有因子，直接返回
        elapsed = time.time() - t_start
        stats = GaussNewtonStats(
            num_iters=0,
            converged=True,
            initial_cost=0.0,
            final_cost=0.0,
            final_step_norm=0.0,
            final_cost_change=0.0,
            elapsed_time_s=elapsed,
        )
        return theta.copy(), stats

    # 计算初始 cost
    def _compute_cost(theta_vec: np.ndarray) -> float:
        cost_val = 0.0
        for f in factors:
            r = f.residual(theta_vec).reshape(-1)
            W = f.weight_chol()
            r_w = W @ r
            w = _robust_weight(np.linalg.norm(r_w), robust_loss, robust_param)
            if w < 1.0:
                r_w = np.sqrt(w) * r_w
            cost_val += 0.5 * float(r_w.T @ r_w)
        return cost_val

    cost_old = _compute_cost(theta)
    initial_cost = cost_old

    converged = False
    final_step_norm = 0.0
    final_cost_change = 0.0

    if verbose:
        print(f"[GN] initial cost = {initial_cost:.6e}")

    for it in range(1, max_iters + 1):
        # --- 构建 Normal Equations: H δ = -g ---
        H = np.zeros((D, D), dtype=float)
        g = np.zeros(D, dtype=float)

        for f in factors:
            r = f.residual(theta).reshape(-1)   # (m,)
            W = f.weight_chol()                # (m,m)
            J = f.jacobian(theta)              # (m,D)

            # 加权
            r_w = W @ r
            J_w = W @ J

            # 鲁棒核
            w = _robust_weight(np.linalg.norm(r_w), robust_loss, robust_param)
            if w < 1.0:
                scale = np.sqrt(w)
                r_w = scale * r_w
                J_w = scale * J_w

            # 累加到 H, g
            H += J_w.T @ J_w
            g += J_w.T @ r_w

        # --- 解 H δ = -g ---
        try:
            delta = np.linalg.solve(H, -g)
        except np.linalg.LinAlgError:
            # 数值不稳定时，可以退回为最小二乘或直接中止
            delta, *_ = np.linalg.lstsq(H, -g, rcond=None)

        step_norm = float(np.linalg.norm(delta))
        final_step_norm = step_norm

        theta = theta + delta
        _wrap_yaw_all_states(theta)

        # --- 计算新 cost ---
        cost_new = _compute_cost(theta)
        cost_change = cost_new - cost_old
        rel_change = abs(cost_change) / max(cost_old, 1.0)
        final_cost_change = cost_change

        if verbose:
            print(
                f"[GN] iter={it:02d}  cost={cost_new:.6e}  "
                f"Δcost={cost_change:.3e}  ||δ||={step_norm:.3e}"
            )

        # 收敛判据
        if step_norm < tol_step or rel_change < tol_cost_rel:
            converged = True
            cost_old = cost_new
            break

        cost_old = cost_new

    final_cost = cost_old

    # ==== 计时结束 ====
    elapsed = time.time() - t_start

    stats = GaussNewtonStats(
        num_iters=it if 'it' in locals() else 0,
        converged=converged,
        initial_cost=initial_cost,
        final_cost=final_cost,
        final_step_norm=final_step_norm,
        final_cost_change=final_cost_change,
        elapsed_time_s=elapsed,
    )

    # 无论 verbose 与否，都打印一行总耗时摘要，方便评估部署
    print(
        f"[GN] total wall-time = {elapsed:.3f} s "
        f"(dim={D}, factors={len(factors)}, iters={stats.num_iters}, "
        f"converged={stats.converged})"
    )

    if verbose:
        flag = "CONVERGED" if converged else "NOT CONVERGED"
        print(
            f"[GN] done: {flag}, iters={stats.num_iters}, "
            f"initial_cost={initial_cost:.6e}, final_cost={final_cost:.6e}"
        )

    return theta, stats

