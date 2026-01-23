# offline_nav/src/offnav/eskf/math_utils.py
from __future__ import annotations

import numpy as np


def wrap_pm_pi(a):
    """
    Wrap angle(s) to [-pi, pi).
    Supports float or ndarray.
    """
    x = np.asarray(a, dtype=float)
    y = (x + np.pi) % (2.0 * np.pi) - np.pi
    return float(y) if y.ndim == 0 else y


def rot_x(phi: float) -> np.ndarray:
    c, s = np.cos(phi), np.sin(phi)
    return np.array([[1.0, 0.0, 0.0],
                     [0.0, c, -s],
                     [0.0, s,  c]], dtype=float)


def rot_y(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[ c, 0.0, s],
                     [0.0, 1.0, 0.0],
                     [-s, 0.0, c]], dtype=float)


def rot_z(psi: float) -> np.ndarray:
    c, s = np.cos(psi), np.sin(psi)
    return np.array([[c, -s, 0.0],
                     [s,  c, 0.0],
                     [0.0, 0.0, 1.0]], dtype=float)


def rpy_to_R_nb_enu(roll: float, pitch: float, yaw: float, *, check_orthonormal: bool = False) -> np.ndarray:
    """
    R_nb: nav(ENU) <- body(FRD)

    Convention:
      R_nb = Rz(yaw) * Ry(pitch) * Rx(roll)

    Notes:
      - body: FRD (x fwd, y right, z down)
      - nav : ENU (x east, y north, z up)
      - yaw : right-hand about +U (up) axis, in nav frame (mathematical yaw)

    If check_orthonormal=True, performs a cheap sanity check.
    """
    R = rot_z(float(yaw)) @ rot_y(float(pitch)) @ rot_x(float(roll))

    if check_orthonormal:
        # numerical sanity: R^T R ~= I, det(R) ~= +1
        RtR = R.T @ R
        err = float(np.max(np.abs(RtR - np.eye(3))))
        det = float(np.linalg.det(R))
        if (not np.isfinite(err)) or err > 1e-6 or (not np.isfinite(det)) or abs(det - 1.0) > 1e-6:
            raise ValueError(f"R_nb not orthonormal: max|RtR-I|={err:.3e}, det={det:.6f}")
    return R


def R_bn_from_R_nb(R_nb: np.ndarray) -> np.ndarray:
    """R_bn: body <- nav. For rotation matrices, inverse == transpose."""
    R = np.asarray(R_nb, dtype=float).reshape(3, 3)
    return R.T


def yaw_from_R_nb_enu(R_nb: np.ndarray) -> float:
    """
    Extract yaw from R_nb under the same convention as rpy_to_R_nb_enu.
    yaw = atan2(R[1,0], R[0,0]) for ENU with Rz*Ry*Rx.
    """
    R = np.asarray(R_nb, dtype=float).reshape(3, 3)
    return float(np.arctan2(R[1, 0], R[0, 0]))


def project_to_SO3(R: np.ndarray) -> np.ndarray:
    """
    Project a near-rotation matrix to SO(3) via SVD.
    Useful if upstream numeric noise creates slight non-orthonormality.
    """
    A = np.asarray(R, dtype=float).reshape(3, 3)
    U, _, Vt = np.linalg.svd(A)
    R2 = U @ Vt
    if np.linalg.det(R2) < 0.0:
        U[:, -1] *= -1.0
        R2 = U @ Vt
    return R2
