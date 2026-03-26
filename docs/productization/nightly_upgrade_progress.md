# Nightly Upgrade Progress

## 文档状态

- 状态：Authoritative
- 说明：记录当前阶段最新一轮的产品化 / 文档化进展摘要。

## 日期

2026-03-26

## 当前目标

本轮最新目标是在不放宽安全边界的前提下，把“怎么本地调试、怎么板上启动、哪些改动属于高风险核心主链”固定成新的执行基线。重点是：

1. 把核心 C++ 主链改动收紧到单模块、单点、单轮最小回归
2. 优先继续推进外围模块的启动、诊断、日志和 bundle 收口
3. 先把本地调试 / field startup / 日志导出流程文档化，再决定是否进入核心代码修补
4. 把设备识别与分级启动 profile 先做成外围 gate，避免 tty 跳变和设备误绑直接带进 authority 进程
5. 用真实 IMU / Volt32 / DVL 样本把设备识别规则从启发式收紧成样本支撑

## 历史完成项（截至 2026-03-25）

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

## 历史验证方式（截至 2026-03-25）

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


## 2026-03-26 追加进展：核心 C++ 主链高风险执行原则与本地/实地启动 guide

本轮只做 docs/runbook 收口，不触碰 authority C++ 逻辑。

### 已落地

1. 新增 `docs/runbook/local_debug_and_field_startup_guide.md`，统一说明：
   - mock / preflight / bench safe smoke
   - supervisor 运行文件与 child logs 查看顺序
   - 无设备时的最小验证路径
   - 板上设备就位前检查项
   - 串口 / by-id 确认方式
   - 必须保持 `--pwm-dummy` 的场景
   - 日志导出与 incident bundle 最小步骤
2. `CODEX_HANDOFF.md` 已同步新增“核心 C++ 主链高风险区域”约束。
3. `CODEX_NEXT_ACTIONS.md` 已同步新增：
   - 外围模块 / 核心主链边界
   - 核心主链一次只改一个小点
   - 每次都要做最小回归
   - 后续涉及核心主链时的固定收口要求

### 本轮验证

已完成：

- 复核 `supervisor_phase0_operator_guide.md`
- 复核 `usb_reconnect_bench_plan.md`
- 复核 `bringup_runbook.md`
- 复核 `log_replay_guide.md`
- 复核 `incident_timeline_usage.md`
- docs-only 交叉引用与命令路径人工检查

当前未执行：

- 新的核心 C++ 改动
- 真实 bench / 实地 smoke
- incident bundle 自动整合


## 2026-03-26 追加进展：外围排障闭环 Phase 1 incident bundle

本轮只推进外围模块商业化收口，不触碰核心 C++ 主链 authority 逻辑。

### 已落地

1. 新增 `tools/supervisor/incident_bundle.py`，把 supervisor run files、child logs、低频事件入口和现有高频日志入口导出到固定 bundle 目录。
2. `phase0_supervisor.py` 新增 `bundle` 子命令，作为统一导出入口。
3. 默认导出目录固定为 `<run_dir>/bundle/<timestamp>/`，并生成：
   - `bundle_summary.json`
   - `bundle_summary.txt`
   - `supervisor/`
   - `child_logs/`
   - `events/`
   - `nav/`
   - `control/`
   - `telemetry/`
4. required / optional / incomplete 规则已固定：
   - required：supervisor 自己的 4 个 run files
   - optional：child logs、结构化低频事件、高频 `bin/csv`
   - 缺失时 bundle 仍导出，但会明确标成 incomplete
5. 新增 `docs/runbook/incident_bundle_guide.md`，并更新 `local_debug_and_field_startup_guide.md`，把 bundle 导出、查看顺序和问题反馈路径写清楚。

### 本轮验证

已执行：

- `python3 -m py_compile tools/supervisor/phase0_supervisor.py tools/supervisor/incident_bundle.py tools/supervisor/tests/test_phase0_supervisor.py`
- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor`
- 一次真实 `mock start -> stop -> bundle --json`

已确认：

- bundle 默认输出到 `<run_dir>/bundle/<timestamp>/`
- required 缺失时 `required_ok=false`
- optional 缺失时 `bundle_status=incomplete`
- `bundle_summary` 会明确列出缺失项和 `merge_robot_timeline` readiness

### 当前未执行

- 真实 `bench` / 实机环境的 bundle 导出演练
- 一键压缩归档或上传
- supervisor 内直接代跑 `merge_robot_timeline.py`


## 2026-03-26 追加进展：真实 bench bundle 演练与最小归档 helper

本轮仍然只推进外围排障闭环，不触碰核心 C++ authority 逻辑。

### 已落地

1. 在真实主机执行了一次 `bench` preflight / start / bundle 演练，拿到了真实 failure-path run dir。
2. 已确认真实 `run_dir` 的 bundle 导出可用：
   - `required_ok=true`
   - `bundle_status=incomplete`
   - `run_stage=preflight_failed_before_spawn`
3. 已确认零字节 `child_logs` 会进入 bundle，`events/nav/control/telemetry` 缺失属于该样本的预期结果。
4. 新增 `tools/supervisor/bundle_archive.py`，可把现有 bundle 最小打成同级 `.tar.gz`。
5. runbook 已同步补充：preflight-failed 样本的判读方式，以及本地归档 helper 的使用方式。

### 本轮验证

已执行：

- `python3 -m py_compile tools/supervisor/tests/test_phase0_supervisor.py tools/supervisor/bundle_archive.py tools/supervisor/tests/test_bundle_archive.py`
- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor tools.supervisor.tests.test_bundle_archive`
- `python3 tools/supervisor/phase0_supervisor.py bundle --run-dir /tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835 --json`
- `python3 tools/supervisor/bundle_archive.py --bundle-dir /tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835/bundle/20260326_202046 --json`

### 当前未完成

- 设备就绪条件下真正进入 `child_process_started` 的 `bench safe smoke`
- 基于真实 child-process 样本再次复核 `events/` 与高频日志收集
- 上传或问题单集成


## 2026-03-26 追加进展：设备识别辅助工具与分级启动 profile

本轮继续只做外围增强，不碰核心 C++ authority 主链。

### 已落地

1. 新增设备识别辅助工具：
   - `tools/supervisor/device_identification.py`
   - `tools/supervisor/device_identification_rules.json`
2. 新增分级启动 profile 目录：
   - `tools/supervisor/device_profiles.py`
3. `phase0_supervisor.py` 新增：
   - `device-scan`
   - `startup-profiles`
   - `--startup-profile auto|...`
4. `bench preflight` 已能根据识别结果做 `startup_profile_gate`：
   - `no_sensor` / `volt_only` / `reserved` 不允许继续进入当前 `bench` authority 链
   - 歧义设备直接拒绝自动绑定
5. run files 已同步写入当前 startup profile 与设备识别摘要。

### 本轮验证

已执行：

1. `python3 -m py_compile`
2. `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor tools.supervisor.tests.test_bundle_archive tools.supervisor.tests.test_device_identification`
3. `python3 tools/supervisor/phase0_supervisor.py startup-profiles --json`
4. `python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json`
5. `python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --startup-profile auto --run-root /tmp/phase0_supervisor_device_profile_preflight`

### 当前限制

1. 动态指纹还没有经过真实 IMU / DVL / Volt32 长时间样本校准。
2. `imu_dvl_usbl` / `full_stack` 仍是预留设计。
3. 当前只做 gate / 记录，不按 profile 改写 authority 进程图。

## 2026-03-26 追加进展：设备识别规则已按真实样本收紧

本轮只做 `UnderwaterRobotSystem` 的外围工具和文档收口，不触碰核心 C++ authority 主链。

### 已落地

1. 已读取并分析真实 IMU / Volt32 / DVL 样本。
2. 已确认：
   - DVL `SA/TS/BI/BS/BE/BD` 是稳定强动态 token
   - Volt32 `CH0..CH15` 导出 CSV 与 `V/A` 后缀可作为样本支撑
   - IMU 当前 runtime 主链是 `WIT Modbus-RTU` 轮询，因此被动动态识别不能当主判据
3. `device_identification.py` 已改成更保守的可信绑定策略：
   - `score < 0.60` 回退 `unknown`
   - 高分冲突显式 `ambiguous`
   - 输出 `resolution.reason`、`resolution.top_candidate`、`rule_support`
4. `device_identification_rules.json` 已明确写出：
   - 哪些规则已经是样本支撑
   - 哪些仍是 partial
   - 哪些仍只是 candidate-only
5. `test_device_identification.py` 已改成样本驱动验证，并新增真实样本摘录夹具。

### 本轮验证

已执行：

- `python3 -m py_compile tools/supervisor/device_identification.py tools/supervisor/device_profiles.py tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_device_identification.py`
- `python3 -m unittest tools.supervisor.tests.test_device_identification`

当前仍未执行：

- 真实 bench 下的 `imu_only` 推荐稳定性验证
- 真实 bench 下的 `imu_dvl` 推荐稳定性验证
- 真实 `/dev/serial/by-id` / sysfs 静态快照校准
- IMU live serial 主动探测验证

### 下一步最建议做的事

1. 在真实 bench 上补采静态身份快照，用于继续收紧 IMU / Volt32 / DVL 白名单。
2. 在真实 bench 条件下分别验证 `imu_only` 与 `imu_dvl` 的 profile 推荐和 gate。
3. 若继续推进，只在 supervisor / preflight / runbook 侧做轻量收口，不提前改核心 authority 主链。

