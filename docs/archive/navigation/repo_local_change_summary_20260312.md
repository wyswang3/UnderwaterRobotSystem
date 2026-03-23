# 本地改动说明（2026-03-12）

## 仓库

- 路径：`UnderwaterRobotSystem/UnderwaterRobotSystem`
- 本轮功能提交：`7166ce0 统一导航共享协议并补充导航整改文档`

## 本轮改动范围

本仓库本轮承担的是“共享协议与审查文档收口”职责，核心内容包括：

- 升级 `shared/msg/nav_state.hpp`
- 升级 `shared/msg/nav_state_view.hpp`
- 升级 `shared/shm/nav_state_shm.hpp`
- 新增导航专项审查、故障处理、SHM 契约、测试计划文档

## 关键改动说明

### 1. 共享协议从“数值结构”升级为“显式状态语义结构”

`NavState` 新增并统一了以下字段语义：

- `valid`
- `stale`
- `degraded`
- `nav_state`
- `fault_code`
- `sensor_mask`
- `age_ms`

同时新增：

- `NavRunState`
- `NavFaultCode`
- `NavSensorBits`

目标是让导航、gateway、控制三端对“是否可信、是否过期、为什么不可用”使用同一套语言。

### 2. NavStateView 控制契约升级

`NavStateView` wire version 升级到 `2`，补齐：

- `stale`
- `degraded`
- `nav_state`
- `fault_code`
- `sensor_mask`
- `status_flags`

避免控制侧继续依赖保留字段或模糊布尔量理解导航状态。

### 3. SHM 契约版本升级

`shared/shm/nav_state_shm.hpp` 中 `payload version` 升级到 `2`，用于显式拒绝旧布局，避免导航发布端和读取端静默错配。

### 4. 文档补齐

新增文档：

- `docs/navigation/nav_module_review.md`
- `docs/navigation/nav_fault_handling_plan.md`
- `docs/navigation/nav_shm_contract_review.md`
- `docs/test/nav_module_test_plan.md`

这些文档对应本轮导航 P0 整改的审查结论、契约定义和测试基线。

## 下游验证结果

本仓库没有独立运行目标；兼容性通过下游仓库验证：

- `Underwater-robot-navigation` 已完成 `uwnav_navd` 编译和 `nav_core_test_nav_runtime_status`
- `OrangePi_STM32_for_ROV` 已完成 `nav_viewd`、`pwm_control_program` 编译，以及导航相关测试

## 仍需注意

- 当前工程目录下存在一份仓库外的 `UnderwaterRobotSystem/shared` 副本，实际构建仍引用那份副本。
- 本仓库中的 `shared/` 已同步到本轮语义，但后续应尽快收敛为单一真实源，避免再次出现协议漂移。

## 远程提交前建议

- 先对比本仓库内 `shared/` 与实际构建引用的外层 `shared/` 是否完全一致。
- 再审查下游两个仓库是否都基于本协议提交完成，避免远端出现“协议已推、消费端未跟上”的半升级状态。
