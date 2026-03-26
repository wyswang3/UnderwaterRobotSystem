# UnderwaterRobotSystem

`UnderwaterRobotSystem` 是当前水下机器人项目的系统级集成与文档镜像仓。

它的职责不是承载所有一线开发，而是提供：

- 系统级架构说明、接口契约、runbook 和产品化进展
- 跨仓一致的文档基线与交接入口
- shared 契约、控制链、导航链、GCS 链之间的关系说明
- 历史参考与归档材料的统一索引

如果你是技术开发者或后续 Codex，会把这个仓当作“系统文档入口”，但不要把它误认为所有代码的唯一真源。

## 1. 代码真实源在哪里

当前主线代码分布在独立仓库中：

- 控制与执行链：`OrangePi_STM32_for_ROV`
- 在线导航链：`Underwater-robot-navigation`
- GCS / UI：`UnderWaterRobotGCS`
- shared 契约真实源：`UnderwaterRobotSystem/shared`

本仓主要负责：

- 版本化文档与交叉引用
- 系统级基线冻结
- 运行说明、验证说明和交接摘要

## 2. 当前文档体系

当前文档目录固定为：

- `docs/architecture/`
- `docs/interfaces/`
- `docs/runbook/`
- `docs/productization/`
- `docs/handoff/`
- `docs/archive/`

说明：

- `docs/handoff/` 是当前 Codex 交接体系固定入口
- `docs/archive/` 只保留历史参考，不作为当前唯一基线
- 详细目录说明见 `docs/documentation_index.md`

## 3. 推荐阅读顺序

如果你是第一次进入当前项目，推荐按以下顺序阅读：

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/documentation_index.md`
5. `docs/project_memory.md`
6. `docs/architecture/upgrade_strategy.md`
7. 当前任务相关的接口契约与 runbook

如果你是要继续实现功能，再进入：

1. `OrangePi_STM32_for_ROV/README.md`
2. `Underwater-robot-navigation/README.md`
3. `UnderWaterRobotGCS/README.md`
4. 对应仓库的真实入口代码

## 4. 当前系统主线

控制主线：

```text
GCS(TUI/GUI)
  -> gateway/gcs_server
  -> GCS Intent SHM
  -> pwm_control_program
  -> PwmClient
  -> orangepi_send / STM32 / ESC / Thrusters
```

导航主线：

```text
IMU + DVL
  -> nav_core/uwnav_navd
  -> NavState SHM + nav_timing.bin + nav_state.bin
  -> gateway/nav_viewd
  -> NavView SHM
  -> pwm_control_program
```

诊断与复盘主线：

```text
nav_timing.bin + nav_state.bin + control CSV + telemetry timeline/events
  -> merge_robot_timeline.py
  -> incident bundle
  -> uwnav_nav_replay + replay_compare.py
```

## 5. 当前最重要的文档

当前权威基线优先看：

- `docs/documentation_index.md`
- `docs/project_memory.md`
- `docs/architecture/system_main_dataflow.md`
- `docs/architecture/upgrade_strategy.md`
- `docs/interfaces/*.md` 中与你任务相关的契约
- `docs/runbook/*.md` 中与你任务相关的操作说明

设计草案和阶段性计划：

- `docs/architecture/control_nav_integration_plan.md`
- `docs/architecture/sensor_toolchain_refactor_plan.md`
- `docs/interfaces/logging_contract.md`

历史参考：

- `docs/archive/archive_index.md`
- `docs/archive/` 下的旧总览、旧测试、旧整改记录

## 6. 当前不应把这个仓库理解成什么

请不要把这个仓库理解成：

- 顶层统一构建系统
- 所有运行时代码的唯一入口
- GUI 产品仓
- 实时控制或实时导航的唯一实现仓

它的正确定位是：

- 系统级文档与交接入口
- 跨仓边界与契约说明仓
- 历史材料与当前基线的整理仓
