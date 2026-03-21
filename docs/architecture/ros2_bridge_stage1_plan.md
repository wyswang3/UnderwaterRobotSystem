# ROS2 Bridge Stage1 Plan

## 适用范围

本文档定义 UnderwaterRobotSystem 的 ROS2 外围桥接第一阶段基线。

目标不是把系统整体 ROS2 化，而是：

1. 冻结第一批 mirror 消息
2. 建立只读 bridge
3. 为后续 UI backend、health monitor、rosbag2 和 diagnostics 提供统一外部数据总线

## 1. Stage1 边界

本阶段明确允许：

- `shared/msg/*` 到 `rov_msgs` 的语义镜像
- 从现有 SHM 权威状态做只读 bridge
- 供 UI backend / diagnostics / logging / tools 消费的外围 topic
- Python 实现的验证工具和 bridge glue code

本阶段明确不做：

- 用 ROS2 替换 `nav_core`、`nav_viewd`、`ControlLoop`、`ControlGuard`
- 用 ROS2 替换 `gcs_server` 或 `ControlIntent` 权威入口
- 任何 ROS2 写回控制或导航主链的能力
- 在 bridge 中重算 stale、age、fault 或 command 语义
- 让核心主链依赖 ROS graph 存活

## 2. 第一批 mirror 消息

| 消息 | 语义真源 | 说明 |
| --- | --- | --- |
| `TelemetryFrameV2` | `shared/msg/telemetry_frame_v2.hpp` | 控制权威运行态镜像 |
| `NavStateView` | `shared/msg/nav_state_view.hpp` | 控制消费视角的导航状态镜像 |
| `NavState` | `shared/msg/nav_state.hpp` | 导航 raw/debug 状态镜像 |
| `HealthSummary` | `TelemetryFrameV2.system` | 紧凑 health 派生镜像 |
| `CommandResult` | `TelemetryFrameV2.last_command_result` | 命令结果子结构镜像 |
| `EventRecord` | `TelemetryFrameV2.last_event` / `events[]` | 事件与 fault 子结构镜像 |
| `ControlIntentState` | `TelemetryFrameV2.intent` | 控制入口状态的只读观测镜像 |
| `MotorTestState` | `TelemetryFrameV2.intent.motor_test` | 电机测试子结构镜像 |
| `ControlState` | `TelemetryFrameV2.control` | 控制运行态子结构镜像 |
| `SystemState` | `TelemetryFrameV2.system` | 系统健康 / session / nav 摘要子结构镜像 |

说明：

- `Fault/Event mirror` 在 stage1 中通过 `EventRecord` 嵌套在 `TelemetryFrameV2` 内提供。
- `HealthSummary` 是为了给 ROS2 外围层提供轻量消费入口，不是新的 authority source。

## 3. Stage1 topic 与数据源

| Topic | Source | 默认来源 | 用途 |
| --- | --- | --- | --- |
| `/rov/telemetry` | `TelemetryFrameV2` | `/rovctrl_telemetry_v2` | UI backend / diagnostics / rosbag 输入 |
| `/rov/health` | `HealthSummary` | `TelemetryFrameV2.system` 派生 | 健康摘要和告警聚合 |
| `/rov/nav_view` | `NavStateView` | `/rovctrl_nav_view_v1` | 控制视角导航消费镜像 |
| `/rov/nav_state_raw` | `NavState` | `/rov_nav_state_v1` | 调试、录包、对照分析 |

## 4. 只读 bridge 结构

当前实现按职责拆为：

1. `layouts.py`
   - `ctypes` 镜像当前 shared ABI 和 SHM layout
2. `shm_reader.py`
   - 只读打开 `/dev/shm` 或 file-backed source
   - 使用既有 producer 的 seqlock / seq 规则取稳定快照
3. `mapping.py`
   - 把 authority snapshot 映射成 bridge-side dataclass mirror
   - 不重算 stale / age / fault / command 语义
4. `publisher_backend.py`
   - `recording` / `stdout` / `ros2` backend
5. `bridge.py`
   - 聚合 reader + mapping + publisher
6. `tools/run_sample_bridge_validation.py`
   - 在无 ROS2 环境下做 deterministic dry-run

## 5. 时间与状态语义约束

本阶段必须保留以下语义：

- `TelemetryFrameV2.stamp_ns`
- `NavStateView.stamp_ns`
- `NavStateView.mono_ns`
- `NavState.t_ns`
- `NavStateView.age_ms`
- `NavState.age_ms`
- `TelemetryFrameV2.system.nav_age_ms`
- `fault_code`
- `status_flags`
- `nav_valid / nav_stale / nav_degraded`
- `last_command_result`

硬规则：

1. 时间字段保持 `uint64` monotonic / steady 语义。
2. 不把这些字段改写为 ROS wall time 或 `Header.stamp` authority。
3. 不在 bridge 中根据 topic 收到时刻重新推导新鲜度。
4. `HealthSummary` 仅做字段压缩，不做新安全结论。

## 6. Stage1 验收结果

当前 stage1 已做到：

- 第一批 `.msg` 文件冻结
- 只读 SHM reader 与 mirror mapping 实现完成
- bridge 可输出 `/rov/telemetry`、`/rov/health`、`/rov/nav_view`、`/rov/nav_state_raw`
- 单测覆盖映射、reader、失败隔离和 ABI 尺寸一致性
- 提供一个不依赖 ROS2 runtime 的 dry-run 验证脚本

当前 stage1 还没有做到：

- colcon build / generated Python msg 包验证
- 真实 ROS2 graph 下的发布订阅回环
- rosbag2 录包验证
- 独立的 `/rov/events` topic 或 health monitor node

## 7. 后续阶段建议

### Stage2

- 在 ROS2 主机上补 package 化和真实发布验证
- 加入 health monitor / diagnostics aggregator
- 为 GUI backend 提供更稳定的消费入口

### Stage3

- 引入 rosbag2 录包与 replay 对照
- 视需要增加 bench / diagnostics service 或 action
- 仍保持只读 mirror 为主，不让 ROS2 接管 authority
