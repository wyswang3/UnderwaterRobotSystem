# Telemetry UI Contract

## 适用范围

当前 UI / 外围消费契约的真实上游为：

- `shared/msg/telemetry_frame_v2.hpp`
- `shared/msg/nav_state_view.hpp`
- `shared/msg/nav_state.hpp`
- gateway `StatusTelemetry` 适配层
- `UnderWaterRobotGCS/src/urogcs/telemetry/ui_viewmodels.py`
- `UnderWaterRobotGCS/src/urogcs/app/tui/*`
- `UnderWaterRobotGCS/src/urogcs/app/gui/*`
- `OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge/*`
- `OrangePi_STM32_for_ROV/ros2_bridge/rov_msgs/msg/*`

默认共享内存名称：

- `/rovctrl_telemetry_v2`
- `/rovctrl_nav_view_v1`
- `/rov_nav_state_v1`

当前 UI / 外围消费真实基线：

- TUI 是成熟主路径
- PySide6 GUI 已有第一阶段首页骨架
- ROS2 bridge 已启动第一阶段，只提供只读 mirror topic
- 因此当前 UI 契约必须始终以权威状态字段为准，不以具体前端形态为准

## 1. 总原则

UI 和外围消费者必须明确区分两类状态：

1. 本地操作员刚发送或刚请求的状态
2. 机器人侧权威运行时已经生效的状态

这两者不相等时，不得把本地请求误显示成远端已执行成功。

## 2. 远端权威字段

当前 UI 和外围消费者必须能拿到并正确解释的远端字段包括：

### 会话 / 链路

- `session_state`
- `session_id`
- `heartbeat_age_ms`
- `link_alive` 或等价链路活性

### 控制运行态

- `active_mode`
- `armed`
- `estop_latched`
- `failsafe_active`
- `control_source`
- `controller_name`
- `desired_controller`

### 导航运行态

- `nav_valid`
- `nav_state`
- `nav_stale`
- `nav_degraded`
- `nav_fault_code`
- `nav_status_flags`
- `nav_age_ms`

### 故障 / 健康

- `fault_state`
- `health_state`
- `last_fault_code`

### 命令结果

- `last_command_result.status`
- `last_command_result.cmd_seq`
- `last_command_result.fault_code`
- `last_event`

## 3. 本地字段

当前 UI 仍需要单独保留本地状态：

- 最近一次发送的命令类型
- 最近一次发送的命令序号
- 是否还在等待 ACK
- 最近一次 ACK 结果
- 最近一次本地下发的 DOF 意图
- 本地请求的 mode / estop / arm 意图

## 4. 当前推荐显示层次

前端形态可以不同，但推荐阅读层次必须保持一致：

- 连接 / 会话
- 设备 / 导航可信性
- 控制运行态
- 命令 transport 与 runtime 分层状态
- 故障摘要与下一步建议
- 最近事件 / 日志 / 提示

TUI、GUI 和未来 ROS2 UI backend 都必须消费同一套权威字段，而不是各自重造状态语义。

## 5. 命令状态解释规则

命令状态必须分层展示：

1. `sent`
   - 本地已经发出
2. `acknowledged`
   - 会话 / 传输已 ACK
3. `accepted / executed`
   - 远端控制栈已经接受 / 执行
4. `rejected / expired / failed`
   - 远端控制栈明确拒绝、过期或执行失败

硬规则：

- transport ACK 不等于运行时执行成功
- `ARM`、`ESTOP`、mode 切换成功，必须以远端权威状态或远端命令结果为准

## 6. 导航诊断解释规则

当前推荐从 `nav_fault_code + nav_status_flags` 派生操作员可读摘要：

- `reconnecting`
  - 对应 IMU / DVL reconnecting 位
- `mismatch`
  - 对应设备身份不匹配位
- `offline`
  - 对应 not-found / disconnected 类 fault，且不是 mismatch / reconnecting 更能解释的情况
- `stale`
  - `nav_stale=1`
- `invalid`
  - `nav_valid=0`
- `degraded`
  - `nav_valid=1 && nav_degraded=1`

当前 UI 的最小目标不是“漂亮”，而是“可快速判断为什么不能用”。

## 7. ROS2 外围 mirror 约束

当前 ROS2 bridge 只允许提供只读 mirror topic：

- `/rov/telemetry`
  - `TelemetryFrameV2` mirror
- `/rov/health`
  - 从 `TelemetryFrameV2.system` 派生的紧凑 health summary
- `/rov/nav_view`
  - `NavStateView` mirror
- `/rov/nav_state_raw`
  - `NavState` debug/raw mirror

硬规则：

1. `stamp_ns` / `t_ns` 保持原始 monotonic / steady 语义，不改成 wall time authority。
2. `age_ms` 保持原始年龄语义，不在 bridge 中归零或重算为“topic 新鲜度”。
3. `fault_code` / `status_flags` / `command_result` 必须按原字段镜像。
4. bridge topic 只用于 UI backend / diagnostics / rosbag / tools，不允许回灌控制或导航主链。

## 8. 权威边界

当前必须记住：

1. `TelemetryFrameV2`、`NavStateView`、`NavState` 是运行态语义真源。
2. gateway session 只对会话 / 链路字段权威。
3. UI 和 ROS2 消费层不能自行发明新的安全判断逻辑。
4. GUI 或 ROS2 consumer 只能消费同一套权威字段，不能重造一套演示态语义。

## 9. 兼容性说明

gateway 当前仍可能向 GCS 输出紧凑 `StatusTelemetry` 以保持兼容。

但兼容不是允许丢语义：

- `armed`
- `mode`
- `failsafe`
- `nav_valid / nav_state / nav_stale / nav_degraded`
- `fault / health`
- `command result`

这些关键权威字段不能在适配过程中被模糊掉。
