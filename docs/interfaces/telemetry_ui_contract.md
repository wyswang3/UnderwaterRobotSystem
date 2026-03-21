# Telemetry UI Contract

## 适用范围

当前 UI/遥测契约的真实上游为：

- `shared/msg/telemetry_frame_v2.hpp`
- gateway `StatusTelemetry` 适配层
- `UnderWaterRobotGCS/src/urogcs/telemetry/ui_viewmodels.py`
- `UnderWaterRobotGCS/src/urogcs/app/tui/*`

默认共享内存名称：

- `/rovctrl_telemetry_v2`

当前 UI 真实基线：

- TUI 是当前成熟主路径
- GUI 入口文件存在，但 `src/urogcs/app/gui_main.py` 当前为空
- 因此当前 UI 契约应先以 TUI 为准，不要假定图形界面已经产品化

## 1. 总原则

UI 必须明确区分两类状态：

1. 本地操作员刚发送或刚请求的状态
2. 机器人侧权威运行时已经生效的状态

这两者不相等时，不得把本地请求误显示成远端已执行成功。

## 2. 远端权威字段

当前 UI 必须能拿到并正确解释的远端字段包括：

### 会话/链路

- `session_state`
- `session_id`
- `link_alive` 或等价链路活性
- `heartbeat_age_ms`

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

### 故障/健康

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
- 本地请求的 mode/estop/arm 意图

## 4. 当前推荐显示层次

TUI 当前至少应保持下面的阅读层次：

- `[ROV]`
  - 会话/链路/接收年龄
- `[OP ]`
  - 本地请求意图
- `[AUTH]`
  - 远端权威运行态
- `[NAV]`
  - 导航可信性和诊断摘要
- `[CMD]`
  - 本地发送、ACK、远端命令结果三层状态
- `[DOF]`
  - 最近一次本地 DOF 发送值
- `[LOG]`
  - 最近一条本地提示

## 5. 命令状态解释规则

命令状态必须分层展示：

1. `sent`
   - 本地已经发出
2. `acked`
   - 会话/传输已 ACK
3. `accepted/executed`
   - 远端控制栈已经接受/执行
4. `rejected/expired/failed`
   - 远端控制栈明确拒绝、过期或执行失败

硬规则：

- transport ACK 不等于运行时执行成功
- `ARM`、`ESTOP`、mode 切换成功，必须以远端权威状态或远端命令结果为准

## 6. 导航诊断解释规则

当前推荐从 `nav_fault_code + nav_status_flags` 派生操作员可读摘要：

- `reconnecting`
  - 对应 `IMU/DVL reconnecting` 位
- `mismatch`
  - 对应设备身份不匹配位
- `offline`
  - 对应 not-found/disconnected 类 fault，且不是 mismatch/reconnecting 更能解释的情况
- `stale`
  - `nav_stale=1`
- `invalid`
  - `nav_valid=0`
- `degraded`
  - `nav_valid=1 && nav_degraded=1`

当前 UI 的最小目标不是“漂亮”，而是“可快速判断为什么不能用”。

## 7. 权威边界

当前必须记住：

1. `TelemetryFrameV2` 是运行态语义真源。
2. gateway session 只对会话/链路字段权威。
3. UI 不能自行发明新的安全判断逻辑。
4. 若未来增加 GUI 或 ROS 2 consumer，也必须消费同一套权威字段，而不是重造一套演示态语义。

## 8. 兼容性说明

gateway 当前仍可能向 GCS 输出紧凑 `StatusTelemetry` 以保持兼容。

但兼容不是允许丢语义：

- `armed`
- `mode`
- `failsafe`
- `nav_valid/nav_state/nav_stale/nav_degraded`
- `fault/health`
- `command result`

这些关键权威字段不能在适配过程中被模糊掉。
