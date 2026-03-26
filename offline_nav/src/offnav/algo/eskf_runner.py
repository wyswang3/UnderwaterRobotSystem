# src/offnav/algo/eskf_runner.py
from __future__ import annotations

"""
eskf_runner.py

对外暴露统一接口（保持向后兼容）：
- EskfInputs / EskfOutputs：管线 I/O 数据结构
- build_eskf_timeline：根据配置构建 IMU+DVL 时间轴
- run_eskf_pipeline：按 mode 运行 ESKF（full_ins / local_vel）
- EskfDiagnostics：从 models.eskf_state 转发，方便旧代码 import
"""

from offnav.models.eskf_state import EskfDiagnostics

from .eskf_common import EskfInputs, EskfOutputs
from .eskf_timeline import build_eskf_timeline
from .eskf_engine import run_eskf_pipeline

__all__ = [
    "EskfInputs",
    "EskfOutputs",
    "build_eskf_timeline",
    "run_eskf_pipeline",
    "EskfDiagnostics",
]
