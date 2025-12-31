#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ROV 项目代码质量审计工具（轻量级静态分析）

功能概述：
- 扫描指定工程目录下的源码文件（支持多种扩展名）
- 统计代码行数（总行数 / 空行 / 注释行 / 代码行 / 分支关键字）
- 计算每个文件的复杂度与“风险分数”（嵌套层数、最长函数等）
- 分析 include 依赖关系，导出 Graphviz dot 图
- 按规则扫描“危险模式”（危险 C 函数、可疑 C++/Python 写法、TODO 等）
- 可选：结合 git 历史记录计算“热点文件”（近期修改频繁的文件）
- 最终生成：
  - 原始 JSON 汇总：raw/summary.json
  - 多个 CSV 明细表：tables/*.csv
  - 依赖关系图：graphs/deps.dot
  - Markdown 总结报告：summary.md

典型用途：
- 评估一个 ROV / 控制系统项目的代码规模与复杂度
- 对比不同阶段的工作量变化（提交前后跑一遍）
- 帮助识别重构优先级（高风险 + 高热点的文件）
"""

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
    ap = argparse.ArgumentParser(
        description="ROV Project Quality Audit (轻量级代码质量审计 / static analysis)"
    )
    ap.add_argument(
        "--root",
        default=".",
        help="项目根目录（默认当前目录） / project root",
    )
    ap.add_argument(
        "--out",
        default="reports/quality",
        help="输出报告目录（会自动创建） / output dir for reports",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=20,
        help="报告中展示的 Top N 文件（按风险或规模排序） / Top N in report",
    )
    ap.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="限制扫描文件数量，0 表示不限制 / limit scanned files (0 = unlimited)",
    )
    ap.add_argument(
        "--git-days",
        type=int,
        default=0,
        help="启用 git 热点分析的时间窗口（单位：天，0 表示关闭） / git hotspots window days (0 = disable)",
    )
    ap.add_argument(
        "--ext",
        nargs="*",
        default=DEFAULT_EXTS,
        help=(
            "需要扫描的文件扩展名列表，例如：--ext .c .cpp .hpp .py "
            "/ extensions to scan"
        ),
    )
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

    # ============ 基本信息输出 ============
    out.mkdir(parents=True, exist_ok=True)
    print("[INFO] 代码质量审计启动 / Quality Audit started")
    print(f"[INFO] root = {cfg.root}   (项目根目录)")
    print(f"[INFO] out  = {cfg.out}   (报告输出目录)")
    print(f"[INFO] exts = {cfg.exts}   (扫描的扩展名)")
    print(
        f"[INFO] max_files = "
        f"{cfg.max_files if cfg.max_files > 0 else 'unlimited'} "
        "(扫描文件数量上限)"
    )

    # ============ 扫描文件列表 ============
    files = iter_source_files(cfg.root, cfg.exts, cfg.skip_dirs, cfg.max_files)
    print(f"[INFO] scanned_files = {len(files)} (实际扫描的源码文件数)")

    # ============ 各类分析 ============
    print("[INFO] 分析代码行数 (LOC)...")
    loc = metrics_loc.analyze(files, cfg.root)

    print("[INFO] 分析复杂度与风险分数...")
    comp = metrics_complexity.analyze(files, cfg.root, loc["files"])

    print("[INFO] 分析 include 依赖关系...")
    deps = deps_includes.analyze(files, cfg.root)

    print("[INFO] 扫描危险模式与 TODO...")
    risk = risk_scan.analyze(files, cfg.root)

    git = {"enabled": False, "reason": "disabled"}
    if cfg.git_days and cfg.git_days > 0:
        print(f"[INFO] 启用 git 热点分析，时间窗口 = {cfg.git_days} 天...")
        git = git_hotspots.analyze(cfg.root, cfg.git_days)
    else:
        print("[INFO] git 热点分析已关闭（如需启用请设置 --git-days）")

    # ============ 汇总结果 ============
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

    # ============ 导出 JSON ============

    # raw json
    write_json(cfg.out / "raw" / "summary.json", summary)

    # ============ 导出 CSV 表格 ============
    # 1) 每个文件的行数统计
    write_csv(
        cfg.out / "tables" / "loc_files.csv",
        [
            "rel_path",
            "lang",
            "total_lines",
            "blank_lines",
            "comment_lines",
            "code_lines",
            "branch_tokens",
        ],
        [
            [
                f["rel_path"],
                f["lang"],
                str(f["total_lines"]),
                str(f["blank_lines"]),
                str(f["comment_lines"]),
                str(f["code_lines"]),
                str(f["branch_tokens"]),
            ]
            for f in loc["files"]
        ],
    )

    # 2) 每个文件的复杂度与风险
    write_csv(
        cfg.out / "tables" / "risk_files.csv",
        [
            "rel_path",
            "lang",
            "risk_score",
            "code_lines",
            "comment_lines",
            "comment_ratio",
            "branch_tokens",
            "max_func_len",
            "max_nest",
        ],
        [
            [
                f["rel_path"],
                f["lang"],
                str(f["risk_score"]),
                str(f["code_lines"]),
                str(f["comment_lines"]),
                str(f["comment_ratio"]),
                str(f["branch_tokens"]),
                str(f["max_func_len"]),
                str(f["max_nest"]),
            ]
            for f in comp["per_file"]
        ],
    )

    # 3) include 依赖边
    write_csv(
        cfg.out / "tables" / "include_edges.csv",
        ["from", "to", "count"],
        [[e["from"], e["to"], str(e["count"])] for e in deps["module_edges"]],
    )

    # 4) 风险命中统计
    write_csv(
        cfg.out / "tables" / "risk_hits.csv",
        [
            "rel_path",
            "lang",
            "risk_hits_score",
            "todo",
            "danger_c_funcs",
            "danger_cpp_patterns",
            "danger_py_patterns",
            "control_keywords",
        ],
        [
            [
                f["rel_path"],
                f["lang"],
                str(f["risk_hits_score"]),
                str(f["todo"]),
                str(f["danger_c_funcs"]),
                str(f["danger_cpp_patterns"]),
                str(f["danger_py_patterns"]),
                str(f["control_keywords"]),
            ]
            for f in risk["per_file"]
        ],
    )

    # ============ 导出依赖图 ============

    (cfg.out / "graphs").mkdir(parents=True, exist_ok=True)
    (cfg.out / "graphs" / "deps.dot").write_text(deps["dot"], encoding="utf-8")

    # ============ 生成 Markdown 总结报告 ============

    md = report_md.render(summary)
    (cfg.out / "summary.md").write_text(md, encoding="utf-8")

    # ============ 结束提示 ============
    print("[INFO] 审计完成 / Done.")
    print(f"[INFO] Markdown 报告: {cfg.out / 'summary.md'}")
    print(f"[INFO] 原始 JSON   : {cfg.out / 'raw' / 'summary.json'}")
    print(
        "[INFO] 依赖图 DOT : "
        f"{cfg.out / 'graphs' / 'deps.dot'}  "
        "(可使用 Graphviz 渲染：dot -Tpng deps.dot -o deps.png)"
    )


if __name__ == "__main__":
    main()
