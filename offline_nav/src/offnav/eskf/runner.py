from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import numpy as np
import pandas as pd

from .config import Eskf2DConfig
from .io_csv import load_imu_filtered_csv, load_dvl_bi_csv, load_dvl_be_csv
from .math_utils import wrap_pm_pi, rpy_to_R_nb_enu
from .filter import Eskf2D

from offnav.eskf.monitor import FocusMonitor, FocusMonitorConfig


# =============================================================================
# helpers
# =============================================================================

def _nearest_index(t_arr: np.ndarray, t: float, start_hint: int = 0) -> int:
    """
    两指针友好：从 start_hint 开始向前推进，找到最接近 t 的索引。
    假设 t_arr 单调递增。
    """
    n = int(t_arr.size)
    if n <= 0:
        return 0
    i = max(0, min(int(start_hint), n - 1))
    while i + 1 < n and float(t_arr[i + 1]) <= t:
        i += 1
    if i + 1 < n:
        if abs(float(t_arr[i + 1]) - t) < abs(float(t_arr[i]) - t):
            return i + 1
    return i


def _sanitize_sort_imu(imu) -> None:
    idx = np.argsort(imu.t)
    imu.t = imu.t[idx]
    imu.roll = imu.roll[idx]
    imu.pitch = imu.pitch[idx]
    imu.yaw = imu.yaw[idx]
    imu.acc_b = imu.acc_b[idx, :]
    imu.gyro_b = imu.gyro_b[idx, :]


def _sanitize_sort_dvl_bi(bi) -> None:
    idx = np.argsort(bi.t)
    bi.t = bi.t[idx]
    bi.v_b = bi.v_b[idx, :]


def _sanitize_sort_dvl_be(be) -> None:
    idx = np.argsort(be.t)
    be.t = be.t[idx]
    be.v_enu = be.v_enu[idx, :]


def _finite_mask_1d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    return np.isfinite(x)


def _time_overlap_window(
    imu_t: np.ndarray, bi_t: np.ndarray
) -> Tuple[float, float]:
    """
    路线 A：严格对齐起止点，只在两者交集时间窗内运行。
    """
    imu_t = np.asarray(imu_t, dtype=float).reshape(-1)
    bi_t = np.asarray(bi_t, dtype=float).reshape(-1)

    imu_ok = imu_t[np.isfinite(imu_t)]
    bi_ok = bi_t[np.isfinite(bi_t)]
    if imu_ok.size == 0 or bi_ok.size == 0:
        return (float("nan"), float("nan"))

    t0 = max(float(imu_ok[0]), float(bi_ok[0]))
    t1 = min(float(imu_ok[-1]), float(bi_ok[-1]))
    return (t0, t1)


def _yaw_used_from_imu(cfg: Eskf2DConfig, yaw_meas_rad: float) -> float:
    """
    统一 yaw 约定（避免 sign/offset 重复）：
      yaw_used = wrap( yaw_sign * yaw_meas + yaw_offset )
    """
    y = cfg.yaw_sign * float(yaw_meas_rad) + float(getattr(cfg, "yaw_offset_rad", 0.0))
    return wrap_pm_pi(y) if cfg.yaw_wrap else y


def _init_filter_state(f: Eskf2D, cfg: Eskf2DConfig, imu) -> None:
    """
    初始化策略（路线 A 简洁版）：
      - p,v 用 config init_*
      - yaw 用 IMU 首帧（经 yaw_sign+yaw_offset），并写入 f.yaw
      - bgz 用 config init_bgz
      - P0 用 cfg 的 P0_* 标量
    """
    # position/vel
    f.p[:] = np.array([cfg.init_E, cfg.init_N], dtype=float)
    f.v[:] = np.array([cfg.init_vE, cfg.init_vN], dtype=float)

    # yaw: prefer IMU first sample unless you明确要求用 cfg.init_yaw_rad
    yaw0 = _yaw_used_from_imu(cfg, float(imu.yaw[0]))
    # 如果你确实想强制用 cfg.init_yaw_rad，就把下面一行换成 cfg.init_yaw_rad
    f.yaw = yaw0

    # bgz
    f.bgz = float(cfg.init_bgz)

    # covariance
    # 约定：state = [E, N, vE, vN, yaw, bgz]
    P = np.zeros((6, 6), dtype=float)
    P[0, 0] = float(cfg.P0_pos_m2)
    P[1, 1] = float(cfg.P0_pos_m2)
    P[2, 2] = float(cfg.P0_vel_m2s2)
    P[3, 3] = float(cfg.P0_vel_m2s2)
    P[4, 4] = float(cfg.P0_yaw_rad2)
    P[5, 5] = float(cfg.P0_bgz_rad2s2)
    f.P[:, :] = P


def _build_monitor(cfg: Eskf2DConfig) -> FocusMonitor:
    mon_cfg = FocusMonitorConfig(
        enabled=bool(getattr(cfg, "focus_enabled", True)),
        record_every_update=int(getattr(cfg, "focus_record_every", 1)),
        record_on_trigger_always=bool(getattr(cfg, "focus_record_on_trigger_always", True)),

        ratio_warn=float(getattr(cfg, "focus_ratio_warn", 5.0)),
        vpre_warn_mps=float(getattr(cfg, "focus_vpre_warn_mps", 3.0)),
        nis_warn=float(getattr(cfg, "focus_nis_warn", 100.0)),
        verr_h_warn_mps=float(getattr(cfg, "focus_verr_h_warn_mps", 0.30)),

        # 新触发阈值（如果 cfg 没配就用 monitor 默认）
        dx_norm_warn=float(getattr(cfg, "focus_dx_norm_warn", 2.0)),
        rwhite_norm_warn=float(getattr(cfg, "focus_rwhite_norm_warn", 10.0)),
        rinflate_warn=float(getattr(cfg, "focus_rinflate_warn", 50.0)),

        out_csv=str(cfg.focus_csv_path) if getattr(cfg, "focus_csv_path", None) else None,
    )
    return FocusMonitor(mon_cfg)


def _record_bi_update(
    *,
    mon: FocusMonitor,
    kind: str,
    t_meas_s: float,
    t_imu_s: float,
    dt_match_s: float,
    v_pre_enu: np.ndarray,
    v_post_enu: np.ndarray,
    p_pre_enu: np.ndarray,
    p_post_enu: np.ndarray,
    v_meas_enu: np.ndarray,
    v_be_ref_enu: np.ndarray,
    f: Eskf2D,
    diag: Any,
    yaw_used_rad: float,
    ok_prop: bool,
    dt_prop_s: float,
) -> None:
    """
    把 monitor 需要的“增强诊断字段”统一在这里喂进去。
    要求：你的 filter.update_dvl_xy 返回的 diag 尽量包含：
      - nis, r(2,), S(2,2)
      - ok/note/extra
      - 可选：R(2,2), K(6,2), dx(6,), S_diag(2,)
    """
    used = bool(getattr(diag, "ok", True))
    reason = str(getattr(diag, "note", "USED_OK"))

    extra = getattr(diag, "extra", {}) or {}

    # residual pad to ENU3
    if hasattr(diag, "r"):
        r2 = np.asarray(getattr(diag, "r"), dtype=float).reshape(2)
        r_enu = np.array([float(r2[0]), float(r2[1]), 0.0], dtype=float)
    else:
        r_enu = None

    # S diag
    S_diag = None
    if hasattr(diag, "S_diag"):
        sd = np.asarray(getattr(diag, "S_diag"), dtype=float).reshape(-1)
        if sd.size >= 2:
            S_diag = np.array([float(sd[0]), float(sd[1]), np.nan], dtype=float)

    # Optional: enrich used_reason (保持你原来的风格)
    if reason != "USED_OK":
        parts = [reason]
        rinfl = extra.get("R_inflate", None)
        nis0 = extra.get("nis0", None)
        sp_pre = extra.get("speed_pred_h", None)
        sp_meas = extra.get("speed_meas_h", None)
        ratio = extra.get("ratio_pred_over_meas", None)
        try:
            if rinfl is not None and np.isfinite(float(rinfl)) and float(rinfl) != 1.0:
                parts.append(f"Rinf={float(rinfl):.1f}")
            if nis0 is not None and np.isfinite(float(nis0)):
                parts.append(f"nis0={float(nis0):.1f}")
            if (sp_pre is not None) and (sp_meas is not None) and np.isfinite(float(sp_pre)) and np.isfinite(float(sp_meas)):
                parts.append(f"spd={float(sp_pre):.2f}/{float(sp_meas):.2f}")
            if ratio is not None and np.isfinite(float(ratio)):
                parts.append(f"ratio={float(ratio):.2f}")
            reason = "|".join(parts)
        except Exception:
            pass

    mon.record_update(
        kind=str(kind),
        t_meas_s=float(t_meas_s),
        t_imu_s=float(t_imu_s),
        dt_match_s=float(dt_match_s),

        v_pre_enu=v_pre_enu,
        v_post_enu=v_post_enu,
        p_pre_enu=p_pre_enu,
        p_post_enu=p_post_enu,

        v_meas_enu=v_meas_enu,
        v_be_ref_enu=v_be_ref_enu,

        r_enu=r_enu,
        S_diag=S_diag,
        nis=float(getattr(diag, "nis", np.nan)),

        used=bool(used),
        used_reason=str(reason),

        # --- enhanced diagnostics ---
        extra=extra,
        S_2x2=getattr(diag, "S", None),
        R_2x2=getattr(diag, "R", None),
        K_6x2=getattr(diag, "K", None),
        dx_6=getattr(diag, "dx", None),
        P_6x6=getattr(f, "P", None),

        yaw_state_rad=float(getattr(f, "yaw", np.nan)),
        yaw_used_rad=float(yaw_used_rad),
        bgz_rad_s=float(getattr(f, "bgz", np.nan)),

        prop_ok=bool(ok_prop),
        dt_prop_s=float(dt_prop_s),
    )


# =============================================================================
# outputs
# =============================================================================

@dataclass
class Eskf2DOutputs:
    traj_df: pd.DataFrame
    focus_df: pd.DataFrame


# =============================================================================
# main
# =============================================================================

def run_eskf2d(
    imu_path: str | Path,
    dvl_bi_path: str | Path,
    dvl_be_path: str | Path,
    cfg: Eskf2DConfig,
) -> Eskf2DOutputs:
    imu = load_imu_filtered_csv(imu_path)
    bi = load_dvl_bi_csv(dvl_bi_path)
    be = load_dvl_be_csv(dvl_be_path)

    # sort & sanitize
    _sanitize_sort_imu(imu)
    _sanitize_sort_dvl_bi(bi)
    _sanitize_sort_dvl_be(be)

    # strict overlap window (Route A)
    t0, t1 = _time_overlap_window(imu.t, bi.t)
    if not np.isfinite(t0) or not np.isfinite(t1) or t1 <= t0:
        raise RuntimeError(f"[ESKF2D] invalid overlap window: t0={t0}, t1={t1}")

    # mask IMU to overlap (strict)
    m_imu = _finite_mask_1d(imu.t) & (imu.t >= t0) & (imu.t <= t1)
    if not np.any(m_imu):
        raise RuntimeError("[ESKF2D] no IMU samples in overlap window")
    imu_ids = np.nonzero(m_imu)[0]

    # find starting indices
    k0 = int(imu_ids[0])

    # main filter
    f = Eskf2D(cfg)
    f.set_time(float(imu.t[k0]))
    _init_filter_state(f, cfg, imu)

    # pointers for BE reference
    be_ptr = 0

    # Focus monitor
    mon = _build_monitor(cfg)

    # DVL pointer: start from first BI within overlap
    bi_t = np.asarray(bi.t, dtype=float).reshape(-1)
    j = int(np.searchsorted(bi_t, t0, side="left"))
    n_bi = int(bi_t.size)

    # trajectory rows
    traj_rows: List[Dict[str, Any]] = []

    # IMU dt tracker for monitoring
    t_last_imu = float(imu.t[k0])

    for k in range(k0, int(imu.t.size)):
        tk = float(imu.t[k])
        if not np.isfinite(tk):
            continue
        if tk < t0:
            continue
        if tk > t1:
            break

        # dt for propagation diag (not filter dt clamp)
        dt_prop = float(tk - t_last_imu)
        t_last_imu = tk

        # 1) propagate with IMU k
        ok_prop = f.propagate(
            t=tk,
            acc_b=imu.acc_b[k],
            gyro_b=imu.gyro_b[k],
            roll=float(imu.roll[k]),
            pitch=float(imu.pitch[k]),
            yaw_meas=float(imu.yaw[k]),
        )

        # 2) consume BI DVL with t <= tk (and within overlap)
        while j < n_bi and float(bi_t[j]) <= tk:
            t_dvl = float(bi_t[j])
            if not np.isfinite(t_dvl) or t_dvl < t0 or t_dvl > t1:
                j += 1
                continue

            v_b = bi.v_b[j].astype(float).reshape(3)

            # Use IMU attitude at current k (simple; later可升级到“DVL时间最近IMU”)
            roll = float(imu.roll[k])
            pitch = float(imu.pitch[k])

            # IMPORTANT: yaw used must be consistent and not double-sign
            # 这里我们明确：用 IMU yaw_meas（同一时刻 k）做 yaw_used（带 sign+offset）
            yaw_used = _yaw_used_from_imu(cfg, float(imu.yaw[k]))

            R_nb = rpy_to_R_nb_enu(roll, pitch, yaw_used)
            v_nav = (R_nb @ v_b.reshape(3)).reshape(3)
            v_meas_EN = v_nav[:2].astype(float)

            # pre snapshot
            v_pre_2 = f.v.copy().astype(float).reshape(2)
            p_pre_2 = f.p.copy().astype(float).reshape(2)
            v_pre_enu = np.array([v_pre_2[0], v_pre_2[1], 0.0], dtype=float)
            p_pre_enu = np.array([p_pre_2[0], p_pre_2[1], 0.0], dtype=float)

            # update
            diag = f.update_dvl_xy(v_meas_EN)

            # post snapshot
            v_post_2 = f.v.copy().astype(float).reshape(2)
            p_post_2 = f.p.copy().astype(float).reshape(2)
            v_post_enu = np.array([v_post_2[0], v_post_2[1], 0.0], dtype=float)
            p_post_enu = np.array([p_post_2[0], p_post_2[1], 0.0], dtype=float)

            # BE-U reference (optional)
            be_ptr = _nearest_index(be.t, t_dvl, start_hint=be_ptr)
            vU_be = float(be.v_enu[be_ptr, 2]) if be.t.size > 0 else float("nan")

            dt_match = float(tk - t_dvl)

            _record_bi_update(
                mon=mon,
                kind="BI",
                t_meas_s=t_dvl,
                t_imu_s=tk,
                dt_match_s=dt_match,
                v_pre_enu=v_pre_enu,
                v_post_enu=v_post_enu,
                p_pre_enu=p_pre_enu,
                p_post_enu=p_post_enu,
                v_meas_enu=np.array([float(v_meas_EN[0]), float(v_meas_EN[1]), 0.0], dtype=float),
                v_be_ref_enu=np.array([float("nan"), float("nan"), float(vU_be)], dtype=float),
                f=f,
                diag=diag,
                yaw_used_rad=yaw_used,
                ok_prop=ok_prop,
                dt_prop_s=dt_prop,
            )

            j += 1

        # 3) trajectory output
        if cfg.output_full_rate or (k % max(1, int(cfg.output_stride)) == 0):
            be_ptr = _nearest_index(be.t, tk, start_hint=be_ptr)
            vU_be = float(be.v_enu[be_ptr, 2]) if be.t.size > 0 else float("nan")

            s = f.snapshot()
            traj_rows.append(
                {
                    "t_s": tk,
                    "E": s["E"],
                    "N": s["N"],
                    "yaw_rad": s["yaw_rad"],
                    "yaw_deg": float(np.rad2deg(s["yaw_rad"])),
                    "vE": s["vE"],
                    "vN": s["vN"],
                    "vU_be_ref": vU_be,
                    "bgz": s["bgz"],
                    "prop_ok": int(bool(ok_prop)),
                    "dt_prop_s": float(dt_prop),
                }
            )

    traj_df = pd.DataFrame(traj_rows)
    focus_df = mon.to_dataframe() if mon.enabled else pd.DataFrame()

    # write focus csv if configured
    if getattr(cfg, "focus_csv_path", None):
        outp = Path(str(cfg.focus_csv_path))
        outp.parent.mkdir(parents=True, exist_ok=True)
        focus_df.to_csv(outp, index=False)

    if cfg.print_summary:
        summ = mon.summary() if mon.enabled else {}
        print(
            f"[ESKF2D] overlap=[{t0:.3f},{t1:.3f}]  "
            f"imu_n={int(imu_ids.size)}  bi_n_inwin={int(max(0, min(n_bi, np.searchsorted(bi_t, t1, 'right')) - np.searchsorted(bi_t, t0, 'left')))}  "
            f"focus_records={int(summ.get('records', 0))}  triggers={int(summ.get('triggers', 0))}  "
            f"max_ratio={summ.get('max_ratio', float('nan'))}  "
            f"max_vpre={summ.get('max_speed_pre_h', float('nan'))}  "
            f"max_nis={summ.get('max_nis', float('nan'))}  "
            f"max_rinfl={summ.get('max_rinflate', float('nan'))}  "
            f"focus_csv={getattr(cfg, 'focus_csv_path', None)}"
        )

    return Eskf2DOutputs(traj_df=traj_df, focus_df=focus_df)


def run_eskf2d_from_csv(
    imu_csv: str,
    dvl_bi_csv: str,
    dvl_be_csv: str,
    out_traj_csv: Optional[str] = "out/nav/eskf2d_traj.csv",
    cfg: Optional[Eskf2DConfig] = None,
) -> Eskf2DOutputs:
    if cfg is None:
        cfg = Eskf2DConfig()

    out = run_eskf2d(imu_csv, dvl_bi_csv, dvl_be_csv, cfg)

    if out_traj_csv:
        p = Path(out_traj_csv)
        p.parent.mkdir(parents=True, exist_ok=True)
        out.traj_df.to_csv(p, index=False)

    return out
