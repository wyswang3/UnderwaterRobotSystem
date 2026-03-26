# src/offnav/algo/__init__.py
from __future__ import annotations

# Dead-reckoning 管线
from .deadreckon import DeadReckonConfig, run_deadreckon_pipeline

# 新版 ESKF：统一从 eskf_engine 暴露
from .eskf_engine import (
    run_eskf_pipeline,
    EskfInputs,
    EskfOutputs,
    build_eskf_timeline,
)

# 诊断结构体从 models 暴露
from offnav.models.eskf_state import EskfDiagnostics


__all__ = [
    # deadreckon
    "DeadReckonConfig",
    "run_deadreckon_pipeline",

    # ESKF
    "run_eskf_pipeline",
    "EskfInputs",
    "EskfOutputs",
    "build_eskf_timeline",
    "EskfDiagnostics",
]
