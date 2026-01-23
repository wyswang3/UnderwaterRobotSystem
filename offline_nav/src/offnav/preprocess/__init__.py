# offline_nav/src/offnav/preprocess/__init__.py
from __future__ import annotations

# IMU
from .imu_processing import (
    ImuPreprocessConfig,
    ImuProcessedData,
    preprocess_imu_simple,
    load_imu_processed_csv,
)

# DVL
# 说明：
# - 你刚刚的目标是“BI/BE 事件流分开 + 异常值/低通 + 输出更少列”
# - 因此 dvl_processing 里通常会新增更贴近产物语义的 API（例如 preprocess_dvl_events / load_dvl_events_csv）
# - 为了不破坏现有调用链，这里同时提供“旧名兼容 + 新名导出”
from .dvl_processing import (
    DvlPreprocessConfig,
    DvlProcessedData,
    preprocess_dvl_simple,   # 兼容旧调用：返回 DvlProcessedData
    load_dvl_processed_csv,  # 兼容旧产物读回
)

# 如果你在新 dvl_processing.py 里已经实现了“更精简产物”的新 API，请在此导出：
# （下面这些名字你可以按你实现的实际函数名改）
try:
    from .dvl_processing import (
        DvlEventsConfig,            # 新：更聚焦 BI/BE 事件流的配置
        DvlEventsData,              # 新：更精简的数据封装（例如只含 df_bi/df_be）
        preprocess_dvl_events,      # 新：直接产出 BI/BE 两份“关键列”数据
        load_dvl_events_csv,        # 新：读回 BI/BE 两份简洁 CSV
    )

    _HAS_DVL_EVENTS_API = True
except Exception:
    _HAS_DVL_EVENTS_API = False


__all__ = [
    # -----------------
    # IMU
    # -----------------
    "ImuPreprocessConfig",
    "ImuProcessedData",
    "preprocess_imu_simple",
    "load_imu_processed_csv",

    # -----------------
    # DVL (compat)
    # -----------------
    "DvlPreprocessConfig",
    "DvlProcessedData",
    "preprocess_dvl_simple",
    "load_dvl_processed_csv",
]

# 仅当新 API 存在时才导出（避免 import error 破坏整个包）
if _HAS_DVL_EVENTS_API:
    __all__ += [
        "DvlEventsConfig",
        "DvlEventsData",
        "preprocess_dvl_events",
        "load_dvl_events_csv",
    ]
