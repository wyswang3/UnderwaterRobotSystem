# Supervisor Phase0 Operator Guide

## 文档状态

- 状态：Authoritative
- 说明：定义当前 Phase 0 supervisor 的最小操作步骤、运行文件用途和 bench safe smoke 的复现方式。

## 适用范围

本文档只适用于当前 `UnderwaterRobotSystem` 集成仓中的薄 supervisor：

- `tools/supervisor/phase0_supervisor.py`

当前边界：

1. 只负责 preflight、启停顺序、状态文件、故障摘要和子进程 sidecar 输出日志
2. 不接管 `uwnav_navd`、`pwm_control_program`、`nav_viewd`、`gcs_server` 的 authority
3. `bench` profile 继续强制使用 `pwm_control_program --pwm-dummy`

## 1. 启动前先做 preflight

进入集成仓：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
```

先执行：

```bash
python3 tools/supervisor/phase0_supervisor.py preflight   --profile bench   --run-root /tmp/phase0_supervisor_bench_smoke
```

当前 preflight 会检查：

1. Python 版本
2. `run_root` 可写性
3. `/dev/shm` 可读写性
4. 进程工作目录可访问性
5. 关键二进制存在且可执行
6. 关键配置文件存在且可读
7. `nav_daemon.yaml` 中设备节点是否存在
8. `/dev/serial/by-id` 是否可见
9. `gcs_server` 默认端口 `14550` 是否可绑定
10. 是否已有 active run 未停止

当前已知 bench 设备阻塞长这样：

- `bench_device_ttyUSB0`
- `bench_device_ttyACM0`

如果看到这两个检查失败，说明当前主机没有可供 `uwnav_navd` 使用的 IMU / DVL 设备节点。

## 2. 真实 bench safe smoke

只有在 preflight 通过后，才进入真实 `bench` safe smoke：

```bash
python3 tools/supervisor/phase0_supervisor.py start   --profile bench   --detach   --run-root /tmp/phase0_supervisor_bench_smoke   --start-settle-s 0.2   --poll-interval-s 0.2   --stop-timeout-s 5.0
```

设计说明：

- 当前 `bench` profile 会拉起真实二进制
- 当前 `pwm_control_program` 仍带 `--pwm-dummy`
- detached 模式默认会把每个子进程的 `stdout/stderr` 收到 `child_logs/<process>/stdout.log|stderr.log`
- 这保证了 Phase 0 只做安全烟测，不直接驱动真实 PWM 输出

常用可选项：

- `--child-output inherit`
  - 前台直通子进程输出，适合开发者盯终端
- `--child-output capture`
  - 推荐用于 detached / 现场调试，会落 sidecar 日志文件
- `--child-output quiet`
  - 丢弃子进程输出，只保留 supervisor 自己的状态文件
- `--fault-tail-lines 40`
  - 最近一次故障摘要里额外附带最后 40 行 child log

如果当前环境不具备设备条件，`start` 会在 preflight 阶段失败并返回非零，但仍会生成运行文件，便于直接看阻塞点。

## 3. 查看当前状态

```bash
python3 tools/supervisor/phase0_supervisor.py status   --run-root /tmp/phase0_supervisor_bench_smoke   --json
```

重点看：

1. `supervisor_state`
2. `child_output_mode`
3. `last_fault_event`
4. `last_fault_message`
5. 各进程的 `state / pid / exit_code / log_files`

常见状态：

- `running`
- `stopped`
- `failed`
- `not_started`

## 4. 停止当前 run

```bash
python3 tools/supervisor/phase0_supervisor.py stop   --run-root /tmp/phase0_supervisor_bench_smoke   --timeout-s 10.0
```

当前预期退出顺序固定为：

1. `gcs_server`
2. `pwm_control_program`
3. `nav_viewd`
4. `uwnav_navd`

如果 live supervisor 已退出，`stop` 会进入 fallback stop，并继续更新状态文件和故障摘要。

## 5. 四个运行文件分别看什么

### `run_manifest.json`

看这次 run 的静态描述：

- `run_id`
- `profile`
- `run_dir`
- 四个运行文件路径
- `child_output_mode` / `child_logs_dir`
- 固定启动顺序 / 退出顺序
- 每个进程的命令行、依赖路径和预定 `stdout/stderr` 日志文件

### `process_status.json`

看当前 run 的动态状态：

- `supervisor_state`
- `child_output_mode`
- `last_fault_event`
- `last_fault_message`
- `last_fault_process_name` / `last_fault_details`
- 每个进程的 `state / pid / start_wall_time / stop_wall_time / exit_code / log_files`

### `last_fault_summary.txt`

先快速看最近一次失败结论。

适合操作员先判断：

- 是 preflight 失败
- 还是进程运行中退出
- 还是 stop 超时
- 最近一次失败对应的是哪个进程
- 对应 child `stdout/stderr` 最后几行是什么

### `supervisor_events.csv`

看完整事件时间线。

当前至少会记录：

- supervisor 启动
- 每一项 preflight 的通过/失败
- 进程启动
- 进程停止
- stop 请求
- fallback stop

### `child_logs/<process>/stdout.log|stderr.log`

看子进程自己的滚动输出。

适合在以下场景直接打开：

- `process_start_failed`
- `process_stopped` 且 `result=failed`
- `last_fault_summary.txt` 已给出 `stdout_log` / `stderr_log` 路径

## 6. 常见失败先看哪里

### 情况 A：`preflight_failed`

先按顺序看：

1. `last_fault_summary.txt`
2. `process_status.json`
3. `supervisor_events.csv`

设备相关失败时，优先检查：

- `/dev/ttyUSB0`
- `/dev/ttyACM0`
- `/dev/serial/by-id`

并建议先跑：

```bash
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
```

### 情况 B：`gcs_bind` 失败

说明 `14550` 端口已被占用。先检查是否还有旧 `gcs_server` 或其他调试工具未退出。

### 情况 C：进程 `state=failed`

当前 Phase 0 已支持最小 child stdout / stderr 收口。优先按顺序看：

1. `last_fault_summary.txt`
2. `process_status.json` 里的 `last_fault_process_name / last_fault_details`
3. `child_logs/<process>/stdout.log|stderr.log`
4. `supervisor_events.csv`

如果 `child_output=inherit`，仍要回到当前终端；如果 `child_output=quiet`，则只能依赖 supervisor 事件和对应仓库自己的日志目录。

## 7. 最小复现流程

下一次 bench safe smoke 建议固定用下面流程：

1. `preflight --profile bench`
2. 若设备未就绪，记录 preflight 失败结果并停止本轮
3. 若设备就绪，再执行 `start --profile bench --detach`
4. 立即执行 `status --json`
5. 确认运行文件齐全
6. 执行 `stop`
7. 再看一次 `status --json` 与 `supervisor_events.csv`

结论写法要求：

- 如果只完成了 preflight failure-path，就写“真实 bench 被设备条件阻塞，failure-path 诊断已验证”
- 只有在真实进程完成 `start -> status -> stop` 后，才能写“真实 bench safe smoke 已完成”
