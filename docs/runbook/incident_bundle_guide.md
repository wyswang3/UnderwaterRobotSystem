# Incident Bundle Guide

## 文档状态

- 状态：Authoritative
- 说明：定义当前 Phase 1 最小 incident bundle 导出入口、目录结构和缺失文件判定规则。

## 适用范围

本文档只覆盖外围排障闭环：

- `tools/supervisor/phase0_supervisor.py bundle`
- `tools/supervisor/incident_bundle.py`
- supervisor run files
- child logs
- 现有低频结构化事件入口
- 现有高频 `bin/csv` 日志入口

本文档不覆盖：

- 核心 C++ authority 逻辑修改
- `merge_robot_timeline.py` 的内部切窗算法
- 新的压缩归档平台或问题单平台

## 1. 导出入口

默认导出最近一次 run：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_mock
```

需要机器可读 summary 时：

```bash
python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_mock   --json
```

需要指定某次 run 或指定导出位置时：

```bash
python3 tools/supervisor/phase0_supervisor.py bundle   --run-dir /path/to/run_dir   --bundle-dir /tmp/incident_bundle_case01
```

适合立刻导出的时机：

1. `preflight` 失败后，准备反馈设备/路径问题时。
2. `bench` safe smoke 异常退出后。
3. `mock` 生命周期回归异常后。
4. 操作员准备反馈问题前。
5. 清理 `/tmp`、覆盖 `run_root` 或重启板子前。

## 2. 默认目录结构

默认输出目录：

- `<run_dir>/bundle/<YYYYMMDD_HHMMSS>/`

当前固定目录结构：

```text
bundle/
  bundle_summary.json
  bundle_summary.txt
  supervisor/
    run_manifest.json
    process_status.json
    last_fault_summary.txt
    supervisor_events.csv
  child_logs/
    <process>/stdout.log
    <process>/stderr.log
  events/
    uwnav_navd/nav_events.csv
    nav_viewd/nav_events.csv
    pwm_control_program/control_events.csv
    gcs_server/comm_events.csv
  nav/
    nav_timing.bin
    nav_state.bin
    nav.bin
  control/
    control_loop_*.csv
  telemetry/
    telemetry_timeline_*.csv
    telemetry_events_*.csv
```

说明：

- `events/`、`nav/`、`control/`、`telemetry/` 下的文件会按“存在则复制，不存在则标缺失”的方式处理。
- 当前只复制原始日志，不改原始 `bin/csv` 格式，也不在导出阶段做二次分析。
- `bundle_summary.json` 和 `bundle_summary.txt` 是导出后的第一入口。

## 3. 必须与可选规则

当前 Phase 1 规则固定如下：

1. required
   - `supervisor/run_manifest.json`
   - `supervisor/process_status.json`
   - `supervisor/last_fault_summary.txt`
   - `supervisor/supervisor_events.csv`
2. optional
   - `child_logs/`
   - `events/uwnav_navd/nav_events.csv`
   - `events/nav_viewd/nav_events.csv`
   - `events/pwm_control_program/control_events.csv`
   - `events/gcs_server/comm_events.csv`
   - `nav/nav_timing.bin`
   - `nav/nav_state.bin`
   - `nav/nav.bin`
   - `control/control_loop_*.csv`
   - `telemetry/telemetry_timeline_*.csv`
   - `telemetry/telemetry_events_*.csv`

为什么这样分：

- required 只保留 supervisor 自己的运行真源；缺这些文件时，连“这次 run 到底发生了什么”都无法最小复盘。
- optional 允许缺失，因为不同 run 可能只走了 preflight、只走了 mock，或现场还没触发所有日志入口。
- 这样组织 bundle，可以先把外围排障闭环做扎实，而不倒逼核心链路改目录或改 ABI。

## 4. 缺失文件与 incomplete 判定

导出脚本不会因为 optional 缺失就失败；它会把结果明确标出来：

- `bundle_status=complete`
  - required 和 optional 都齐。
- `bundle_status=incomplete`
  - 只要 required 或 optional 中有任何缺失，就标成 incomplete。
- `required_ok=false`
  - 至少有一个 required 文件缺失。

需要重点看：

- `missing_required_keys`
- `missing_optional_keys`
- `artifacts[]`

如果看到 `bundle_status=incomplete`，处理顺序固定为：

1. 先看 `missing_required_keys`。
2. 若 required 都齐，再看 `missing_optional_keys`。
3. 再决定是回原始 `run_dir` 补日志，还是直接进入 replay / timeline 分析。

如果真实样本是：

- `run_stage=preflight_failed_before_spawn`
- `required_ok=true`

则当前应解释为：

- bundle 导出成功，supervisor 最小真源已经齐全。
- `bundle_status=incomplete` 只是因为 authority 子进程没有真正启动，`events/`、`nav/`、`control/`、`telemetry/` 缺失属于预期现象。
- 零字节 `child_logs/<process>/stdout.log|stderr.log` 也属于预期样本，不应误判成 bundle 导出失败。

## 5. 导出后先看什么

推荐固定顺序：

1. `bundle_summary.txt`
2. `supervisor/last_fault_summary.txt`
3. `supervisor/process_status.json`
4. `supervisor/supervisor_events.csv`
5. 对应进程的 `child_logs/<process>/stdout.log|stderr.log`
6. `events/` 下的低频结构化事件
7. `nav/`、`control/`、`telemetry/` 下的高频日志

这样排序的原因：

- 先回答“哪个进程、在哪个阶段失败”。
- 再回答“状态为什么切换”。
- 最后才看高频详细时序，避免一上来淹没在大文件里。

## 6. 与 merge_robot_timeline 的关系

如果 `bundle_summary.json` 里出现：

- `merge_robot_timeline.ready=true`

说明当前 bundle 已经具备最小 replay 输入。此时可以直接使用 summary 里的 `command_hint`，或手动执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/merge_robot_timeline.py   --nav-timing /path/to/nav_timing.bin   --nav-state /path/to/nav_state.bin   --control-log /path/to/control_loop_xxx.csv   --telemetry-timeline /path/to/telemetry_timeline_xxx.csv   --telemetry-events /path/to/telemetry_events_xxx.csv   --bundle-dir /tmp/replay_bundle_case01
```

如果 `merge_robot_timeline.ready=false`，含义只是 replay 输入还不完整，不等于 bundle 导出失败。

## 7. 最小归档 helper

如果 bundle 已经导出，只是想保留样本或交给别人继续分析，可以使用最小 helper：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
python3 tools/supervisor/bundle_archive.py   --run-dir /path/to/run_dir
```

如果已经知道 bundle 目录，也可以直接指定：

```bash
python3 tools/supervisor/bundle_archive.py   --bundle-dir /path/to/run_dir/bundle/20260326_202046   --json
```

当前行为固定为：

1. 默认把目标 bundle 目录打成同级 `<bundle_dir>.tar.gz`。
2. 只压缩已经导出的 bundle，不会重新执行 bundle 导出。
3. 不上传、不联网、不做额外分析。
4. `--json` 会输出 `archive_path`、`archive_format=tar.gz`、`archive_size_bytes` 等摘要字段。

## 8. 当前阶段明确不做的事

1. 不重写 `nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`、`telemetry_timeline_*.csv`、`telemetry_events_*.csv`。
2. 不把 `bundle` 命令扩成新的“大平台”或问题单系统。
3. 不为了 bundle 改核心 C++ authority 逻辑、共享 ABI 或进程 authority 边界。
4. 不在 supervisor 里直接代跑 `merge_robot_timeline.py`。
5. 不把缺文件自动修复逻辑塞进 bundle 导出器。
