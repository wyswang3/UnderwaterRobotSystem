#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .common import safe_read_text, top_dir

INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^">]+)[">]', re.MULTILINE)

def _is_project_include(inc: str) -> bool:
    # 形如 "io/input/xxx.hpp" / "control_core/xxx.hpp"
    return "/" in inc or inc.endswith((".h", ".hpp", ".hh"))

def analyze(files: List[Path], root: Path) -> Dict:
    """
    生成：
      - module->module include 次数矩阵（一级目录）
      - header 被 include 次数 Top
      - 循环依赖（模块级）
      - Graphviz dot
    """
    module_edges: Dict[Tuple[str, str], int] = defaultdict(int)
    header_in_degree: Dict[str, int] = defaultdict(int)
    graph: Dict[str, Set[str]] = defaultdict(set)

    for p in files:
        rel = os.path.relpath(p, root)
        txt = safe_read_text(p)
        src_mod = top_dir(rel)

        for inc in INCLUDE_RE.findall(txt):
            if not _is_project_include(inc):
                continue
            # 归一化：把 include 路径当作相对“模块路径”
            dst_mod = inc.split("/")[0] if "/" in inc else "(root)"
            module_edges[(src_mod, dst_mod)] += 1
            header_in_degree[inc] += 1
            if src_mod != dst_mod:
                graph[src_mod].add(dst_mod)

    # 计算循环：对模块图做简单 DFS 找回路
    cycles: List[List[str]] = []
    visited: Set[str] = set()
    stack: Set[str] = set()
    path: List[str] = []

    def dfs(u: str):
        visited.add(u)
        stack.add(u)
        path.append(u)
        for v in graph.get(u, set()):
            if v not in visited:
                dfs(v)
            elif v in stack:
                # 找到回路
                if v in path:
                    idx = path.index(v)
                    cyc = path[idx:] + [v]
                    # 去重（粗）
                    if len(cyc) >= 3:
                        cycles.append(cyc)
        stack.remove(u)
        path.pop()

    for n in list(graph.keys()):
        if n not in visited:
            dfs(n)

    # dot
    dot_lines = ["digraph deps {", '  rankdir=LR;', '  node [shape=box];']
    for (a, b), w in sorted(module_edges.items(), key=lambda x: x[1], reverse=True):
        if a == b:
            continue
        dot_lines.append(f'  "{a}" -> "{b}" [label="{w}"];')
    dot_lines.append("}")

    # matrix rows
    modules = sorted(set([a for (a, _) in module_edges.keys()] + [b for (_, b) in module_edges.keys()]))
    matrix: List[Dict] = []
    for a in modules:
        row = {"from": a}
        for b in modules:
            row[b] = module_edges.get((a, b), 0)
        matrix.append(row)

    top_headers = sorted(header_in_degree.items(), key=lambda x: x[1], reverse=True)[:100]

    return {
        "modules": modules,
        "module_edges": [{"from": a, "to": b, "count": w} for (a, b), w in module_edges.items()],
        "matrix": matrix,
        "top_headers": [{"header": h, "count": c} for h, c in top_headers],
        "cycles": cycles[:50],
        "dot": "\n".join(dot_lines),
    }
