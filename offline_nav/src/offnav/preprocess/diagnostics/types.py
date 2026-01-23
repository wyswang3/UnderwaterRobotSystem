# offline_nav/src/offnav/preprocess/diagnostics/types.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass
class DtStats:
    median: float
    p95: float
    min: float
    max: float
    bad_ratio: float  # dt outlier ratio

@dataclass
class VecStats:
    mean: np.ndarray   # (3,)
    std: np.ndarray    # (3,)
    p95_abs: np.ndarray  # (3,)
    norm_mean: float

@dataclass
class ImuDiagReport:
    fs_hz: float
    sensor_to_body_map: str
    mount_rpy_deg: tuple[float, float, float]

    dt: DtStats

    acc_raw_bw: VecStats
    g_body_bw: VecStats | None
    residual_bw: VecStats | None  # e.g. acc_raw + g_body

    acc_lin_bw: VecStats | None

    gyro_in_bw: VecStats
    gyro_out_bw: VecStats | None
    gyro_diff: VecStats | None

    gyro_out_zero_ratio: tuple[float, float, float] | None

    notes: list[str]
@dataclass
class ScalarStats:
    mean: float
    std: float
    p95_abs: float
    max_abs: float

@dataclass
class DvlFrameSummary:
    name: str                 # "BI" or "BE"
    n_all: int
    n_gate_ok: int
    pass_ratio: float
    t_min: float
    t_max: float
    dt_median: float
    dt_p95: float
    gate_reason_counts: dict[str, int]

    # static window stats (first static_s seconds)
    v_mean: np.ndarray        # (3,)
    v_std: np.ndarray         # (3,)
    v_p95_abs: np.ndarray     # (3,)
    v_max_abs: np.ndarray     # (3,)

    # jump stats over full run
    dv_p95_abs: np.ndarray    # (3,)
    dv_max_abs: np.ndarray    # (3,)
    dvxy_p95: float
    dvxy_max: float

    # BE specific (optional)
    vu_stats: ScalarStats | None

@dataclass
class DvlDiagReport:
    run_id: str
    static_s: float

    # mixed stream composition, e.g. {"BI":1234,"BE":1200,"TS":...}
    stream_src_counts: dict[str, int]

    # summaries
    BI: DvlFrameSummary | None
    BE: DvlFrameSummary | None

    notes: list[str]