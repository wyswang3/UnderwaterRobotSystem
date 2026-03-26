# Logging Contract

## 文档状态

- 状态：Working draft
- 说明：当前设计方向和字段分层已冻结，但尚未全部实施。

## 1. 目标与范围

本文档定义当前阶段最小统一日志规范，用于支撑以下目标：

1. 控制、导航、通信、supervisor 和三传感器工具链的日志可对齐。
2. incident bundle 可以通过稳定文件名和 manifest 自动定位关键日志。
3. 不改写现有 authority 主链的高频二进制 / 高频 CSV 策略。
4. 为后续 supervisor、bundle、replay、operator diagnostics 提供统一入口。

本文档适用于：

- `uwnav_navd`
- `nav_viewd`
- `pwm_control_program`
- `gcs_server`
- supervisor / launcher
- IMU / DVL / Volt32 采集工具链
- incident bundle / replay / compare 工具

本文档不要求：

- 把全部日志一次性改成同一种实现
- 把全部高频数据从二进制改成 CSV/JSON
- 让 UI 或 ROS2 成为新的日志 authority
- 为了日志统一改写 control/nav authority 逻辑

## 2. 日志分层

当前日志应固定为四层，而不是继续把 stderr、manifest、快照和 replay 输入混成一类。

### 2.1 启动 / 运维日志

用于记录：

- 进程启动、停止、退出码
- PID、CLI、配置摘要
- 设备绑定结果、日志目录、child log 路径
- `run_manifest.json`
- `process_status.json`
- `last_fault_summary.txt`

特点：

- 低频
- 面向运维与故障入口定位
- 允许使用 JSON / TXT

### 2.2 事件日志

用于记录：

- 状态切换
- 故障进入 / 恢复
- 命令接收 / 拒绝 / 失败
- 会话建立 / 丢失
- publish 抑制 / 失败
- 设备重连 / mismatch / online

特点：

- 低频
- 强调稳定 schema 和跨模块字段对齐
- 是 incident bundle 的首选摘要源

### 2.3 状态快照日志

用于记录：

- 当前 nav / control / comm 的关键状态摘要
- mode / armed / estop / controller
- nav_valid / nav_stale / nav_degraded / nav_fault_code
- session 状态与最后命令结果

特点：

- 低频或中低频
- 面向“当时系统整体状态是什么”
- 不替代事件日志，也不替代高频 replay 输入

### 2.4 高频数据日志

用于记录高频状态、采样或时序，允许保留现有二进制或高频 CSV 形式。

典型内容：

- `nav.bin`
- `nav_timing.bin`
- `nav_state.bin`
- `control_loop_*.csv`
- `telemetry_timeline_*.csv`
- 传感器 raw / parsed CSV

特点：

- 强调写入效率
- 主要服务 replay、对齐、建模和离线分析
- 不应承担现场第一眼故障摘要职责

## 3. 公共字段规范

### 3.1 核心公共字段

所有事件日志应尽量包含以下核心字段：

| 字段 | 含义 | 是否必需 |
| --- | --- | --- |
| `mono_ns` | 本地单调时钟时间戳 | 必需 |
| `wall_time` | 人类可读时间 | 推荐 |
| `component` | 逻辑组件名 | 必需 |
| `event` | 稳定事件枚举 | 必需 |
| `level` | `info/warn/error` | 必需 |
| `run_id` | 本次运行标识 | 必需 |
| `message` | 人类可读摘要 | 必需 |

说明：

- `mono_ns` 是统一对齐主时间，不得省略。
- `wall_time` 只用于人读，不作为排序依据。
- `component` 应稳定，例如 `uwnav_navd`、`nav_viewd`、`control_guard`、`gcs_session`、`supervisor`、`imu_capture`。

### 3.2 关联字段

以下字段建议“有就写”，但不强制每一类日志都带：

| 字段 | 含义 | 适用建议 |
| --- | --- | --- |
| `process_name` | 进程名 | 启动/运维必需，事件日志强烈建议 |
| `pid` | 进程 PID | 启动/运维必需，事件日志推荐 |
| `fault_code` | 规范化故障码 | fault/reject/recovery 事件建议必写 |
| `session_id` | 会话号 | comm/control 命令链推荐 |
| `mode` | 当前或目标模式 | control / nav_view / command 事件推荐 |
| `controller` | 当前控制器 | control 事件与快照推荐 |

### 3.3 域扩展字段

以下字段按域使用，不建议强制全域统一为空列：

| 字段 | 适用范围 | 建议 |
| --- | --- | --- |
| `status_flags` | 单域事件文件 | 可用，但要保证语义单一 |
| `nav_valid` | nav/control 事件与快照 | 推荐 |
| `nav_stale` | nav/control 事件与快照 | 推荐 |
| `nav_degraded` | nav/control 事件与快照 | 推荐 |
| `command_id` | command lifecycle | 推荐，但需先冻结语义 |
| `cmd_seq` | control intent / command result | 推荐 |

### 3.4 `status_flags` 约束

1. 若一个文件只记录 nav 事件，可使用 `status_flags`。
2. 若文件可能被 bundle 或 merge 工具跨域消费，优先使用 `nav_status_flags` 之类的带前缀字段。
3. 不允许让操作员猜这次的 `status_flags` 到底来自 nav 还是 control。

### 3.5 `command_id / cmd_seq` 约束

当前至少存在两种不同语义的编号：

1. transport / protocol 层 packet seq
2. control intent 层 `cmd_seq`

因此不建议把它们都塞进一个 `cmd_seq` 字段。

建议定义：

- `command_id`
  - 外部命令关联号
  - GCS 路径下优先承载 wire packet seq，或后续冻结后的 intent id
- `cmd_seq`
  - control intent / control result 的内部序号

若事件处在 GCS 命令路径上，建议同时记录：

- `session_id`
- `command_id`
- `cmd_seq`

## 4. 各域最小扩展字段

### 4.1 三传感器记录

三传感器 raw / parsed / event 记录建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `est_ns` | 估计或统一时间基 |
| `sensor_id` | 例如 `imu0` / `dvl0` / `volt0` |
| `record_kind` | `raw` / `parsed` / `event` |
| `sample_seq` | 样本序号 |
| `parse_ok` | 是否解析成功 |
| `drop_reason` | 若失败，记录原因 |
| `device_path` | 串口路径 |

### 4.2 导航事件

导航事件日志建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `nav_valid` | 当前导航是否有效 |
| `nav_stale` | 当前导航是否 stale |
| `nav_degraded` | 当前导航是否降级 |
| `nav_health` | 健康枚举 |

### 4.2.1 2026-03-25 已落地的 `nav_events.csv`

当前已落地两类导航事件 CSV：

1. `uwnav_navd` 的 `nav_events.csv`
   - 公共字段：`mono_ns`、`wall_time`、`component`、`event`、`level`、`run_id`、`process_name`、`pid`、`fault_code`、`message`
   - 导航字段：`nav_valid`、`nav_stale`、`nav_degraded`、`nav_status_flags`
   - 设备 / 观测字段：`device_label`、`device_path`、`state`、`reason`、`sensor_id`、`reason_class`、`sample_age_ms`
2. `nav_viewd` 的 `nav_events.csv`
   - 公共字段同上
   - 决策字段：`age_ms_from_nav_pub`、`publish`、`diagnostic_only`、`degraded_publish`、`no_nav_yet`、`stale_triggered`
   - 来源字段：`source_valid`、`source_stale`、`source_degraded`、`source_fault_code`

说明：两个进程都使用稳定文件名，是为了便于后续 incident bundle 统一引用；当前差异化字段保留在各自 CSV 内，不强行抹平。
| `nav_status_flags` | 状态位 |
| `nav_age_ms` | 状态年龄 |
| `fault_code` | 规范化故障码 |

说明：

- `nav.bin`、`nav_timing.bin`、`nav_state.bin` 仍可保留现有格式。
- 统一要求的是事件日志和 bundle 的最小字段，不是重写所有 nav 高频日志。

### 4.3 控制事件

控制事件日志建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `mode` | 控制模式 |
| `armed` | 上锁状态 |
| `estop` | 急停状态 |
| `controller` | 当前控制器 |
| `command_result` | 命令结果 |
| `fault_code` | 故障码 |
| `nav_valid` | 控制侧看到的导航有效位 |
| `nav_stale` | 控制侧看到的导航 stale 位 |
| `nav_degraded` | 控制侧看到的导航 degraded 位 |

### 4.3.1 2026-03-25 已落地的 `control_events.csv`

当前已先在 `ControlGuard` 路径落地 `control_events.csv`：

- 公共字段：`mono_ns`、`wall_time`、`component`、`event`、`level`、`run_id`、`process_name`、`pid`、`fault_code`、`message`
- 控制字段：`mode`、`requested_mode`、`controller`、`armed`、`estop_latched`、`failsafe_action`
- 导航 gating 字段：`nav_present`、`nav_valid`、`nav_stale`、`nav_degraded`

说明：本轮先把 Guard 低频事件放到进程边界写盘，后续再把 controller / allocator / PWM 边界补进同一文件。

### 4.4 通信事件

通信事件日志建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `session_id` | 会话号 |
| `session_state` | 会话状态 |
| `link_alive` | 链路是否活跃 |
| `peer_addr` | 对端地址 |
| `command_id` | 外部命令关联号 |
| `cmd_seq` | 若已生成 control intent，则记录内部序号 |
| `command_type` | 命令类型 |
| `command_result` | 处理结果 |
| `fault_code` | 故障码 |

### 4.5 Supervisor 事件

supervisor 事件日志建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `process_name` | 进程名 |
| `action` | `start/stop/restart/check` |
| `result` | `ok/failed/retrying` |
| `restart_count` | 重启次数 |
| `exit_code` | 退出码 |
| `message` | 摘要 |

## 5. 事件枚举建议

为避免 incident bundle 和 merge 工具解析困难，建议优先使用以下稳定事件名：

- `process_started`
- `process_start_failed`
- `process_stopped`
- `process_restart_scheduled`
- `device_bind_state_changed`
- `serial_open_failed`
- `device_reconnecting`
- `device_online`
- `device_timeout`
- `sensor_update_rejected`
- `nav_publish_state_changed`
- `nav_view_decision_changed`
- `nav_view_publish_failed`
- `nav_view_source_recovered`
- `guard_reject`
- `guard_failsafe_entered`
- `guard_failsafe_cleared`
- `guard_nav_gating_changed`
- `controller_mode_switch_failed`
- `controller_compute_failed`
- `pwm_set_failed`
- `pwm_step_failed`
- `command_received`
- `command_packet_rejected`
- `intent_injected`
- `intent_injection_failed`
- `command_rejected`
- `command_failed`
- `command_expired`
- `session_established`
- `session_lost`

## 6. 时间字段规范

### 6.1 必备字段

- `mono_ns`
  - 单调时间主字段
  - 用于跨日志对齐和 incident bundle 排序

### 6.2 可选字段

- `est_ns`
  - 统一时间基或估计时间
- `wall_time`
  - 仅用于人读，不作为主排序依据
- `age_ms`
  - 对状态年龄或链路延迟的辅助解释

### 6.3 约束

1. 任何事件日志都不能只写 wall clock 而不写 `mono_ns`。
2. `mono_ns` 的含义必须与 `time_contract.md` 保持一致。
3. 不允许在不同模块里重新定义“主时间”语义。
4. `run_id` 应通过 manifest、supervisor 或 launcher 统一下发，不要让每个 C++ 组件各自发明目录口径。
5. 当前已落地的 C++ 事件写入路径会优先读取 `ROV_RUN_ID`；若现场尚未统一下发，则退回 `process-pid-time` 本地 run_id，后续再由 supervisor / manifest 收口。

## 7. 命名与目录规范

### 7.1 运行目录建议

建议以 `run_id` 组织一次运行的输出：

```text
logs/
  YYYY-MM-DD/
    <run_id>/
      manifest/
      nav/
      control/
      comm/
      sensors/
      bundle/
```

### 7.2 文件命名建议

- manifest
  - `run_manifest.json`
  - `process_status.json`
- 事件日志
  - `nav_events.csv`
  - `control_events.csv`
  - `comm_events.csv`
  - `supervisor_events.csv`
  - `imu_events.csv`
  - `dvl_events.csv`
  - `volt_events.csv`
- 状态快照
  - `nav_snapshot.csv`
  - `control_snapshot.csv`
  - `comm_snapshot.csv`
  - `session_summary.json`
- sidecar 输出日志
  - `child_logs/<process>/stdout.log`
  - `child_logs/<process>/stderr.log`
- 高频日志
  - 保留现有 `nav.bin`、`nav_timing.bin`、`nav_state.bin`
  - 控制与 telemetry 高频日志沿用现有命名

### 7.3 目录规范原则

1. 先按运行会话收敛，再按模块分类。
2. 传感器 raw / parsed / event 日志归到 `sensors/` 下。
3. incident bundle 的导出目录必须能反向引用本次 `run_id`。

## 8. Incident Bundle 对接方式

incident bundle 不应依赖“猜测目录”。

建议 supervisor 和各模块提供以下能力：

1. `run_manifest.json` 指出本次日志目录。
2. 事件日志使用稳定文件名。
3. 状态快照使用稳定文件名。
4. 高频日志保留现有文件名，但由 manifest 标注路径。
5. bundle 先收集事件日志和快照，再按需附加高频日志切片。
6. 若 supervisor / launcher 已做 child stdout/stderr 收口，manifest 也应标出 sidecar 文本日志路径。

最小 bundle 输入建议：

- `run_manifest.json`
- `nav_events.csv`
- `control_events.csv`
- `comm_events.csv`
- `supervisor_events.csv`
- 若存在，再附加 `child_logs/<process>/stdout.log|stderr.log`
- `nav_snapshot.csv`
- `control_snapshot.csv`
- `comm_snapshot.csv`
- `session_summary.json`
- `nav_timing.bin`
- `nav_state.bin`
- `control_loop_*.csv`
- `telemetry_timeline_*.csv`
- `telemetry_events_*.csv`

若存在传感器采集工具链，再附加：

- `imu_events.csv`
- `dvl_events.csv`
- `volt_events.csv`
- 相关 raw / parsed 记录

## 9. 落地策略

本轮只建议做最小统一，不建议一次性大改。

### 9.1 第一优先级

1. 冻结四层分工。
2. 冻结公共字段和命令关联字段语义。
3. 统一事件日志命名。
4. 输出 run manifest 并让 bundle 能引用它。
5. 保持现有高频日志不动。

### 9.2 第二优先级

1. 三传感器工具链接入统一 writer。
2. supervisor 生成统一事件日志。
3. 继续补第一批低频高价值事件点；其中 `uwnav_navd`、`nav_viewd`、`ControlGuard` 已落地，`pwm_control_program` 其余边界与 `gcs_server` 仍待补齐。
4. 引入低频状态快照日志。
5. incident bundle 通过 manifest 拉取日志。

### 9.3 明确不建议立即做

1. 重写全部高频日志格式。
2. 把所有日志都并成单一大文件。
3. 为了日志统一改写 control/nav authority 逻辑。
4. 让 ROS2 topic 取代本地日志真源。
5. 为了补 `session_id` 先改 shared ABI，再带出多仓兼容波动。

## 10. 最小验收标准

后续进入实现阶段时，建议按以下标准验收：

1. 事件日志跨模块都带 `mono_ns`、`component`、`event`、`run_id`、`message`。
2. incident bundle 能通过 manifest 找到本次运行的关键日志。
3. `uwnav_navd`、`nav_viewd`、`ControlGuard` 与 supervisor 已有统一低频事件日志；后续补齐 `pwm_control_program` 其余边界和 `gcs_server`。
4. 若启用了 child stdout/stderr 收口，manifest 必须能反向定位对应 sidecar 文本日志。
5. 状态快照层和事件层的职责分离清楚，不再互相挤占。
6. 本轮实现不破坏现有 replay 与高频日志闭环。
