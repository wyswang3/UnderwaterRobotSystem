# Documentation Index

## 文档状态

- 状态：Authoritative
- 说明：当前系统文档仓主入口。根目录只保留 4 篇主文档，其余内容按固定子目录分层，目标是让读者先找到入口，再进入细节。

## 1. 当前目录结构 / Current Layout

### 1.1 根目录只保留 4 篇主文档

- `docs/documentation_index.md`
  - 总入口 / start here
- `docs/operator_manual.md`
  - 当前操作说明 / current operator path
- `docs/project_memory.md`
  - 当前阶段判断 / current technical thinking
- `docs/upgrade_strategy.md`
  - 当前升级主线 / current upgrade strategy

### 1.2 固定子目录

| Directory | 用途 | 说明 |
| --- | --- | --- |
| `docs/handoff/` | Codex handoff | 交接、进度、下一轮动作 |
| `docs/baseline/` | system baseline | 系统总览、阶段补充、商业化收口 |
| `docs/contracts/` | contracts | 时间、导航、遥测、控制契约 |
| `docs/operator/` | operator support | GCS、supervisor、现场操作补充 |
| `docs/validation/` | validation / replay | bench、replay、bundle、验证 |
| `docs/control_route/` | control route | 控制侧路线、设备识别、集成计划 |
| `docs/navigation_route/` | navigation route | 导航侧路线、故障、传感器链 |
| `docs/ros2_route/` | ROS2 route | ROS2 bridge、UI backend、消息映射 |
| `docs/history/` | history / archive | 旧规划、阶段快照、历史证据 |

规则：

1. 新文档先判断是否应并入 4 篇主文档。
2. 不能并入时，只能进入上表中的固定子目录。
3. 不再恢复随意扩张的平铺文件，也不再新增临时目录。

## 2. Start Here / 快速阅读路径

### 2.1 Codex startup path

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/project_memory.md`
5. `docs/upgrade_strategy.md`
6. 当前任务对应的 contract / operator / route 文档

补充：

- 时间线：`docs/handoff/CODEX_PROGRESS_LOG.md`
- 历史材料：`docs/history/archive_index.md`

### 2.2 New developer path

1. `docs/project_memory.md`
2. `docs/upgrade_strategy.md`
3. `docs/baseline/system_main_dataflow.md`
4. `docs/contracts/time_contract.md`
5. `docs/contracts/nav_state_contract.md`
6. `docs/contracts/telemetry_ui_contract.md`

### 2.3 Operator / integration path

1. `docs/operator_manual.md`
2. `docs/operator/香橙派_当前实验_操作员使用说明.md`
3. `docs/operator/gcs_ui_operator_guide.md`
4. `docs/operator/local_debug_and_field_startup_guide.md`
5. `docs/validation/incident_bundle_guide.md`

## 3. Current Main Docs / 当前 4 篇主文档

- `documentation_index.md`
  - 用来判断“先看哪篇”，不是技术细节总汇
- `operator_manual.md`
  - 用来跑当前最小可执行操作路径
- `project_memory.md`
  - 用来理解当前阶段、边界、已完成与未完成
- `upgrade_strategy.md`
  - 用来理解当前技术路线和优先级排序

## 4. Subdirectory Guide / 子目录导航

### 4.1 `docs/handoff/`

- `CODEX_HANDOFF.md`
- `CODEX_NEXT_ACTIONS.md`
- `CODEX_PROGRESS_LOG.md`

用途：

- 交接恢复
- 下一轮动作
- 时间线追踪

### 4.2 `docs/baseline/`

- `system_main_dataflow.md`
- `commercialization_review.md`
- `minimum_viable_runtime_profiles.md`
- `teleop_primary_operator_lane.md`
- `cross_repo_compatibility_matrix.md`

用途：

- 当前系统总路径
- 当前交付形态和最小运行轮廓

### 4.3 `docs/contracts/`

- `time_contract.md`
- `nav_state_contract.md`
- `nav_view_contract.md`
- `telemetry_ui_contract.md`
- `control_intent_contract.md`
- `logging_contract.md`

用途：

- 跨仓真实语义边界
- shared / telemetry / timing 对齐

### 4.4 `docs/operator/`

- `gcs_ui_operator_guide.md`
- `local_debug_and_field_startup_guide.md`
- `supervisor_phase0_operator_guide.md`
- `device_binding_and_reconnect.md`
- `fault_code_reference.md`
- `香橙派_当前实验_操作员使用说明.md`

用途：

- 当前操作补充
- 现场 bring-up / GCS / supervisor / fault lookup

### 4.5 `docs/validation/`

- `field_validation_checklist.md`
- `local_teleop_smoke_checklist.md`
- `incident_bundle_guide.md`
- `incident_timeline_usage.md`
- `log_replay_guide.md`
- `logging_full_chain_audit.md`
- `nav_timing_log_guide.md`
- `replay_injection_guide.md`
- `usb_reconnect_bench_plan.md`

用途：

- bench / replay / compare / bundle / triage

### 4.6 `docs/control_route/`

- `control_nav_integration_plan.md`
- `device_identification_and_profiles_plan.md`

用途：

- 控制侧技术路线
- 设备识别与 profile 思路

### 4.7 `docs/navigation_route/`

- `nav_fault_handling_plan.md`
- `nav_module_review.md`
- `nav_shm_contract_review.md`
- `sensor_toolchain_refactor_plan.md`

用途：

- 导航侧技术路线
- 故障传播、传感器链、共享状态审查

### 4.8 `docs/ros2_route/`

- `ros2_bridge_stage1_plan.md`
- `ros2_bridge_validation_guide.md`
- `ros2_refactor_assessment.md`
- `rov_msgs_mapping.md`
- `ui_upgrade_plan.md`
- `ui_windows_support_audit.md`

用途：

- ROS2 外围桥接路线
- UI backend / bridge / message mapping

### 4.9 `docs/history/`

- `archive_index.md`
- `nightly_upgrade_progress.md`
- `system_overview_legacy.md`
- `project_quality_audit_chinese_explanation.md`
- `first_dive_checklist_legacy.md`
- `repo_local_change_summary_20260312.md`
- `nav_module_test_plan.md`
- `p0_contract_baseline_test_report.md`
- `project_upgrade_master_plan.md`

用途：

- 历史证据
- 旧结论与阶段快照

## 5. Consolidated / Removed / 已合并与删除

以下重复文档已并入主文档，不再单独保留：

- `bringup_runbook.md`
  - 并入：`operator_manual.md`、`docs/operator/local_debug_and_field_startup_guide.md`
- `customer_onboarding_guide.md`
  - 并入：`operator_manual.md`、`docs/operator/香橙派_当前实验_操作员使用说明.md`
- `customer_fault_recovery_guide.md`
  - 并入：`operator_manual.md`、`docs/operator/gcs_ui_operator_guide.md`
- `commercial_upgrade_roadmap.md`
  - 并入：`docs/baseline/commercialization_review.md`、`upgrade_strategy.md`
- `p0_contract_baseline_status.md`
  - 删除；历史判断已被 `project_memory.md` 与 `docs/handoff/CODEX_PROGRESS_LOG.md` 覆盖

## 6. 使用规则 / Reading Rules

1. 先看根目录 4 篇主文档，再看对应子目录。
2. 契约问题优先看 `docs/contracts/`，不要从 UI 文档反推真实语义。
3. 历史材料只用于证据，不作为当前默认口径。
4. 如果一篇文档只重复主文档、又没有证据价值，就继续删，不再囤积。
