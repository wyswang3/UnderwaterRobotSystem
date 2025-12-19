#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .common import (
    ScanConfig,
    DEFAULT_EXTS,
    DEFAULT_SKIP_DIRS,
    iter_source_files,
    norm_exts,
    write_json,
    write_csv,
)
from . import metrics_loc, metrics_complexity, deps_includes, risk_scan, git_hotspots, report_md

def main():
    ap = argparse.ArgumentParser(description="ROV Project Quality Audit (static analysis, lightweight)")
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--out", default="reports/quality", help="output dir")
    ap.add_argument("--top", type=int, default=20, help="Top N in report")
    ap.add_argument("--max-files", type=int, default=0, help="limit scanned files (0=unlimited)")
    ap.add_argument("--git-days", type=int, default=0, help="enable git hotspots window days (0=disable)")
    ap.add_argument("--ext", nargs="*", default=DEFAULT_EXTS, help="extensions to scan")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    exts = norm_exts(args.ext)

    cfg = ScanConfig(
        root=root,
        out=out,
        exts=exts,
        skip_dirs=set(DEFAULT_SKIP_DIRS),
        top_n=args.top,
        max_files=args.max_files,
        git_days=args.git_days,
    )

    out.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] root={cfg.root}")
    print(f"[INFO] out ={cfg.out}")
    print(f"[INFO] exts={cfg.exts}")
    print(f"[INFO] max_files={cfg.max_files if cfg.max_files>0 else 'unlimited'}")

    files = iter_source_files(cfg.root, cfg.exts, cfg.skip_dirs, cfg.max_files)
    print(f"[INFO] scanned_files={len(files)}")

    loc = metrics_loc.analyze(files, cfg.root)
    comp = metrics_complexity.analyze(files, cfg.root, loc["files"])
    deps = deps_includes.analyze(files, cfg.root)
    risk = risk_scan.analyze(files, cfg.root)

    git = {"enabled": False, "reason": "disabled"}
    if cfg.git_days and cfg.git_days > 0:
        git = git_hotspots.analyze(cfg.root, cfg.git_days)

    summary = {
        "meta": {
            "root": str(cfg.root),
            "out": str(cfg.out),
            "files_scanned": len(files),
        },
        "loc": loc,
        "complexity": comp,
        "deps": deps,
        "risk": risk,
        "git": git,
    }

    # raw json
    write_json(cfg.out / "raw" / "summary.json", summary)

    # tables
    # loc per file
    write_csv(
        cfg.out / "tables" / "loc_files.csv",
        ["rel_path", "lang", "total_lines", "blank_lines", "comment_lines", "code_lines", "branch_tokens"],
        [[f["rel_path"], f["lang"], str(f["total_lines"]), str(f["blank_lines"]), str(f["comment_lines"]), str(f["code_lines"]), str(f["branch_tokens"])]
         for f in loc["files"]]
    )

    # complexity per file
    write_csv(
        cfg.out / "tables" / "risk_files.csv",
        ["rel_path", "lang", "risk_score", "code_lines", "comment_lines", "comment_ratio", "branch_tokens", "max_func_len", "max_nest"],
        [[f["rel_path"], f["lang"], str(f["risk_score"]), str(f["code_lines"]), str(f["comment_lines"]), str(f["comment_ratio"]),
          str(f["branch_tokens"]), str(f["max_func_len"]), str(f["max_nest"])]
         for f in comp["per_file"]]
    )

    # include edges
    write_csv(
        cfg.out / "tables" / "include_edges.csv",
        ["from", "to", "count"],
        [[e["from"], e["to"], str(e["count"])] for e in deps["module_edges"]]
    )

    # risk hits
    write_csv(
        cfg.out / "tables" / "risk_hits.csv",
        ["rel_path", "lang", "risk_hits_score", "todo", "danger_c_funcs", "danger_cpp_patterns", "danger_py_patterns", "control_keywords"],
        [[f["rel_path"], f["lang"], str(f["risk_hits_score"]), str(f["todo"]), str(f["danger_c_funcs"]), str(f["danger_cpp_patterns"]),
          str(f["danger_py_patterns"]), str(f["control_keywords"])]
         for f in risk["per_file"]]
    )

    # graphs
    (cfg.out / "graphs").mkdir(parents=True, exist_ok=True)
    (cfg.out / "graphs" / "deps.dot").write_text(deps["dot"], encoding="utf-8")

    # markdown report
    md = report_md.render(summary)
    (cfg.out / "summary.md").write_text(md, encoding="utf-8")

    print("[INFO] Done.")
    print(f"[INFO] Report: {cfg.out / 'summary.md'}")
    print(f"[INFO] Raw   : {cfg.out / 'raw' / 'summary.json'}")
    print(f"[INFO] Graph : {cfg.out / 'graphs' / 'deps.dot'} (render with graphviz: dot -Tpng deps.dot -o deps.png)")

if __name__ == "__main__":
    main()
