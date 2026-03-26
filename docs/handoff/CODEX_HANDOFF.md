# CODEX_HANDOFF

## 文档状态

- 状态：Authoritative
- 说明：Codex 当前阶段恢复上下文的高密度交接摘要。

## 0. 2026-03-26 覆盖更新

从这一轮开始，核心 C++ 主链明确视为高风险区域，默认执行原则已经收紧：

1. 必须先区分外围模块和核心主链。
2. 外围模块优先继续推进：
   - supervisor / launcher
   - Python 传感器工具链
   - GCS / UI
   - 日志解析工具
   - incident bundle
   - ROS2 外围桥接
3. 核心主链包括：
   - `uwnav_navd`
   - `nav_viewd`
   - `ControlGuard`
   - `ControlLoop`
   - `gcs_server` 核心行为
   - `NavState / NavStateView / TelemetryFrameV2` 语义相关部分
4. 若必须改核心 C++ 主链，本轮只允许改一个小点，并且必须：
   - 先做最小设计或代码审查
   - 只动一个核心 authority 模块
   - 每次都做最小可回归验证
   - 不顺手重构
5. 当前阶段优先策略：
   - 继续优先推进外围模块
   - 导航侧优先补日志、报错检查、状态暴露与调试能力
   - 不先大改 ESKF 结构和核心融合逻辑
   - 等实地实验条件具备后，再集中优化导航算法本身
6. 新增必须维护的操作文档：
   - `docs/runbook/local_debug_and_field_startup_guide.md`
7. 后续只要涉及核心 C++ 主链改动，收口时必须额外说明：
   - 为什么必须改这个点
   - 为什么这轮只改这个点
   - 做了哪些验证
   - 哪些风险暂时没动

本轮因此先做 docs/runbook 基线收口，不把前一轮发现的核心链路小 drift 直接并入同轮修复；若后续要修，必须按“单模块、单点、单轮最小回归”执行。

## 0.05 2026-03-26 追加更新：外围排障闭环 Phase 1 incident bundle

本轮只触碰 `UnderwaterRobotSystem` 的 supervisor / tooling / runbook，不触碰 `uwnav_navd`、`nav_viewd`、`ControlGuard`、`ControlLoop` 或 `gcs_server` 核心 authority 行为。

已落地：

1. 新增 `tools/supervisor/incident_bundle.py`，把 supervisor run files、child logs、低频事件入口和现有高频日志入口按固定目录导出到 `<run_dir>/bundle/<timestamp>/`。
2. `tools/supervisor/phase0_supervisor.py` 新增 `bundle` 子命令，支持：
   - 默认导出 latest run
   - 指定 `--run-dir`
   - 指定 `--bundle-dir`
   - `--json` 输出 `bundle_summary`
3. bundle 当前固定产物：
   - `bundle_summary.json`
   - `bundle_summary.txt`
   - `supervisor/`
   - `child_logs/`
   - `events/`
   - `nav/`
   - `control/`
   - `telemetry/`
4. required / optional 规则已落地：
   - required：`run_manifest.json`、`process_status.json`、`last_fault_summary.txt`、`supervisor_events.csv`
   - optional：child logs、`nav_events.csv`、`control_events.csv`、`comm_events.csv`、`nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`、`telemetry_timeline_*.csv`、`telemetry_events_*.csv`
   - 缺失时 bundle 仍导出，但明确标成 `bundle_status=incomplete`
5. 若 `nav/control/telemetry` 输入齐全，`bundle_summary` 会额外给出 `merge_robot_timeline.ready` 与 `command_hint`；本轮仍不在 supervisor 内直接代跑 merge。

本轮验证：

- `python3 -m py_compile tools/supervisor/phase0_supervisor.py tools/supervisor/incident_bundle.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor`：通过（7 个用例）
- 真实 `mock start -> stop -> bundle --json`：通过，并确认缺高频日志时 `bundle_status=incomplete`

## 0.06 2026-03-26 追加更新：真实 bench run dir bundle 验证与最小归档 helper

本轮继续只触碰 `UnderwaterRobotSystem` 的 supervisor / tooling / runbook，不触碰核心 C++ authority 行为。

已确认：

1. 本机在 `2026-03-26` 的真实 `bench` preflight 仍被设备阻塞：
   - `bench_device_ttyUSB0`
   - `bench_device_ttyACM0`
2. 因此前提设备未就绪，真实 `bench safe smoke` 还不能写成“已完成”；当前结论仍然是 failure-path 样本。
3. 但真实 `start --profile bench --detach` 已成功生成 run dir：
   - `/tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835`
4. 从该真实 `run_dir` 执行 `bundle --run-dir ... --json`：通过，并确认：
   - `required_ok=true`
   - `bundle_status=incomplete`
   - `run_stage=preflight_failed_before_spawn`
   - 零字节 `child_logs` 被正确收集
   - `events/nav/control/telemetry` 缺失符合预期
5. 新增 `tools/supervisor/bundle_archive.py`，可把现有 bundle 目录最小打包成同级 `<bundle_dir>.tar.gz`，不重新导出、不上传。
6. `docs/runbook/incident_bundle_guide.md` 与 `docs/runbook/local_debug_and_field_startup_guide.md` 已同步写明：
   - `preflight_failed_before_spawn + required_ok=true` 仍然表示 bundle 导出成功
   - 真实 failure-path 样本的零字节 child logs / 缺失高频日志属于预期
   - 新的本地归档 helper 用法

## 0.07 2026-03-26 追加更新：设备识别辅助工具与分级启动 profile

本轮继续只触碰 `UnderwaterRobotSystem` 的 supervisor / tooling / runbook，不触碰 `uwnav_navd`、`nav_viewd`、`ControlGuard`、`ControlLoop` 或 `gcs_server` 核心 authority 行为。

已落地：

1. 新增 `tools/supervisor/device_identification.py`、`tools/supervisor/device_identification_rules.json`、`tools/supervisor/device_profiles.py`。
2. `phase0_supervisor.py` 新增：
   - `device-scan`
   - `startup-profiles`
   - `--startup-profile auto|...`
3. `bench preflight` 现在会在原有设备节点检查之外，额外输出：
   - `device_inventory`
   - `device_recommendations`
   - `startup_profile`
   - `device_binding_ambiguity`
   - `startup_profile_gate`
4. 当前 gate 规则已经落地：
   - 若识别结果是 `no_sensor` / `volt_only` / `reserved`，或存在歧义，`bench preflight` 直接失败
   - 只有 `launch_mode=bench_safe_smoke` 的 `startup_profile` 才允许继续做当前 `bench` 链路
5. `run_manifest.json`、`process_status.json`、`last_fault_summary.txt` 已同步暴露：
   - `startup_profile`
   - `startup_profile_source`
   - `recommended_startup_profile`
   - `device_identification` / `device_counts` / `recommended_bindings`
6. 当前最小实现只做 recommendation / gate / 记录，不重写 `bench` 的 authority 进程图。

本轮验证：

- `python3 -m py_compile tools/supervisor/phase0_supervisor.py tools/supervisor/device_profiles.py tools/supervisor/device_identification.py ...`：通过
- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor tools.supervisor.tests.test_bundle_archive tools.supervisor.tests.test_device_identification`：通过（17 个用例）
- `python3 tools/supervisor/phase0_supervisor.py startup-profiles --json`：通过
- `python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json`：通过，当前主机返回 `no_sensor`
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --startup-profile auto --run-root /tmp/phase0_supervisor_device_profile_preflight`：按预期因为缺设备节点 + `startup_profile_gate=no_sensor` 失败


## 0.08 2026-03-26 追加更新：设备识别规则已按真实样本校准

本轮继续只触碰 `UnderwaterRobotSystem` 的 supervisor / tooling / runbook，不触碰核心 C++ authority 行为。

已确认：

1. 已用真实样本校准 IMU / Volt32 / DVL 规则，不再只靠经验 token。
2. DVL 的 `SA/TS/BI/BS/BE/BD` reply token 已升级成强动态规则。
3. Volt32 的 `CH0..CH15` 导出 CSV 结构与 `V/A` 值后缀已升级成样本支撑；`CHn:` live serial 行语法仍只是 partial 规则。
4. IMU 已确认当前 runtime 是 `WIT Modbus-RTU` 轮询，因此被动动态探测不能再当主判据；导出 CSV 字段集合已作为样本支撑，旧 `0x55` 同步帧只保留兼容候选位。
5. `device_identification.py` 现在会输出：
   - `resolution.reason`
   - `resolution.top_candidate`
   - `rule_support`
   - 更严格的 `unknown / ambiguous` 退化行为
6. `device_identification_rules.json` 已写明每类设备的样本支撑等级与剩余缺口。
7. `tools/supervisor/tests/test_device_identification.py` 已改成样本驱动验证，覆盖：
   - IMU 样本
   - Volt32 样本
   - DVL 样本
   - unknown 样本
   - mixed-sample ambiguity
   - sample-backed profile recommendation

本轮验证：

- `python3 -m py_compile tools/supervisor/device_identification.py tools/supervisor/device_profiles.py tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_device_identification.py`：通过
- `python3 -m unittest tools.supervisor.tests.test_device_identification`：通过（10 个用例）

当前剩余风险：

1. 还没有真实 `/dev/serial/by-id` / sysfs 快照去继续收紧 IMU / Volt32 / DVL 的静态白名单。
2. IMU live serial 主探测仍未实现；当前只能明确“被动采样不足时宁可 unknown，也不硬判”。
3. Volt32 还缺原始串口行日志，所以 `CHn:` 规则仍只能算 partial。
4. USBL 仍无真实样本。

## 0.1 2026-03-25 覆盖更新

当前最新优先级已从“只围绕 Phase 0 supervisor 收口”推进到“日志体系 Phase B 第一批 C++ 低频结构化事件落地”，但边界不变：

1. 仍然不做高频日志重写。
2. 仍然不改 shared ABI。
3. 仍然不做三传感器重构、导航模式重构或 ROS2 侧大整合。
4. 允许在 authority 主链里做小步、低风险、低频的结构化事件落点。

本轮已落地：

- `uwnav_navd`：`device_bind_state_changed`、`serial_open_failed`、`sensor_update_rejected`、`nav_publish_state_changed`
- `nav_viewd`：`nav_view_decision_changed`、`nav_view_publish_failed`、`nav_view_source_recovered`
- `ControlGuard`：`guard_reject`、`guard_failsafe_entered`、`guard_failsafe_cleared`、`guard_nav_gating_changed`
- 低频结构化事件文件：`nav_events.csv`、`control_events.csv`

## 1. 当前阶段

当前项目阶段不是“继续堆功能”，而是：

1. 保持控制、导航、状态传播、执行链的 C/C++ 主线可信
2. 先完成文档体系、启动边界、日志边界、工具链边界的收口
3. 在此基础上，再推进 supervisor、三传感器工具链和日志统一的最小实现

当前阶段判断：

- P0 权威状态与契约基线已建立
- P1 bring-up / reconnect / replay / 诊断仍在收口
- 外围 bridge / UI / 工具层允许继续推进，但不得侵入 authority 主链

当前已进入 Phase 0 supervisor 稳定化阶段：

1. 原型不再只是 mock 生命周期验证，而是已经开始对真实 `bench` 环境做安全烟测准备
2. 当前最关键的工作是把 preflight、运行文件和 operator 使用步骤收口为可复现基线
3. 在真实设备未就绪前，允许先把 failure-path 诊断做清楚，但不能把它写成“真实主链已验证完成”

## 2. 当前主目标

当前最高主目标是：

- 先把“项目怎么读、怎么接、怎么继续做”固定下来
- 再做低风险实现收敛，而不是直接大重构

对应当前已冻结的方向：

1. `uwnav_navd` 保持导航 authority
2. `pwm_control_program` 保持控制 authority
3. `gcs_server` 保持通信边界
4. `nav_viewd` 保持导航到控制的桥接边界
5. ROS2 继续只做外围只读 bridge / diagnostics / UI backend 候选
6. 三传感器 Python 链继续定位为工具链，不回灌 authority 主线

当前 Phase 0 supervisor 的直接目标已经收口为：

1. 在继续保持 `--pwm-dummy` 的前提下，为真实 `bench` safe smoke 提供最小可操作入口
2. 在真实设备缺失时，让 preflight 和运行文件能直接给出可读阻塞点
3. 为下一次真实设备到位后的复现提供最小 runbook

## 3. 已完成关键工作

### 3.1 架构与重构设计已冻结

已完成的设计文档：

- `docs/architecture/control_nav_integration_plan.md`
- `docs/architecture/sensor_toolchain_refactor_plan.md`
- `docs/interfaces/logging_contract.md`

这些文档已经明确：

- authority 边界
- supervisor / launcher 角色
- 三传感器工具链公共抽象方向
- 最小统一日志契约
- 分阶段实施顺序

### 3.2 文档体系已标准化

本轮已建立：

- `docs/documentation_index.md`
- `docs/handoff/CODEX_HANDOFF.md`
- `docs/handoff/CODEX_PROGRESS_LOG.md`
- `docs/handoff/CODEX_NEXT_ACTIONS.md`
- `docs/archive/archive_index.md`

并完成：

- 旧文档归档
- 活跃导航专题文档收敛到 `docs/architecture/`
- 权威基线、Working draft、Archived、Obsolete 状态标识收口

### 3.3 Phase 0 supervisor 已从原型推进到“可做安全烟测准备”

当前已落地能力：

1. 最小命令入口
   - `preflight`
   - `start`
   - `status`
   - `stop`
2. 固定启动顺序
   - `uwnav_navd`
   - `nav_viewd`
   - `pwm_control_program`
   - `gcs_server`
3. 固定退出顺序
   - `gcs_server`
   - `pwm_control_program`
   - `nav_viewd`
   - `uwnav_navd`
4. 最小运行文件维护
   - `run_manifest.json`
   - `process_status.json`
   - `last_fault_summary.txt`
   - `supervisor_events.csv`
5. `bench` profile 继续保持：
   - 真实二进制路径
   - 显式配置路径
   - `pwm_control_program --pwm-dummy`
6. `preflight` 本轮已补强到：
   - Python 版本
   - `run_root` 可写
   - `/dev/shm` 可读写
   - 进程工作目录可访问
   - 关键二进制存在且可执行
   - 关键配置文件存在且可读
   - `nav_daemon.yaml` 中设备节点可见性检查
   - `/dev/serial/by-id` 可见性提示
   - `gcs_server` UDP 端口占用检查
   - 已有 active run 检查
7. 已新增最小 operator 说明：
   - `docs/runbook/supervisor_phase0_operator_guide.md`

### 3.4 本轮实际验证结果

本轮已完成：

1. `python3 -m py_compile`：通过
2. `python3 -m unittest discover -s tools/supervisor/tests -p 'test_*.py'`：通过（4 个用例）
3. 真实 `bench` preflight：已执行
4. 真实 `bench` start failure-path：已执行并检查运行文件
5. 手动 `mock` start / status / stop 回归：已执行

本轮真实 `bench` 环境结论（2026-03-23）：

- 当前主机不存在 `/dev/ttyUSB0`
- 当前主机不存在 `/dev/ttyACM0`
- 当前主机不存在 `/dev/serial/by-id`
- 因此真实 `bench` safe smoke 被 preflight 阶段阻塞
- 本轮没有启动真实 authority 进程，这是刻意保持安全边界后的结果，不是漏做

failure-path 运行文件已验证：

- `process_status.json` 正确写成 `supervisor_state=failed`
- `last_fault_summary.txt` 正确写出 `preflight_failed`
- `supervisor_events.csv` 正确记录每一项 preflight 结果
- `run_manifest.json` 正确保留 profile、run 文件路径和预定启停顺序

mock 回归结果：

- detached `start`：通过
- `status --json`：通过
- `stop`：通过
- `supervisor_events.csv` 已验证逆序退出记录为：
  - `gcs_server`
  - `pwm_control_program`
  - `nav_viewd`
  - `uwnav_navd`

## 4. 技术边界

以下边界必须继续严格遵守：

1. 控制、导航、状态传播、执行链核心主线优先保持 C/C++。
2. Python 允许用于：
   - 启动编排
   - 传感器工具链
   - 日志解析
   - 配置检查
   - 非实时辅助模块
3. 不为了“整合”把 authority 链迁到 Python。
4. ROS2 不进入 control / nav authority 主线。
5. `shared/` 是运行时共享契约真实源；文档仓镜像不是唯一真源。
6. 当前 Phase 0 supervisor 仍然只是薄外壳，不得借机把 `gcs_server` 变成父进程；允许在 `uwnav_navd`、`nav_viewd`、`ControlGuard` 内补低频结构化事件，但不得顺手改 authority 逻辑和高频路径。

## 5. 本轮直接触碰的仓库

本轮直接改动的仓库：

- `Underwater-robot-navigation`
  - 更新 `nav_core/src/nav_core/app/nav_daemon_runner.cpp`
  - 为 `uwnav_navd` 新增低频 `nav_events.csv` 写入与首批 4 个事件
- `OrangePi_STM32_for_ROV`
  - 更新 `gateway/apps/nav_viewd.cpp`
  - 更新 `pwm_control_program/include/control_core/control_guard.hpp`
  - 更新 `pwm_control_program/src/control_core/control_guard.cpp`
  - 更新 `pwm_control_program/src/control_core/loop/control_loop_run.cpp`
  - 更新 `pwm_control_program/tests/test_v1_closed_loop.cpp`
- `UnderwaterRobotSystem`
  - 更新 `docs/architecture/logging_full_chain_audit.md`
  - 更新 `docs/interfaces/logging_contract.md`
  - 更新 handoff / progress / next actions / nightly

本轮未提交，未推送。

## 6. 当前风险

1. 本轮只补了 `uwnav_navd`、`nav_viewd`、`ControlGuard` 的第一批低频事件；`pwm_control_program` 其余边界和 `gcs_server` 仍未进入统一事件日志。
2. supervisor 已能最小自动整合 run files、child logs、低频事件入口与现有高频日志入口，但还没有直接一键代跑 `merge_robot_timeline.py` 或输出压缩归档。
3. 当前 `run_id` 在 C++ 侧优先读 `ROV_RUN_ID`，若未统一注入则仍会退回本地 fallback，跨进程完全一致性还有待后续收口。
4. 真实 `bench` / 实机环境还没有用新的结构化事件日志跑一轮现场 smoke。
5. 当前仍保留不少 stdout/stderr 调试输出，后续要避免和新的结构化事件语义重叠失控。

## 7. 下一步最建议做的事

1. 先在真实 `bench` 或最小可控环境里跑一轮带新事件日志的 smoke，确认 `nav_events.csv` / `control_events.csv` 的路径、字段和现场可读性。
2. 继续沿日志 Phase B 推进，但只补剩余高价值低频点：
   - `pwm_control_program` 的 controller / allocator / PWM 边界
   - `gcs_server` 的 command lifecycle / ack / inject 结果
3. 在第一批事件点稳定后，再进入 Phase C：统一 nav / control / comm 的低频状态快照。
4. 下一步要把新的 bundle 导出入口接到真实 bench / safe smoke 故障反馈流程里，但不要在此基础上顺手扩成复杂日志平台。

## 8. 下次启动优先阅读顺序

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/project_memory.md`
5. `docs/architecture/upgrade_strategy.md`
6. 相关接口契约与 runbook，优先：
   - `docs/runbook/local_debug_and_field_startup_guide.md`
   - `docs/runbook/incident_bundle_guide.md`
   - `docs/runbook/supervisor_phase0_operator_guide.md`
   - `docs/runbook/usb_reconnect_bench_plan.md`


## 9. 2026-03-23 导航侧传感器采集工具链防呆收口

本轮新增一条独立于 supervisor 的低风险收口线，只触碰 `Underwater-robot-navigation` 的 Python 采集 / 校验工具，不改 `uwnav_navd` authority 主逻辑。

### 已确认的问题

1. `data/2026-01-06/dvl/` 下的三份 DVL 采集文件都只有表头，没有数据行。
2. 旧采集脚本在“串口缺失 / 坏帧 / 解析 0 帧 / 非数字值”场景下，可见性不足。
3. `imu_data_verifier.py` 温度字段名写错。
4. `volt32_data_verifier.py` 错用了 IMU 时间基。
5. IMU 底层厂家驱动在串口打开失败后仍会启动循环读，导致后台持续刷 `'NoneType' object has no attribute 'write'`。

### 本轮已做的事

1. 新增统一的 Python 采集诊断工具：
   - `uwnav/io/acquisition_diagnostics.py`
   - `uwnav/io/channel_frames.py`
2. 补强 IMU / DVL / Volt32 采集脚本：
   - 为每次 session 落 `*_events_*.csv` 与 `*_session_summary_*.json`
   - 明确记录 `open_failed` / `empty_capture` / `no_parsed_frames` / `runtime_error`
   - 对串口路径缺失、坏行、异常单位、异常通道、解析 0 帧做最小防呆
3. 补强 DVL 串口接口：
   - 增加最小 `on_event` 回调
   - 增加 `stats_dict()`
   - 对 open fail / idle timeout / parse empty / callback error / read error 提供计数与事件
4. 修复 IMU failure-path：
   - `device_model.py` 打开失败时不再启动循环读
   - `IMUReader.open()` 现在会显式抛 `RuntimeError`，让上层能稳定收口为 `open_failed`
5. 修复 verifier 明确 bug：
   - `imu_data_verifier.py` 改为读取 `temperature_c`
   - `volt32_data_verifier.py` 改为 `stamp("volt0", SensorKind.OTHER)`，并复用共享通道解析器

### 本轮验证

已执行：

- `python3 -m py_compile`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- DVL 缺设备失败路径 smoke：通过，已生成 `dvl_capture_events_*.csv` 与 `dvl_capture_session_summary_*.json`
- Volt32 缺设备失败路径 smoke：通过，已生成 `volt_capture_events_*.csv` 与 `volt_capture_session_summary_*.json`
- IMU 缺设备失败路径 smoke：通过，且已确认不再出现后台无限刷屏

### 当前剩余风险

1. 真实硬件就绪时的 IMU / DVL / Volt32 实采 smoke 仍未做。
2. DVL 真实数据仍需结合水池/台架环境验证 `parsed_frames` 与 TB 表是否稳定产生。
3. Volt32 当前只做了“单位识别 + 坏值隔离”，尚未上升到通道语义级校验。
4. 统一日志大收口和三传感器公共模块抽取仍然不要提前展开。


## 10. 2026-01-26 DVL 真实原始样本已接入

新增确认：当前已经拿到一份可用的 DVL 原始采集文件：

- `/home/wys/orangepi/2026-01-26/dvl_raw_lines_20260126_104848.csv`

这份样本与 2026-01-06 的“只有表头”文件不同，包含 35761 条有效 raw 记录，已确认持续出现：

- `SA`
- `TS`
- `BI`
- `BS`
- `BE`
- `BD`

基于这份样本，本轮已把 DVL parser / 映射层收紧为：

1. `parse_lines()` 只从真实数据帧起点切块，不再把 `CZ/CS` 回显和乱码切成伪帧。
2. `_pkt_to_dvldata()` 只放行 `BI/BS/BE/BD/WI/WS/WE/WD`。
3. `SA/TS` 与噪声片段继续保留在 raw logger，但不再污染 parsed/TB。

当前基于真实样本的统计结果：

- motion/distance 帧可稳定识别为：
  - `BD=5916`
  - `BS=5907`
  - `BI=5905`
  - `BE=5905`
- 旧逻辑会误放行的 `S0 / I  / E ` 等伪帧已被压掉。


## 11. 传感器总开关已新增

当前导航侧 Python 采集链已经有一个统一入口：

- `apps/acquire/sensor_capture_launcher.py`

作用：

1. 一次拉起 `imu_logger.py`、`DVL_logger.py`、`Volt32_logger.py`。
2. 统一接收 `SIGINT/SIGTERM`，并向全部子采集脚本发起停机。
3. 额外落一份 launcher 自己的：
   - `sensor_launcher_manifest_*.json`
   - `sensor_launcher_events_*.csv`
   - `sensor_launcher_session_summary_*.json`

当前边界仍然保持：

- launcher 只做进程编排，不改各传感器脚本内部采集逻辑。
- 各传感器自己的 CSV / events / session summary 仍然各自独立落盘。
- 若任一子脚本早退，launcher 会统一停掉剩余子脚本并将本次 run 标记为 `child_failed`。

## 12. 2026-03-23 当前接续状态

截至本次会话结束，当前有两条已经实际落地、且都完成过最小验证的工作线：

1. `UnderwaterRobotSystem` 集成仓中的 Phase 0 薄 supervisor
2. `Underwater-robot-navigation` 导航仓中的三传感器 Python 采集工具链防呆收口与总开关

本次会话已确认的本地提交位置：

- `Underwater-robot-navigation`
  - 分支：`feature/nav-p0-contract-baseline`
  - 最新本地提交：`3f12bfc`
  - 提交说明：`Harden sensor capture tooling and add launcher`
- `UnderwaterRobotSystem`
  - 分支：`feature/docs-p0-baseline-alignment`
  - 最新本地提交：`a60dccd`
  - 提交说明：`Align baseline docs and add phase0 supervisor`

截至补记本段前，4 个主仓工作区都已经整理为干净状态：

1. `Underwater-robot-navigation`
2. `OrangePi_STM32_for_ROV`
3. `UnderwaterRobotSystem`
4. `UnderWaterRobotGCS`

下次继续时，建议不要再从 `stash` 或零散临时目录找状态，而是直接从上述两个本地提交和 handoff 文档接续。

下次最稳的继续顺序：

1. 若继续 supervisor：
   - 先在设备就绪环境重跑真实 `bench` safe smoke
   - 继续保持 `--pwm-dummy`
   - 只修 Phase 0 supervisor 自己暴露的问题
2. 若继续导航侧传感器工具链：
   - 先用真实 IMU / DVL / Volt32 设备跑一轮 hardware-in-the-loop smoke
   - 优先核对 launcher summary、各传感器 session summary 与 CSV 是否一致
   - 不要把当前 launcher 膨胀成 supervisor 或统一日志平台

