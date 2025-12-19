#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple

from .common import safe_read_text, detect_lang

# 用一个更稳的：在“(”前抓到最后一个标识符作为函数名
CPP_FUNC_RE = re.compile(
    r'^[^\S\r\n]*'                      # 行首空白
    r'(?:template\s*<[^;{>]+>\s*)?'     # 可选 template<...>
    r'(?:inline\s+|static\s+|constexpr\s+|virtual\s+|friend\s+|explicit\s+)*'
    r'(?:[\w:\<\>\~\*&\s]+\s+)?'        # 返回类型/限定符（粗略）
    r'(?P<name>~?[\w:]+)\s*'            # 函数名（含析构/命名空间/类作用域）
    r'\([^;{}]*\)\s*'                   # 参数（不允许 ; { }，避免声明/宏）
    r'(?:const\s*)?(?:noexcept\s*)?(?:->\s*[^{]+)?\s*'  # 可选尾返回
    r'\{',                               # 函数体开始
    re.MULTILINE
)


PY_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(.*\)\s*:\s*$", re.MULTILINE)

def _cpp_functions(text: str) -> List[Tuple[str, int, int, int]]:
    lines = text.splitlines()
    out: List[Tuple[str, int, int, int]] = []

    for m in CPP_FUNC_RE.finditer(text):
        name = m.group("name")
        start_line0 = text[:m.start()].count("\n")  # 0-based
        i = start_line0

        brace = 0
        in_func = False
        max_nest = 0

        while i < len(lines):
            line = lines[i]

            # 粗略：只做括号统计（不做字符串/注释消隐），用于“相对排序”足够
            opens = line.count("{")
            closes = line.count("}")
            brace += opens - closes

            if not in_func and opens > 0:
                in_func = True

            if in_func:
                max_nest = max(max_nest, brace)

            if in_func and brace <= 0:
                end_line0 = i
                out.append((name, start_line0 + 1, end_line0 + 1, max_nest))
                break

            i += 1

    return out


def _py_functions(text: str) -> List[Tuple[str, int, int, int]]:
    """
    (name, start, end, max_indent_depth)
    通过缩进层级粗估嵌套深度。
    """
    lines = text.splitlines()
    out: List[Tuple[str, int, int, int]] = []
    def_lines = [(m.group(1), text[:m.start()].count("\n")) for m in PY_DEF_RE.finditer(text)]
    for idx, (name, start0) in enumerate(def_lines):
        start = start0
        end = (def_lines[idx + 1][1] - 1) if idx + 1 < len(def_lines) else (len(lines) - 1)
        base_indent = len(lines[start]) - len(lines[start].lstrip(" "))
        max_depth = 0
        for i in range(start + 1, end + 1):
            ln = lines[i]
            if not ln.strip():
                continue
            ind = len(ln) - len(ln.lstrip(" "))
            if ind > base_indent:
                depth = (ind - base_indent) // 4  # 假设 4 空格缩进
                max_depth = max(max_depth, depth)
        out.append((name, start + 1, end + 1, max_depth))
    return out

def analyze(files: List[Path], root: Path, loc_files: List[Dict]) -> Dict:
    """
    依赖 metrics_loc 的 files 列表（含 code_lines / branch_tokens 等）
    输出：
      - 每文件：max_func_len、max_nest、risk_score
      - TopN 风险文件
      - TopN 长函数
    """
    loc_map = {f["rel_path"]: f for f in loc_files}

    per_file: List[Dict] = []
    long_funcs: List[Dict] = []

    for p in files:
        rel = os.path.relpath(p, root)
        base = loc_map.get(rel)
        if not base:
            continue
        lang = detect_lang(p)
        txt = safe_read_text(p)

        max_func_len = 0
        max_nest = 0

        if lang == "cpp":
            funcs = _cpp_functions(txt)
            for (name, s, e, nest) in funcs:
                flen = max(0, e - s + 1)
                max_func_len = max(max_func_len, flen)
                max_nest = max(max_nest, nest)
                if flen >= 120:
                    long_funcs.append({
                        "rel_path": rel,
                        "func": name,
                        "start": s,
                        "end": e,
                        "len": flen,
                        "nest": nest,
                    })
        elif lang == "python":
            funcs = _py_functions(txt)
            for (name, s, e, nest) in funcs:
                flen = max(0, e - s + 1)
                max_func_len = max(max_func_len, flen)
                max_nest = max(max_nest, nest)
                if flen >= 80:
                    long_funcs.append({
                        "rel_path": rel,
                        "func": name,
                        "start": s,
                        "end": e,
                        "len": flen,
                        "nest": nest,
                    })

        # 风险评分（可调权重）
        code_lines = base["code_lines"]
        branch = base["branch_tokens"]
        comment = base["comment_lines"]
        comment_ratio = (comment / max(1, comment + code_lines))

        risk = (
            code_lines
            + 15 * max_func_len
            + 40 * max_nest
            + 8 * branch
            + (200 if comment_ratio < 0.05 and code_lines > 200 else 0)
        )

        per_file.append({
            "rel_path": rel,
            "lang": lang,
            "code_lines": code_lines,
            "comment_lines": comment,
            "branch_tokens": branch,
            "max_func_len": max_func_len,
            "max_nest": max_nest,
            "comment_ratio": round(comment_ratio, 4),
            "risk_score": int(risk),
        })

    top_risk = sorted(per_file, key=lambda x: x["risk_score"], reverse=True)
    long_funcs_sorted = sorted(long_funcs, key=lambda x: x["len"], reverse=True)

    return {
        "per_file": per_file,
        "top_risk": top_risk[:100],
        "long_functions": long_funcs_sorted[:200],
    }
