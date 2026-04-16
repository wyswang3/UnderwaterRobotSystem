# UnderwaterRobotSystem

`UnderwaterRobotSystem` 是当前项目的 system-level docs / integration mirror 仓库。

它的职责不是替代各代码仓，而是提供：

- 跨仓一致的技术基线
- 当前阶段判断、升级思路和 operator runbook
- shared contract、control chain、nav chain、GCS chain 的关系说明
- handoff / progress / history 的稳定入口

如果你是新加入的开发者，这个仓最像“文档入口”；如果你要改真实运行时代码，仍然要回到对应代码仓。

## 当前阶段 / Current Project Status

当前项目已经不再是“先把链路跑通”的原型阶段，而是：

- P0 authority state / contract baseline 已基本建立
- P1 bring-up / reconnect / replay / diagnostics 仍在继续收口
- P2 controller framework、GUI、ROS2 peripheral layer 开始受控推进

当前总目标是：

1. 稳住 control / nav / execution 主链
2. 收口 shared / replay / reconnect / operator diagnostics
3. 在 authority boundary 清晰的前提下扩展 GUI / bridge / tooling

## 真实代码源在哪里

当前运行时代码真实源分布在：

- `../shared/`
  - shared contract real source
- `../OrangePi_STM32_for_ROV/`
  - control loop、gateway、PWM / STM32 execution
- `../Underwater-robot-navigation/`
  - navigation runtime、sensor binding、replay / diagnostics
- `../../UnderWaterRobotGCS/`
  - GCS、TUI / GUI、protocol client、operator tooling

本仓主要负责系统级文档，不负责主运行时实现。

## docs 目录当前结构

当前 `docs/` 已改为“4 篇主文档 + 固定子目录”：

根目录主文档：

- `docs/documentation_index.md`
- `docs/operator_manual.md`
- `docs/project_memory.md`
- `docs/upgrade_strategy.md`

固定子目录：

- `docs/handoff/`
- `docs/baseline/`
- `docs/contracts/`
- `docs/operator/`
- `docs/validation/`
- `docs/control_route/`
- `docs/navigation_route/`
- `docs/ros2_route/`
- `docs/history/`

这个结构的目标不是“分类越多越好”，而是：

- 根目录只保留当前必须先看的主文档
- 细节按路线和用途下沉
- 历史材料不再伪装成活跃入口

## 推荐阅读顺序

如果你是第一次进入这个工作区，推荐按下面顺序看：

1. 工作区根目录 `AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/documentation_index.md`
5. `docs/project_memory.md`
6. `docs/upgrade_strategy.md`

然后按任务进入对应路线：

- control：`docs/control_route/` + `OrangePi_STM32_for_ROV/README.md`
- navigation：`docs/navigation_route/` + `Underwater-robot-navigation/README.md`
- GCS：`../../UnderWaterRobotGCS/README.md`
- contracts：`docs/contracts/`

## 当前系统主线

控制主线：

```text
GCS(TUI/GUI)
  -> gateway/gcs_server
  -> GCS Intent SHM
  -> pwm_control_program
  -> orangepi_send / STM32 / ESC / Thrusters
```

导航主线：

```text
IMU + DVL
  -> nav_core/uwnav_navd
  -> NavState SHM + nav_state.bin + nav_timing.bin
  -> gateway/nav_viewd
  -> NavView SHM
  -> pwm_control_program
```

复盘主线：

```text
nav logs + control logs + telemetry timeline
  -> incident bundle
  -> uwnav_nav_replay
  -> replay_compare / diagnostics
```

## 这个仓当前最适合做什么

适合：

- 看系统级边界
- 看当前项目进度和技术路线
- 看跨仓 contract / runbook / validation 说明
- 做 handoff 和后续协作

不适合：

- 把这里当成单体主仓
- 从这里直接推断所有 runtime 代码真实实现
- 用历史文档替代当前基线

## 最重要的文档入口

当前最重要的入口仍然是：

- [docs/documentation_index.md](/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/documentation_index.md)
- [docs/project_memory.md](/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/project_memory.md)
- [docs/operator_manual.md](/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/operator_manual.md)
- [docs/upgrade_strategy.md](/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/upgrade_strategy.md)

如果你准备继续做运行时开发，再回到各代码仓的 README 和真实代码入口。
