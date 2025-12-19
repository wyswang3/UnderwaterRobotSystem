#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

def _run_git(root: Path, args: List[str]) -> Tuple[int, str]:
    try:
        p = subprocess.run(["git"] + args, cwd=root, capture_output=True, text=True)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)

def analyze(root: Path, days: int) -> Dict:
    """
    统计最近 N 天变更次数（按文件）。
    """
    if not (root / ".git").exists():
        return {"enabled": False, "reason": "not a git repository", "hot_files": []}

    code, out = _run_git(root, ["log", f"--since={days}.days", "--name-only", "--pretty=format:"])
    if code != 0:
        return {"enabled": False, "reason": out.strip()[:200], "hot_files": []}

    freq: Dict[str, int] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        freq[line] = freq.get(line, 0) + 1

    hot = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:200]
    return {
        "enabled": True,
        "days": days,
        "hot_files": [{"path": p, "changes": n} for p, n in hot],
    }
