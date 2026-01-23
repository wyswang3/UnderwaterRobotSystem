# offline_nav/src/offnav/eskf/filter.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from .config import Eskf2DConfig
from .math_utils import wrap_pm_pi, rpy_to_R_nb_enu


# =============================================================================
# helpers
# =============================================================================

def _Q_cv_1d(dt: float, q: float) -> np.ndarray:
    """
    Continuous white-noise acceleration model -> discrete Q for [p, v] in 1D:
      p_dot = v
      v_dot = w,  E[w^2]=q
    """
    dt2 = dt * dt
    dt3 = dt2 * dt
    dt4 = dt2 * dt2
    return np.array(
        [[0.25 * dt4 * q, 0.5 * dt3 * q],
         [0.5 * dt3 * q, dt2 * q]],
        dtype=float,
    )


def _sym(A: np.ndarray) -> np.ndarray:
    return 0.5 * (A + A.T)


# =============================================================================
# diagnostics
# =============================================================================

@dataclass
class UpdateDiag:
    # ---- required (keep downstream interface) ----
    nis: float
    r: np.ndarray       # residual (2,)
    S: np.ndarray       # innovation covariance (2,2)

    # ---- optional but recommended ----
    S_diag: np.ndarray = field(default_factory=lambda: np.full((2,), np.nan, dtype=float))
    z: np.ndarray = field(default_factory=lambda: np.full((2,), np.nan, dtype=float))
    vhat: np.ndarray = field(default_factory=lambda: np.full((2,), np.nan, dtype=float))
    K: np.ndarray = field(default_factory=lambda: np.full((6, 2), np.nan, dtype=float))
    dx: np.ndarray = field(default_factory=lambda: np.full((6,), np.nan, dtype=float))
    R: np.ndarray = field(default_factory=lambda: np.full((2, 2), np.nan, dtype=float))

    ok: bool = True
    note: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # robust shapes
        try:
            self.r = np.asarray(self.r, dtype=float).reshape(-1)
        except Exception:
            self.r = np.full((2,), np.nan, dtype=float)
        if self.r.size != 2:
            rr = np.full((2,), np.nan, dtype=float)
            rr[: min(2, self.r.size)] = self.r[: min(2, self.r.size)]
            self.r = rr

        try:
            self.S = np.asarray(self.S, dtype=float).reshape(2, 2)
        except Exception:
            self.S = np.full((2, 2), np.nan, dtype=float)

        if self.S_diag is None:
            self.S_diag = np.full((2,), np.nan, dtype=float)
        self.S_diag = np.asarray(self.S_diag, dtype=float).reshape(-1)
        if self.S_diag.size != 2:
            self.S_diag = np.diag(self.S).astype(float) if self.S.shape == (2, 2) else np.full((2,), np.nan, dtype=float)

        if self.z is None:
            self.z = np.full((2,), np.nan, dtype=float)
        self.z = np.asarray(self.z, dtype=float).reshape(-1)
        if self.z.size != 2:
            zz = np.full((2,), np.nan, dtype=float)
            zz[: min(2, self.z.size)] = self.z[: min(2, self.z.size)]
            self.z = zz

        if self.vhat is None:
            self.vhat = np.full((2,), np.nan, dtype=float)
        self.vhat = np.asarray(self.vhat, dtype=float).reshape(-1)
        if self.vhat.size != 2:
            vv = np.full((2,), np.nan, dtype=float)
            vv[: min(2, self.vhat.size)] = self.vhat[: min(2, self.vhat.size)]
            self.vhat = vv

        try:
            self.K = np.asarray(self.K, dtype=float).reshape(6, 2)
        except Exception:
            self.K = np.full((6, 2), np.nan, dtype=float)

        try:
            self.dx = np.asarray(self.dx, dtype=float).reshape(6)
        except Exception:
            self.dx = np.full((6,), np.nan, dtype=float)

        try:
            self.R = np.asarray(self.R, dtype=float).reshape(2, 2)
        except Exception:
            self.R = np.full((2, 2), np.nan, dtype=float)


# =============================================================================
# Eskf2D filter
# =============================================================================

class Eskf2D:
    """
    2D planar ESKF.

    nominal state:
      p = [E, N]
      v = [vE, vN]
      yaw (rad)
      bgz (rad/s)

    error-state (6):
      dx = [dE, dN, dvE, dvN, dyaw, dbg]
    """

    def __init__(self, cfg: Eskf2DConfig) -> None:
        self.cfg = cfg

        # nominal
        self.p = np.array([cfg.init_E, cfg.init_N], dtype=float)
        self.v = np.array([cfg.init_vE, cfg.init_vN], dtype=float)
        self.yaw = float(cfg.init_yaw_rad)
        self.bgz = float(cfg.init_bgz)

        # covariance
        self.P = np.zeros((6, 6), dtype=float)
        self.P[0, 0] = float(cfg.P0_pos_m2)
        self.P[1, 1] = float(cfg.P0_pos_m2)
        self.P[2, 2] = float(cfg.P0_vel_m2s2)
        self.P[3, 3] = float(cfg.P0_vel_m2s2)
        self.P[4, 4] = float(cfg.P0_yaw_rad2)
        self.P[5, 5] = float(cfg.P0_bgz_rad2s2)

        self.t_last: Optional[float] = None
        self.initialized: bool = False
        self.last_update: Optional[UpdateDiag] = None

    # -------------------------------------------------------------------------
    # yaw handling (single source of truth for IMU-meas yaw mapping)
    # -------------------------------------------------------------------------
    def _yaw_used_from_meas(self, yaw_meas: float) -> float:
        y = float(self.cfg.yaw_sign) * float(yaw_meas) + float(self.cfg.yaw_offset_rad)
        return wrap_pm_pi(y) if self.cfg.yaw_wrap else y

    # -------------------------------------------------------------------------
    # initialization
    # -------------------------------------------------------------------------
    def initialize(self, t0: float, yaw_meas: Optional[float] = None) -> None:
        self.t_last = float(t0)

        src = str(getattr(self.cfg, "init_yaw_source", "imu")).lower().strip()
        if src == "imu":
            if yaw_meas is None or (not np.isfinite(float(yaw_meas))):
                self.yaw = float(self.cfg.init_yaw_rad)
            else:
                self.yaw = self._yaw_used_from_meas(float(yaw_meas))
        else:
            self.yaw = float(self.cfg.init_yaw_rad)
            if self.cfg.yaw_wrap:
                self.yaw = wrap_pm_pi(self.yaw)

        self.initialized = True

    def set_time(self, t: float) -> None:
        self.t_last = float(t)

    # -------------------------------------------------------------------------
    # propagation
    # -------------------------------------------------------------------------
    def propagate(
        self,
        t: float,
        acc_b: np.ndarray,
        gyro_b: np.ndarray,
        roll: float,
        pitch: float,
        yaw_meas: float,
    ) -> bool:
        """
        Route A engineering-consistent propagation:

        - yaw state propagates by (gz - bgz)
        - acceleration rotation uses STATE yaw (self.yaw), so model is self-consistent
        - yaw_meas is only used for diagnostics (yaw_err) and for initialization
        """
        tk = float(t)

        # init on first call
        if (self.t_last is None) or (not self.initialized):
            self.initialize(t0=tk, yaw_meas=yaw_meas)
            return True

        dt = tk - float(self.t_last)
        if (not np.isfinite(dt)) or (dt <= float(self.cfg.dt_min_s)):
            self.t_last = tk
            return False
        if dt > float(self.cfg.dt_max_s):
            self.t_last = tk
            return False

        # 1) yaw integrate (gyro_z - bgz)
        gb = np.asarray(gyro_b, dtype=float).reshape(3)
        gz = float(gb[2])
        self.yaw = float(self.yaw + (gz - self.bgz) * dt)
        if self.cfg.yaw_wrap:
            self.yaw = wrap_pm_pi(self.yaw)

        # 2) accel -> nav(ENU) using STATE yaw
        R_nb = rpy_to_R_nb_enu(float(roll), float(pitch), float(self.yaw))
        a_b = np.asarray(acc_b, dtype=float).reshape(3)
        a_nav = (R_nb @ a_b).reshape(3)

        # If acc is specific force (a - g), then a = f + gvec, where gvec=[0,0,-g] in ENU
        if not bool(self.cfg.imu_acc_is_linear):
            a_nav[2] -= float(self.cfg.gravity_mps2)

        a_EN = a_nav[:2].astype(float)

        # deadzone/clip (optional)
        acc_deadzone = float(getattr(self.cfg, "acc_deadzone_mps2", 0.0))
        if acc_deadzone > 0.0:
            a_EN = np.where(np.abs(a_EN) < acc_deadzone, 0.0, a_EN)

        acc_clip = float(getattr(self.cfg, "acc_clip_mps2", float("inf")))
        if np.isfinite(acc_clip) and acc_clip > 0.0:
            a_EN = np.clip(a_EN, -acc_clip, acc_clip)

        # 3) nominal integrate
        self.v = self.v + a_EN * dt

        leak = float(getattr(self.cfg, "vel_leak_1ps", 0.0))
        if leak > 0.0:
            fac = max(0.0, 1.0 - leak * dt)
            self.v = self.v * fac

        vmax = float(getattr(self.cfg, "v_hard_max_mps", float("inf")))
        if np.isfinite(vmax) and vmax > 0.0:
            sp = float(np.hypot(self.v[0], self.v[1]))
            if sp > vmax:
                self.v = self.v * (vmax / sp)

        self.p = self.p + self.v * dt

        # 4) covariance propagation
        F = np.zeros((6, 6), dtype=float)
        F[0, 2] = 1.0
        F[1, 3] = 1.0

        # dv sensitivity to dyaw via rotation: compute around STATE yaw
        eps = 1e-6
        yaw_eps = wrap_pm_pi(self.yaw + eps) if self.cfg.yaw_wrap else (self.yaw + eps)
        R_nb_eps = rpy_to_R_nb_enu(float(roll), float(pitch), float(yaw_eps))
        a_nav_eps = (R_nb_eps @ a_b).reshape(3)
        if not bool(self.cfg.imu_acc_is_linear):
            a_nav_eps[2] -= float(self.cfg.gravity_mps2)
        a_EN_eps = a_nav_eps[:2].astype(float)

        if acc_deadzone > 0.0:
            a_EN_eps = np.where(np.abs(a_EN_eps) < acc_deadzone, 0.0, a_EN_eps)
        if np.isfinite(acc_clip) and acc_clip > 0.0:
            a_EN_eps = np.clip(a_EN_eps, -acc_clip, acc_clip)

        da_dyaw = (a_EN_eps - a_EN) / eps
        F[2, 4] = float(da_dyaw[0])
        F[3, 4] = float(da_dyaw[1])

        # dyaw_dot = -dbg
        F[4, 5] = -1.0

        Phi = np.eye(6, dtype=float) + F * dt

        # process noise:
        # treat q_vel_extra_mps2 as additional accel sigma (engineering, but self-consistent)
        sig_acc = float(self.cfg.sigma_acc_mps2)
        sig_extra = float(getattr(self.cfg, "q_vel_extra_mps2", 0.0))
        sig_acc_eff = float(np.hypot(sig_acc, sig_extra))
        q_acc = sig_acc_eff * sig_acc_eff

        Q1 = _Q_cv_1d(dt, q_acc)

        Q = np.zeros((6, 6), dtype=float)
        # E axis
        Q[0, 0] = Q1[0, 0]; Q[0, 2] = Q1[0, 1]
        Q[2, 0] = Q1[1, 0]; Q[2, 2] = Q1[1, 1]
        # N axis
        Q[1, 1] = Q1[0, 0]; Q[1, 3] = Q1[0, 1]
        Q[3, 1] = Q1[1, 0]; Q[3, 3] = Q1[1, 1]

        # yaw noise from gyro_z
        q_gz = float(self.cfg.sigma_gyro_z_rad_s) ** 2
        Q[4, 4] += q_gz * dt * dt

        # bg random walk
        q_bg = float(self.cfg.sigma_bgz_rw) ** 2
        Q[5, 5] += q_bg * dt

        self.P = Phi @ self.P @ Phi.T + Q
        self.P = _sym(self.P)

        # --- store time
        self.t_last = tk
        return True

    # -------------------------------------------------------------------------
    # update: DVL horizontal velocity in EN
    # -------------------------------------------------------------------------
    def update_dvl_xy(self, v_meas_EN: np.ndarray, R: Optional[np.ndarray] = None) -> UpdateDiag:
        z_raw = np.asarray(v_meas_EN, dtype=float).reshape(2)
        if not np.all(np.isfinite(z_raw)):
            diag = UpdateDiag(
                nis=float("nan"),
                r=np.array([np.nan, np.nan], dtype=float),
                S=np.full((2, 2), np.nan, dtype=float),
                ok=False,
                note="REJECT_Z_NAN",
            )
            self.last_update = diag
            return diag

        vhat = np.asarray(self.v, dtype=float).reshape(2)

        speed_pred_h = float(np.hypot(vhat[0], vhat[1]))
        speed_meas_h_raw = float(np.hypot(z_raw[0], z_raw[1]))

        eps_sp = float(getattr(self.cfg, "meas_speed_eps_mps", 0.03))
        zupt_speed = float(getattr(self.cfg, "zupt_speed_mps", 0.06))
        is_zupt = bool(speed_meas_h_raw <= zupt_speed)

        z = np.zeros((2,), dtype=float) if is_zupt else z_raw

        ratio_pred_over_meas = float("inf")
        if speed_meas_h_raw > eps_sp:
            ratio_pred_over_meas = speed_pred_h / speed_meas_h_raw

        H = np.zeros((2, 6), dtype=float)
        H[0, 2] = 1.0
        H[1, 3] = 1.0

        # measurement cov
        if R is None:
            if is_zupt:
                s = float(getattr(self.cfg, "sigma_dvl_zupt_mps", 0.03))
            else:
                s = float(getattr(self.cfg, "sigma_dvl_xy_mps", 0.20))
            Rm = np.diag([s * s, s * s]).astype(float)
        else:
            Rm = np.asarray(R, dtype=float).reshape(2, 2)

        Rm = _sym(Rm)
        meas_jitter = float(getattr(self.cfg, "meas_jitter", 1e-9))
        Rm = Rm + meas_jitter * np.eye(2, dtype=float)

        # innovation
        r = (z - vhat).reshape(2, 1)
        HPHt = H @ self.P @ H.T
        S = _sym(HPHt + Rm)
        S_eps = float(getattr(self.cfg, "S_jitter", 1e-9))
        S = S + S_eps * np.eye(2, dtype=float)

        # nis0
        nis0 = self._quadform(S, r)

        # gating/inflation params
        nis_soft = float(getattr(self.cfg, "nis_soft", 15.0))
        nis_hard = float(getattr(self.cfg, "nis_hard", 80.0))
        nis_target = float(getattr(self.cfg, "nis_target", nis_soft))

        ratio_soft = float(getattr(self.cfg, "ratio_soft", 3.0))
        ratio_hard = float(getattr(self.cfg, "ratio_hard", 8.0))

        inflate_max = float(getattr(self.cfg, "r_inflate_max", 1e3))
        post_inflate_hard_reject = bool(getattr(self.cfg, "post_inflate_hard_reject", True))

        note = "USED_OK"
        inflated = 1.0

        # ---- ZUPT path: always apply ----
        if is_zupt:
            K, dx = self._kalman_update(H, S, r)
            self._inject(dx)
            self._joseph(H, K, Rm)

            nis = nis0
            note = f"ZUPT_USED|nis0={nis0:.1f}|spd={speed_pred_h:.2f}/{speed_meas_h_raw:.2f}|z=0"
            diag = self._make_diag(
                ok=True, note=note, nis=nis, r=r, S=S, z=z, vhat=vhat, K=K, dx=dx, Rm=Rm,
                extra=dict(
                    nis0=nis0, nis1=nis,
                    speed_pred_h=speed_pred_h,
                    speed_meas_h=speed_meas_h_raw,
                    is_zupt=True,
                    ratio_pred_over_meas=ratio_pred_over_meas,
                    R_inflate=1.0,
                    HPHt_diag=np.diag(HPHt).copy(),
                    R_diag=np.diag(Rm).copy(),
                    HPHt_over_R=float(np.trace(HPHt) / max(1e-12, np.trace(Rm))),
                ),
            )
            self.last_update = diag
            return diag

        # ---- hard reject pre ----
        hard_ratio_bad = (speed_meas_h_raw > eps_sp) and (ratio_pred_over_meas > ratio_hard)
        if (nis0 > nis_hard) or hard_ratio_bad:
            if nis0 > nis_hard:
                note = f"REJECT_NIS|nis0={nis0:.1f}|spd={speed_pred_h:.2f}/{speed_meas_h_raw:.2f}|ratio={ratio_pred_over_meas:.2f}"
            else:
                note = f"REJECT_RATIO|nis0={nis0:.1f}|spd={speed_pred_h:.2f}/{speed_meas_h_raw:.2f}|ratio={ratio_pred_over_meas:.2f}"

            diag = self._make_diag(
                ok=False, note=note, nis=nis0, r=r, S=S, z=z, vhat=vhat,
                K=None, dx=None, Rm=Rm,
                extra=dict(
                    nis0=nis0,
                    speed_pred_h=speed_pred_h,
                    speed_meas_h=speed_meas_h_raw,
                    is_zupt=False,
                    ratio_pred_over_meas=ratio_pred_over_meas,
                    R_inflate=inflated,
                    HPHt_diag=np.diag(HPHt).copy(),
                    R_diag=np.diag(Rm).copy(),
                    HPHt_over_R=float(np.trace(HPHt) / max(1e-12, np.trace(Rm))),
                ),
            )
            self.last_update = diag
            return diag

        # ---- soft inflation ----
        soft_ratio_bad = (speed_meas_h_raw > eps_sp) and (ratio_pred_over_meas > ratio_soft)
        need_inflate = (nis0 > nis_soft) or soft_ratio_bad

        if need_inflate:
            f_nis = max(1.0, nis0 / max(1e-9, nis_target))
            f_ratio = 1.0
            if soft_ratio_bad:
                rr = ratio_pred_over_meas / max(1e-9, ratio_soft)
                f_ratio = max(1.0, rr * rr)

            inflated = float(min(inflate_max, max(f_nis, f_ratio)))
            Rm = Rm * inflated

            note = f"INFLATE_Rx{inflated:.1f}|nis0={nis0:.1f}|spd={speed_pred_h:.2f}/{speed_meas_h_raw:.2f}|ratio={ratio_pred_over_meas:.2f}"
            S = _sym(HPHt + Rm)
            S = S + S_eps * np.eye(2, dtype=float)

        nis1 = self._quadform(S, r)

        if post_inflate_hard_reject and (nis1 > nis_hard):
            note2 = f"REJECT_POST_INFLATE|nis1={nis1:.1f}|Rinf={inflated:.1f}|nis0={nis0:.1f}"
            diag = self._make_diag(
                ok=False, note=note2, nis=nis1, r=r, S=S, z=z, vhat=vhat,
                K=None, dx=None, Rm=Rm,
                extra=dict(
                    nis0=nis0, nis1=nis1,
                    speed_pred_h=speed_pred_h,
                    speed_meas_h=speed_meas_h_raw,
                    is_zupt=False,
                    ratio_pred_over_meas=ratio_pred_over_meas,
                    R_inflate=inflated,
                    HPHt_diag=np.diag(HPHt).copy(),
                    R_diag=np.diag(Rm).copy(),
                    HPHt_over_R=float(np.trace(HPHt) / max(1e-12, np.trace(Rm))),
                ),
            )
            self.last_update = diag
            return diag

        # ---- actual update ----
        K, dx = self._kalman_update(H, S, r)
        self._inject(dx)
        self._joseph(H, K, Rm)

        diag = self._make_diag(
            ok=True, note=note, nis=nis1, r=r, S=S, z=z, vhat=vhat,
            K=K, dx=dx, Rm=Rm,
            extra=dict(
                nis0=nis0, nis1=nis1,
                speed_pred_h=speed_pred_h,
                speed_meas_h=speed_meas_h_raw,
                is_zupt=False,
                ratio_pred_over_meas=ratio_pred_over_meas,
                R_inflate=inflated,
                HPHt_diag=np.diag(HPHt).copy(),
                R_diag=np.diag(Rm).copy(),
                HPHt_over_R=float(np.trace(HPHt) / max(1e-12, np.trace(Rm))),
            ),
        )
        self.last_update = diag
        return diag

    # -------------------------------------------------------------------------
    # internals
    # -------------------------------------------------------------------------
    @staticmethod
    def _quadform(S: np.ndarray, r: np.ndarray) -> float:
        try:
            return float((r.T @ np.linalg.solve(S, r)).reshape(()))
        except np.linalg.LinAlgError:
            return float((r.T @ np.linalg.pinv(S) @ r).reshape(()))

    def _kalman_update(self, H: np.ndarray, S: np.ndarray, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        PHt = self.P @ H.T  # (6x2)
        try:
            X = np.linalg.solve(S, PHt.T)  # (2x6)
            K = X.T
        except np.linalg.LinAlgError:
            K = PHt @ np.linalg.pinv(S)
        dx = (K @ r).reshape(6)
        return K, dx

    def _inject(self, dx: np.ndarray) -> None:
        dx = np.asarray(dx, dtype=float).reshape(6)

        self.p[0] += float(dx[0])
        self.p[1] += float(dx[1])
        self.v[0] += float(dx[2])
        self.v[1] += float(dx[3])

        self.yaw += float(dx[4])
        if self.cfg.yaw_wrap:
            self.yaw = wrap_pm_pi(self.yaw)

        self.bgz += float(dx[5])
        bgz_max = float(getattr(self.cfg, "bgz_abs_max_rad_s", float("inf")))
        if np.isfinite(bgz_max):
            self.bgz = float(np.clip(self.bgz, -bgz_max, bgz_max))

    def _joseph(self, H: np.ndarray, K: np.ndarray, Rm: np.ndarray) -> None:
        I = np.eye(6, dtype=float)
        A = I - (K @ H)
        self.P = A @ self.P @ A.T + K @ Rm @ K.T
        self.P = _sym(self.P)

    def _make_diag(
        self,
        ok: bool,
        note: str,
        nis: float,
        r: np.ndarray,
        S: np.ndarray,
        z: np.ndarray,
        vhat: np.ndarray,
        K: Optional[np.ndarray],
        dx: Optional[np.ndarray],
        Rm: np.ndarray,
        extra: Dict[str, Any],
    ) -> UpdateDiag:
        diag = UpdateDiag(
            nis=float(nis),
            r=np.asarray(r, dtype=float).reshape(2),
            S=np.asarray(S, dtype=float).reshape(2, 2),
            ok=bool(ok),
            note=str(note),
        )
        try:
            diag.z = np.asarray(z, dtype=float).reshape(2).copy()
            diag.vhat = np.asarray(vhat, dtype=float).reshape(2).copy()
            diag.S_diag = np.diag(diag.S).copy()
            diag.R = np.asarray(Rm, dtype=float).reshape(2, 2).copy()
            if K is not None:
                diag.K = np.asarray(K, dtype=float).reshape(6, 2).copy()
            if dx is not None:
                diag.dx = np.asarray(dx, dtype=float).reshape(6).copy()
            diag.extra.update(extra or {})
        except Exception:
            pass
        return diag

    # -------------------------------------------------------------------------
    # snapshot
    # -------------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return {
            "E": float(self.p[0]),
            "N": float(self.p[1]),
            "vE": float(self.v[0]),
            "vN": float(self.v[1]),
            "yaw_rad": float(self.yaw),
            "bgz": float(self.bgz),
        }
