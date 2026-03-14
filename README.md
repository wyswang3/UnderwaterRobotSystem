# UnderwaterRobotSystem

`UnderwaterRobotSystem` 是当前水下机器人项目的系统级集成与文档镜像仓。

它的职责不是承载所有一线开发，而是提供：

- 系统级架构说明、runbook、测试计划和升级记录
- 控制/导航之间共用的 `shared` 消息与 SHM 契约
- 离线分析与质量评估辅助内容
- 对独立代码仓的镜像快照，方便统一查阅

如果你是技术开发者或代码学习者，这个仓库应该被当作“总目录”和“系统上下文入口”，而不是唯一真源。

## 1. 代码真源在哪里

当前主线代码分布在几个独立仓库中：

- 控制与执行链：`OrangePi_STM32_for_ROV`
- 在线导航链：`Underwater-robot-navigation`
- GCS/UI：`UnderWaterRobotGCS`（当前是同工作区下的独立仓库，不在本镜像仓内部）

本仓内也带有 `OrangePi_STM32_for_ROV/` 和 `Underwater-robot-navigation/` 目录，但更适合做统一查阅、系统联调和文档交叉引用，不建议把这里当作子仓库历史的唯一来源。

## 2. 当前系统主线

当前已经验证的系统主线可以概括为两条。

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

## 3. 这个仓库里最值得先看的目录

- `docs/architecture/`
  - 系统级架构说明、模块关系、契约边界
- `docs/runbook/`
  - 实际联调、日志导出、replay、USB 台架等操作说明
- `docs/test/`
  - 模块测试计划、验证记录、回归约束
- `docs/productization/`
  - 迭代进度、升级阶段、风险与下一步计划
- `shared/msg/` 和 `shared/shm/`
  - 控制/导航/GCS 共享的数据结构与内存布局约定
- `offline_nav/`
  - 离线导航分析与批处理工具，偏研究与复盘用途

## 4. 推荐阅读顺序

如果你是第一次进入项目，建议按下面顺序阅读。

1. 本 README
2. [OrangePi_STM32_for_ROV/README.md](/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/README.md)
3. [Underwater-robot-navigation/README.md](/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/README.md)
4. [UnderWaterRobotGCS/README.md](/home/wys/orangepi/UnderWaterRobotGCS/README.md)
5. `docs/runbook/` 下与你当前任务最相关的说明

如果你要跟代码：

1. 先理解系统链路和 shared 契约
2. 再进入控制仓或导航仓的子模块 README
3. 最后再看具体源文件和测试

## 5. 当前已经工程化的能力

截至当前阶段，系统已经形成了几项明确可用能力：

- 控制侧状态/契约、时间语义和 telemetry 权威态已经收口
- 导航侧时间链路、设备绑定与 stale 传播已经具备最小闭环
- incident bundle、最小 replay 注入和 replay compare 已经能用于事故窗口验证
- 真实主机负路径样本已经进入复盘闭环

## 6. 当前仍然不是这个仓库要做的事

请不要把这个仓库理解成下面这些东西：

- 不是已经修好的顶层统一构建系统
- 不是所有代码提交都只需要改一个仓
- 不是 GUI 产品仓
- 不是实时控制或实时导航的唯一代码入口

## 7. 对代码学习者的建议

这个项目跨了 C、C++、Python、UDP、SHM、日志工具和运行文档，直接从单个 `.cpp` 文件开始看会很痛苦。更好的路径是：

1. 先看 README 和 runbook，知道“程序实际怎么跑”
2. 再看 shared 契约，知道“模块之间交换什么”
3. 再看控制和导航各自的主循环入口
4. 最后再看工具脚本和测试

如果你按这个顺序看，代码会更像一个系统，而不是一堆分散文件。
