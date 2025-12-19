#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple

from .common import (
    BRANCH_TOKENS,
    detect_lang,
    safe_read_text,
    top_dir,
)

@dataclass
class FileLoc:
    rel_path: str
    lang: str
    total_lines: int
    blank_lines: int
    comment_lines: int
    code_lines: int

    # 简单分支 token（用于后续风险评分）
    branch_tokens: int

def _count_comment_and_code(text: str, lang: str) -> Tuple[int, int, int, int, int]:
    """
    返回：total, blank, comment, code, branch_tokens
    简化实现：对 C/C++ 和 Python 做块注释/行注释识别。
    """
    lines = text.splitlines()
    total = len(lines)
    blank = 0
    comment = 0
    code = 0
    branch_cnt = 0

    in_block = False
    # C/C++ block: /* ... */
    # Python block: """ ... """ or ''' ... '''
    py_block_delims = ['"""', "'''"]

    for raw in lines:
        s = raw.rstrip("\n")
        st = s.strip()
        if not st:
            blank += 1
            continue

        low = st.lower()

        # 分支 token（粗计）
        for tok in BRANCH_TOKENS:
            if tok in low:
                branch_cnt += 1

        if lang == "cpp":
            if in_block:
                comment += 1
                if "*/" in st:
                    in_block = False
                continue

            if st.startswith("//"):
                comment += 1
                continue

            if "/*" in st:
                comment += 1
                if "*/" not in st:
                    in_block = True
                # 行内可能也有代码：简单处理为“既算 comment 也算 code”不做，保持保守
                # 这里以“只算 comment”为主，避免虚高 code
                continue

            # 非注释行
            code += 1

        elif lang == "python":
            if in_block:
                comment += 1
                if any(d in st for d in py_block_delims):
                    in_block = False
                continue

            if st.startswith("#"):
                comment += 1
                continue

            if any(st.startswith(d) for d in py_block_delims):
                comment += 1
                # 单行 """xxx""" 视为注释
                if sum(st.count(d) for d in py_block_delims) < 2:
                    in_block = True
                continue

            code += 1
        else:
            # 其他语言：只有空行/非空行
            code += 1

    return total, blank, comment, code, branch_cnt

def analyze(files: List[Path], root: Path) -> Dict:
    file_stats: List[FileLoc] = []
    for p in files:
        rel = os.path.relpath(p, root)
        lang = detect_lang(p)
        txt = safe_read_text(p)
        total, blank, comment, code, branch = _count_comment_and_code(txt, "cpp" if lang == "cpp" else ("python" if lang == "python" else lang))
        file_stats.append(FileLoc(rel, lang, total, blank, comment, code, branch))

    # 聚合
    by_lang: Dict[str, Dict[str, int]] = {}
    by_topdir: Dict[str, int] = {}
    totals = {"files": 0, "total_lines": 0, "blank_lines": 0, "comment_lines": 0, "code_lines": 0, "branch_tokens": 0}

    for f in file_stats:
        totals["files"] += 1
        totals["total_lines"] += f.total_lines
        totals["blank_lines"] += f.blank_lines
        totals["comment_lines"] += f.comment_lines
        totals["code_lines"] += f.code_lines
        totals["branch_tokens"] += f.branch_tokens

        if f.lang not in by_lang:
            by_lang[f.lang] = {"files": 0, "code_lines": 0, "comment_lines": 0, "total_lines": 0}
        by_lang[f.lang]["files"] += 1
        by_lang[f.lang]["code_lines"] += f.code_lines
        by_lang[f.lang]["comment_lines"] += f.comment_lines
        by_lang[f.lang]["total_lines"] += f.total_lines

        td = top_dir(f.rel_path)
        by_topdir[td] = by_topdir.get(td, 0) + f.code_lines

    # Top 文件（按 code_lines）
    top_by_loc = sorted(file_stats, key=lambda x: x.code_lines, reverse=True)

    return {
        "totals": totals,
        "by_lang": by_lang,
        "by_topdir": by_topdir,
        "files": [asdict(x) for x in file_stats],
        "top_by_loc": [asdict(x) for x in top_by_loc[:50]],
    }
