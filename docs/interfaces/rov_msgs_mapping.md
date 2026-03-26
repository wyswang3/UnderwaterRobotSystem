# rov_msgs Mapping

## 适用范围

本文档定义 ROS2 外围桥接当前阶段 `rov_msgs` 的字段映射基线。

语义真源始终是：

- `shared/msg/telemetry_frame_v2.hpp`
- `shared/msg/nav_state_view.hpp`
- `shared/msg/nav_state.hpp`
- `docs/interfaces/time_contract.md`
- `docs/interfaces/nav_state_contract.md`
- `docs/interfaces/nav_view_contract.md`
- `docs/interfaces/control_intent_contract.md`

## 1. 当前消息清单

| `rov_msgs` 消息 | 来源 | 说明 | 是否只读 |
| --- | --- | --- | --- |
| `TelemetryFrameV2` | `shared::msg::TelemetryFrameV2` | 控制权威运行态全量镜像 | 是 |
| `ControlIntentState` | `TelemetryFrameV2.intent` | 控制入口观测态 | 是 |
| `MotorTestState` | `TelemetryFrameV2.intent.motor_test` | 电机测试观测态 | 是 |
| `ControlState` | `TelemetryFrameV2.control` | 控制运行态 | 是 |
| `SystemState` | `TelemetryFrameV2.system` | 系统 / 健康 / nav 摘要 | 是 |
| `CommandResult` | `TelemetryFrameV2.last_command_result` | 最近命令结果 | 是 |
| `EventRecord` | `TelemetryFrameV2.last_event` / `events[]` | 事件和 fault 记录 | 是 |
| `NavStateView` | `shared::msg::NavStateView` | 控制消费视角导航状态 | 是 |
| `NavState` | `shared::msg::NavState` | 导航 raw/debug 状态 | 是 |
| `HealthSummary` | `TelemetryFrameV2.system` + `TelemetryFrameV2.seq/stamp_ns` | 紧凑健康摘要 | 是 |
| `HealthMonitorStatus` | `TelemetryFrameV2` + `NavStateView` | 外围 advisory health / recovery 摘要 | 是 |

说明：

- `HealthMonitorStatus` 是外围 health monitor 节点的派生输出，不是新的 authority 契约。
- 它只能给 UI backend / diagnostics / runbook 指引使用，不能回灌核心链。

## 2. TelemetryFrameV2 mirror

### 顶层字段

| `rov_msgs/TelemetryFrameV2` | shared 来源 | 说明 |
| --- | --- | --- |
| `version` | `TelemetryFrameV2.version` | 原样镜像 |
| `payload_size` | `TelemetryFrameV2.payload_size` | 原样镜像 |
| `seq` | `TelemetryFrameV2.seq` | 原样镜像 |
| `stamp_ns` | `TelemetryFrameV2.stamp_ns` | 保持 monotonic / steady 语义 |
| `valid` | `TelemetryFrameV2.valid` | 原样镜像 |
| `source` | `TelemetryFrameV2.source` | 原样镜像 |
| `attitude_rpy` | `TelemetryFrameV2.attitude_rpy` | 原样镜像 |
| `position` | `TelemetryFrameV2.position` | 原样镜像 |
| `velocity` | `TelemetryFrameV2.velocity` | 原样镜像 |
| `depth_m` | `TelemetryFrameV2.depth_m` | 原样镜像 |
| `event_count` | `TelemetryFrameV2.event_count` | 原样镜像 |
| `event_head` | `TelemetryFrameV2.event_head` | 原样镜像 |
| `events` | `TelemetryFrameV2.events[]` | 原样镜像为 `EventRecord[]` |
| `last_event` | `TelemetryFrameV2.last_event` | 原样镜像为 `EventRecord` |
| `last_command_result` | `TelemetryFrameV2.last_command_result` | 原样镜像为 `CommandResult` |

### intent 子结构

`TelemetryFrameV2.intent.*` -> `rov_msgs/ControlIntentState.*`

关键字段：

- `intent_id`
- `session_id`
- `cmd_seq`
- `stamp_ns`
- `ttl_ms`
- `source`
- `requested_mode`
- `arm_cmd`
- `estop_cmd`
- `valid`
- `dof_cmd[6]`
- `motor_test.*`

说明：

- 这是观测镜像，不是新的 ROS2 控制输入通道。
- `motor_test` 也只是镜像当前权威 telemetry 中已存在的状态。

### control 子结构

`TelemetryFrameV2.control.*` -> `rov_msgs/ControlState.*`

关键字段：

- `active_mode`
- `armed`
- `estop_latched`
- `failsafe_active`
- `control_source`
- `intent_fresh`
- `controller_status`
- `motor_test_active`
- `active_intent_id`
- `controller_name`
- `desired_controller`
- `dof_cmd_applied[6]`
- `thruster_cmd[8]`
- `pwm_duty[8]`
- `consecutive_failures`
- `auto_fail_limit`

### system 子结构

`TelemetryFrameV2.system.*` -> `rov_msgs/SystemState.*`

关键字段：

- `session_state`
- `nav_state`
- `stm32_link_state`
- `pwm_link_state`
- `health_state`
- `degraded`
- `fault_state`
- `last_fault_code`
- `nav_fault_code`
- `nav_status_flags`
- `heartbeat_age_ms`
- `nav_age_ms`
- `nav_valid`
- `nav_health`
- `nav_stale`
- `nav_degraded`
- `session_id`
- `stm32_last_rtt_ms`
- `pwm_tx_frames`
- `stm32_hb_tx`
- `stm32_hb_ack`

## 3. CommandResult / EventRecord mirror

### `rov_msgs/CommandResult`

| 字段 | shared 来源 | 说明 |
| --- | --- | --- |
| `intent_id` | `last_command_result.intent_id` | 原样镜像 |
| `cmd_seq` | `last_command_result.cmd_seq` | 原样镜像 |
| `stamp_ns` | `last_command_result.stamp_ns` | 原样镜像 |
| `event_code` | `last_command_result.event_code` | 原样镜像 |
| `fault_code` | `last_command_result.fault_code` | 原样镜像 |
| `status` | `last_command_result.status` | 保留命令结果语义 |
| `source` | `last_command_result.source` | 原样镜像 |

### `rov_msgs/EventRecord`

| 字段 | shared 来源 | 说明 |
| --- | --- | --- |
| `seq` | `EventRecord.seq` | 原样镜像 |
| `stamp_ns` | `EventRecord.stamp_ns` | 原样镜像 |
| `event_code` | `EventRecord.event_code` | 原样镜像 |
| `fault_code` | `EventRecord.fault_code` | 原样镜像 |
| `arg0` | `EventRecord.arg0` | 原样镜像 |
| `arg1` | `EventRecord.arg1` | 原样镜像 |

## 4. NavStateView mirror

| `rov_msgs/NavStateView` | shared 来源 | 说明 |
| --- | --- | --- |
| `version` | `NavStateView.version` | 原样镜像 |
| `flags` | `NavStateView.flags` | 原样镜像 |
| `stamp_ns` | `NavStateView.stamp_ns` | 原样镜像，保持 monotonic / steady 语义 |
| `mono_ns` | `NavStateView.mono_ns` | 原样镜像 |
| `age_ms` | `NavStateView.age_ms` | 原样镜像，不归零 |
| `valid` | `NavStateView.valid` | 原样镜像 |
| `stale` | `NavStateView.stale` | 原样镜像 |
| `degraded` | `NavStateView.degraded` | 原样镜像 |
| `nav_state` | `NavStateView.nav_state` | 原样镜像 |
| `health` | `NavStateView.health` | 原样镜像 |
| `fault_code` | `NavStateView.fault_code` | 原样镜像 |
| `sensor_mask` | `NavStateView.sensor_mask` | 原样镜像 |
| `status_flags` | `NavStateView.status_flags` | 原样镜像 |
| `pos` | `NavStateView.pos[3]` | 原样镜像 |
| `vel` | `NavStateView.vel[3]` | 原样镜像 |
| `rpy` | `NavStateView.rpy[3]` | 原样镜像 |
| `depth_m` | `NavStateView.depth_m` | 原样镜像 |
| `omega_b` | `NavStateView.omega_b[3]` | 原样镜像 |
| `acc_b` | `NavStateView.acc_b[3]` | 原样镜像 |

说明：

- `NavStateView` 的 stale / no-data / degraded 语义来自现有 `nav_viewd`，bridge 不得改写。
- 这个 mirror 只能给外围 UI / diagnostics / rosbag 使用，不能写回控制输入。

## 5. NavState mirror

| `rov_msgs/NavState` | shared 来源 | 说明 |
| --- | --- | --- |
| `t_ns` | `NavState.t_ns` | 原样镜像，保持 monotonic / steady 语义 |
| `pos` | `NavState.pos[3]` | 原样镜像 |
| `vel` | `NavState.vel[3]` | 原样镜像 |
| `rpy` | `NavState.rpy[3]` | 原样镜像 |
| `depth` | `NavState.depth` | 原样镜像 |
| `omega_b` | `NavState.omega_b[3]` | 原样镜像 |
| `acc_b` | `NavState.acc_b[3]` | 原样镜像 |
| `age_ms` | `NavState.age_ms` | 原样镜像，不归零 |
| `valid` | `NavState.valid` | 原样镜像 |
| `stale` | `NavState.stale` | 原样镜像 |
| `degraded` | `NavState.degraded` | 原样镜像 |
| `nav_state` | `NavState.nav_state` | 原样镜像 |
| `health` | `NavState.health` | 原样镜像 |
| `fault_code` | `NavState.fault_code` | 原样镜像 |
| `sensor_mask` | `NavState.sensor_mask` | 原样镜像 |
| `status_flags` | `NavState.status_flags` | 原样镜像 |

## 6. HealthSummary mirror

`HealthSummary` 不是新的权威契约，而是从 `TelemetryFrameV2` 提炼的只读紧凑镜像：

| `rov_msgs/HealthSummary` | 来源 | 说明 |
| --- | --- | --- |
| `stamp_ns` | `TelemetryFrameV2.stamp_ns` | 保持原始时间语义 |
| `telemetry_seq` | `TelemetryFrameV2.seq` | 追踪对应 telemetry 帧 |
| `session_state` | `TelemetryFrameV2.system.session_state` | 原样镜像 |
| `health_state` | `TelemetryFrameV2.system.health_state` | 原样镜像 |
| `fault_state` | `TelemetryFrameV2.system.fault_state` | 原样镜像 |
| `last_fault_code` | `TelemetryFrameV2.system.last_fault_code` | 原样镜像 |
| `nav_state` | `TelemetryFrameV2.system.nav_state` | 原样镜像 |
| `nav_valid` | `TelemetryFrameV2.system.nav_valid` | 原样镜像 |
| `nav_stale` | `TelemetryFrameV2.system.nav_stale` | 原样镜像 |
| `nav_degraded` | `TelemetryFrameV2.system.nav_degraded` | 原样镜像 |
| `nav_fault_code` | `TelemetryFrameV2.system.nav_fault_code` | 原样镜像 |
| `nav_status_flags` | `TelemetryFrameV2.system.nav_status_flags` | 原样镜像 |
| `nav_age_ms` | `TelemetryFrameV2.system.nav_age_ms` | 原样镜像 |
| `heartbeat_age_ms` | `TelemetryFrameV2.system.heartbeat_age_ms` | 原样镜像 |

## 7. HealthMonitorStatus mirror

`HealthMonitorStatus` 是外围 advisory 节点的派生输出。

来源：

- `TelemetryFrameV2`
- 可选 `NavStateView`

关键字段：

- `stamp_ns`
- `telemetry_seq`
- `severity`
- `session_state`
- `health_state`
- `fault_state`
- `last_fault_code`
- `command_status`
- `command_fault_code`
- `nav_fault_code`
- `nav_status_flags`
- `nav_age_ms`
- `heartbeat_age_ms`
- `nav_valid`
- `nav_stale`
- `nav_degraded`
- `estop_latched`
- `failsafe_active`
- `imu_online / dvl_online`
- `imu_reconnecting / dvl_reconnecting`
- `imu_mismatch / dvl_mismatch`
- `summary`
- `recommended_action`

说明：

- 它只做外围告警摘要和建议动作，不改变核心 stale / fault / safety 语义。
- `summary` / `recommended_action` 是派生解释层，不是新的 authority field。

## 8. 时间语义保留规则

以下规则是强约束：

1. `stamp_ns`、`mono_ns`、`t_ns` 保持 `uint64` monotonic / steady 语义。
2. 不把这些字段静默映射成 wall time authority。
3. `age_ms` 直接镜像现有权威值，不在 bridge 中重新计算 topic latency。
4. `fault_code`、`status_flags`、`nav_valid`、`nav_stale`、`nav_degraded`、`command_result.status` 必须逐字段保留。

## 9. 只读边界

所有 `rov_msgs` 都是只读镜像，不能反向驱动核心链。

当前明确禁止：

- 用 `rov_msgs/ControlIntentState` 替代 `ControlIntent` authority 输入
- 用 `rov_msgs/NavStateView` 写回控制链
- 用 `rov_msgs/NavState` 替代 `nav_viewd`
- 用 `HealthMonitorStatus` 做安全裁决或控制放行
- 根据 ROS2 topic 状态反向修改核心 stale / health / fault 语义
