# src/offnav/algo/eskf_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from offnav.core.nav_config import NavConfig
from offnav.models.eskf_state import EskfFilter, EskfDiagnostics  # noqa: F401

from offnav.algo.eskf_common import (
    EskfInputs,
    EskfOutputs,
    get_roll_pitch_rad,
    postprocess_traj_df,
    audit_dataframe,
)

from offnav.algo.event_timeline import (
    EventKind,
    TimeAlignmentReport,
)

from offnav.algo.eskf_timeline import build_eskf_timeline

from offnav.algo.eskf_measurements import (
    DvlDerivedSignals,
    build_dvl_be_measurement,
    build_dvl_bi_measurement,
)


# =============================================================================
# Focus Monitor: only print the quantities we care about now
# =============================================================================
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List

import numpy as np
import pandas as pd


@dataclass
class FocusMonitor:
    """
    轻度监视器：不在终端打印，改为记录关键量到 CSV，供离线排查。
    记录粒度：每次 used 的 DVL 更新都记录一行（可再加采样/触发策略）。
    """
    enabled: bool = True

    # 记录策略
    record_every_used: int = 1           # 每 N 次 used 更新记录一次（1=全记录）
    record_on_trigger_always: bool = True  # 触发异常时强制记录（即使不在周期点）

    # 触发阈值（用于标记，不一定阻断记录）
    ratio_warn: float = 5.0
    vpre_warn_mps: float = 3.0
    nis_warn: float = 100.0

    # 输出
    out_csv: Optional[str] = None        # 若 None，则由 engine 生成默认路径
    rows: List[Dict[str, Any]] = field(default_factory=list)

    # 内部计数
    _cnt_used: int = 0
    _cnt_record: int = 0
    _cnt_trigger: int = 0

    # 内部极值（用于终端简报）
    _max_ratio: float = float("nan")
    _max_vpre: float = float("nan")
    _max_nis: float = float("nan")

    def on_used_update(
        self,
        *,
        t: float,
        dt_match_s: float,
        v_meas: np.ndarray,
        v_pre: np.ndarray,
        v_post: np.ndarray,
        r: Optional[np.ndarray],
        nis: float,
        used_reason: str,
    ) -> None:
        if not self.enabled:
            return

        self._cnt_used += 1

        v_meas = np.asarray(v_meas, dtype=float).reshape(3)
        v_pre = np.asarray(v_pre, dtype=float).reshape(3)
        v_post = np.asarray(v_post, dtype=float).reshape(3)

        sp_meas = float(np.linalg.norm(v_meas))
        sp_pre = float(np.linalg.norm(v_pre))
        ratio = sp_pre / max(sp_meas, 1e-6)

        dv = v_post - v_pre
        dv_mag = float(np.linalg.norm(dv))

        # residual components
        if r is None:
            r0 = r1 = r2 = float("nan")
        else:
            rr = np.asarray(r, dtype=float).reshape(-1)
            r0 = float(rr[0]) if rr.size > 0 else float("nan")
            r1 = float(rr[1]) if rr.size > 1 else float("nan")
            r2 = float(rr[2]) if rr.size > 2 else float("nan")

        # trigger flags
        trig_ratio = bool(np.isfinite(ratio) and ratio > self.ratio_warn)
        trig_vpre = bool(np.isfinite(sp_pre) and sp_pre > self.vpre_warn_mps)
        trig_nis = bool(np.isfinite(nis) and nis > self.nis_warn)
        triggered = trig_ratio or trig_vpre or trig_nis

        if triggered:
            self._cnt_trigger += 1

        # update max stats
        self._max_ratio = _nanmax(self._max_ratio, ratio)
        self._max_vpre = _nanmax(self._max_vpre, sp_pre)
        self._max_nis = _nanmax(self._max_nis, nis)

        # decide record
        periodic = (self.record_every_used > 0) and (self._cnt_used % self.record_every_used == 0)
        if not (periodic or (self.record_on_trigger_always and triggered)):
            return

        self._cnt_record += 1

        self.rows.append(
            {
                "t_s": float(t),
                "dt_match_s": float(dt_match_s),

                "vE_meas": float(v_meas[0]),
                "vN_meas": float(v_meas[1]),
                "vU_meas": float(v_meas[2]),
                "speed_meas": float(sp_meas),

                "vE_pre": float(v_pre[0]),
                "vN_pre": float(v_pre[1]),
                "vU_pre": float(v_pre[2]),
                "speed_pre": float(sp_pre),

                "vE_post": float(v_post[0]),
                "vN_post": float(v_post[1]),
                "vU_post": float(v_post[2]),

                "dvE": float(dv[0]),
                "dvN": float(dv[1]),
                "dvU": float(dv[2]),
                "dv_mag": float(dv_mag),

                "ratio_pre_over_meas": float(ratio),

                "nis": float(nis),
                "r0": float(r0),
                "r1": float(r1),
                "r2": float(r2),

                "trig_ratio": 1.0 if trig_ratio else 0.0,
                "trig_vpre": 1.0 if trig_vpre else 0.0,
                "trig_nis": 1.0 if trig_nis else 0.0,
                "triggered": 1.0 if triggered else 0.0,

                "used_reason": str(used_reason),
            }
        )

    def flush_csv(self, path: str) -> str:
        """
        将 rows 写入 CSV，返回最终路径。若 rows 为空也会写出表头（便于脚本统一处理）。
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(self.rows)
        if df.empty:
            # 仍然写一个空文件（含列）避免“文件不存在”影响后处理
            df = pd.DataFrame(
                columns=[
                    "t_s", "dt_match_s",
                    "vE_meas", "vN_meas", "vU_meas", "speed_meas",
                    "vE_pre", "vN_pre", "vU_pre", "speed_pre",
                    "vE_post", "vN_post", "vU_post",
                    "dvE", "dvN", "dvU", "dv_mag",
                    "ratio_pre_over_meas",
                    "nis", "r0", "r1", "r2",
                    "trig_ratio", "trig_vpre", "trig_nis", "triggered",
                    "used_reason",
                ]
            )
        df.to_csv(p, index=False)
        return str(p)

    def summary(self) -> Dict[str, Any]:
        return {
            "used_updates": int(self._cnt_used),
            "records": int(self._cnt_record),
            "triggers": int(self._cnt_trigger),
            "max_ratio": float(self._max_ratio),
            "max_speed_pre": float(self._max_vpre),
            "max_nis": float(self._max_nis),
        }


def _nanmax(a: float, b: float) -> float:
    if not np.isfinite(a):
        return float(b)
    if not np.isfinite(b):
        return float(a)
    return float(max(a, b))


# =============================================================================
# Top-level pipeline
# =============================================================================

def run_eskf_pipeline(
    nav_cfg: NavConfig,
    inputs: EskfInputs,
    timeline: list[Any] | None = None,
) -> EskfOutputs:
    """
    在给定 IMU/DVL 输入（以及可选 timeline）上运行 ESKF。

    坐标系约定（本管线保持一致）：
      - nav: ENU（E, N, U），U 向上为正
      - body: FRD（X前 Y右 Z下）

    角色划分：
      - eskf_engine: timeline 驱动 + 调用 propagate/correct + 轨迹与审计汇总
      - eskf_timeline/event_timeline: IMU/DVL 对齐与事件流构造
      - eskf_measurements: DVL(BE/BI)+IMU姿态 -> nav(ENU) 观测构造
    """
    imu_proc = inputs.imu_proc
    df_be = inputs.dvl_be_df

    imu_t = np.asarray(getattr(imu_proc, "t_s", []), dtype=float)
    if imu_t.size == 0:
        raise RuntimeError("IMU t_s is empty in EskfInputs.imu_proc")

    # ---------- timeline & time report ----------
    if timeline is None:
        timeline, rep = build_eskf_timeline(nav_cfg, inputs)
    else:
        rep = _estimate_time_report_from_inputs(imu_t, df_be, timeline=timeline)

    # ---------- mode dispatch (quiet fallback) ----------
    mode = str(getattr(nav_cfg.eskf, "mode", "full_ins")).lower()
    if mode != "full_ins":
        mode = "full_ins"

    return _run_eskf_full_ins(
        nav_cfg=nav_cfg,
        inputs=inputs,
        imu_t=imu_t,
        timeline=timeline,
        rep=rep,
    )

# =============================================================================
# full_ins engine
# =============================================================================

def _run_eskf_full_ins(
    nav_cfg: NavConfig,
    inputs: EskfInputs,
    imu_t: np.ndarray,
    timeline: List[Any],
    rep: TimeAlignmentReport,
) -> EskfOutputs:
    """
    full_ins：IMU propagate + DVL 速度更新。

    坐标系约定：
      - nav: ENU（E, N, U），U 向上为正
      - body: FRD（X前 Y右 Z下）
    """
    imu_proc = inputs.imu_proc

    # DVL derived signals (one-shot)
    derived = DvlDerivedSignals.from_inputs(inputs)

    # filter init
    eskf = EskfFilter(nav_cfg.eskf, nav_cfg.frames, nav_cfg.deadreckon.init_pose)
    eskf.set_initial_time(float(imu_t[0]))

    has_explicit_R = hasattr(eskf, "correct_dvl_vel_enu_R")

    # --- which DVL measurement source to use ---
    # "BE" (default) | "BI" | "BE_ONLY_Z_BI_XY"
    dvl_update_source = str(getattr(nav_cfg.eskf, "dvl_update_source", "BE")).upper()

    use_be_cfg = bool(getattr(nav_cfg.eskf, "use_dvl_BE_vel", True))
    use_bi_cfg = bool(getattr(nav_cfg.eskf, "use_dvl_BI_vel", True))

    # Resolve to effective switches (avoid double-update for same physical frame)
    use_dvl_be_update = False
    use_dvl_bi_update = False
    if dvl_update_source == "BI":
        use_dvl_bi_update = use_bi_cfg
        use_dvl_be_update = False
    elif dvl_update_source == "BE_ONLY_Z_BI_XY":
        # 仍然走 BE 事件，但 measurement 内部会用 BI 替换水平（你已有实现）
        use_dvl_be_update = use_be_cfg
        use_dvl_bi_update = False
    else:
        # default "BE"
        use_dvl_be_update = use_be_cfg
        use_dvl_bi_update = False

    nav_t_start, nav_t_end = _compute_nav_window(imu_t, rep)

    # buffers
    traj_rows: list[tuple] = []
    audit_rows: list[Dict[str, Any]] = []

    stats = {
        "used": 0,
        "skipped": 0,
        "update_fail": 0,
        "used_be": 0,
        "used_bi": 0,
    }

    # --- Focus monitor (CSV logger) ---
    mon = FocusMonitor(
        enabled=bool(getattr(nav_cfg.eskf, "focus_enabled", True)),
        record_every_used=int(getattr(nav_cfg.eskf, "focus_record_every_used", 1)),
        record_on_trigger_always=bool(getattr(nav_cfg.eskf, "focus_record_on_trigger_always", True)),
        ratio_warn=float(getattr(nav_cfg.eskf, "focus_ratio_warn", 5.0)),
        vpre_warn_mps=float(getattr(nav_cfg.eskf, "focus_vpre_warn_mps", 3.0)),
        nis_warn=float(getattr(nav_cfg.eskf, "focus_nis_warn", 100.0)),
        out_csv=getattr(nav_cfg.eskf, "focus_out_csv", None),
    )

    # main loop
    for ev in timeline:
        if ev.kind == EventKind.IMU:
            _step_imu_propagate_and_log(
                eskf=eskf,
                imu_proc=imu_proc,
                imu_t=imu_t,
                ev=ev,
                traj_rows=traj_rows,
            )
            continue

        if ev.kind == EventKind.DVL_BE:
            _handle_dvl_be_event(
                eskf=eskf,
                nav_cfg=nav_cfg,
                imu_proc=imu_proc,
                imu_t=imu_t,
                ev=ev,
                derived=derived,
                nav_t_start=nav_t_start,
                nav_t_end=nav_t_end,
                use_dvl_update=use_dvl_be_update,
                has_explicit_R=has_explicit_R,
                audit_rows=audit_rows,
                stats=stats,
                mon=mon,
            )
            continue

        # NEW: DVL_BI event support
        if hasattr(EventKind, "DVL_BI") and ev.kind == EventKind.DVL_BI:
            _handle_dvl_bi_event(
                eskf=eskf,
                nav_cfg=nav_cfg,
                imu_proc=imu_proc,
                imu_t=imu_t,
                ev=ev,
                derived=derived,
                nav_t_start=nav_t_start,
                nav_t_end=nav_t_end,
                use_dvl_update=use_dvl_bi_update,
                has_explicit_R=has_explicit_R,
                audit_rows=audit_rows,
                stats=stats,
                mon=mon,
            )
            continue

    traj_df = pd.DataFrame(
        traj_rows,
        columns=["t_s", "E", "N", "U", "yaw_rad", "yaw_deg", "vE", "vN", "vU"],
    )
    traj_df = postprocess_traj_df(traj_df, nav_cfg.eskf)

    diag: EskfDiagnostics = eskf.diag
    audit_df = audit_dataframe(audit_rows)

    # =========================
    # flush focus csv + summary
    # =========================
    focus_csv: Optional[str] = None
    focus_sum: Optional[Dict[str, Any]] = None

    if mon.enabled:
        out_path = str(mon.out_csv) if mon.out_csv else "out/diag/eskf_focus_monitor.csv"
        focus_csv = mon.flush_csv(out_path)
        focus_sum = mon.summary()

    # =========================
    # final one-line summary
    # =========================
    if bool(getattr(nav_cfg.eskf, "print_summary", True)):
        msg = (
            f"[ESKF] mode=full_ins dvl_src={dvl_update_source} "
            f"used={stats['used']} (BE={stats['used_be']}, BI={stats['used_bi']}) "
            f"skip={stats['skipped']} fail={stats['update_fail']}"
        )
        if focus_sum is not None:
            msg += (
                f" focus_records={focus_sum.get('records', -1)}"
                f" focus_triggers={focus_sum.get('triggers', -1)}"
                f" focus_max_ratio={float(focus_sum.get('max_ratio', float('nan'))):.3f}"
                f" focus_max_vpre={float(focus_sum.get('max_speed_pre', float('nan'))):.3f}"
                f" focus_max_nis={float(focus_sum.get('max_nis', float('nan'))):.3f}"
            )
        if focus_csv is not None:
            msg += f" focus_csv={focus_csv}"
        print(msg)

    return EskfOutputs(traj_df=traj_df, diag=diag, audit_df=audit_df)

# =============================================================================
# Helpers: IMU step
# =============================================================================

def _step_imu_propagate_and_log(
    eskf: EskfFilter,
    imu_proc: Any,
    imu_t: np.ndarray,
    ev: Any,
    traj_rows: list[tuple],
) -> None:
    k = int(ev.imu_k)
    tk = float(imu_t[k])
    if not np.isfinite(tk):
        return

    acc_b = imu_proc.acc_mps2[k]
    gyro_b = imu_proc.gyro_in_rad_s[k]
    roll_rad, pitch_rad = get_roll_pitch_rad(imu_proc, k)

    eskf.propagate_imu(tk, acc_b, gyro_b, roll_rad, pitch_rad)

    # log state
    E, Nn, U = eskf.p_enu
    vE, vN, vU = eskf.v_enu
    yaw_rad = float(getattr(eskf, "yaw_rad", np.nan))

    traj_rows.append((tk, E, Nn, U, yaw_rad, float(np.rad2deg(yaw_rad)), vE, vN, vU))


# =============================================================================
# Helpers: DVL event
# =============================================================================
def _handle_dvl_be_event(
    *,
    eskf: EskfFilter,
    nav_cfg: NavConfig,
    imu_proc: Any,
    imu_t: np.ndarray,
    ev: Any,
    derived: DvlDerivedSignals,
    nav_t_start: float,
    nav_t_end: float,
    use_dvl_update: bool,
    has_explicit_R: bool,
    audit_rows: list[Dict[str, Any]],
    stats: Dict[str, int],
    mon: FocusMonitor,
) -> None:
    j = int(ev.dvl_j)
    k = int(ev.imu_anchor_k) if getattr(ev, "imu_anchor_k", None) is not None else None
    t_dvl = float(ev.t_s)

    # 0) window check
    if (not np.isfinite(t_dvl)) or (t_dvl < nav_t_start) or (t_dvl > nav_t_end):
        _append_skip_audit(
            audit_rows=audit_rows,
            t_imu=np.nan,
            t_dvl=t_dvl,
            dt=np.nan,
            src="BE",
            src_xy="NA",
            reason="OUT_OF_NAV_WINDOW",
        )
        stats["skipped"] += 1
        return

    if k is None:
        _append_skip_audit(
            audit_rows=audit_rows,
            t_imu=np.nan,
            t_dvl=t_dvl,
            dt=np.nan,
            src="BE",
            src_xy="NA",
            reason=str(getattr(ev, "used_reason", "NO_ANCHOR")),
        )
        stats["skipped"] += 1
        return

    # 1) build measurement (nav ENU)
    try:
        v_meas, base_row = build_dvl_be_measurement(
            j=j,
            k=k,
            t_dvl=t_dvl,
            imu_t=imu_t,
            imu_proc=imu_proc,
            eskf=eskf,
            nav_cfg=nav_cfg,
            derived=derived,
        )
    except Exception as e:
        _append_skip_audit(
            audit_rows=audit_rows,
            t_imu=float(imu_t[k]),
            t_dvl=t_dvl,
            dt=float(imu_t[k] - t_dvl),
            src="BE",
            src_xy="ERR",
            reason=f"MEAS_EXCEPTION:{e!r}",
        )
        stats["skipped"] += 1
        return

    # 2) pre-state snapshot (明确：update 前)
    v_pre = np.asarray(eskf.v_enu, dtype=float).reshape(3)
    p_pre = np.asarray(eskf.p_enu, dtype=float).reshape(3)

    row: Dict[str, Any] = dict(base_row)
    row.update(
        {
            "used": 1.0 if bool(getattr(ev, "used", True)) else 0.0,
            "used_reason": str(getattr(ev, "used_reason", "USED_OK")),
            "vE_pre": float(v_pre[0]),
            "vN_pre": float(v_pre[1]),
            "vU_pre": float(v_pre[2]),
            "E_pre": float(p_pre[0]),
            "N_pre": float(p_pre[1]),
            "U_pre": float(p_pre[2]),
            "report_ok": False,
        }
    )

    # 3) event-level gate
    if not bool(getattr(ev, "used", True)):
        audit_rows.append(row)
        stats["skipped"] += 1
        return

    # 4) cfg-level gate
    if not use_dvl_update:
        row["used"] = 0.0
        row["used_reason"] = "DISABLED_BY_CFG"
        audit_rows.append(row)
        stats["skipped"] += 1
        return

    # 5) apply update
    ok = _apply_dvl_update(
        eskf=eskf,
        nav_cfg=nav_cfg,
        v_meas=v_meas,
        has_explicit_R=has_explicit_R,
    )
    if not ok:
        row["used"] = 0.0
        row["used_reason"] = "UPDATE_EXCEPTION"
        audit_rows.append(row)
        stats["update_fail"] += 1
        return

    stats["used"] += 1

    # 6) attach diag (residual/NIS) + return for focus monitor
    nis, r_vec = _attach_update_diag_and_return(eskf, row)

    # 7) post-state & delta (明确：update 后)
    v_post = np.asarray(eskf.v_enu, dtype=float).reshape(3)
    p_post = np.asarray(eskf.p_enu, dtype=float).reshape(3)

    row["vE_post"], row["vN_post"], row["vU_post"] = float(v_post[0]), float(v_post[1]), float(v_post[2])
    row["E_post"], row["N_post"], row["U_post"] = float(p_post[0]), float(p_post[1]), float(p_post[2])

    row["dvE"], row["dvN"], row["dvU"] = float(v_post[0] - v_pre[0]), float(v_post[1] - v_pre[1]), float(v_post[2] - v_pre[2])
    row["dpE"], row["dpN"], row["dpU"] = float(p_post[0] - p_pre[0]), float(p_post[1] - p_pre[1]), float(p_post[2] - p_pre[2])

    audit_rows.append(row)

    # 8) focus monitor print (only when needed)
    mon.on_used_update(
        t=float(row.get("t_imu_s", float(imu_t[k]))),
        dt_match_s=float(row.get("dt_match_s", float("nan"))),
        v_meas=v_meas,
        v_pre=v_pre,
        v_post=v_post,
        r=r_vec,
        nis=float(nis),
        used_reason=str(row.get("used_reason", "USED_OK")),
    )
    
def _handle_dvl_bi_event(
    eskf: EskfFilter,
    nav_cfg: NavConfig,
    imu_proc: Any,
    imu_t: np.ndarray,
    ev: Any,
    derived: DvlDerivedSignals,
    nav_t_start: float,
    nav_t_end: float,
    use_dvl_update: bool,
    has_explicit_R: bool,
    audit_rows: list[Dict[str, Any]],
    stats: Dict[str, int],
    mon: Any,
) -> None:
    j = int(ev.dvl_j)
    k = int(ev.imu_anchor_k) if ev.imu_anchor_k is not None else None
    t_dvl = float(ev.t_s)

    # 0) window check
    if (not np.isfinite(t_dvl)) or (t_dvl < nav_t_start) or (t_dvl > nav_t_end):
        _append_skip_audit(
            audit_rows,
            t_imu=np.nan,
            t_dvl=t_dvl,
            dt=np.nan,
            src="BI",
            src_xy="NA",
            reason="OUT_OF_NAV_WINDOW",
        )
        stats["skipped"] += 1
        return

    if k is None:
        _append_skip_audit(
            audit_rows,
            t_imu=np.nan,
            t_dvl=t_dvl,
            dt=np.nan,
            src="BI",
            src_xy="NA",
            reason=str(getattr(ev, "used_reason", "NO_ANCHOR")),
        )
        stats["skipped"] += 1
        return

    # 1) build measurement (nav ENU)
    try:
        v_meas, base_row = build_dvl_bi_measurement(
            j=j,
            k=k,
            t_dvl=t_dvl,
            imu_t=imu_t,
            imu_proc=imu_proc,
            eskf=eskf,
            nav_cfg=nav_cfg,
            derived=derived,
        )
    except Exception as e:
        _append_skip_audit(
            audit_rows,
            t_imu=float(imu_t[k]),
            t_dvl=t_dvl,
            dt=float(imu_t[k] - t_dvl),
            src="BI",
            src_xy="ERR",
            reason=f"MEAS_EXCEPTION:{e!r}",
        )
        stats["skipped"] += 1
        return

    # 2) pre-state snapshot
    v_pre = np.asarray(getattr(eskf, "v_enu", [np.nan, np.nan, np.nan]), dtype=float).reshape(3)
    p_pre = np.asarray(getattr(eskf, "p_enu", [np.nan, np.nan, np.nan]), dtype=float).reshape(3)

    row: Dict[str, Any] = dict(base_row)
    row.update(
        {
            "used": 1.0 if bool(getattr(ev, "used", True)) else 0.0,
            "used_reason": str(getattr(ev, "used_reason", "USED_OK")),
            "vE_pre": float(v_pre[0]),
            "vN_pre": float(v_pre[1]),
            "vU_pre": float(v_pre[2]),
            "E_pre": float(p_pre[0]),
            "N_pre": float(p_pre[1]),
            "U_pre": float(p_pre[2]),
            "report_ok": False,
        }
    )

    # 3) event-level gate
    if not bool(getattr(ev, "used", True)):
        audit_rows.append(row)
        stats["skipped"] += 1
        return

    # 4) cfg-level gate
    if not use_dvl_update:
        row["used"] = 0.0
        row["used_reason"] = "DISABLED_BY_CFG"
        audit_rows.append(row)
        stats["skipped"] += 1
        return

    # 5) apply update
    ok = _apply_dvl_update(
        eskf=eskf,
        nav_cfg=nav_cfg,
        v_meas=v_meas,
        has_explicit_R=has_explicit_R,
    )
    if not ok:
        row["used"] = 0.0
        row["used_reason"] = "UPDATE_EXCEPTION"
        audit_rows.append(row)
        stats["update_fail"] += 1
        return

    stats["used"] += 1
    stats["used_bi"] += 1

    # 6) attach diag (residual/NIS)
    _attach_update_diag(eskf, row)

    # 7) post-state & delta
    vv = np.asarray(getattr(eskf, "v_enu", [np.nan, np.nan, np.nan]), dtype=float).reshape(3)
    pp = np.asarray(getattr(eskf, "p_enu", [np.nan, np.nan, np.nan]), dtype=float).reshape(3)

    row["vE_post"], row["vN_post"], row["vU_post"] = float(vv[0]), float(vv[1]), float(vv[2])
    row["E_post"], row["N_post"], row["U_post"] = float(pp[0]), float(pp[1]), float(pp[2])

    row["dvE"], row["dvN"], row["dvU"] = float(vv[0] - v_pre[0]), float(vv[1] - v_pre[1]), float(vv[2] - v_pre[2])
    row["dpE"], row["dpN"], row["dpU"] = float(pp[0] - p_pre[0]), float(pp[1] - p_pre[1]), float(pp[2] - p_pre[2])

    audit_rows.append(row)

    # 8) focus monitor
    try:
        mon.maybe_record(row)
    except Exception:
        pass


def _apply_dvl_update(
    eskf: EskfFilter,
    nav_cfg: NavConfig,
    v_meas: np.ndarray,
    has_explicit_R: bool,
) -> bool:
    """
    DVL 速度更新入口（兼容两种实现）：
      - 若 EskfFilter 提供 correct_dvl_vel_enu_R，则由 engine 构造 R
      - 否则调用 correct_dvl_vel_enu(vel, dvl_noise_cfg)

    注意：correct_dvl_vel_enu 的第二参应是 DvlNoiseConfig（或等价字段集合）。
    为兼容旧工程：优先 nav_cfg.dvl_noise，不存在则 fallback 到 nav_cfg.eskf。
    """
    try:
        if has_explicit_R:
            R_meas = _build_dvl_R_meas(nav_cfg)
            eskf.correct_dvl_vel_enu_R(v_meas, R_meas)
        else:
            dvl_noise = getattr(nav_cfg, "dvl_noise", None)
            if dvl_noise is None:
                dvl_noise = nav_cfg.eskf
            eskf.correct_dvl_vel_enu(v_meas, dvl_noise)
        return True
    except Exception:
        return False


def _build_dvl_R_meas(nav_cfg: NavConfig) -> np.ndarray:
    sigma_xy = float(
        getattr(
            nav_cfg.eskf,
            "sigma_dvl_xy_mps",
            getattr(nav_cfg.eskf, "sigma_dvl_mps", 0.20),
        )
    )
    sigma_z = float(
        getattr(
            nav_cfg.eskf,
            "sigma_dvl_z_mps",
            max(0.05, 0.5 * sigma_xy),
        )
    )
    return np.diag([sigma_xy**2, sigma_xy**2, sigma_z**2]).astype(float)


def _attach_update_diag_and_return(eskf: EskfFilter, row: Dict[str, Any]) -> Tuple[float, Optional[np.ndarray]]:
    """
    保留下游字段接口（row['nis','r0','r1','r2','S0','S1','S2']），
    同时返回 (nis, r_vec) 给 FocusMonitor。
    """
    nis = float("nan")
    r0 = r1 = r2 = float("nan")
    S0 = S1 = S2 = float("nan")
    r_vec: Optional[np.ndarray] = None

    if (
        hasattr(eskf, "diag")
        and hasattr(eskf.diag, "updates")
        and isinstance(eskf.diag.updates, list)
        and len(eskf.diag.updates) > 0
    ):
        u = eskf.diag.updates[-1]
        row["report_ok"] = True

        nis = float(getattr(u, "nis", np.nan))
        rr = np.asarray(getattr(u, "r", []), dtype=float).reshape(-1)
        ss = np.asarray(getattr(u, "S_diag", []), dtype=float).reshape(-1)

        r_vec = rr.copy() if rr.size > 0 else None

        if rr.size > 0:
            r0 = float(rr[0])
        if rr.size > 1:
            r1 = float(rr[1])
        if rr.size > 2:
            r2 = float(rr[2])

        if ss.size > 0:
            S0 = float(ss[0])
        if ss.size > 1:
            S1 = float(ss[1])
        if ss.size > 2:
            S2 = float(ss[2])

    row.update({"nis": nis, "r0": r0, "r1": r1, "r2": r2, "S0": S0, "S1": S1, "S2": S2})
    return nis, r_vec


def _append_skip_audit(
    audit_rows: list[Dict[str, Any]],
    t_imu: float,
    t_dvl: float,
    dt: float,
    src: str,
    src_xy: str,
    reason: str,
) -> None:
    audit_rows.append(
        {
            "t_imu_s": t_imu,
            "t_dvl_s": t_dvl,
            "dt_match_s": dt,
            "src": src,
            "src_xy": src_xy,
            "used": 0.0,
            "used_reason": reason,
        }
    )


# =============================================================================
# Helpers: nav window & time report
# =============================================================================

def _compute_nav_window(imu_t: np.ndarray, rep: TimeAlignmentReport) -> Tuple[float, float]:
    nav_t_start = rep.imu_t0 if np.isfinite(rep.imu_t0) else float(imu_t[0])
    nav_t_end = rep.imu_t1 if np.isfinite(rep.imu_t1) else float(imu_t[-1])
    return float(nav_t_start), float(nav_t_end)


def _estimate_time_report_from_inputs(
    imu_t: np.ndarray,
    df_be: Optional[pd.DataFrame],
    timeline: Optional[list[Any]] = None,
) -> TimeAlignmentReport:
    """
    当外部传入 timeline 时，构造一个尽量完整且对 TimeAlignmentReport 字段自适配的报告。

    关键目标：
      - 不再依赖 TimeAlignmentReport 的固定字段集合（字段新增也不炸）
      - 尽可能从 timeline 里估计 nav_k0/nav_t0/n_dvl_used
    """
    t_imu0, t_imu1 = float(imu_t[0]), float(imu_t[-1])

    # 取 DVL 时间（如果有）
    try:
        # 兼容旧实现：event_timeline 内部曾用 _extract_time_s
        from offnav.algo.event_timeline import _extract_time_s  # noqa: WPS433
        if df_be is not None:
            t_dvl = np.asarray(_extract_time_s(df_be), dtype=float)
        else:
            t_dvl = np.asarray([], dtype=float)
    except Exception:
        # 如果你后来把它改成 public extract_time_s，也可以在这里再尝试一次
        try:
            from offnav.algo.event_timeline import extract_time_s  # type: ignore
            if df_be is not None:
                t_dvl = np.asarray(extract_time_s(df_be), dtype=float)
            else:
                t_dvl = np.asarray([], dtype=float)
        except Exception:
            t_dvl = np.asarray([], dtype=float)

    if t_dvl.size > 0:
        dvl_t0 = float(t_dvl[0])
        dvl_t1 = float(t_dvl[-1])
        dvl_n = int(t_dvl.size)
        dt0 = t_imu0 - dvl_t0
        dt1 = t_imu1 - dvl_t1
    else:
        dvl_t0 = float("nan")
        dvl_t1 = float("nan")
        dvl_n = 0
        dt0 = float("nan")
        dt1 = float("nan")

    # --- 从 timeline 推断新增字段（如果存在）---
    nav_k0 = 0
    nav_t0 = t_imu0
    n_dvl_used = 0

    if timeline is not None and len(timeline) > 0:
        # nav_k0/nav_t0：取 timeline 中第一条 IMU 事件（更贴近“实际导航起点”）
        for ev in timeline:
            if getattr(ev, "kind", None) == EventKind.IMU and getattr(ev, "imu_k", None) is not None:
                nav_k0 = int(ev.imu_k)
                nav_t0 = float(getattr(ev, "t_s", t_imu0))
                break

        # n_dvl_used：统计 timeline 里 used=True 的 DVL_BE 事件数
        for ev in timeline:
            if getattr(ev, "kind", None) == EventKind.DVL_BE:
                if bool(getattr(ev, "used", True)):
                    n_dvl_used += 1

    # --- 自适配构造 TimeAlignmentReport ---
    rep_kwargs: Dict[str, Any] = {
        "imu_t0": t_imu0,
        "imu_t1": t_imu1,
        "imu_n": int(imu_t.size),
        "dvl_t0": dvl_t0,
        "dvl_t1": dvl_t1,
        "dvl_n": dvl_n,
        "dt0_imu_minus_dvl": dt0,
        "dt1_imu_minus_dvl": dt1,
        "nav_k0": nav_k0,
        "nav_t0": nav_t0,
        "n_dvl_used": n_dvl_used,
    }

    # 根据 dataclass 字段过滤（最稳）
    fields = getattr(TimeAlignmentReport, "__dataclass_fields__", None)
    if isinstance(fields, dict) and len(fields) > 0:
        rep_kwargs = {k: v for k, v in rep_kwargs.items() if k in fields}

    return TimeAlignmentReport(**rep_kwargs)
