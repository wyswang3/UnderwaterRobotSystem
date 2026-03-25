# Documentation Index

## 文档状态

- 状态：Authoritative
- 说明：当前文档体系总索引、目录说明与权威基线清单。

## 1. 文档目录结构

当前文档目录固定为以下结构：

- `docs/architecture/`
  - 系统架构、主数据流、重构设计、跨仓兼容与专题评审
- `docs/interfaces/`
  - shared / SHM / telemetry / 时间 / logging 等接口契约
- `docs/runbook/`
  - bring-up、operator、replay、故障恢复、验证步骤
- `docs/productization/`
  - 当前阶段产品化收口、夜间进展、专题计划
- `docs/handoff/`
  - Codex 交接体系固定入口
- `docs/archive/`
  - 历史参考、旧总览、阶段性快照、测试报告与局部审查记录

约束：

1. 新增文档优先放入以上 6 类目录。
2. 不再新增 `docs/navigation/`、`docs/test/` 这类临时目录。
3. 普通文档统一使用英文、小写、下划线命名。
4. 交接文档固定使用：
   - `CODEX_HANDOFF.md`
   - `CODEX_PROGRESS_LOG.md`
   - `CODEX_NEXT_ACTIONS.md`

## 2. Codex 优先阅读顺序

每次新会话启动后，优先阅读顺序固定为：

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/project_memory.md`
5. `docs/architecture/upgrade_strategy.md`
6. 相关接口契约与 runbook

补充说明：

- 若需要补上下文细节，再看 `docs/handoff/CODEX_PROGRESS_LOG.md`
- 若需要历史证据，再看 `docs/archive/archive_index.md`

## 3. 当前权威基线

以下文档当前被定义为权威基线：

### 3.1 总体基线

- `docs/project_memory.md`
- `docs/architecture/system_main_dataflow.md`
- `docs/architecture/upgrade_strategy.md`
- `docs/documentation_index.md`

### 3.2 接口契约基线

- `docs/interfaces/time_contract.md`
- `docs/interfaces/nav_state_contract.md`
- `docs/interfaces/nav_view_contract.md`
- `docs/interfaces/telemetry_ui_contract.md`
- `docs/interfaces/control_intent_contract.md`

### 3.3 运行与验证基线

- `docs/runbook/gcs_ui_operator_guide.md`
- `docs/runbook/supervisor_phase0_operator_guide.md`
- `docs/runbook/log_replay_guide.md`
- `docs/runbook/usb_reconnect_bench_plan.md`
- `docs/runbook/replay_injection_guide.md`

### 3.4 Codex 交接基线

- `docs/handoff/CODEX_HANDOFF.md`
- `docs/handoff/CODEX_PROGRESS_LOG.md`
- `docs/handoff/CODEX_NEXT_ACTIONS.md`

## 4. 当前 Working Draft 文档

以下文档是当前有效的设计草案或阶段性计划，可用于后续实施，但不能直接当成“已经全部落地的事实”：

- `docs/architecture/control_nav_integration_plan.md`
- `docs/architecture/sensor_toolchain_refactor_plan.md`
- `docs/architecture/logging_full_chain_audit.md`
- `docs/interfaces/logging_contract.md`
- `docs/architecture/ros2_bridge_stage1_plan.md`
- `docs/architecture/ros2_refactor_assessment.md`
- `docs/productization/ui_upgrade_plan.md`
- `docs/productization/ui_windows_support_audit.md`

## 5. 当前 Archived / Historical 文档

以下文档仅作历史参考，不作为当前唯一事实依据：

- `docs/archive/root/system_overview_legacy.md`
- `docs/archive/root/project_quality_audit_chinese_explanation.md`
- `docs/archive/root/first_dive_checklist_legacy.md`
- `docs/archive/navigation/repo_local_change_summary_20260312.md`
- `docs/archive/test/nav_module_test_plan.md`
- `docs/archive/test/p0_contract_baseline_test_report.md`
- `docs/architecture/project_upgrade_master_plan.md`
- `docs/productization/codex_handoff.md`

说明：

- 若 Archived 文档与权威基线冲突，一律以权威基线和代码为准。
- Archived 文档主要用于理解当时的规划口径、整改背景或测试证据。

## 6. 命名与状态标识规范

### 6.1 命名规范

1. 普通文档：英文、小写、下划线。
2. 避免使用：`final_v2_new_latest` 这类不可维护命名。
3. 交接文档：固定大写命名。

### 6.2 状态标识

关键文档开头统一使用以下状态之一：

- `Authoritative`
- `Working draft`
- `Archived`
- `Obsolete`

含义：

- `Authoritative`
  - 当前生效基线
- `Working draft`
  - 方向已冻结，但尚未全部实施
- `Archived`
  - 历史参考，保留证据价值
- `Obsolete`
  - 已被新路径或新文档替代

## 7. 当前整理原则

本轮整理后的原则如下：

1. 先保证“主入口清晰”，再补细节。
2. 先区分权威基线与历史参考，再谈内容增补。
3. 交接文档固定到 `docs/handoff/`，不再散落在其他目录。
4. 夜间进展保留在 `docs/productization/`，交接摘要保留在 `docs/handoff/`。
