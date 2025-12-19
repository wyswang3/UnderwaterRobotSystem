#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

DEFAULT_SKIP_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", "build",
    "cmake-build-debug", "cmake-build-release", "dist", "out",
    "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache",

    # 重要：第三方与产物目录
    "third_party", "external", "vendor", "deps",
    "generated", "gen", "logs", "data",
}


DEFAULT_EXTS = [
    ".c", ".cpp", ".cc", ".cxx",
    ".h", ".hpp", ".hh",
    ".py",
    ".cmake", "CMakeLists.txt",
]

C_EXTS = {".c", ".h"}
CPP_EXTS = {".cpp", ".cc", ".cxx", ".hpp", ".hh"}
PY_EXTS = {".py"}

BRANCH_TOKENS = ["if", "for", "while", "switch", "case", "?:", "elif", "except", "catch"]

DANGEROUS_C_FUNCS = [
    "strcpy", "strcat", "sprintf", "vsprintf", "gets",
    "scanf", "sscanf", "fscanf",
    "memcpy", "memmove",  # 不一定危险，但需要审计边界
]

DANGEROUS_CPP_PATTERNS = [
    r"\bnew\b",
    r"\bdelete\b",
    r"\breinterpret_cast<",
    r"\bconst_cast<",
]

DANGEROUS_PY_PATTERNS = [
    r"except\s*:\s*\n",               # 裸 except
    r"except\s+Exception\s*:\s*\n",   # 泛化捕获（可接受但需关注）
    r"subprocess\.(Popen|run)\(",
    r"os\.system\(",
]

CONTROL_CRITICAL_KEYWORDS = [
    "ControlGuard", "estop", "failsafe", "ttl", "armed",
    "set_all_mid", "setAllMid", "PWM", "thruster", "allocation",
    "ControlIntent", "Telemetry", "gcs",
]

@dataclass
class ScanConfig:
    root: Path
    out: Path
    exts: List[str]
    skip_dirs: Set[str]
    top_n: int
    max_files: int
    git_days: int

def norm_exts(exts: Iterable[str]) -> List[str]:
    out: List[str] = []
    for e in exts:
        if e == "CMakeLists.txt":
            out.append("CMakeLists.txt")
        else:
            e2 = e.lower()
            if not e2.startswith("."):
                e2 = "." + e2
            out.append(e2)
    return out

def is_match_ext(path: Path, exts: List[str]) -> bool:
    if path.name == "CMakeLists.txt" and "CMakeLists.txt" in exts:
        return True
    return path.suffix.lower() in exts

def iter_source_files(root: Path, exts: List[str], skip_dirs: Set[str], max_files: int) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = os.path.basename(dirpath)
        if base in skip_dirs:
            dirnames[:] = []
            continue

        # 也跳过隐藏目录（可按需去掉）
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]

        for fn in filenames:
            p = Path(dirpath) / fn
            if not is_match_ext(p, exts):
                continue
            files.append(p)
            if max_files > 0 and len(files) >= max_files:
                return files
    return files

def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def top_dir(rel_path: str) -> str:
    parts = rel_path.split(os.sep)
    return "(root)" if len(parts) <= 1 else parts[0]

def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def write_csv(path: Path, header: List[str], rows: List[List[str]]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", s)

def detect_lang(path: Path) -> str:
    if path.name == "CMakeLists.txt" or path.suffix.lower() == ".cmake":
        return "cmake"
    ext = path.suffix.lower()
    if ext in PY_EXTS:
        return "python"
    if ext in (C_EXTS | CPP_EXTS):
        return "cpp"
    return ext.lstrip(".") or "unknown"
