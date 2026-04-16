# Archive Index

## 文档状态

- 状态：Authoritative
- 说明：说明 `docs/history/` 中哪些材料只是历史证据，哪些旧文档已经被主文档吸收并删除。

## 1. History Policy / 历史材料规则

### 1.1 继续保留到 `docs/history/`

满足以下任一条件时，文档保留在 `docs/history/`：

1. 仍有阶段证据价值
2. handoff / progress log 还会引用
3. 能帮助解释为什么今天会演化成当前结构

### 1.2 直接删除而不保留独立文件

满足以下条件时，直接删除：

1. 只是主文档的重复压缩版
2. 没有独立证据价值
3. 已被更清晰的主文档吸收

## 2. Current Historical Set / 当前历史集

### 2.1 历史总览与阶段快照

- `system_overview_legacy.md`
  - 早期系统总览，带较强规划口径
- `project_quality_audit_chinese_explanation.md`
  - 阶段性质量审查说明
- `project_upgrade_master_plan.md`
  - 早期总升级计划快照
- `nightly_upgrade_progress.md`
  - 旧的夜间进度记录，现由 `docs/handoff/CODEX_PROGRESS_LOG.md` 替代

### 2.2 历史操作与整改证据

- `first_dive_checklist_legacy.md`
  - 早期实验 checklist
- `repo_local_change_summary_20260312.md`
  - 单轮整改历史记录

### 2.3 历史测试材料

- `nav_module_test_plan.md`
  - 阶段性测试计划
- `p0_contract_baseline_test_report.md`
  - 阶段性测试报告

## 3. 本轮已删除并并入主文档

- `bringup_runbook.md`
  - 合并到 `docs/operator_manual.md` 与 `docs/operator/local_debug_and_field_startup_guide.md`
- `customer_onboarding_guide.md`
  - 合并到 `docs/operator_manual.md` 与 `docs/operator/香橙派_当前实验_操作员使用说明.md`
- `customer_fault_recovery_guide.md`
  - 合并到 `docs/operator_manual.md` 与 `docs/operator/gcs_ui_operator_guide.md`
- `commercial_upgrade_roadmap.md`
  - 合并到 `docs/baseline/commercialization_review.md` 与 `docs/upgrade_strategy.md`
- `p0_contract_baseline_status.md`
  - 历史判断已被 `docs/project_memory.md` 与 `docs/handoff/CODEX_PROGRESS_LOG.md` 覆盖

## 4. 使用规则 / How To Use

1. 新任务不要把 `docs/history/` 当默认入口。
2. `docs/history/` 与当前代码或权威基线冲突时，以代码和主文档为准。
3. 如果某篇历史材料已经没有证据价值，应继续删，不保留“为了完整而完整”的文件。
