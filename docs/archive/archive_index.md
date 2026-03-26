# Archive Index

## 文档状态

- 状态：Authoritative
- 说明：当前 archive 目录的归档索引，用于说明哪些文档已退出权威基线，以及为什么仍保留。

## 1. 归档原则

以下文档会进入 `docs/archive/`：

1. 早期规划总览，已明显落后于当前代码结构
2. 阶段性评估报告，已不再作为当前主线依据
3. 单次整改过程记录、本地变更摘要
4. 历史测试计划和测试报告
5. 仍有证据价值，但不适合继续放在权威目录中的文档

## 2. 当前已归档文档

### 2.1 根目录旧文档

- `root/system_overview_legacy.md`
  - 原因：早期系统总览偏规划口径，与当前多仓与 authority 边界已有明显差异
- `root/project_quality_audit_chinese_explanation.md`
  - 原因：阶段性质量评估说明，保留历史审查背景，不再作为当前基线
- `root/first_dive_checklist_legacy.md`
  - 原因：早期入水实验 checklist，与当前在线导航/控制基线不一致

### 2.2 导航整改过程记录

- `navigation/repo_local_change_summary_20260312.md`
  - 原因：属于单次整改交接记录，保留历史上下文，不再作为当前主线入口

### 2.3 测试历史产物

- `test/nav_module_test_plan.md`
  - 原因：阶段性测试计划，保留审查依据
- `test/p0_contract_baseline_test_report.md`
  - 原因：阶段性测试报告，保留验证证据

## 3. 保留在原目录但视为历史参考的文档

以下文档因路径仍有参考价值，暂不移动，但状态视为历史参考：

- `docs/architecture/project_upgrade_master_plan.md`
- `docs/productization/codex_handoff.md`

原因：

- 前者是早期升级总规划快照
- 后者是旧 handoff 路径，现已被 `docs/handoff/CODEX_HANDOFF.md` 替代

## 4. 使用规则

1. 新任务不要再把 Archived 文档当成默认入口。
2. 当 Archived 文档与代码或权威基线冲突时，以代码与权威基线为准。
3. 如需继续保留归档文档，应优先在 archive 中维护，而不是重新放回主目录。
