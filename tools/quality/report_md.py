#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        return "_(empty)_\n"
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out) + "\n"

def render(summary: Dict) -> str:
    loc = summary["loc"]
    comp = summary["complexity"]
    deps = summary["deps"]
    risk = summary["risk"]
    git = summary.get("git", {})

    totals = loc["totals"]
    by_lang = loc["by_lang"]
    by_dir = loc["by_topdir"]

    md = []
    md.append("# Project Quality Audit Report\n")
    md.append(f"- Root: `{summary['meta']['root']}`\n")
    md.append(f"- Files scanned: **{totals['files']}**\n")
    md.append(f"- Code LOC: **{totals['code_lines']}** (comments {totals['comment_lines']}, blanks {totals['blank_lines']})\n")
    md.append(f"- Branch tokens (rough): **{totals['branch_tokens']}**\n")

    md.append("\n## 1. Language Breakdown\n")
    rows = []
    for k, v in sorted(by_lang.items(), key=lambda kv: kv[1]["code_lines"], reverse=True):
        rows.append([k, str(v["files"]), str(v["code_lines"]), str(v["comment_lines"]), str(v["total_lines"])])
    md.append(_md_table(["Lang", "Files", "Code LOC", "Comment lines", "Total lines"], rows))

    md.append("\n## 2. LOC by Top-level Directory\n")
    rows = [[k, str(v)] for k, v in sorted(by_dir.items(), key=lambda kv: kv[1], reverse=True)]
    md.append(_md_table(["Top Dir", "Code LOC"], rows))

    md.append("\n## 3. Top Risk Files (Composite Score)\n")
    rows = []
    for f in comp["top_risk"][:20]:
        rows.append([f["rel_path"], str(f["risk_score"]), str(f["code_lines"]), str(f["max_func_len"]), str(f["max_nest"]), str(f["branch_tokens"]), str(f["comment_ratio"])])
    md.append(_md_table(["File", "Risk", "LOC", "MaxFuncLen", "MaxNest", "BranchTok", "CommentRatio"], rows))

    md.append("\n## 4. Long Functions (Need Refactor Candidates)\n")
    rows = []
    for fn in comp["long_functions"][:20]:
        rows.append([fn["rel_path"], fn["func"], f"{fn['start']}-{fn['end']}", str(fn["len"]), str(fn["nest"])])
    md.append(_md_table(["File", "Function", "Lines", "Len", "Nest"], rows))

    md.append("\n## 5. Include Dependency Health (C/C++)\n")
    md.append(f"- Modules detected: {len(deps['modules'])}\n")
    md.append(f"- Cycles detected: {len(deps['cycles'])}\n")
    if deps["cycles"]:
        md.append("\n### Cycles (Top)\n")
        for c in deps["cycles"][:10]:
            md.append("- " + " -> ".join(c) + "\n")

    md.append("\n### Top Included Headers\n")
    rows = [[x["header"], str(x["count"])] for x in deps["top_headers"][:20]]
    md.append(_md_table(["Header", "Count"], rows))

    md.append("\n## 6. Risk Scan\n")
    md.append(f"- TODO/FIXME/HACK/XXX: **{risk['totals']['todo']}**\n")
    md.append(f"- Dangerous C funcs hits: **{risk['totals']['danger_c_funcs']}**\n")
    md.append(f"- Dangerous C++ patterns hits: **{risk['totals']['danger_cpp_patterns']}**\n")
    md.append(f"- Dangerous Python patterns hits: **{risk['totals']['danger_py_patterns']}**\n")
    md.append(f"- Control keywords hits: **{risk['totals']['control_keywords']}**\n")

    md.append("\n### Top Risk-hit Files\n")
    rows = []
    for f in risk["top_risk_hits"][:20]:
        rows.append([f["rel_path"], str(f["risk_hits_score"]), str(f["todo"]), str(f["danger_c_funcs"]), str(f["danger_cpp_patterns"]), str(f["danger_py_patterns"]), str(f["control_keywords"])])
    md.append(_md_table(["File", "Score", "TODO", "C-func", "C++pat", "Pypat", "CtrlKW"], rows))

    md.append("\n## 7. Git Hotspots (Optional)\n")
    if git.get("enabled"):
        rows = [[x["path"], str(x["changes"])] for x in git["hot_files"][:20]]
        md.append(f"- Window: last **{git['days']}** days\n\n")
        md.append(_md_table(["File", "Changes"], rows))
    else:
        md.append(f"- Disabled: {git.get('reason','n/a')}\n")

    md.append("\n## 8. Suggested Actions (Prioritized)\n")
    md.append("1) Review **Top Risk Files**: split long functions, reduce nesting, isolate responsibilities.\n")
    md.append("2) Break **include cycles** and reduce cross-module includes; move shared types to a stable `shared/` or `interfaces/` layer.\n")
    md.append("3) Resolve **risk hits**: TODO/FIXME triage, audit memcpy/strcpy-like calls, ban naked `except:`.\n")
    md.append("4) Add tests around **ControlGuard / failsafe / TTL / estop** paths; these are safety-critical for ROV.\n")

    return "".join(md)
