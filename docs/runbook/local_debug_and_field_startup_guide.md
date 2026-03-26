# Local Debug And Field Startup Guide

## 文档状态

- 状态：Authoritative
- 说明：固定当前阶段本地调试、safe smoke、现场前检查和日志导出流程；不放宽核心 C++ authority 主链边界。

## 适用范围

本文档覆盖两类活动：

1. 本地调试
2. 板上 bring-up / 实地实验前启动准备

本文档面向以下运行链：

- `tools/supervisor/phase0_supervisor.py`
- `uwnav_navd`
- `nav_viewd`
- `pwm_control_program`
- `gcs_server`
- incident bundle / replay / merge timeline 工具

本文档当前不覆盖：

- 真实推进器放权后的作业流程
- ESKF / 融合算法调参步骤
- ROS2 外围消费层的完整现场流程

## 当前边界

1. `uwnav_navd`、`nav_viewd`、`ControlGuard`、`ControlLoop`、`gcs_server` 核心行为，以及 `NavState / NavStateView / TelemetryFrameV2` 语义相关部分，统一视为核心 C++ 主链高风险区域。
2. 本地调试优先验证：preflight、运行文件、child logs、结构化低频事件、高频日志可导出性，以及 failure-path 是否清楚。
3. 当前阶段不为了“方便调试”直接改 authority 逻辑或放宽安全边界。
4. `mock`、本地 dry-run、`bench` safe smoke、以及设备未完成现场放行动作前的板上启动，默认继续保持 `pwm_control_program --pwm-dummy`。
5. 若后续必须改核心 C++ 主链，只允许单模块、单小点、单轮最小回归，不允许顺手重构。

## A. 本地调试

### A.1 先选调试模式

当前建议只在以下三种模式里选一种开始：

1. `mock`
   - 适合本机无设备时验证 supervisor 生命周期、运行文件和 stop 顺序。
2. `bench preflight / safe smoke`
   - 适合板上或 bench 环境验证设备可见性、子进程可启动性和 failure-path。
3. replay / incident review
   - 适合不碰设备时验证日志传播链和事故窗口。

### A.1.1 先做设备识别和 startup profile 判定

进入集成仓后，先固定按以下顺序判断串口与 profile：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
python3 tools/supervisor/phase0_supervisor.py startup-profiles --json
```

使用原则：

1. 先用 `--sample-policy off` 看静态身份，不急着打开串口。
2. 如果静态身份不足、当前是 `ttyUSB* / ttyACM*` 不稳定路径，才允许补一轮：

```bash
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy auto --json
```

3. 若输出 `ambiguous=true`、推荐 `startup_profile=no_sensor` 或 `volt_only`，结论应写成“停在 preflight / 独立采样”，不要继续当成 `bench` safe smoke。

### A.1.2 当前样本支撑规则怎么判读

当前 `device-scan` 输出需要这样解释：

1. `dvl`
   - `SA/TS/BI/BS/BE/BD` 已经由真实 `dvl_raw_lines` 样本支撑，可把它当强动态规则。
2. `volt32`
   - `CH0..CH15` 导出 CSV 结构和 `V/A` 后缀已经由真实样本支撑。
   - 现场 live serial 的 `CHn:` 行语法仍是部分样本支撑，不要写成“已完全校准”。
3. `imu`
   - 真实样本已经支撑导出 CSV 字段集合。
   - 但当前 runtime 主链走 `WIT Modbus-RTU` 轮询，被动采样可能无字节；如果静态白名单不足，应保持 `unknown`，不要硬判。
4. `usbl`
   - 本轮仍是候选占位规则。

操作员最应该先看：

- `resolution.reason`
- `candidate_scores`
- `rule_support`
- `risk_hints`

如果 `resolution.reason=score_below_floor` 或 `ambiguous=true`，结论应写成“未形成可信绑定”，而不是“识别失败后继续猜测设备类型”。

### A.2 mock / preflight / bench safe smoke 怎么跑

进入集成仓：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
```

先做 `bench` preflight：

```bash
python3 tools/supervisor/phase0_supervisor.py preflight   --profile bench   --startup-profile auto   --run-root /tmp/phase0_supervisor_bench_smoke
```

说明：

- `--startup-profile auto` 会根据当前设备集合自动推荐 `no_sensor / volt_only / imu_only / imu_dvl ...`。
- 如果 preflight 新增 `startup_profile_gate`，表示当前设备集合只允许停在 preflight / 采样工具，不允许继续做 `bench` authority 链启动。

无设备或只做生命周期回归时，先跑 `mock`：

```bash
python3 tools/supervisor/phase0_supervisor.py start   --profile mock   --detach   --run-root /tmp/phase0_supervisor_mock

python3 tools/supervisor/phase0_supervisor.py status   --run-root /tmp/phase0_supervisor_mock   --json

python3 tools/supervisor/phase0_supervisor.py stop   --run-root /tmp/phase0_supervisor_mock   --timeout-s 5.0

python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_mock   --json
```

只有在 `bench` preflight 通过后，才允许做 `bench` safe smoke：

```bash
python3 tools/supervisor/phase0_supervisor.py start   --profile bench   --detach   --run-root /tmp/phase0_supervisor_bench_smoke   --start-settle-s 0.2   --poll-interval-s 0.2   --stop-timeout-s 5.0
```

说明：

- 当前 `bench` profile 仍以 safe smoke 为目标，不是现场放权流程。
- 当前 `bench` profile 默认保持 `pwm_control_program --pwm-dummy`。
- 若 `bench` preflight 因设备未就绪失败，结论必须写成“failure-path 诊断已验证”，不能写成“authority 主链已验证通过”。

### A.3 supervisor 运行文件怎么看

当前最重要的运行文件有 5 类：

1. `run_manifest.json`
   - 看这次 run 的静态描述、路径、固定启停顺序、child log 路径，以及 `startup_profile / device_identification` 摘要。
2. `process_status.json`
   - 看当前 supervisor 状态、每个子进程状态、PID、exit code、最近故障字段，以及当前被选中的 `startup_profile`。
3. `last_fault_summary.txt`
   - 操作员第一眼故障摘要入口。
4. `supervisor_events.csv`
   - 看 preflight、start、stop、fallback stop 的完整时间线。
5. `child_logs/<process>/stdout.log|stderr.log`
   - 看单个进程自己的滚动输出。

建议排查顺序固定为：

1. `last_fault_summary.txt`
2. `process_status.json`
3. `supervisor_events.csv`
4. 对应进程的 `child_logs`

### A.4 child logs 怎么看

推荐 detached 模式配合 `--child-output capture` 使用，这样每个进程会有独立的 sidecar：

- `child_logs/uwnav_navd/stdout.log`
- `child_logs/uwnav_navd/stderr.log`
- `child_logs/nav_viewd/stdout.log`
- `child_logs/nav_viewd/stderr.log`
- `child_logs/pwm_control_program/stdout.log`
- `child_logs/pwm_control_program/stderr.log`
- `child_logs/gcs_server/stdout.log`
- `child_logs/gcs_server/stderr.log`

使用原则：

1. 先看 supervisor 运行文件定位是哪一个进程失败。
2. 再只打开对应进程的 `stdout/stderr`，不要一上来同时翻所有文本日志。
3. 如果 child log 和结构化事件日志语义冲突，以当前代码路径和结构化事件为准，再回头检查文本是否过时。

### A.5 本地没有设备时怎么验证

当前推荐最小无设备验证顺序：

1. 跑 `bench` preflight --startup-profile auto，确认设备缺失和 `startup_profile_gate` 能被明确指出。
2. 运行：

```bash
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
```

3. 跑一轮 `mock start -> status -> stop`，确认 supervisor 生命周期正常。
4. 对受影响仓执行最相关的最小构建 / 单测 / smoke。
5. 如果需要验证传播语义，改走 replay / merge timeline，而不是伪造“本地无设备也等于现场验证通过”。

### A.6 最小回归怎么做

当前统一按改动类型选回归，不混做：

1. docs-only
   - 复核文档交叉引用、命令、路径和结论表述。
2. 外围模块改动
   - 运行对应 Python 单测、语法检查或工具 smoke。
   - 若涉及 supervisor / incident bundle，至少做一轮 `mock start -> stop -> bundle`，并确认 `bundle_summary` 的缺失提示符合预期。
3. 核心 C++ 主链改动
   - 先说明为什么必须改。
   - 一次只改一个核心模块的一个小点。
   - 至少构建受影响目标。
   - 至少运行最相关单测或最小 smoke。
   - 收口时必须明确：为什么只改这个点、做了哪些验证、哪些风险暂时没动。

## B. 实际工作 / 实地实验启动

### B.1 板子上设备就位前检查项

上板或现场前，至少先确认：

1. 工作目录、配置文件和二进制路径正确。
2. `run_root` 可写。
3. `/dev/shm` 可读写。
4. 没有上一次残留的 active run。
5. `gcs_server` 预期端口没有被旧进程占用。
6. 当前供电、网络和 SSH 会话稳定。
7. 当前阶段仍以 safe startup 为目标，不把本次启动当作算法调参入口。

### B.2 串口和 by-id 如何确认

板子上优先确认四层视图：

```bash
ls -l /dev/serial/by-id
ls -l /dev/ttyUSB* /dev/ttyACM*
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
```

至少核对：

- `path`
- `canonical_path`
- `vendor_id`
- `product_id`
- `serial`
- `device_type`
- `confidence`
- `recommended_binding`
- `ambiguous`

如果 `by-id` 不存在、目标串口不出现，或者 `device-scan` 给出 `ambiguous=true / startup_profile=no_sensor / startup_profile=volt_only`，先停在 preflight，不进入 authority 进程启动。

补充说明：

- 如果 IMU 只有静态候选但 `dynamic_probe` 没拿到字节，不要直接写成 IMU 故障；当前更可能是 Modbus 轮询设备的被动采样特性。
- 如果 DVL 命中 `SA/TS/BI/BS/BE/BD` 多类 token，可优先信任动态识别结果。
- 若 `device_type=unknown` 但 `resolution.top_candidate` 存在，必须把 top candidate 和 score 一起记录，方便后续 bench 复核。

### B.3 启动顺序

当前推荐顺序固定为：

1. `device-scan --sample-policy off --json`
2. `startup-profiles --json`
3. `preflight --profile bench --startup-profile auto`
   - 只有可信识别到的设备才会参与 profile 计数；`unknown` / `ambiguous` 都不会被当成可用设备。
4. `uwnav_navd`
5. `nav_viewd`
6. `pwm_control_program`
7. `gcs_server`
8. GCS / TUI

若使用 supervisor，则优先走：

```bash
python3 tools/supervisor/phase0_supervisor.py start   --profile bench   --detach   --run-root /tmp/phase0_supervisor_bench_smoke
```

### B.4 哪些模式必须保持 `--pwm-dummy`

当前阶段以下场景都必须保持 `--pwm-dummy`：

1. `mock` 生命周期回归。
2. 本地 dry-run。
3. `bench` safe smoke。
4. 设备刚接好、只验证 bring-up / 日志 / 诊断传播、还没有明确推进器放行结论的板上启动。

本文档不授权真实 PWM 放权；若需要进入真实推进器输出，必须由单独的现场安全流程和放行结论覆盖。

### B.5 哪些日志要提前准备

进入现场前，至少预留并确认以下日志入口：

1. supervisor `run_root`
2. `child_logs/`
3. 导航高频日志：`nav_timing.bin`、`nav_state.bin`
4. 控制高频日志：`control_loop_*.csv`
5. telemetry 日志：`telemetry_timeline_*.csv`、`telemetry_events_*.csv`
6. 低频结构化事件：`nav_events.csv`、`control_events.csv`（若本轮路径已启用）
7. `usb_serial_snapshot.py` 的现场快照输出

### B.6 出问题先看哪些文件

推荐现场排查入口固定为：

1. `last_fault_summary.txt`
2. `process_status.json`
3. `supervisor_events.csv`
4. 对应进程的 `child_logs/<process>/stdout.log|stderr.log`
5. `nav_events.csv` / `control_events.csv`
6. `nav_timing.bin` / `nav_state.bin`
7. `control_loop_*.csv` / `telemetry_timeline_*.csv` / `telemetry_events_*.csv`

含义：

- 前 4 项先回答“哪个进程、在哪个阶段、为什么失败”。
- 低频结构化事件再回答“状态为什么切换”。
- 高频日志最后回答“详细时序和传播窗口是什么”。

### B.7 如何导出日志和 incident bundle

当前 Phase 1 已支持最小自动导出，不再要求先手工拼 supervisor run files。

建议在以下时机立刻导出：

1. `preflight` 失败后。
2. `bench` safe smoke 异常退出后。
3. `mock` 生命周期回归异常后。
4. 操作员准备反馈问题前。
5. 清理 `/tmp`、覆盖 `run_root` 或重启板子前。

默认导出最近一次 run：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_bench_smoke
```

如果要拿机器可读 summary：

```bash
python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_bench_smoke   --json
```

如果要指定某一次 run 或指定 bundle 目录：

```bash
python3 tools/supervisor/phase0_supervisor.py bundle   --run-dir /path/to/run_dir   --bundle-dir /tmp/incident_bundle_case01
```

默认输出位置：

1. `<run_dir>/bundle/<YYYYMMDD_HHMMSS>/bundle_summary.json`
2. `<run_dir>/bundle/<YYYYMMDD_HHMMSS>/bundle_summary.txt`
3. 同目录下的 `supervisor/`、`child_logs/`、`events/`、`nav/`、`control/`、`telemetry/`

当前规则：

1. required 只包含 `run_manifest.json`、`process_status.json`、`last_fault_summary.txt`、`supervisor_events.csv`。
2. child logs、`nav_events.csv`、`control_events.csv`、`comm_events.csv`、`nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`、`telemetry_*` 都属于 optional。
3. 只要有任何缺失，bundle 仍然导出，但会明确写成 `bundle_status=incomplete`。
4. `missing_required_keys` / `missing_optional_keys` 会直接告诉你缺什么。
5. `merge_robot_timeline.ready=false` 只表示 replay 输入还不完整，不等于 bundle 导出失败。
6. 如果 `run_stage=preflight_failed_before_spawn` 且 `required_ok=true`，应解释为“bundle 导出成功，但真实 bench safe smoke 被 preflight 阻塞”；此时零字节 child logs 和缺失的 `events/nav/control/telemetry` 都属于预期结果。

导出后先看：

1. `bundle_summary.txt`
2. `supervisor/last_fault_summary.txt`
3. `supervisor/process_status.json`
4. `supervisor/supervisor_events.csv`
5. `child_logs/<process>/stdout.log|stderr.log`
6. `events/` 下的结构化低频事件
7. `nav/`、`control/`、`telemetry/` 下的高频日志

如果 `bundle_summary.json` 里的 `merge_robot_timeline.ready=true`，再继续用 `command_hint` 或手动执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/merge_robot_timeline.py   --nav-timing /path/to/nav_timing.bin   --nav-state /path/to/nav_state.bin   --control-log /path/to/control_loop_xxx.csv   --telemetry-timeline /path/to/telemetry_timeline_xxx.csv   --telemetry-events /path/to/telemetry_events_xxx.csv   --bundle-dir /tmp/replay_bundle_case01
```

若要只切事故窗口，可增加：

```bash
  --event reconnecting   --window-before-ms 150   --window-after-ms 350
```

更完整的 bundle 目录与规则说明，统一看：

- `docs/runbook/incident_bundle_guide.md`

如果 bundle 已经导出、只需要压缩归档当前样本，可执行：

```bash
python3 tools/supervisor/bundle_archive.py   --bundle-dir /path/to/run_dir/bundle/20260326_202046
```

默认输出为同级 `<bundle_dir>.tar.gz`；这个 helper 只做本地压缩，不会重新导出 bundle，也不会上传。

## 当前阶段结论写法

1. 只完成本地 mock / preflight / failure-path 时，必须写：
   - “本地/bench failure-path 已验证，未进入真实 authority 放行。”
2. 只完成日志导出和 replay 时，必须写：
   - “已验证传播语义/事故窗口，不等同于真实现场闭环。”
3. 只有在设备就绪、safe smoke 完整跑完且结论明确时，才允许写：
   - “bench safe smoke 已完成。”
4. 没有单独现场安全流程前，不得把本文件解释成“真实推进器输出放行指南”。
