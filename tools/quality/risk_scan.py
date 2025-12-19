#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List

from .common import (
    CONTROL_CRITICAL_KEYWORDS,
    DANGEROUS_C_FUNCS,
    DANGEROUS_CPP_PATTERNS,
    DANGEROUS_PY_PATTERNS,
    detect_lang,
    safe_read_text,
)

TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

def _scan_patterns(text: str, patterns: List[str]) -> int:
    cnt = 0
    for pat in patterns:
        cnt += len(re.findall(pat, text))
    return cnt

def analyze(files: List[Path], root: Path) -> Dict:
    per_file: List[Dict] = []
    totals = {
        "todo": 0,
        "danger_c_funcs": 0,
        "danger_cpp_patterns": 0,
        "danger_py_patterns": 0,
        "control_keywords": 0,
    }

    for p in files:
        rel = os.path.relpath(p, root)
        lang = detect_lang(p)
        txt = safe_read_text(p)
        if not txt:
            continue

        todo = len(TODO_RE.findall(txt))

        danger_c = 0
        danger_cpp = 0
        danger_py = 0

        if lang == "cpp":
            for f in DANGEROUS_C_FUNCS:
                danger_c += len(re.findall(rf"\b{re.escape(f)}\b", txt))
            danger_cpp = _scan_patterns(txt, DANGEROUS_CPP_PATTERNS)

        if lang == "python":
            danger_py = _scan_patterns(txt, DANGEROUS_PY_PATTERNS)

        control_kw = 0
        for kw in CONTROL_CRITICAL_KEYWORDS:
            control_kw += txt.count(kw)

        totals["todo"] += todo
        totals["danger_c_funcs"] += danger_c
        totals["danger_cpp_patterns"] += danger_cpp
        totals["danger_py_patterns"] += danger_py
        totals["control_keywords"] += control_kw

        score = todo * 5 + danger_c * 8 + danger_cpp * 6 + danger_py * 6 + (1 if control_kw > 0 else 0)

        per_file.append({
            "rel_path": rel,
            "lang": lang,
            "todo": todo,
            "danger_c_funcs": danger_c,
            "danger_cpp_patterns": danger_cpp,
            "danger_py_patterns": danger_py,
            "control_keywords": control_kw,
            "risk_hits_score": score,
        })

    top_risk_hits = sorted(per_file, key=lambda x: x["risk_hits_score"], reverse=True)[:100]
    top_todo = sorted(per_file, key=lambda x: x["todo"], reverse=True)[:100]

    return {
        "totals": totals,
        "per_file": per_file,
        "top_risk_hits": top_risk_hits,
        "top_todo": top_todo,
    }
