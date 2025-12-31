#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Dict, List


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    """简单的 Markdown 表格工具。"""
    if not rows:
        return "_(empty)_\n"
    out: List[str] = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out) + "\n"


def _fmt_pct(part: int, total: int) -> str:
    """格式化百分比，给非专业人士一个直观感觉。"""
    if total <= 0:
        return "0%"
    return f"{(part / total) * 100:.1f}%"


def render(summary: Dict) -> str:
    """
    生成代码质量评估报告（Markdown 格式）

    设计目标：
    - 对工程师：提供可追踪的技术指标（LOC、复杂度、风险、依赖、git 热点等）
    - 对非专业读者：用自然语言说明“项目有多大、多复杂、风险大概在哪些地方”
    """
    loc = summary["loc"]
    comp = summary["complexity"]
    deps = summary["deps"]
    risk = summary["risk"]
    git = summary.get("git", {})

    totals = loc["totals"]
    by_lang = loc["by_lang"]
    by_dir = loc["by_topdir"]

    total_files = totals["files"]
    code_loc = totals["code_lines"]
    comment_loc = totals["comment_lines"]
    blank_loc = totals["blank_lines"]
    total_loc = totals["total_lines"]
    branch_tokens = totals["branch_tokens"]

    # 粗略估算：每 50 行代码 ~ 1 页技术书
    approx_pages = code_loc / 50.0 if code_loc > 0 else 0.0

    # 全局注释比例
    comment_ratio_total = _fmt_pct(comment_loc, code_loc + comment_loc)

    # 复杂度 / 风险总览（基于 per_file risk_score 的一个粗略级别）
    per_file = comp.get("per_file", [])
    risk_scores = [f.get("risk_score", 0) for f in per_file]
    max_risk = max(risk_scores) if risk_scores else 0
    avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

    if max_risk < 30:
        risk_level = "低 / Low"
    elif max_risk < 70:
        risk_level = "中 / Medium"
    else:
        risk_level = "高 / High"

    # 一些“人话”级别的评价
    if code_loc < 5000:
        size_desc = "体量较小，便于整体重构。"
    elif code_loc < 20000:
        size_desc = "中等规模，需要有结构化的模块设计。"
    else:
        size_desc = "代码规模较大，适合按照子系统（驱动 / 控制 / 通信等）分级管理。"

    if comment_loc == 0:
        comment_desc = "几乎没有注释，建议优先补充关键模块的注释。"
    elif comment_loc / max(code_loc, 1) < 0.2:
        comment_desc = "注释偏少，建议在核心控制 / 安全相关代码增加解释。"
    else:
        comment_desc = "注释比例还可以，可在复杂模块继续增强。"

    # Git 热点简单描述
    if git.get("enabled"):
        hotspot_desc = (
            f"启用了最近 {git.get('days', '?')} 天的 git 热点分析，"
            "可以看到哪些文件“改动频繁 + 复杂度高”，适合作为重点关注对象。"
        )
    else:
        hotspot_desc = (
            "当前未启用 git 热点分析，可在运行工具时增加 `--git-days` "
            "参数来观察“最近修改最频繁”的文件。"
        )

    md: List[str] = []

    # ========== 封面 & 概览 ==========
    md.append("# 水下机器人项目代码质量评估报告 / Project Quality Audit Report\n\n")
    md.append("本报告由内部代码分析工具自动生成，旨在：\n")
    md.append("- 用**可量化指标**说明当前工程的代码规模、复杂度和潜在风险；\n")
    md.append("- 帮助非专业读者直观理解：这个工程“有多大、多复杂、风险在哪”；\n")
    md.append("- 为后续重构、测试和工程管理提供决策参考。\n\n")

    md.append("## 0. 概览 / Executive Summary\n\n")
    md.append(f"- 项目根目录 (Project root)：`{summary['meta']['root']}`\n")
    md.append(f"- 扫描文件数 (Files scanned)：**{total_files}**\n")
    md.append(
        f"- 代码总行数 (Code LOC)：**{code_loc}**，"
        f"约折合 **{approx_pages:.1f} 页** 技术书（按每页 ~50 行估算）\n"
    )
    md.append(
        f"- 注释行数 (Comment LOC)：**{comment_loc}**，"
        f"注释比例 (Comment ratio)：**{comment_ratio_total}** —— {comment_desc}\n"
    )
    md.append(
        f"- 分支关键字计数 (Branch tokens, 反映 if/循环等复杂度大致数量)："
        f"**{branch_tokens}**\n"
    )
    md.append(
        f"- 复杂度 / 风险综合水平 (Overall risk level)：**{risk_level}** "
        f"(平均风险评分 ~{avg_risk:.1f}，最高 ~{max_risk:.1f})\n"
    )
    md.append(f"- 规模评价 (Project size)：{size_desc}\n")
    md.append(f"- Git 热点分析 (Git hotspots)：{hotspot_desc}\n\n")

    md.append(
        "简单来说：如果你不是写代码的人，可以把这个工程理解为——\n\n"
        f"- 大约有 **{approx_pages:.1f} 页** 的“代码说明书”；\n"
        "- 其中一部分文件结构比较复杂，是未来维护和出问题的重点区域；\n"
        "- 报告后面列出的 Top 表格，就是“最值得优先关注”的那一批文件。\n\n"
    )

    # ========== 1. 语言分布 ==========
    md.append("## 1. 语言分布 / Language Breakdown\n\n")
    md.append(
        "这一部分用于回答：**“这个工程主要是用什么语言写的，各占多少量？”**\n\n"
    )
    rows: List[List[str]] = []
    for k, v in sorted(
        by_lang.items(), key=lambda kv: kv[1]["code_lines"], reverse=True
    ):
        lang_files = v["files"]
        lang_code = v["code_lines"]
        lang_comment = v["comment_lines"]
        lang_total = v["total_lines"]
        rows.append(
            [
                k,
                str(lang_files),
                str(lang_code),
                str(lang_comment),
                str(lang_total),
                _fmt_pct(lang_code, code_loc),
            ]
        )
    md.append(
        _md_table(
            ["Lang", "Files", "Code LOC", "Comment LOC", "Total LOC", "Code %"],
            rows,
        )
    )

    # ========== 2. 按顶层目录统计 LOC ==========
    md.append("## 2. 按顶层目录的代码量 / LOC by Top-level Directory\n\n")
    md.append(
        "这一部分回答：**“控制 / 通信 / 导航 / 公共库等大模块，各自大概有多少代码？”**\n\n"
    )
    rows = []
    for k, v in sorted(by_dir.items(), key=lambda kv: kv[1], reverse=True):
        rows.append([k or "<root>", str(v), _fmt_pct(v, code_loc)])
    md.append(_md_table(["Top Dir", "Code LOC", "Code %"], rows))

    # ========== 3. 高风险文件 ==========
    md.append("## 3. 高风险文件（综合评分） / Top Risk Files (Composite Score)\n\n")
    md.append(
        "这里列出的是**结构复杂 + 行数较多 + 分支较多**的文件，"
        "通常是“最难改、最容易出问题”的地方。\n\n"
    )
    rows = []
    for f in comp["top_risk"][:20]:
        rows.append(
            [
                f["rel_path"],
                str(f["risk_score"]),
                str(f["code_lines"]),
                str(f["max_func_len"]),
                str(f["max_nest"]),
                str(f["branch_tokens"]),
                f"{f['comment_ratio']:.2f}",
            ]
        )
    md.append(
        _md_table(
            [
                "File",
                "RiskScore",
                "Code LOC",
                "MaxFuncLen",
                "MaxNest",
                "BranchTok",
                "CommentRatio",
            ],
            rows,
        )
    )

    # ========== 4. 超长函数 ==========
    md.append("## 4. 超长函数（重构候选） / Long Functions (Refactor Candidates)\n\n")
    md.append(
        "这一部分用来回答：**“哪些函数太长 / 嵌套太深，需要拆分？”**\n\n"
        "经验上，超过 100 行、嵌套层数很多的函数，在调试和扩展时成本很高，"
        "适合优先拆分为更小的子函数。\n\n"
    )
    rows = []
    for fn in comp["long_functions"][:20]:
        rows.append(
            [
                fn["rel_path"],
                fn["func"],
                f"{fn['start']}-{fn['end']}",
                str(fn["len"]),
                str(fn["nest"]),
            ]
        )
    md.append(_md_table(["File", "Function", "Lines", "Len", "Nest"], rows))

    # ========== 5. 依赖健康度 ==========
    md.append("## 5. 头文件依赖健康度（C/C++） / Include Dependency Health (C/C++)\n\n")
    md.append(
        "这一部分关注：**“模块之间的耦合关系是否清晰，有没有互相环状依赖？”**\n\n"
        f"- 检测到的 C/C++ 模块数 (Modules detected)：**{len(deps['modules'])}** 个\n"
        f"- 发现的环状依赖 (Cycles detected)：**{len(deps['cycles'])}** 处\n\n"
    )
    if deps["cycles"]:
        md.append("### 5.1 环状依赖示例 / Sample Cycles (Top)\n\n")
        for c in deps["cycles"][:10]:
            md.append("- " + " -> ".join(c) + "\n")
        md.append("\n")

    md.append("### 5.2 高频被引用头文件 / Top Included Headers\n\n")
    rows = [
        [x["header"], str(x["count"])]
        for x in deps["top_headers"][:20]
    ]
    md.append(_md_table(["Header", "Include Count"], rows))

    # ========== 6. 风险关键字扫描 ==========
    md.append("## 6. 风险扫描 / Risk Scan\n\n")
    md.append(
        "通过扫描 TODO/FIXME/HACK、危险 C 函数、可疑 C++/Python 写法等，"
        "给出一些“可能需要额外注意”的位置。\n\n"
    )
    md.append(
        f"- TODO / FIXME / HACK / XXX 总数：**{risk['totals']['todo']}**\n"
    )
    md.append(
        f"- 危险 C 函数（如 strcpy/memcpy 等）命中次数："
        f"**{risk['totals']['danger_c_funcs']}**\n"
    )
    md.append(
        f"- 危险 C++ 模式命中次数：**{risk['totals']['danger_cpp_patterns']}**\n"
    )
    md.append(
        f"- 危险 Python 模式命中次数：**{risk['totals']['danger_py_patterns']}**\n"
    )
    md.append(
        f"- 控制相关关键字（estop/failsafe 等）命中次数："
        f"**{risk['totals']['control_keywords']}**\n\n"
    )

    md.append("### 6.1 高风险命中文件 / Top Risk-hit Files\n\n")
    rows = []
    for f in risk["top_risk_hits"][:20]:
        rows.append(
            [
                f["rel_path"],
                str(f["risk_hits_score"]),
                str(f["todo"]),
                str(f["danger_c_funcs"]),
                str(f["danger_cpp_patterns"]),
                str(f["danger_py_patterns"]),
                str(f["control_keywords"]),
            ]
        )
    md.append(
        _md_table(
            ["File", "Score", "TODO", "C-func", "C++pat", "Pypat", "CtrlKW"],
            rows,
        )
    )

    # ========== 7. Git 热点 ==========
    md.append("## 7. Git 热点文件（可选） / Git Hotspots (Optional)\n\n")
    if git.get("enabled"):
        md.append(
            f"- 分析窗口 (Window)：最近 **{git['days']}** 天内的提交记录\n\n"
        )
        rows = [
            [x["path"], str(x["changes"])]
            for x in git["hot_files"][:20]
        ]
        md.append(_md_table(["File", "Changes"], rows))
        md.append(
            "这些文件往往兼具两种特征：**“经常被修改” + “本身较复杂”**，\n"
            "适合作为重构、补充测试、加强文档的优先目标。\n\n"
        )
    else:
        md.append(f"- 当前未启用 (Disabled)：{git.get('reason', 'n/a')}\n\n")

    # ========== 8. 建议行动 ==========
    md.append("## 8. 建议行动（按优先级） / Suggested Actions (Prioritized)\n\n")
    md.append(
        "从工程管理和质量提升的角度，推荐按以下顺序推进：\n\n"
    )
    md.append(
        "1) **聚焦 Top Risk Files**：\n"
        "   - 拆分超长函数，降低嵌套层次；\n"
        "   - 将“控制逻辑 / 安全相关逻辑”与“日志 / 调试代码”分离。\n"
    )
    md.append(
        "2) **处理依赖环和高耦合模块**：\n"
        "   - 打破 include 环状依赖；\n"
        "   - 将共用类型下沉到稳定的 `shared/` 或 `interfaces/` 层。\n"
    )
    md.append(
        "3) **清理风险关键字与危险函数**：\n"
        "   - 系统性梳理 TODO/FIXME，区分“短期必须处理”和“长期规划”；\n"
        "   - 避免使用不安全的 C 函数（如裸 `strcpy`），统一封装安全 API。\n"
    )
    md.append(
        "4) **加强安全路径测试（特别是 ROV 相关）**：\n"
        "   - 为 `ControlGuard` / 急停 (estop) / Failsafe 等模块增加单元测试；\n"
        "   - 在真实或仿真环境中验证“异常输入 / 网络中断 / 传感器异常”场景。\n"
    )
    md.append(
        "5) **向非专业干系人汇报**：\n"
        "   - 使用本报告中的“代码规模”“风险等级”和几张 Top 表格，"
        "简单解释工程当前完成度和后续工作量的大致方向。\n\n"
    )

    md.append("_本报告由自动化工具生成，无需手工编辑。如需再次评估，可在项目根目录重新运行审计脚本。_\n")

    return "".join(md)
