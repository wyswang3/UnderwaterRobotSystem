# offline_nav/src/offnav/eskf/monitor.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Mapping

import numpy as np
import pandas as pd


# =============================================================================
# helpers
# =============================================================================

def _finite(x: Any, default=np.nan) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else float(default)
    except Exception:
        return float(default)


def _as_arr(x: Any, n: Optional[int] = None) -> np.ndarray:
    try:
        a = np.asarray(x, dtype=float).reshape(-1)
    except Exception:
        a = np.asarray([], dtype=float)
    if n is not None:
        out = np.full((n,), np.nan, dtype=float)
        if a.size > 0:
            out[: min(n, a.size)] = a[: min(n, a.size)]
        return out
    return a


def _norm2(x: Any) -> float:
    a = _as_arr(x)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan")
    return float(np.linalg.norm(a))


def _safe_trace(M: Any) -> float:
    try:
        A = np.asarray(M, dtype=float)
        if A.ndim != 2 or A.shape[0] != A.shape[1]:
            return float("nan")
        return float(np.trace(A))
    except Exception:
        return float("nan")


def _safe_cond(M: Any) -> float:
    try:
        A = np.asarray(M, dtype=float)
        if A.ndim != 2 or A.shape[0] != A.shape[1]:
            return float("nan")
        if not np.all(np.isfinite(A)):
            return float("nan")
        return float(np.linalg.cond(A))
    except Exception:
        return float("nan")


def _solve_safe(A: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Solve A x = b with fallback to pinv."""
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(A) @ b


def _whiten_residual(S_2x2: Any, r_2: Any) -> np.ndarray:
    """
    Compute whitened residual e = L^{-1} r where S = L L^T (Cholesky).
    If Cholesky fails, fallback to solve(S, r) then approximate with sqrt diag.
    """
    r = _as_arr(r_2, 2).reshape(2, 1)
    try:
        S = np.asarray(S_2x2, dtype=float).reshape(2, 2)
        S = 0.5 * (S + S.T)
        # jitter for numeric stability
        S = S + 1e-12 * np.eye(2, dtype=float)
        L = np.linalg.cholesky(S)
        e = np.linalg.solve(L, r).reshape(2)
        return e
    except Exception:
        # fallback: use y = S^{-1} r, scale roughly
        try:
            S = np.asarray(S_2x2, dtype=float).reshape(2, 2)
            y = _solve_safe(S, r).reshape(2)
            # not true whitening, but still provides direction/magnitude signal
            return y
        except Exception:
            return np.full((2,), np.nan, dtype=float)


def _get(extra: Optional[Mapping[str, Any]], key: str, default: Any = None) -> Any:
    if extra is None:
        return default
    try:
        return extra.get(key, default)
    except Exception:
        return default


# =============================================================================
# config
# =============================================================================

@dataclass
class FocusMonitorConfig:
    """
    轻量监视器配置：用于“只盯关键物理量”，并落盘到 CSV。

    触发（trigger）条件：可用于定位
      - 传播爆炸（|v_pre| 大）
      - 语义错/单位错（ratio 大）
      - 统计不一致（NIS 大 / 白化残差大）
      - 更新过猛（|dx| 大）
      - 观测噪声被大量 inflate（R_inflate 大）
      - 2D 速度误差大（verr_h）
    """
    enabled: bool = True
    record_every_update: int = 1
    record_on_trigger_always: bool = True

    # --- trigger thresholds ---
    vpre_warn_mps: float = 3.0
    ratio_warn: float = 5.0
    nis_warn: float = 100.0
    verr_h_warn_mps: float = 0.3

    # new triggers
    dx_norm_warn: float = 2.0               # |dx| (state correction) large
    rwhite_norm_warn: float = 10.0          # |S^{-1/2} r|
    rinflate_warn: float = 50.0             # R inflation factor

    out_csv: Optional[str] = None

    # record extra matrices scalars
    record_cov_metrics: bool = True
    record_whitened_residual: bool = True
    record_state_yaw: bool = True


# =============================================================================
# monitor
# =============================================================================

class FocusMonitor:
    """
    只负责：
      - 收集每次 update 的关键字段（含诊断 / 一致性指标）
      - 决定是否记录（节流 + trigger）
      - 最后 flush 到 CSV
      - 给 summary 方便终端一行打印
    """

    def __init__(self, cfg: FocusMonitorConfig) -> None:
        self.cfg = cfg
        self._rows: List[Dict[str, Any]] = []
        self._n_update_seen = 0
        self._n_recorded = 0
        self._n_triggered = 0

        # summary accumulators
        self._max_ratio = -np.inf
        self._max_vpre = -np.inf
        self._max_nis = -np.inf
        self._max_verr_h = -np.inf

        # new summary
        self._max_rinflate = -np.inf
        self._max_dx_norm = -np.inf
        self._max_rwhite = -np.inf

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.enabled)

    def _should_record(self, triggered: bool) -> bool:
        if not self.enabled:
            return False
        self._n_update_seen += 1

        if triggered and self.cfg.record_on_trigger_always:
            self._n_triggered += 1
            return True

        n = int(self.cfg.record_every_update)
        if n <= 1:
            return True
        return (self._n_update_seen % n) == 0

    # -------------------------------------------------------------------------
    # main entry
    # -------------------------------------------------------------------------
    def record_update(
        self,
        *,
        kind: str,                 # "BI" | "BE" | "OTHER"
        t_meas_s: float,
        t_imu_s: float,
        dt_match_s: float,

        # pre/post state (ENU)
        v_pre_enu: Sequence[float],
        v_post_enu: Sequence[float],
        p_pre_enu: Optional[Sequence[float]] = None,
        p_post_enu: Optional[Sequence[float]] = None,

        # measurements (ENU)
        v_meas_enu: Optional[Sequence[float]] = None,
        v_be_ref_enu: Optional[Sequence[float]] = None,

        # innovation/nis (basic)
        r_enu: Optional[Sequence[float]] = None,          # residual (meas - pred) in ENU (2D -> pad U=0)
        S_diag: Optional[Sequence[float]] = None,         # diag(S) if you already have it
        nis: Optional[float] = None,

        # flags
        used: bool = True,
        used_reason: str = "USED_OK",

        # ---------------- NEW: pass-through diagnostics ----------------
        extra: Optional[Mapping[str, Any]] = None,        # diag.extra directly
        S_2x2: Optional[np.ndarray] = None,               # full S (2x2)
        R_2x2: Optional[np.ndarray] = None,               # full R used (2x2)
        K_6x2: Optional[np.ndarray] = None,
        dx_6: Optional[Sequence[float]] = None,
        P_6x6: Optional[np.ndarray] = None,               # covariance after update (or before; choose consistently)
        yaw_state_rad: Optional[float] = None,            # filter yaw state
        yaw_used_rad: Optional[float] = None,             # yaw used to rotate BI->ENU at this update
        bgz_rad_s: Optional[float] = None,                # gyro bias state
        prop_ok: Optional[bool] = None,                   # propagation success flag for this IMU step
        dt_prop_s: Optional[float] = None,                # IMU dt used in propagation
    ) -> None:
        if not self.enabled:
            return

        v_pre = np.asarray(v_pre_enu, dtype=float).reshape(3)
        v_post = np.asarray(v_post_enu, dtype=float).reshape(3)

        v_meas = None if v_meas_enu is None else np.asarray(v_meas_enu, dtype=float).reshape(3)
        v_be = None if v_be_ref_enu is None else np.asarray(v_be_ref_enu, dtype=float).reshape(3)

        # core magnitudes
        speed_pre_h = float(np.linalg.norm(v_pre[:2])) if np.isfinite(v_pre[:2]).all() else float("nan")
        speed_post_h = float(np.linalg.norm(v_post[:2])) if np.isfinite(v_post[:2]).all() else float("nan")

        speed_meas_h = float(np.linalg.norm(v_meas[:2])) if v_meas is not None and np.isfinite(v_meas[:2]).all() else float("nan")
        ratio = float(speed_pre_h / max(speed_meas_h, 1e-9)) if np.isfinite(speed_pre_h) and np.isfinite(speed_meas_h) else float("nan")

        # velocity errors (post - meas)
        verrE = verrN = verrU = float("nan")
        verr_h = float("nan")
        if v_meas is not None and np.isfinite(v_meas).all() and np.isfinite(v_post).all():
            dv = v_post - v_meas
            verrE, verrN, verrU = float(dv[0]), float(dv[1]), float(dv[2])
            verr_h = float(np.linalg.norm(dv[:2]))

        # vertical reference error (BE as reference)
        vU_be = float("nan")
        vU_post = float(v_post[2]) if np.isfinite(v_post[2]) else float("nan")
        vU_ref_err = float("nan")
        if v_be is not None and np.isfinite(v_be[2]) and np.isfinite(vU_post):
            vU_be = float(v_be[2])
            vU_ref_err = float(vU_post - vU_be)

        # pull extra scalars (from diag.extra if provided)
        nis0 = _finite(_get(extra, "nis0", np.nan))
        nis1 = _finite(_get(extra, "nis1", np.nan))
        rinfl = _finite(_get(extra, "R_inflate", np.nan))
        hphtr = _finite(_get(extra, "HPHt_over_R", np.nan))

        # residual & innovation
        nis_v = _finite(nis)
        r2 = _as_arr(r_enu, 3)  # accept (2,) or (3,)
        rE = _finite(r2[0])
        rN = _finite(r2[1])
        rU = _finite(r2[2]) if r2.size >= 3 else float("nan")

        # obtain S diag
        if S_diag is None:
            # try from full S
            if S_2x2 is not None:
                try:
                    Sd = np.diag(np.asarray(S_2x2, dtype=float).reshape(2, 2)).astype(float)
                    S_diag_use = np.array([Sd[0], Sd[1], np.nan], dtype=float)
                except Exception:
                    S_diag_use = np.array([np.nan, np.nan, np.nan], dtype=float)
            else:
                S_diag_use = np.array([np.nan, np.nan, np.nan], dtype=float)
        else:
            ss = _as_arr(S_diag)
            if ss.size >= 2:
                S_diag_use = np.array([_finite(ss[0]), _finite(ss[1]), _finite(ss[2]) if ss.size >= 3 else np.nan], dtype=float)
            else:
                S_diag_use = np.array([np.nan, np.nan, np.nan], dtype=float)

        # whitened residual (2D)
        rwhite = np.full((2,), np.nan, dtype=float)
        rwhite_norm = float("nan")
        if bool(self.cfg.record_whitened_residual):
            S_for_white = S_2x2 if S_2x2 is not None else None
            if S_for_white is not None:
                rwhite = _whiten_residual(S_for_white, r2[:2])
                rwhite_norm = _norm2(rwhite)

        # dx stats
        dx = _as_arr(dx_6, 6)
        dx_norm = _norm2(dx)
        dx_v_h = float(np.linalg.norm(dx[2:4])) if np.isfinite(dx[2:4]).all() else float("nan")
        dx_yaw = _finite(dx[4])
        dx_bgz = _finite(dx[5])

        # cov metrics
        Pcond = float("nan")
        P_pos_tr = P_vel_tr = P_yaw = P_bgz = float("nan")
        if bool(self.cfg.record_cov_metrics) and P_6x6 is not None:
            P = np.asarray(P_6x6, dtype=float)
            if P.shape == (6, 6) and np.all(np.isfinite(P)):
                Pcond = _safe_cond(P)
                P_pos_tr = float(P[0, 0] + P[1, 1])
                P_vel_tr = float(P[2, 2] + P[3, 3])
                P_yaw = float(P[4, 4])
                P_bgz = float(P[5, 5])

        # yaw chain
        yaw_state = _finite(yaw_state_rad)
        yaw_used = _finite(yaw_used_rad)
        yaw_err = float("nan")
        if bool(self.cfg.record_state_yaw) and np.isfinite(yaw_state) and np.isfinite(yaw_used):
            # wrap to [-pi, pi] difference
            yaw_err = float(((yaw_state - yaw_used + np.pi) % (2.0 * np.pi)) - np.pi)

        # triggers
        triggered = False
        if np.isfinite(speed_pre_h) and speed_pre_h > self.cfg.vpre_warn_mps:
            triggered = True
        if np.isfinite(ratio) and ratio > self.cfg.ratio_warn:
            triggered = True
        if np.isfinite(nis_v) and nis_v > self.cfg.nis_warn:
            triggered = True
        if np.isfinite(verr_h) and verr_h > self.cfg.verr_h_warn_mps:
            triggered = True

        # new triggers
        if np.isfinite(dx_norm) and dx_norm > float(self.cfg.dx_norm_warn):
            triggered = True
        if np.isfinite(rwhite_norm) and rwhite_norm > float(self.cfg.rwhite_norm_warn):
            triggered = True
        if np.isfinite(rinfl) and rinfl > float(self.cfg.rinflate_warn):
            triggered = True

        # update summary maxima
        if np.isfinite(ratio):
            self._max_ratio = max(self._max_ratio, ratio)
        if np.isfinite(speed_pre_h):
            self._max_vpre = max(self._max_vpre, speed_pre_h)
        if np.isfinite(nis_v):
            self._max_nis = max(self._max_nis, nis_v)
        if np.isfinite(verr_h):
            self._max_verr_h = max(self._max_verr_h, verr_h)

        if np.isfinite(rinfl):
            self._max_rinflate = max(self._max_rinflate, rinfl)
        if np.isfinite(dx_norm):
            self._max_dx_norm = max(self._max_dx_norm, dx_norm)
        if np.isfinite(rwhite_norm):
            self._max_rwhite = max(self._max_rwhite, rwhite_norm)

        if not self._should_record(triggered):
            return

        self._n_recorded += 1

        # base row: keep your existing schema (do not remove)
        row: Dict[str, Any] = {
            "kind": str(kind),
            "used": 1.0 if bool(used) else 0.0,
            "used_reason": str(used_reason),

            "t_meas_s": _finite(t_meas_s),
            "t_imu_s": _finite(t_imu_s),
            "dt_match_s": _finite(dt_match_s),

            "vE_pre": _finite(v_pre[0]), "vN_pre": _finite(v_pre[1]), "vU_pre": _finite(v_pre[2]),
            "vE_post": _finite(v_post[0]), "vN_post": _finite(v_post[1]), "vU_post": _finite(v_post[2]),

            "vE_meas": _finite(v_meas[0]) if v_meas is not None else np.nan,
            "vN_meas": _finite(v_meas[1]) if v_meas is not None else np.nan,
            "vU_meas": _finite(v_meas[2]) if v_meas is not None else np.nan,

            "vU_be": _finite(vU_be),
            "vU_ref_err": _finite(vU_ref_err),

            "speed_pre_h": _finite(speed_pre_h),
            "speed_post_h": _finite(speed_post_h),
            "speed_meas_h": _finite(speed_meas_h),
            "ratio_pre_over_meas": _finite(ratio),

            "verrE": _finite(verrE),
            "verrN": _finite(verrN),
            "verrU": _finite(verrU),
            "verr_h": _finite(verr_h),

            "nis": _finite(nis_v),
            "triggered": 1.0 if triggered else 0.0,
        }

        # optional: residual entries
        if r_enu is not None:
            row["rE"] = rE
            row["rN"] = rN
            row["rU"] = rU

        # optional: S diag entries
        row["SE"] = _finite(S_diag_use[0])
        row["SN"] = _finite(S_diag_use[1])
        row["SU"] = _finite(S_diag_use[2])

        # optional: positions
        if p_pre_enu is not None:
            ppre = np.asarray(p_pre_enu, dtype=float).reshape(3)
            row["E_pre"] = _finite(ppre[0]); row["N_pre"] = _finite(ppre[1]); row["U_pre"] = _finite(ppre[2])
        if p_post_enu is not None:
            ppost = np.asarray(p_post_enu, dtype=float).reshape(3)
            row["E_post"] = _finite(ppost[0]); row["N_post"] = _finite(ppost[1]); row["U_post"] = _finite(ppost[2])

        # ----------------------------
        # NEW: update-chain diagnostics
        # ----------------------------
        row["nis0"] = nis0
        row["nis1"] = nis1 if np.isfinite(nis1) else np.nan
        row["R_inflate"] = rinfl
        row["HPHt_over_R"] = hphtr

        # diag extras if present
        # (kept explicit to avoid exploding columns)
        HPHt_diag = _as_arr(_get(extra, "HPHt_diag", None), 2)
        R_diag = _as_arr(_get(extra, "R_diag", None), 2)
        row["HPHt_E"] = _finite(HPHt_diag[0])
        row["HPHt_N"] = _finite(HPHt_diag[1])
        row["R_E"] = _finite(R_diag[0])
        row["R_N"] = _finite(R_diag[1])

        # whitened residual
        row["rwhiteE"] = _finite(rwhite[0])
        row["rwhiteN"] = _finite(rwhite[1])
        row["rwhite_norm"] = _finite(rwhite_norm)

        # dx stats
        row["dx_norm"] = _finite(dx_norm)
        row["dx_v_h"] = _finite(dx_v_h)
        row["dx_yaw"] = _finite(dx_yaw)
        row["dx_bgz"] = _finite(dx_bgz)

        # state / timing metadata (optional)
        row["prop_ok"] = 1.0 if bool(prop_ok) else (0.0 if prop_ok is not None else np.nan)
        row["dt_prop_s"] = _finite(dt_prop_s)
        row["yaw_state_rad"] = yaw_state
        row["yaw_used_rad"] = yaw_used
        row["yaw_err_rad"] = _finite(yaw_err)
        row["bgz_rad_s"] = _finite(bgz_rad_s)

        # covariance metrics
        row["Pcond"] = _finite(Pcond)
        row["P_pos_tr"] = _finite(P_pos_tr)
        row["P_vel_tr"] = _finite(P_vel_tr)
        row["P_yaw"] = _finite(P_yaw)
        row["P_bgz"] = _finite(P_bgz)

        # optional: raw matrix traces if you pass them
        if P_6x6 is not None:
            row["P_tr"] = _finite(_safe_trace(P_6x6))
        if S_2x2 is not None:
            row["S_tr"] = _finite(_safe_trace(S_2x2))
            row["S_cond"] = _finite(_safe_cond(S_2x2))
        if R_2x2 is not None:
            row["R_tr"] = _finite(_safe_trace(R_2x2))
            row["R_cond"] = _finite(_safe_cond(R_2x2))

        self._rows.append(row)

    # -------------------------------------------------------------------------
    # output
    # -------------------------------------------------------------------------
    def to_dataframe(self) -> pd.DataFrame:
        if not self._rows:
            return pd.DataFrame()
        return pd.DataFrame(self._rows)

    def flush_csv(self, out_path: str | Path) -> str:
        outp = Path(out_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        df = self.to_dataframe()
        df.to_csv(outp, index=False)
        return str(outp)

    def summary(self) -> Dict[str, Any]:
        return {
            "updates_seen": int(self._n_update_seen),
            "records": int(self._n_recorded),
            "triggers": int(self._n_triggered),

            "max_ratio": float(self._max_ratio) if np.isfinite(self._max_ratio) else float("nan"),
            "max_speed_pre_h": float(self._max_vpre) if np.isfinite(self._max_vpre) else float("nan"),
            "max_nis": float(self._max_nis) if np.isfinite(self._max_nis) else float("nan"),
            "max_verr_h": float(self._max_verr_h) if np.isfinite(self._max_verr_h) else float("nan"),

            "max_rinflate": float(self._max_rinflate) if np.isfinite(self._max_rinflate) else float("nan"),
            "max_dx_norm": float(self._max_dx_norm) if np.isfinite(self._max_dx_norm) else float("nan"),
            "max_rwhite_norm": float(self._max_rwhite) if np.isfinite(self._max_rwhite) else float("nan"),
        }
