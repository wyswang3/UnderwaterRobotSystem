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

当前改为扁平文档体系：

- 本仓只保留一个 `docs/` 根目录
- 系统级基线、交接、runbook、阶段评审都直接放在 `docs/` 下
- repo 内部技术细节优先回收到对应代码仓的 `docs/`

文档状态与阅读顺序以 `docs/documentation_index.md` 为准。

## 3. 推荐阅读顺序

如果你是第一次进入当前项目，推荐按以下顺序阅读：

1. 工作区根目录下的 `AGENTS.md`
2. `docs/CODEX_HANDOFF.md`
3. `docs/CODEX_NEXT_ACTIONS.md`
4. `docs/documentation_index.md`
5. `docs/project_memory.md`
6. `docs/upgrade_strategy.md`
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

## 5. 当前默认操作路径

当前面向操作员的默认主路径已经固定为：

```text
device-check -> device-scan -> startup-profiles -> preflight -> start -> status -> teleop -> stop -> bundle
```

当前默认 supervisor profile：

```text
control_only
```

这表示：

- 默认最小运行链只要求 `pwm_control_program + gcs_server`
- 导航增强链路不是默认启动硬依赖
- 当前先把“遥控 + 状态观察 + 日志导出”跑稳
- IMU / DVL 属于增强观察条件，不是默认起步硬条件

当前操作员界面的边界也已固定：

- `TUI` 是当前成熟 teleop 主路径
- `GUI` 是当前只读 status / motion observer
- `GUI` 当前已经能观察机器人状态，但还不是完整导航工作站

当前 GUI 对 `Motion Info` 只能按以下等级解释：

- `Control Only`
- `Attitude Feedback`
- `Relative Nav`

不要把它们误写成：

- 完整绝对定位
- 完整自动控制台
- GUI authority 已升级

## 6. 当前推荐的操作说明入口

如果你是现场操作员，优先看：

1. `docs/operator_manual.md`
2. `docs/gcs_ui_operator_guide.md`
3. `OrangePi_STM32_for_ROV/docs/pwm_teleop_user_manual.md`

其中：

- `docs/operator_manual.md`
  - 是当前版本化的车端 / 上位机最短操作手册
  - 适合快速抄命令和理解 OrangePi 侧与上位机侧分工
- `docs/gcs_ui_operator_guide.md`
  - 是系统级版本化 runbook
  - 更适合解释 GUI 六卡片和 capability wording
- `OrangePi_STM32_for_ROV/docs/pwm_teleop_user_manual.md`
  - 更偏手动控制和 PWM / 现场联调流程

如果当前部署在 OrangePi 上，并且项目统一使用 `~/venvs/py311` 虚拟环境，可在仓根直接执行：

```bash
source ./enter_py311.sh
```

该脚本会基于当前用户的 `HOME` 解析虚拟环境路径，不依赖固定的 `/home/<user>/...` 写法。

## 7. 当前导航主链的最新收口点

`Underwater-robot-navigation/nav_core` 最近已完成几项关键收口：

- IMU 串口识别从“硬编码路径优先”升级为“串口行为识别 + Modbus 主动探测”
- C++ IMU 串口初始化已对齐 Python raw `8N1`
- 修复 WIT Modbus RTU CRC 线序漂移（默认按标准 lo-hi 发送，并兼容历史 hi-lo 诊断）
- IMU 串口排障输出支持单帧十六进制 dump，便于快速确认“回了什么原始字节”
- `nav_daemon` 已继续拆成小模块，而不是把逻辑堆回主程序
- `NavHealthMonitor` 已接入正常导航主链，不再只在实验编译开关下存在
- 导航运行时现在能输出健康审查根因：
  - `transport_timing`
  - `sensor_input`
  - `estimator_consistency`
  - `estimator_numeric`

需要注意：

- 更细根因当前仍走 stderr / `nav_events.csv`
- 本轮没有扩 shared `NavState` ABI
- GUI 当前仍只消费既有权威状态语义，不直接显示这套审查器全部内部指标

## 8. 当前最重要的文档

当前权威基线优先看：

- `docs/documentation_index.md`
- `docs/project_memory.md`
- `docs/system_main_dataflow.md`
- `docs/upgrade_strategy.md`
- `docs/*.md` 中与你任务相关的契约
- `docs/*.md` 中与你任务相关的操作说明

设计草案和阶段性计划：

- `docs/control_nav_integration_plan.md`
- `docs/sensor_toolchain_refactor_plan.md`
- `docs/logging_contract.md`

历史参考：

- `docs/archive_index.md`
- `docs/` 下的旧总览、旧测试、旧整改记录

## 9. 当前不应把这个仓库理解成什么

请不要把这个仓库理解成：

- 顶层统一构建系统
- 所有运行时代码的唯一入口
- GUI 产品仓
- 实时控制或实时导航的唯一实现仓

它的正确定位是：

- 系统级文档与交接入口
- 跨仓边界与契约说明仓
- 历史材料与当前基线的整理仓
