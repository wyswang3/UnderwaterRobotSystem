# Project Memory

## 适用范围

本文档是 `UnderwaterRobotSystem` 当前阶段的项目记忆基线，面向后续持续升级。

时间基线：

- 文档整理时间：2026-03-20
- 证据来源：
  - 当前工作区代码
  - 各仓库 README、runbook、接口头文件
  - 当前可见分支与提交历史
  - 2026-03 中旬阶段性文档与测试产物

## 1. 当前多仓基线

截至 2026-03-20，当前工作区主分支状态为：

| 仓库 | 当前分支 | 当前 HEAD | 角色 |
| --- | --- | --- | --- |
| `Underwater-robot-navigation` | `feature/nav-p0-contract-baseline` | `2329255` | 导航运行时、设备绑定、日志/replay 工具 |
| `OrangePi_STM32_for_ROV` | `feature/control-p0-status-telemetry-baseline` | `c23d83d` | gateway、控制主循环、PWM/STM32 执行链 |
| `UnderWaterRobotGCS` | `feature/gcs-p0-status-telemetry-alignment` | `3e2cb04` | 上位机、协议客户端、TUI/诊断 |
| `UnderwaterRobotSystem` | `feature/docs-p0-baseline-alignment` | `054ea73` | 系统级文档、镜像、兼容性基线 |

重要说明：

- 运行时共享契约真实源在 `/home/wys/orangepi/UnderwaterRobotSystem/shared`
- 集成仓内的 `shared/` 是镜像，不是运行时唯一真源

## 2. 从最初到当前的升级历史

### 阶段一：原型搭建与主链路打通

时间范围：

- 2025-11-27 至 2025-12 下旬

阶段特征：

- 先把传感器、导航、控制、执行、GCS 几条链跑通
- 重点是“能联起来”，不是“状态语义可信”

代表变化：

- 系统级集成仓初始化
- 控制核心开始拆出 `ControllerManager`、`ThrusterAllocator`
- 导航开始发布共享状态到控制侧
- GCS 初始协议、会话、遥测框架建立

阶段问题：

- 硬件/控制耦合偏重
- 共享契约不稳定
- 时间语义和 stale 语义不统一
- GCS 状态更偏演示态而不是权威运行态

### 阶段二：配置化、时间基收口与平台适配

时间范围：

- 2026-01-06 至 2026-01-23

阶段特征：

- 从硬编码行为逐步转向配置驱动
- 从单点采集/离线分析过渡到在线导航守护进程

代表变化：

- 控制映射和分配矩阵配置化
- Orange Pi ARM 适配
- timebase 统一
- `nav_core` 在线守护进程、DVL 实时预处理和 ESKF 主线落地

阶段收益：

- 后续 P0/P1 契约收口有了前提
- 控制/导航不再完全依赖硬编码路径和时间解释

### 阶段三：P0/P1 可信性基线与故障传播闭环

时间范围：

- 2026-03-12 至 2026-03-14

阶段特征：

- 从“数值能跑”切换到“状态语义可信”
- 以共享契约为主线逐层收口：
  - 共享结构
  - 导航发布
  - gateway 视图
  - 控制保护
  - 遥测/UI
  - 日志与 replay

关键变化：

- `NavState` / `NavStateView` 引入显式 `valid/stale/degraded/fault_code`
- `nav_viewd` stale/no-data 时不再把旧运动学 payload 继续喂给控制
- `ControlGuard` 不再只看一个模糊布尔值，而是显式看导航状态语义
- `TelemetryFrameV2` 成为控制运行时权威状态源
- GCS/TUI 开始区分本地操作意图和远端权威状态
- 设备绑定状态机、重连、时间诊断、incident bundle、最小 replay、compare 链落地

### 阶段四：P1.3 收口与 P2 控制框架起步

时间范围：

- 2026-03-14 至当前

阶段特征：

- P1 继续补实机负路径、replay compare 和工具链
- 控制侧进入 PID hold-controller 框架阶段

关键变化：

- 真实主机无设备负路径样本采集
- `merge_robot_timeline.py`、`replay_compare.py` 完成最小闭环
- `uwnav_nav_replay` 支持 incident bundle 注入
- PID 控制器族和 telemetry 统一组装逻辑落地

当前边界：

- 当前 Auto 更接近 hold controller
- 还不能宣称已经完成 trajectory tracking / 任务调度

## 3. 已完成的 P0/P1 工作

### 已完成的 P0 工作

- 导航共享契约和状态语义收口
- `omega_b/acc_b` 语义改正为真实 IMU 测量，不再输出伪正常 bias 数值
- `NavState -> NavStateView -> ControlGuard` 语义打通
- 控制侧去掉本地 demo override，安全裁决统一由 `ControlGuard` 收口
- `TelemetryFrameV2` 成为权威运行时状态源
- GCS/TUI 使用权威运行态，不再依赖 gateway 猜测值

### 已完成的 P1 工作

- IMU/DVL 设备绑定状态机
- 错设备、断连、重连、mismatch/reconnecting 状态传播
- `nav_timing.bin`、`nav_state.bin`
- control CSV、telemetry timeline/event CSV
- incident bundle 导出
- 最小 `NavState` replay 注入
- `replay_compare.py` 关键状态签名对照
- GCS/TUI 对导航诊断字段的最小展示

### 当前仍在进行中的 P1 工作

- 真实 IMU/DVL 热插拔与重枚举样本
- 更完整的 replay 节奏/时序一致性
- `shared/` 单一真源治理
- 顶层聚合构建与产物清理治理

## 4. 当前已知问题与风险

当前最重要的风险仍然是：

1. 真实硬件 USB 重枚举验证不完整。
2. replay compare 目前还是关键状态签名级，不是完整时序级。
3. 无设备负路径样本中 `NavState::t_ns == 0`，极端场景时间语义还不够理想。
4. 根级 `shared/` 与镜像副本并存，长期会带来 ABI 漂移风险。
5. 顶层聚合构建还不是可信入口。
6. 控制框架虽然开始进入 PID 阶段，但 trajectory/reference 语义尚未收口。

## 5. 当前项目主链路

### 上位机指令主链路

`GCS TUI -> session_client -> UDP -> gcs_server -> /rovctrl_gcs_intent_v1 -> pwm_control_program -> PwmClient -> orangepi_send -> STM32`

说明：

- 当前更可信的操作路径是远程 GCS
- 本地 `teleop_local` / `intentd` 路径仍在代码里，但主要是 bench/实验用途

### 导航主链路

`IMU + DVL -> nav_core/uwnav_navd -> /rov_nav_state_v1 + nav_timing.bin + nav_state.bin -> nav_viewd -> /rovctrl_nav_view_v1 -> pwm_control_program`

### 遥测/状态反馈主链路

`pwm_control_program -> /rovctrl_telemetry_v2 -> gcs_server status adapter -> UDP -> GCS/TUI`

### 日志与复盘主链路

`nav_timing.bin + nav_state.bin + control CSV + telemetry CSV -> merge_robot_timeline.py -> incident bundle -> uwnav_nav_replay -> replay_compare.py`

## 6. 当前客户/操作员反馈问题

以下内容基于当前交付形态、现有代码和操作说明推断，不是独立客服系统导出的工单表：

1. UI 仍以 TUI 为主，阅读门槛较高。
   - 操作员需要理解 `[OP] / [AUTH] / [NAV] / [CMD]` 等文本语义。
2. GUI 尚未产品化。
   - `UnderWaterRobotGCS/src/urogcs/app/gui_main.py` 当前为空文件。
3. 现场工作流仍偏开发者导向。
   - 常见路径仍是 `SSH + 多进程启动 + 终端/TUI`。
4. 诊断信息已经比早期强很多，但仍然以 fault code 和文本摘要为主。
   - 对非开发者仍不够直观。
5. 界面美观性和跨平台操作体验不是当前主优先级。
   - 虽然有 `scripts/*.ps1`，但当前成熟主路径仍是终端式使用方式。

## 7. 当前为什么这样设计

当前架构不是“没来得及统一”，而是有明确工程原因：

1. 控制、导航、状态传播、执行链必须优先保证本地安全和可预测性。
   - 所以核心主线放在 C/C++ 本地进程和 SHM 上。
2. 最终安全裁决必须留在机器人侧。
   - `ControlGuard`、PWM 安全层、STM32 传输不依赖远端 UI 或 ROS 2。
3. 多仓拆分是为了把控制、导航、GCS 和共享契约边界拆清楚。
   - 代价是协作和版本收口更难，但系统边界更清晰。
4. 日志/replay/incident bundle 被做成一等公民，是因为真实池测/台架问题难以复现。
5. ROS 2 被限制在外围，是因为当前核心问题不是“消息总线不够多”，而是“主链可信性和安全闭环必须先稳”。

## 8. 当前文档与代码一致性说明

这轮审查发现几个需要明确记录的点：

1. 运行时共享契约真实源在根级 `shared/`，不是集成仓镜像。
2. 旧版 `docs/system_overview.md` 仍带有较强的规划口径。
   - 例如 `control_algorithms/` 作为未来层的表述不能直接当成当前主线事实。
3. 旧版 `docs/architecture/project_upgrade_master_plan.md` 记录的是早期 P0/P1 快照。
   - 后续升级应以新的 `upgrade_strategy.md` 为准。
4. `UnderWaterRobotGCS/docs/operator_guide.md` 更适合作为历史上手说明。
   - 当前跨仓一致的操作解释以系统级 `gcs_ui_operator_guide.md` 为准。

## 9. 后续升级时必须记住的判断

如果后续任务需要在方案之间做取舍，优先级顺序应当是：

1. 保住控制/导航/状态传播主链的 C/C++ 可信性
2. 保住 shared 契约和时间语义的一致性
3. 补全实机重连、日志和 replay 闭环
4. 提升操作员诊断体验
5. 最后才是更复杂的 Auto/trajectory/UI/bridge 扩展
