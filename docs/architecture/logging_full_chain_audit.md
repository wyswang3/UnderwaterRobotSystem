# Full-Chain Logging Audit

## 文档状态

- 状态：Working draft
- 说明：本轮只做全链路日志专项审查、分层冻结和实施路线设计，不在本文件中直接推进大规模 C++ 主链改造。

## 1. 本轮目标与范围

本轮目标是先把“日志到底缺什么、先补哪里最值、哪些字段必须统一”说清楚，再进入第一批 C++ 日志点落地。

范围覆盖：

- `supervisor`
- 三传感器 Python tooling
- `uwnav_navd / nav_core`
- `nav_viewd`
- `pwm_control_program`
- `ControlGuard / ControllerManager / ControlLoop`
- `gcs_server`
- telemetry / incident bundle 入口

本轮明确不做：

- 三传感器体系重构
- 导航模式重构
- 控制框架大改
- 为了日志统一去改写 authority 主链语义

## 2. 当前全链路日志现状

### 2.1 审查依据

本轮主要审查以下入口：

- `UnderwaterRobotSystem/tools/supervisor/phase0_supervisor.py`
- `Underwater-robot-navigation/uwnav/io/acquisition_diagnostics.py`
- `Underwater-robot-navigation/apps/acquire/sensor_capture_launcher.py`
- `Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_runner.cpp`
- `Underwater-robot-navigation/nav_core/src/nav_core/app/device_binding.cpp`
- `Underwater-robot-navigation/nav_core/src/nav_core/app/nav_runtime_status.cpp`
- `Underwater-robot-navigation/nav_core/src/nav_core/estimator/nav_health_monitor.cpp`
- `OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp`
- `OrangePi_STM32_for_ROV/gateway/src/IPC/nav/nav_view_policy.cpp`
- `OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/control_guard.cpp`
- `OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp`
- `OrangePi_STM32_for_ROV/pwm_control_program/src/io/log/control_loop_logger.cpp`
- `OrangePi_STM32_for_ROV/pwm_control_program/src/io/log/telemetry_timeline_logger.cpp`
- `OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp`
- `OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp`
- `Underwater-robot-navigation/nav_core/tools/merge_robot_timeline.py`

### 2.2 各环节现状

| 环节 | 当前已有日志 | 现状判断 | 主要缺口 |
| --- | --- | --- | --- |
| `supervisor` | `run_manifest.json`、`process_status.json`、`last_fault_summary.txt`、child `stdout/stderr` sidecar | 启动/运维层已经明显增强，现场至少能先看到进程失败和子进程 tail | 仍缺稳定的 `supervisor_events.csv`，事件和状态还散在 JSON/TXT；`run_id` 还没有自然传到 C++ 主链事件日志 |
| 传感器 Python tooling | `events.csv`、`session_summary.json`、launcher child logs | 目前是最接近“结构化事件日志”的一段，字段、计数器、`run_id` 已有统一基础 | 事件只能说明采集端，不足以解释 nav/control 最终后果；bundle 还没自动收它们 |
| `uwnav_navd / nav_core` | `nav_timing.bin`、`nav.bin`、`nav_state.bin`、`nav_events.csv`、少量 `stderr`、设备绑定 timing trace | 高频日志和 replay 基础较强，第一批低频结构化事件也已落地 | `NavHealthMonitor` 指标还没有对操作员导出；`run_id` 仍主要靠环境变量传入；bundle 还没自动收 `nav_events.csv` |
| `nav_viewd` | 聚合计数器、`stderr`、`nav_events.csv`，下游通过 `NavStateView` 看 stale/degraded/fault | 策略逻辑清楚，且第一批低频决策事件已落地 | `nav_events.csv` 还没有接到统一 manifest / bundle；当前默认路径仍偏本地目录约定，后续要和 run_id / run_root 对齐 |
| `pwm_control_program` | `control_loop_*.csv`、`telemetry_timeline_*.csv`、`telemetry_events_*.csv`、若干 stdout/stderr | C++ 主链里最接近完整日志闭环的一段，高频和 telemetry 事件都在 | Guard / controller / allocator / PWM 边界的拒绝原因仍然偏散；很多关键原因只在调试文本里，不利于 bundle 自动汇总 |
| `ControlGuard / ControllerManager / ControlLoop` | 模式切换、failsafe、arm/estop、controller compute、PWM error 的 stdout/stderr；Telemetry event code；`control_events.csv`（当前先覆盖 Guard 低频事件） | Guard 的 reject / failsafe / nav gating 已有稳定事件出口，开始具备因果链基础 | `ControllerManager`、allocator、PWM 边界还没有同步进入 `control_events.csv`；stdout/stderr 仍然不少，bundle 自动汇总也还没接 |
| `gcs_server` | 会话握手、ACK、部分命令注入 stdout/stderr；STATUS 发送使用 telemetry adapter | 能看出会话建立、丢失、ACK 发没发 | 缺 `comm_events.csv`；缺 packet seq -> session_id -> intent cmd_seq -> control result 的关联链；命令注入成败目前不可稳定复盘 |
| telemetry / incident bundle | `merge_robot_timeline.py` 可合并 nav/control/telemetry，并导出 `incident_summary.json` | 已有最小 replay / compare / bundle 框架 | 仍靠显式输入路径，没接 supervisor manifest；新的 child logs、sensor summary、sensor events 还没自动纳入 |

### 2.3 现有优点与问题分布

现有链路并不是“完全没日志”，而是出现了明显的不均衡：

1. 高频日志比低频事件日志强。
2. replay 输入比现场一眼可读的故障摘要强。
3. Python tooling 的结构化程度比 C++ 主链强。
4. telemetry 能说明“结果是什么”，但常常不能说明“为什么走到这里”。

## 3. 排障盲区

### 3.1 现在仍然很难靠日志快速定位的问题

1. `uwnav_navd` 设备错绑、重连抖动、串口打开失败时，本轮已经能通过 `nav_events.csv` 看到第一层状态切换和拒绝原因；但下一次重试时机、更多 health monitor 细节和跨进程 run 关联仍不够完整。
2. `nav_viewd` 进入 stale / no-nav / diagnostic-only publish 时，本轮已经能通过 `nav_view_decision_changed` 看到主要改判原因；但 manifest / bundle 还没自动把这类事件和上下游日志串成一条现场时间线。
3. `ControlGuard` 做 TTL / nav gating / estop / mode reject 时，本轮已经能输出结构化低频事件；但 controller / allocator / PWM 边界还没并入同一条 `control_events.csv` 因果链。
4. `gcs_server` 的命令生命周期无法稳定关联。当前至少存在三套编号空间：GCS wire packet `seq`、会话 `session_id`、控制侧 `cmd_seq / intent_id`。它们没有被持续记录在同一条链上。
5. incident bundle 还没有把 supervisor child logs、sensor `events.csv`、`session_summary.json` 自动带进去。现场经常还要手工再找 sidecar 日志。

### 3.2 关键链路中“有日志但难关联”的位置

1. `nav_timing.bin` 和 `nav_state.bin` 很强，但对现场来说门槛较高，且不直接表达“这次错误对 control / GCS 的影响是什么”。
2. `telemetry_events_*.csv` 有事件码和命令结果，但主要是数值事件，缺少当前 mode、controller、nav gating 上下文。
3. `ControlLoop`、`ControlGuard`、`gcs_session` 里已有很多 stdout/stderr 调试信息，但它们既没有 `run_id`，也没有稳定 CSV 字段，不利于自动筛选和排序。
4. `process_status.json` 与各进程自己的日志之间，目前还缺一个“稳定引用链”，bundle 也没有统一利用。

### 3.3 低价值或帮助有限的现状

以下输出并非完全没用，但不应当继续作为主排障手段扩张：

- `ControlGuard` 的逐状态 stdout 调试打印
- `ControlLoop` 的 teleop DOF / thruster command 调试文本
- `gcs_session` 的握手十六进制调试输出
- `nav_daemon` 每 10 秒一次的状态摘要 stderr

这些信息适合保留为 bench debug 或 trace 开关，但不应承担统一事件日志职责。

## 4. 统一日志分层建议

建议把当前日志冻结为四层，而不是继续把 manifest、stderr、事件和高频数据混在一起。

### 4.1 启动 / 运维日志

适合记录：

- 进程启动、停止、退出码
- 关键配置、日志目录、PID、CLI 参数
- 串口绑定结果、设备路径、重试计划
- 子进程 stdout/stderr sidecar 路径
- 运行 manifest、`process_status.json`、`last_fault_summary.txt`

不适合记录：

- 每帧导航状态
- 每周期 PWM / thruster 值
- 高频采样

建议载体：

- JSON / TXT / 少量 CSV
- 可以同步写

### 4.2 事件日志

适合记录：

- 状态切换
- 故障进入 / 恢复
- 拒绝原因
- 命令生命周期
- 会话建立 / 丢失
- publish 成功 / 抑制 / 失败

不适合记录：

- 高频数值波形
- 每周期重复 heartbeat

建议载体：

- 低频 append-only CSV
- 行级稳定 schema
- 对 control / nav 主循环优先采用“状态变化触发 + 速率限制”

### 4.3 状态快照日志

适合记录：

- 当前 mode / armed / estop / controller
- 当前 nav_valid / nav_stale / nav_degraded / nav_fault_code
- 当前 session 状态与最后命令结果
- 当前设备在线 / 重连 / mismatch 概况

不适合记录：

- 原始采样
- 高频控制输出
- 每个错误的详细堆栈

建议载体：

- 低频 CSV 或 JSON
- 1Hz 到 5Hz 为主，或状态变化时额外打一帧

### 4.4 高频数据日志

适合记录：

- `nav.bin`
- `nav_timing.bin`
- `nav_state.bin`
- `control_loop_*.csv`
- `telemetry_timeline_*.csv`
- 传感器 raw / parsed CSV

不适合记录：

- 现场第一眼排障摘要
- 只靠 grep 的人工浏览

建议载体：

- 二进制或高频 CSV
- 主要服务 replay、compare、离线分析

### 4.5 当前日志到四层的映射

| 现有产物 | 建议归层 |
| --- | --- |
| `run_manifest.json` / `process_status.json` / `last_fault_summary.txt` | 启动 / 运维 |
| 传感器 `events.csv` | 事件日志 |
| `session_summary.json` | 状态快照 |
| `telemetry_events_*.csv` | 事件日志 |
| `telemetry_timeline_*.csv` | 状态快照与高频边界层 |
| `control_loop_*.csv` | 高频数据日志 |
| `nav_timing.bin` / `nav_state.bin` / `nav.bin` | 高频数据日志 |
| child `stdout/stderr` sidecar | 启动 / 运维附加证据，不替代结构化事件日志 |

## 5. 统一字段规范建议

### 5.1 字段分级

建议不要把所有字段都升格成“每条日志都必须有”，而是分三层：

1. 核心公共字段
2. 关联字段
3. 域扩展字段

### 5.2 核心公共字段

以下字段建议对事件日志统一冻结：

| 字段 | 建议 |
| --- | --- |
| `mono_ns` | 必需；主排序时间 |
| `wall_time` | 推荐；便于人读，但不参与主排序 |
| `component` | 必需；稳定逻辑组件名 |
| `event` | 必需；稳定事件枚举 |
| `level` | 必需；`info/warn/error` |
| `run_id` | 必需；跨 supervisor / sensors / C++ 主链统一关联 |
| `message` | 必需；人类可读摘要 |

说明：

- `component` 表示逻辑日志写入者，例如 `uwnav_navd`、`nav_viewd`、`control_guard`、`gcs_session`。
- `process_name` 不等同于 `component`。一个进程内可能有多个高价值组件。

### 5.3 关联字段

以下字段建议“有就写，不强制全域都有”：

| 字段 | 建议 |
| --- | --- |
| `process_name` | 启动/运维日志必需；事件日志强烈建议 |
| `pid` | 启动/运维日志必需；事件日志推荐 |
| `fault_code` | 故障、拒绝、恢复事件建议必写 |
| `session_id` | 仅对 comm / control 命令链强烈建议 |
| `mode` | control / nav_view / command 事件推荐 |
| `controller` | control 事件与快照推荐 |

### 5.4 域扩展字段

以下字段建议按域使用，而不是强制所有文件都带：

| 字段 | 适用范围 | 建议 |
| --- | --- | --- |
| `status_flags` | 单域事件文件 | 若文件语义单一可用 |
| `nav_valid` | nav/control 事件与快照 | 推荐 |
| `nav_stale` | nav/control 事件与快照 | 推荐 |
| `nav_degraded` | nav/control 事件与快照 | 推荐 |
| `command_id` | command lifecycle | 推荐，但需先定义语义 |
| `cmd_seq` | control intent / command result | 推荐 |

### 5.5 对 `status_flags` 的建议

不建议在所有跨域日志里只保留一个模糊的 `status_flags`。

建议做法：

1. 单域文件中允许使用 `status_flags`，前提是该文件全是 nav 或全是 control。
2. 需要跨域合并或 bundle 统一引用时，优先使用带前缀字段，例如 `nav_status_flags`。
3. 不要让操作员猜这次的 `status_flags` 到底是哪一层定义的。

### 5.6 对 `command_id / cmd_seq` 的建议

当前至少存在两种不同语义的编号：

1. transport / protocol 层的 packet seq
2. control intent 层的 `cmd_seq`

因此不建议强行只保留一个 `cmd_seq`。

建议冻结为：

- `command_id`
  - 表示“这次命令生命周期的外部关联号”
  - GCS 路径下优先承载 packet seq 或后续稳定 intent id
- `cmd_seq`
  - 表示 control intent / control result 的内部序号

若事件发生在 GCS 路径上，建议同时记录：

- `session_id`
- `command_id`
- `cmd_seq`

### 5.7 当前最明显的字段盲区

当前 C++ 主链里最明显的关联盲区有两处：

1. `gcs_session` 的 `session_id` 与 GCS wire packet `seq` 没有稳定带到结构化日志。
2. `decode_control_intent()` 目前把 control internal `session_id` 直接置 0，说明“命令关联字段”还没有真正贯通到 control 侧。

在 Phase A 之前，不建议为了补这一个字段立刻改 shared ABI；先把 comm 事件日志里的映射链稳定下来更低风险。

## 6. 第一批最值得落地的 C++ 日志点

原则：

- 先补低频、高价值、最能提升现场排障效率的点
- 先补状态切换和拒绝原因
- 不先往高频主循环里塞大量字符串日志

### 6.1 `uwnav_navd`

第一批建议：

1. `device_bind_state_changed`
   - 触发：binder 状态变化
   - 字段：`device_label`、`device_path`、`state`、`reason`、`fault_code`
2. `serial_open_failed`
   - 触发：串口 init / start 失败
   - 字段：`device_path`、`baud`、`message`
3. `sensor_update_rejected`
   - 触发：IMU/DVL 观测拒绝原因首次出现或原因类别变化
   - 字段：`sensor_id`、`reason_class`、`fault_code`、`sample_age_ms`
4. `nav_publish_state_changed`
   - 触发：`valid/stale/degraded/fault_code/status_flags` 组合变化
   - 字段：`nav_valid`、`nav_stale`、`nav_degraded`、`fault_code`、`nav_status_flags`

不建议首批直接做：

- 每个 IMU 样本都写文本事件
- 每个 DVL 更新都写 JSON

2026-03-25 实现状态：

- 已在 `nav_core/src/nav_core/app/nav_daemon_runner.cpp` 落地 `nav_events.csv` 写入路径。
- 已落地事件：`device_bind_state_changed`、`serial_open_failed`、`sensor_update_rejected`、`nav_publish_state_changed`。
- `sensor_update_rejected` 当前只在拒绝类别首次出现或类别切换时写入，覆盖 `preprocess_rejected`、`gated_rejected`、`stale_sample`、`out_of_order`。
- 这样记的原因是先把“为什么这轮导航状态切了”讲清楚，而不是把高频采样路径变成文本日志热点。

### 6.2 `nav_viewd`

第一批建议：

1. `nav_view_decision_changed`
   - 触发：`no_nav_yet / stale_triggered / diagnostic_only / degraded_publish` 组合变化
   - 字段：`nav_valid`、`nav_stale`、`nav_degraded`、`fault_code`、`age_ms_from_nav_pub`
2. `nav_view_publish_failed`
   - 触发：publish 返回失败
3. `nav_view_source_recovered`
   - 触发：从 `no_nav_yet` 或 stale 返回正常透传

重点不是“多打一堆计数器”，而是告诉现场这次为什么改判。

2026-03-25 实现状态：

- 已在 `gateway/apps/nav_viewd.cpp` 落地 `nav_events.csv`。
- 已落地事件：`nav_view_decision_changed`、`nav_view_publish_failed`、`nav_view_source_recovered`。
- `nav_view_decision_changed` 只在 `publish / diagnostic_only / degraded_publish / no_nav_yet / stale_triggered` 组合变化时写入。
- 这样放在 publish 决策边界，是为了直接解释 control-facing `NavStateView` 为什么改判，同时避免 poll slot 高频刷盘。

### 6.3 `ControlGuard`

第一批建议：

1. `guard_reject`
   - 场景：mode reject、motor test reject、clear estop reject
   - 字段：`mode`、`requested_mode`、`armed`、`estop_latched`、`nav_valid`、`nav_stale`、`nav_degraded`、`fault_code`、`message`
2. `guard_failsafe_entered`
   - 场景：TTL、nav gating、estop 导致 zero output / emergency stop
3. `guard_failsafe_cleared`
   - 场景：从 failsafe 恢复
4. `guard_nav_gating_changed`
   - 场景：AUTO 模式下导航从可信变不可信或反向恢复

这些点的价值高于再补 arm/estop 普通状态打印，因为 telemetry 已经能看见 arm/estop 结果，但还看不清 reject reason。

2026-03-25 实现状态：

- 已在 `ControlGuard` 增加低频事件回调，在 `control_loop_run.cpp` 进程边界落 `control_events.csv`。
- 已落地事件：`guard_reject`、`guard_failsafe_entered`、`guard_failsafe_cleared`、`guard_nav_gating_changed`。
- 当前只让 Guard 负责判定和发出结构化事件，不让 Guard 自己直接做文件 I/O。
- 这样做的原因是把“为什么拒绝/为什么进入 failsafe”稳定结构化，同时避免把刷盘逻辑塞回安全决策对象内部。

### 6.4 `pwm_control_program`

第一批建议：

1. `controller_mode_switch_failed`
   - 字段：`mode`、`controller`、`desired_controller`、`cmd_seq`
2. `controller_compute_failed`
   - 字段：`mode`、`controller`、`cmd_seq`、`nav_valid`、`nav_stale`、`nav_degraded`、`fault_code`
3. `allocator_zero_output`
   - 场景：控制器无有效输出或分配器回退到零
4. `pwm_set_failed`
   - 场景：`setTargets()` 失败
5. `pwm_step_failed`
   - 场景：`step()` 失败
6. `pwm_step_abort`
   - 场景：累计错误超过阈值，进入 failsafe 并退出

### 6.5 `gcs_server`

第一批建议：

1. `session_established`
2. `session_lost`
3. `command_packet_rejected`
   - 场景：invalid session、duplicate seq、bad format、not supported
   - 字段：`session_id`、`command_id`、`event`、`message`
4. `intent_injected`
   - 场景：命令成功转成 SHM intent
   - 字段：`session_id`、`command_id`、`cmd_seq`、`mode`、`message`
5. `intent_injection_failed`
   - 场景：SHM publish 失败、命令构造失败

首批不要求 `gcs_server` 直接拿到最终 control result，但至少要先把“哪条外部命令对应了哪条内部 `cmd_seq`”记下来。

## 7. 实时性与性能注意事项

### 7.1 可同步写的内容

- supervisor 启停日志
- 设备绑定状态切换
- 会话建立 / 丢失
- 命令注入成功 / 失败
- failsafe 进入 / 退出
- publish 明确失败

这些点低频且对主循环影响小，可以直接 append。

### 7.2 更适合异步 / 缓冲写的内容

- control 主循环里的事件日志
- nav 主循环里的状态变化日志
- 周期性状态快照

建议做法：

- 先在内存里形成轻量 event record
- 背景 writer 线程负责格式化和刷盘
- 至少避免在高频路径里频繁分配字符串和强制 flush

### 7.3 应降频的内容

- “无导航”连续告警
- IMU / DVL 连续拒绝告警
- thruster activity 文本
- teleop DOF 调试文本

建议统一成：

- 状态变化立刻打一条
- 持续重复问题按固定周期打 summary

### 7.4 更适合二进制的内容

- 高频采样与时序 trace
- replay 输入
- 样本级 timing / state 波形

当前 `nav_timing.bin`、`nav_state.bin` 保持二进制方向是对的，不建议为了“统一日志”改成 JSON。

### 7.5 更适合 CSV / JSON 的内容

CSV 更适合：

- 事件日志
- 状态快照
- command lifecycle

JSON 更适合：

- `run_manifest.json`
- `session_summary.json`
- `incident_summary.json`
- `last_fault_summary.txt` 的后续 JSON 化替代物

### 7.6 不应放进实时主循环高频路径的内容

- 每周期 JSON 序列化
- 每周期字符串拼接并 `flush`
- 每个 PWM step 都写人类可读长文本
- 每个采样点都写事件日志

## 8. incident bundle 后续整合建议

### 8.1 统一入口

后续 bundle 不应再主要依赖“人工把一堆路径拼给脚本”。

建议入口改为：

1. supervisor `run_manifest.json`
2. launcher / sensor sub-manifest
3. 各模块稳定命名的事件日志和快照日志

### 8.2 建议 bundle 收集顺序

1. 先收 `run_manifest.json`
2. 再收启动 / 运维层日志
   - `process_status.json`
   - `last_fault_summary.txt`
   - child `stdout/stderr`
3. 再收事件层
   - `supervisor_events.csv`
   - `nav_events.csv`
   - `control_events.csv`
   - `comm_events.csv`
   - 传感器 `events.csv`
4. 再收状态快照
   - `session_summary.json`
   - control / nav / comm snapshot
   - `telemetry_timeline_*.csv`
5. 最后按窗口裁剪高频日志
   - `nav_timing.bin`
   - `nav_state.bin`
   - `control_loop_*.csv`
   - `telemetry_events_*.csv`

### 8.3 supervisor child logs 的整合方式

建议不把 child `stdout/stderr` 当成主时间线源，而是：

1. 在 manifest 中稳定记录原始路径
2. bundle 默认复制 tail 和原路径引用
3. 若文件较小可直接纳入 bundle
4. 若文件较大则保留引用并按故障窗口追加切片

### 8.4 对 `merge_robot_timeline.py` 的后续建议

建议后续增加两类能力：

1. `--run-manifest`
   - 由 manifest 自动发现 nav/control/telemetry/sensor 日志
2. merged timeline 吞入新增事件日志
   - `nav_events.csv`
   - `control_events.csv`
   - `comm_events.csv`
   - `supervisor_events.csv`

当前 merge 工具已经能处理 nav/control/telemetry 高频输入，但还没有真正吃下 supervisor 和 sensor 事件链。

## 9. 分阶段实施路线图

### Phase A：日志字段和分层冻结

目标：

- 冻结四层日志口径
- 冻结核心字段、关联字段、域扩展字段
- 冻结 stable event names
- 冻结 `command_id / cmd_seq / session_id` 的语义边界

交付：

- `logging_contract.md` 修订
- 本审查文档冻结为实现参考

### Phase B：第一批 C++ 高价值日志点

目标：

- 先补 `uwnav_navd`、`nav_viewd`、`ControlGuard`、`pwm_control_program`、`gcs_server` 的低频高价值事件点

2026-03-25 当前状态：

- 已落地 `uwnav_navd`、`nav_viewd`、`ControlGuard` 第一批低频结构化事件。
- 已新增 `nav_events.csv` 与 `control_events.csv` 的最小写入路径。
- `pwm_control_program` 其余 controller / allocator / PWM 边界事件与 `gcs_server` 的 `comm_events.csv` 仍待后续落地。

范围：

- 新增 `nav_events.csv`
- 新增 `control_events.csv`
- 新增 `comm_events.csv`
- 暂不改高频 replay 日志格式

### Phase C：状态快照统一

目标：

- 统一 nav / control / comm 的低频快照口径

建议产物：

- `nav_snapshot.csv`
- `control_snapshot.csv`
- `comm_snapshot.csv`

原则：

- 尽量与 telemetry 已有字段对齐
- 不再新增第二套难以解释的状态语义

### Phase D：incident bundle 自动整合

目标：

- 让 supervisor manifest 成为 bundle 统一入口
- 自动拉取 child logs、sensor summary、sensor events、C++ 事件日志

建议动作：

- `merge_robot_timeline.py` 支持 manifest 输入
- bundle 输出增加 `bundle_manifest.json`

### Phase E：回归测试与文档收口

目标：

- 单测覆盖事件日志 writer
- replay / bundle / compare 验证不退化
- runbook 与 operator guide 更新

最低验证：

- 至少一组本地 dry-run
- 至少一组 bundle 导出
- 至少一组 replay compare 不退化

## 10. 风险与不建议立即改动的部分

### 10.1 本轮不建议立即做的事

1. 不要为了日志统一重写 `nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`。
2. 不要把所有日志并成一个大文件。
3. 不要在 control / PWM 高速路径里直接堆字符串日志。
4. 不要为了补 `session_id` 立刻改 shared ABI，再带出一轮跨仓兼容改动。
5. 不要先扩散到三传感器重构、导航模式重构或 ROS2 侧日志大整合。

### 10.2 当前已知漂移风险

1. command lifecycle 关联字段目前还没冻结到 wire 真源，后续若要贯通 `session_id`，要先明确 ABI 影响。
2. 现有很多 stdout/stderr 调试文本仍在主链里，后续落结构化事件日志时要避免双写过多导致噪声暴涨。
3. `telemetry_events_*.csv` 已经承担了一部分 control event 职责，后续新增 `control_events.csv` 时要防止语义重叠失控。

### 10.3 推荐的实施态度

后续实现应遵循：

1. 先补最值钱的低频事件点。
2. 先保证跨模块可关联，再考虑更漂亮的日志框架。
3. 先让 incident bundle 自动找到关键日志，再谈更复杂的 UI 呈现。
