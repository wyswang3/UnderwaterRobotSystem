# Logging Contract

## 文档状态

- 状态：Working draft
- 说明：当前设计方向或阶段性方案已冻结，但尚未全部实施。


## 1. 目标与范围

本文档定义当前阶段最小统一日志规范，用于支撑以下目标：

1. 控制、导航、通信和三传感器工具链的事件可对齐
2. incident bundle 可以引用稳定的日志文件与最小公共字段
3. 不改写现有 authority 主链的高频二进制日志策略
4. 为后续 supervisor、复盘、客户诊断提供统一入口

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
- 把全部高频数据从二进制改成 CSV
- 让 UI 或 ROS2 成为新的日志 authority

## 2. 日志分层

当前日志必须分成三层，而不是硬塞成一种格式。

### 2.1 高频数据日志

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
- 不要求每行都具备完整故障描述
- 主要服务回放、对齐、建模和离线分析

### 2.2 事件日志

用于记录状态切换、故障、恢复、重连、启动、退出等低频事件。

典型内容：

- 进程启动成功 / 失败
- 串口绑定成功 / 失败
- 传感器 reconnecting / online / timeout
- nav invalid / stale / degraded
- command accepted / rejected / failed
- session established / lost

特点：

- 强调可读性与跨模块统一字段
- 是 incident bundle 的首选摘要源

### 2.3 运行 manifest

每次启动应生成一次运行 manifest，用于绑定本次运行的配置、进程、设备和日志目录。

特点：

- 低频
- 面向运维和问题定位
- 不替代高频日志与事件日志

## 3. 最小公共字段

所有事件日志都应尽量包含以下最小字段。

| 字段 | 含义 | 是否必需 |
| --- | --- | --- |
| `mono_ns` | 本地单调时钟时间戳 | 必需 |
| `component` | 进程或模块名 | 必需 |
| `event` | 事件类型 | 必需 |
| `level` | `info/warn/error` | 必需 |
| `run_id` | 本次运行标识 | 必需 |
| `message` | 人类可读摘要 | 必需 |
| `state` | 当前状态或目标状态 | 可选 |
| `fault_code` | 规范化故障码 | 可选 |
| `device_id` | 逻辑设备标识 | 可选 |
| `device_path` | 实际设备路径 | 可选 |
| `seq` | 命令或样本序号 | 可选 |

说明：

- `mono_ns` 是统一对齐主时间，不得省略。
- `component` 应稳定，例如 `uwnav_navd`、`nav_viewd`、`control_loop`、`gcs_server`、`supervisor`、`imu_capture`。
- `event` 应使用稳定枚举，不要随意拼自然语言。

## 4. 各域最小扩展字段

### 4.1 三传感器记录最小字段

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

说明：

- raw 记录可以保留原始载荷字段，不要求统一到单一 schema。
- parsed 记录要有统一时间字段和最小状态字段。
- event 记录要写清楚启动、停止、绑定、异常和恢复。

### 4.2 导航状态最小字段

导航事件日志建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `nav_valid` | 当前导航是否有效 |
| `nav_stale` | 当前导航是否 stale |
| `nav_degraded` | 当前导航是否降级 |
| `nav_health` | 健康枚举 |
| `nav_status_flags` | 状态位 |
| `nav_age_ms` | 状态年龄 |
| `fault_code` | 规范化故障码 |

说明：

- `nav.bin`、`nav_timing.bin`、`nav_state.bin` 仍可保留现有格式。
- 统一要求的是事件日志和 incident bundle 的最小字段，不是重写所有 nav 高频日志。

### 4.3 控制状态最小字段

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

### 4.4 通信状态最小字段

通信事件日志建议至少具备：

| 字段 | 含义 |
| --- | --- |
| `mono_ns` | 单调时间 |
| `session_state` | 会话状态 |
| `link_alive` | 链路是否活跃 |
| `peer_addr` | 对端地址 |
| `cmd_seq` | 命令序列号 |
| `command_type` | 命令类型 |
| `command_result` | 处理结果 |
| `fault_code` | 故障码 |

### 4.5 Supervisor 最小字段

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

为避免 incident bundle 解析困难，建议优先使用以下稳定事件名：

- `process_started`
- `process_start_failed`
- `process_stopped`
- `process_restart_scheduled`
- `device_bind_ok`
- `device_bind_failed`
- `device_reconnecting`
- `device_online`
- `device_timeout`
- `parse_error`
- `nav_invalid`
- `nav_stale`
- `nav_degraded`
- `command_received`
- `command_rejected`
- `command_failed`
- `session_established`
- `session_lost`

## 6. 时间字段规范

时间字段必须和现有时间契约保持一致。

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
3. 高频日志保留现有文件名，但由 manifest 标注路径。
4. bundle 先收集事件日志，再按需附加高频日志切片。

最小 bundle 输入建议：

- `run_manifest.json`
- `nav_events.csv`
- `control_events.csv`
- `comm_events.csv`
- `supervisor_events.csv`
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

1. 定义公共字段
2. 统一事件日志命名
3. 输出 run manifest
4. 保持现有高频日志不动

### 9.2 第二优先级

1. 三传感器工具链接入统一 writer
2. supervisor 生成统一事件日志
3. incident bundle 通过 manifest 拉取日志

### 9.3 明确不建议立即做

1. 重写全部高频日志格式
2. 把所有日志都并成单一大文件
3. 为了日志统一而改写 control/nav authority 逻辑
4. 让 ROS2 topic 取代本地日志真源

## 10. 最小验收标准

后续进入实现阶段时，建议按以下标准验收：

1. 事件日志跨模块都带 `mono_ns`、`component`、`event`、`run_id`、`message`。
2. incident bundle 能通过 manifest 找到本次运行的关键日志。
3. `uwnav_navd`、`pwm_control_program`、`gcs_server` 和 supervisor 至少各有一份统一事件日志。
4. 传感器工具链能输出 raw / parsed / event 三类记录，且时间字段一致。
5. 本轮实现不破坏现有 replay 与高频日志闭环。
