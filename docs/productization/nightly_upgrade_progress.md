# Nightly Upgrade Progress

## 文档状态

- 状态：Authoritative
- 说明：记录当前阶段最新一轮的产品化 / 文档化进展摘要。

## 日期

2026-03-25

## 当前目标

本轮目标已经从“Phase 0 薄 supervisor / launcher 原型落地”推进到“真实安全烟测准备 + 最小 operator 可操作性收口”，重点仍然是：

1. 不触碰 authority 主链
2. 优先让真实 `bench` safe smoke 有最小可复现入口
3. 在环境不具备时，把 failure-path 诊断做清楚，而不是把失败留给黑盒进程输出

## 本轮完成项

### 1. Phase 0 supervisor 的 preflight 已补强

本轮新增的低风险检查包括：

- `/dev/shm` 可读写
- 进程工作目录可访问
- 关键配置文件可读性
- `nav_daemon.yaml` 中设备节点可见性
- `/dev/serial/by-id` 可见性提示
- `gcs_server` 端口占用检查

同时修复了 `preflight` CLI 的一个实际缺陷：

- `cmd_preflight` 中未定义变量导致的 `NameError`

### 2. 真实 `bench` 环境已做安全烟测尝试

本轮已实际执行：

- `preflight --profile bench`
- `start --profile bench --detach`
- `status --json`

当前环境结论（2026-03-23）：

- `/dev/ttyUSB0` 不存在
- `/dev/ttyACM0` 不存在
- `/dev/serial/by-id` 不存在

因此本轮真实 `bench` safe smoke 被 preflight 阻塞，没有启动 authority 进程。这是符合当前安全边界的结果。

### 3. failure-path 运行文件已验证

即使真实 `bench` 被 preflight 阻塞，本轮也已验证四个运行文件仍会正确生成：

- `run_manifest.json`
- `process_status.json`
- `last_fault_summary.txt`
- `supervisor_events.csv`

当前 failure-path 已确认能稳定表达：

- 这次 run 的 profile 和路径
- 当前 supervisor 状态
- 最近一次故障摘要
- 每项 preflight 检查的通过/失败时间线

### 4. 最小 operator runbook 已新增

本轮新增：

- `docs/runbook/supervisor_phase0_operator_guide.md`

当前已经说明：

- 如何 `preflight`
- 如何 `start`
- 如何 `status`
- 如何 `stop`
- 四个运行文件分别看什么
- 常见失败时先看哪里

### 5. mock 生命周期已做回归

本轮再次完成：

- `start --profile mock --detach`
- `status --json`
- `stop`

并确认 `supervisor_events.csv` 中的逆序退出记录仍为：

1. `gcs_server`
2. `pwm_control_program`
3. `nav_viewd`
4. `uwnav_navd`

## 本轮验证方式

已执行：

1. `python3 -m py_compile`
2. `python3 -m unittest discover -s tools/supervisor/tests -p 'test_*.py'`
3. `python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --run-root /tmp/phase0_supervisor_bench_smoke`
4. `python3 tools/supervisor/phase0_supervisor.py start --profile bench --detach --run-root /tmp/phase0_supervisor_bench_smoke ...`
5. `python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_bench_smoke --json`
6. 手动 mock smoke：
   - `start --profile mock --detach`
   - `status --json`
   - `stop --timeout-s 5.0`

未执行：

- 设备就绪条件下的真实 `bench` authority 进程启动
- 真机验证
- ROS2 graph / rosbag2 验证
- replay / incident bundle 运行时验证

## 当前阻塞点

1. 当前主机没有 `bench` 所需设备节点。
2. 真实 `bench` 的 authority 进程启停仍待在设备就绪环境验证。
3. 当前还没有 stdout / stderr 收口。

## 下一步最建议做的事

1. 在真实 IMU / DVL 设备就绪后，优先重跑一组完整 `bench` safe smoke。
2. 继续保持 `--pwm-dummy`，不要跨出 Phase 0 supervisor 边界。
3. 如果真实 `bench` 启动成功，再只修 supervisor 自己暴露的问题。
4. 在 Phase 0 稳定前，不要提前展开三传感器工具链和更大范围统一日志。


## 2026-03-23 追加进展：导航侧传感器采集工具链防呆收口

本轮在 `Underwater-robot-navigation` 落地了低风险 Python 工具链补强，不触碰 `uwnav_navd` authority 主线。

### 已落地

1. 新增统一 session 诊断：每次采集都会产出 `*_events_*.csv` 与 `*_session_summary_*.json`。
2. DVL 采集链现在能明确表达 `open_failed` / `no_parsed_frames` / `empty_capture`。
3. Volt32 采集链现在能区分不同数据类型：
   - 数值 + 单位
   - 非数字值
   - 异常单位
   - 超范围通道
4. IMU failure-path 已修复：串口打开失败时不再后台无限刷异常。

### 本轮验证

已执行：

- `python3 -m py_compile`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- DVL / IMU / Volt32 缺设备失败路径 smoke 各 1 轮，均已生成 session summary

当前仍未执行：

- 真实硬件在环 smoke
- DVL 有效样本解析质量验证
- 统一日志扩面


## 2026-03-23 追加进展：DVL 真实样本已替代空样本判断

本轮新增拿到真实 DVL raw 样本：

- `/home/wys/orangepi/2026-01-26/dvl_raw_lines_20260126_104848.csv`

基于这份样本，已完成两项低风险收口：

1. `protocol.py` 只按真实数据帧起点切块，不再把 `CZ/CS` 回显和噪声切成伪帧。
2. `io.py` 的 `DVLData` 映射层只放行 `BI/BS/BE/BD/WI/WS/WE/WD`，不再让 `SA/TS` 和噪声污染 parsed/TB。

当前验证已通过：

- DVL 协议相关 `py_compile`
- 全部导航仓 Python 单测（9 个用例）


## 2026-03-23 追加进展：传感器总开关已可用

本轮新增 `apps/acquire/sensor_capture_launcher.py`，已经可以一条命令统一拉起 IMU / DVL / Volt32 三套采集脚本。

当前已验证：

- launcher 自己的 manifest / events / summary 会生成
- 任一子脚本早退时，launcher 会统一收口剩余子脚本
- 不侵入各传感器脚本内部逻辑


## 2026-03-25 追加进展：日志 Phase B 第一批 C++ 低频结构化事件已落地

本轮开始把统一日志从 docs-only 设计推进到 authority-safe 的最小代码落地，但仍然严格限制在低频事件层。

### 已落地

1. `uwnav_navd` 新增 `nav_events.csv`，先覆盖：
   - `device_bind_state_changed`
   - `serial_open_failed`
   - `sensor_update_rejected`
   - `nav_publish_state_changed`
2. `nav_viewd` 新增 `nav_events.csv`，先覆盖：
   - `nav_view_decision_changed`
   - `nav_view_publish_failed`
   - `nav_view_source_recovered`
3. `ControlGuard` 通过事件回调 + 进程边界写盘，新增 `control_events.csv`，先覆盖：
   - `guard_reject`
   - `guard_failsafe_entered`
   - `guard_failsafe_cleared`
   - `guard_nav_gating_changed`
4. 保持高频日志不动：
   - `nav_timing.bin`
   - `nav_state.bin`
   - `control_loop_*.csv`
   - `telemetry_timeline_*.csv`

### 本轮验证

已执行：

- `cmake --build .../nav_core/build --target uwnav_navd`
- `cmake --build .../OrangePi_STM32_for_ROV/build --target nav_viewd pwm_control_program test_v1_closed_loop test_nav_view_policy`
- `.../build/bin/test_v1_closed_loop`
- `.../build/bin/test_nav_view_policy`
- `.../nav_core/build/test_serial_reconnect_integration`

当前仍未执行：

- 真机 / 实机 smoke
- supervisor manifest 与 incident bundle 自动整合
- `gcs_server` 的统一 `comm_events.csv`
- `pwm_control_program` 其余 controller / allocator / PWM 边界事件
