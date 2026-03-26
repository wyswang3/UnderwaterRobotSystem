# src/offnav/algo/eskf_timeline.py
from __future__ import annotations

from typing import Any, List, Tuple, Optional

import numpy as np

from offnav.core.nav_config import NavConfig
from offnav.algo.event_timeline import (
    TimelineConfig,
    build_imu_events,
    build_dvl_be_events,
    merge_timeline,
    TimeAlignmentReport,
)

# 兼容：旧版本可能没有 build_dvl_bi_events
try:
    from offnav.algo.event_timeline import build_dvl_bi_events  # type: ignore
except Exception:  # pragma: no cover
    build_dvl_bi_events = None  # type: ignore

from .eskf_common import EskfInputs


def _pick_nav_start_from_rep(rep_be: Optional[TimeAlignmentReport],
                            rep_bi: Optional[TimeAlignmentReport]) -> Tuple[int, float]:
    """
    选择导航起点：优先使用 BI 的首个 USED DVL 对齐 anchor（更贴近“IMU+BI”链路），
    若 BI 不存在/无 USED，则退回 BE；最后退回 (k0=0, t0=nan)。

    返回:
      (nav_k0, nav_t0)
    """
    # BI 优先
    if rep_bi is not None:
        nav_k0 = int(getattr(rep_bi, "nav_k0", 0) or 0)
        nav_t0 = float(getattr(rep_bi, "nav_t0", np.nan))
        if nav_k0 > 0 or np.isfinite(nav_t0):
            return nav_k0, nav_t0

    # 再看 BE
    if rep_be is not None:
        nav_k0 = int(getattr(rep_be, "nav_k0", 0) or 0)
        nav_t0 = float(getattr(rep_be, "nav_t0", np.nan))
        return nav_k0, nav_t0

    return 0, float("nan")


def _merge_time_reports(rep_be: Optional[TimeAlignmentReport],
                        rep_bi: Optional[TimeAlignmentReport],
                        nav_k0: int,
                        nav_t0: float) -> TimeAlignmentReport:
    """
    将 BE/BI 的时间报告合并为一个 rep（保持下游接口不变）。

    策略：
      - 以 BE 的 rep 作为 base（BE 一般必有）
      - 注入/覆盖 nav_k0/nav_t0
      - 增加字段：n_dvl_used_be / n_dvl_used_bi / n_dvl_used（总和）
        若 TimeAlignmentReport 没这些字段则自动忽略（通过 dataclass 字段过滤）
    """
    base = rep_be if rep_be is not None else rep_bi
    if base is None:
        # 理论上不会发生（至少应有 BE），但这里兜底不炸
        rep_kwargs = {
            "imu_t0": float("nan"),
            "imu_t1": float("nan"),
            "imu_n": 0,
            "dvl_t0": float("nan"),
            "dvl_t1": float("nan"),
            "dvl_n": 0,
            "dt0_imu_minus_dvl": float("nan"),
            "dt1_imu_minus_dvl": float("nan"),
            "nav_k0": int(nav_k0),
            "nav_t0": float(nav_t0),
            "n_dvl_used": 0,
        }
        fields = getattr(TimeAlignmentReport, "__dataclass_fields__", None)
        if isinstance(fields, dict) and len(fields) > 0:
            rep_kwargs = {k: v for k, v in rep_kwargs.items() if k in fields}
        return TimeAlignmentReport(**rep_kwargs)

    # base -> dict
    rep_kwargs = dict(getattr(base, "__dict__", {}))

    # 覆盖起点
    rep_kwargs["nav_k0"] = int(nav_k0)
    rep_kwargs["nav_t0"] = float(nav_t0)

    # USED 统计
    n_used_be = int(getattr(rep_be, "n_dvl_used", 0) or 0) if rep_be is not None else 0
    n_used_bi = int(getattr(rep_bi, "n_dvl_used", 0) or 0) if rep_bi is not None else 0
    rep_kwargs["n_dvl_used_be"] = n_used_be
    rep_kwargs["n_dvl_used_bi"] = n_used_bi
    rep_kwargs["n_dvl_used"] = int(n_used_be + n_used_bi)  # 总和（用于“一眼看 BI 是否进入”）

    # 过滤 dataclass 字段（避免签名变动炸）
    fields = getattr(TimeAlignmentReport, "__dataclass_fields__", None)
    if isinstance(fields, dict) and len(fields) > 0:
        rep_kwargs = {k: v for k, v in rep_kwargs.items() if k in fields}

    return TimeAlignmentReport(**rep_kwargs)


def build_eskf_timeline(
    nav_cfg: NavConfig,
    inputs: EskfInputs,
) -> Tuple[List[Any], TimeAlignmentReport]:
    """
    根据 nav_config.eskf 的时间匹配策略，把 IMU/DVL 组合成一个事件流 timeline。

    本版支持：
      - DVL_BE 事件流（原有）
      - DVL_BI 事件流（新增）
    严格起点策略：
      - 优先以“首个 USED 的 BI 事件对应的 IMU anchor”作为导航起点
      - 若 BI 不存在或无 USED，则退回 BE

    输出：
      - timeline   : [IMU, DVL_BE, DVL_BI, ...] 事件列表（已按 anchor IMU + 时间排序）
      - time_report: IMU/DVL 覆盖时间段统计（包含 nav_k0/nav_t0/n_dvl_used 等）
    """
    imu_proc = inputs.imu_proc
    df_be = inputs.dvl_be_df
    df_bi = getattr(inputs, "dvl_bi_df", None)  # 兼容：旧 EskfInputs 可能没有该字段

    if df_be is None:
        raise RuntimeError("DVL BE dataframe is None in EskfInputs.dvl_be_df")

    imu_t = np.asarray(getattr(imu_proc, "t_s", []), dtype=float)
    if imu_t.size == 0:
        raise RuntimeError("IMU t_s is empty in EskfInputs.imu_proc")

    # timeline config
    tl_cfg = TimelineConfig(
        match_policy=str(getattr(nav_cfg.eskf, "dvl_match_policy", "anchor_next")),
        match_window_s=float(getattr(nav_cfg.eskf, "dvl_match_window_s", 0.05)),
        drop_older_than_s=float(getattr(nav_cfg.eskf, "dvl_drop_older_than_s", 0.5)),
        require_gate_ok=bool(getattr(nav_cfg.eskf, "require_gate_ok", True)),
        require_speed_ok=bool(getattr(nav_cfg.eskf, "require_speed_ok", True)),
        require_valid=bool(getattr(nav_cfg.eskf, "require_valid", False)),
    )

    # 1) DVL BE events（必做）
    dvl_be_events, rep_be = build_dvl_be_events(imu_t, df_be, tl_cfg)

    # 2) DVL BI events（可选做：有 df_bi 且 event_timeline 支持）
    #    注意：这里只生成“事件流”；是否消费更新在 engine 决定。
    dvl_bi_events: List[Any] = []
    rep_bi: Optional[TimeAlignmentReport] = None

    enable_bi_timeline = bool(getattr(nav_cfg.eskf, "enable_bi_timeline", True))
    if enable_bi_timeline and (df_bi is not None) and (build_dvl_bi_events is not None):
        try:
            dvl_bi_events, rep_bi = build_dvl_bi_events(imu_t, df_bi, tl_cfg)  # type: ignore[misc]
        except Exception:
            # 不炸管线：退化为只用 BE timeline
            dvl_bi_events, rep_bi = [], None

    # 3) 严格起点：优先 BI，否则 BE
    nav_k0, nav_t0 = _pick_nav_start_from_rep(rep_be, rep_bi)

    # 4) IMU events 从 nav_k0 起算
    imu_events = build_imu_events(imu_t, k0=int(nav_k0))

    # 5) 合并事件流：IMU + DVL_BE + DVL_BI
    #    merge_timeline 支持两两合并；这里采用串联合并，保证排序逻辑复用且行为一致。
    timeline = merge_timeline(imu_events, dvl_be_events)
    if len(dvl_bi_events) > 0:
        timeline = merge_timeline(timeline, dvl_bi_events)

    # 6) 合并 time report（保持下游接口为一个 rep）
    rep = _merge_time_reports(rep_be, rep_bi, nav_k0=nav_k0, nav_t0=nav_t0)

    return timeline, rep
