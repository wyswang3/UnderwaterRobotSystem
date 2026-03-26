# CODEX_NEXT_ACTIONS

## 文档状态

- 状态：Authoritative
- 说明：定义当前最高优先级任务、允许范围、禁止事项和验收标准，供下一轮 Codex 直接执行。

## 0. 2026-03-26 执行原则更新

从这一轮开始，执行原则新增以下硬约束：

1. 必须明确区分外围模块和核心 C++ 主链。
2. 外围模块包括：
   - supervisor
   - launcher
   - Python 传感器工具链
   - GCS / UI
   - 日志解析工具
   - incident bundle
   - ROS2 外围桥接
3. 核心 C++ 主链包括：
   - `uwnav_navd`
   - `nav_viewd`
   - `ControlGuard`
   - `ControlLoop`
   - `gcs_server` 核心行为
   - `NavState / NavStateView / TelemetryFrameV2` 语义相关部分
4. 若必须改核心 C++ 主链，必须同时满足：
   - 先做最小设计或代码审查
   - 一次只改一个小点
   - 一次只动一个核心 authority 模块
   - 每次都做最小可回归验证
   - 不允许大面积顺手重构
5. 后续收口时，只要涉及核心 C++ 主链改动，必须额外说明：
   - 为什么必须改这个点
   - 为什么这轮只改这个点
   - 做了哪些验证
   - 哪些风险暂时没动

## 0.1 2026-03-26 incident bundle Phase 1 当前状态

当前已经落地：

1. `tools/supervisor/incident_bundle.py`
2. `phase0_supervisor.py bundle`
3. 固定 bundle 目录与 `bundle_summary.json` / `bundle_summary.txt`
4. required / optional / incomplete 规则
5. `docs/runbook/incident_bundle_guide.md`
6. mock 缺 optional、synthetic 成功采集、required 缺失三类最小验证

因此下一轮不再把“incident bundle 最小自动整合”当成待开始事项，而是继续做外围闭环深化。

## 0.15 2026-03-26 真实 bench bundle 验证当前状态

当前已新增并确认：

1. 在本机真实 `bench` 环境下，`preflight` 仍被 `/dev/ttyUSB0` 与 `/dev/ttyACM0` 缺失阻塞。
2. 因此这轮不能宣称“真实 bench safe smoke 已完成”；当前仍是 failure-path 诊断样本。
3. 但真实 `run_dir` 的 `bundle --run-dir ... --json` 已验证通过，`required_ok=true`，`bundle_status=incomplete`，`run_stage=preflight_failed_before_spawn`。
4. 零字节 `child_logs` 已确认会被收集；`events/nav/control/telemetry` 在该样本里缺失属于预期。
5. `tools/supervisor/bundle_archive.py` 已落地，可把现有 bundle 目录打成同级 `.tar.gz`。

因此下一轮不需要重复验证“preflight 阻塞样本能否导出 bundle”；若设备就绪，应直接重跑一轮真正进入 `child_process_started` 的 `bench` safe smoke。

## 0.20 2026-03-26 设备识别 + startup profile 当前状态

当前已经新增并确认：

1. `tools/supervisor/device_identification.py` 已能输出静态身份、动态指纹、置信度、歧义标志和推荐绑定。
2. `tools/supervisor/device_profiles.py` 已固定：
   - `no_sensor`
   - `volt_only`
   - `imu_only`
   - `imu_dvl`
   - `imu_dvl_usbl`（预留）
   - `full_stack`（预留）
3. `phase0_supervisor.py preflight --profile bench --startup-profile auto` 已能：
   - 推荐 `startup_profile`
   - 在歧义时拒绝
   - 在当前只允许 `preflight_only` 时拒绝进入 `bench` authority 链
4. `run_manifest / process_status / last_fault_summary` 已能记录当前 profile 和已识别设备摘要。
5. 当前实现仍然是“外围 gate + 记录”，不是“按 profile 改写 authority 进程图”。

因此下一轮不需要再从零设计 device identification / startup profile；优先做：

1. 在真实 IMU / Volt32 / DVL 样本下校准 `device_identification_rules.json` 与动态指纹。
2. 在真实 bench 环境确认 `imu_only` / `imu_dvl` 两种场景的推荐是否稳定。
3. 如果要继续推进，只允许讨论 supervisor 的轻量 launch policy，不要直接改核心 C++ authority 主链。


## 0.25 2026-03-26 真实样本校准后的设备识别当前状态

当前已经新增并确认：

1. DVL 的动态规则已经从启发式升级为真实样本支撑。
2. Volt32 的导出 CSV 结构与 `V/A` 后缀已经从启发式升级为真实样本支撑；`CHn:` live serial 行规则仍是 partial。
3. IMU 已确认当前 runtime 主链走 `WIT Modbus-RTU` 轮询，因此被动动态探测不再被当作主判据。
4. `device_identification.py` 现在会把低置信度设备回退为 `unknown`，并把高分冲突显式标成 `ambiguous`。
5. `test_device_identification.py` 已经改成样本驱动验证。

因此下一轮最优先做：

1. 在真实 bench 上补采 `/dev/serial/by-id`、VID/PID、serial、manufacturer、product 快照。
2. 分别在真实 bench 设备集合下验证：
   - `imu_only`
   - `imu_dvl`
3. 只在 supervisor / preflight / runbook 侧继续收口，不提前改核心 authority 主链。
4. 若要继续扩设备识别，只允许补：
   - IMU 主动探测设计
   - Volt32 原始串口行样本
   - USBL 真实样本规则

## 1. 当前最高优先级任务

当前最高优先级任务是：

- 先把 `docs/runbook/local_debug_and_field_startup_guide.md` 与 `docs/runbook/incident_bundle_guide.md` 作为统一操作基线
- 继续优先推进外围模块的故障导出、问题反馈和 replay 前置检查收口
- 导航侧优先补日志、报错检查、状态暴露与调试能力
- 不先大改 ESKF 结构和核心融合逻辑
- 若必须继续碰日志 Phase B 的核心 C++ 模块，只允许单模块、单点推进

当前已落地范围（2026-03-26）：

- Phase B 第一批低频结构化事件
  - `uwnav_navd`
    - `device_bind_state_changed`
    - `serial_open_failed`
    - `sensor_update_rejected`
    - `nav_publish_state_changed`
  - `nav_viewd`
    - `nav_view_decision_changed`
    - `nav_view_publish_failed`
    - `nav_view_source_recovered`
  - `ControlGuard`
    - `guard_reject`
    - `guard_failsafe_entered`
    - `guard_failsafe_cleared`
    - `guard_nav_gating_changed`
- Phase 1 incident bundle 最小自动整合
  - `tools/supervisor/incident_bundle.py`
  - `phase0_supervisor.py bundle`
  - `bundle_summary.json` / `bundle_summary.txt`
  - fixed required / optional / incomplete 规则

## 2. 推荐实施顺序

建议按以下顺序推进：

1. 先维护和使用 `docs/runbook/local_debug_and_field_startup_guide.md` 与 `docs/runbook/incident_bundle_guide.md`
   - 统一本地调试
   - 统一板上 bring-up / field startup 前检查
   - 统一日志导出和 incident bundle 入口
2. 再优先做外围模块工作
   - supervisor / launcher
   - incident bundle / manifest 引用
   - 日志解析工具 / merge timeline / replay compare
3. 导航相关优先做诊断与状态暴露
   - 低频日志
   - 报错检查
   - 状态快照
   - 调试辅助
4. 若必须改核心 C++ 主链
   - 先选一个模块
   - 只改一个小点
   - 做最小构建与最相关回归
   - 不同轮再处理下一个模块

## 3. 本轮允许范围

下一轮允许做的范围：

1. 优先继续做 docs / runbook / supervisor / bundle / 日志工具侧更新。
2. 允许继续改动外围模块：
   - supervisor / launcher
   - Python 传感器工具链
   - GCS / UI
   - 日志解析工具
   - incident bundle
   - ROS2 外围桥接
3. 若必须改核心 C++ 主链，允许改动：
   - `uwnav_navd`
   - `nav_viewd`
   - `pwm_control_program`
   - `gcs_server`
   但必须满足：一次只动一个核心模块、一次只落一个小点、先审查再改、改后立刻做最小回归。
4. 允许继续更新：
   - `docs/architecture/logging_full_chain_audit.md`
   - `docs/interfaces/logging_contract.md`
   - `docs/runbook/local_debug_and_field_startup_guide.md`
   - `docs/runbook/incident_bundle_guide.md`
   - `docs/handoff/CODEX_HANDOFF.md`
   - `docs/handoff/CODEX_PROGRESS_LOG.md`
   - `docs/handoff/CODEX_NEXT_ACTIONS.md`
   - `docs/productization/nightly_upgrade_progress.md`

## 4. 本轮禁止事项

下一轮明确禁止：

1. 不重写 `nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`、`telemetry_timeline_*.csv`。
2. 不把低频事件日志扩成高频文本日志。
3. 不改 shared ABI。
4. 不做 `session_id` 全链路 ABI 贯通。
5. 不展开三传感器重构。
6. 不展开导航模式重构。
7. 不让 ROS2 进入 control / nav authority 主线。
8. 不把 incident bundle 的需求倒逼成 authority 主链大重写。
9. 不同时改多个核心 authority 模块。
10. 不在核心 C++ 主链里顺手做大面积重构。
11. 不在实地条件未具备前提前展开导航算法本体大调。

## 5. 依赖文档

下一轮实现前必须先对齐：

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/runbook/local_debug_and_field_startup_guide.md`
5. `docs/runbook/incident_bundle_guide.md`
6. `docs/architecture/logging_full_chain_audit.md`
7. `docs/interfaces/logging_contract.md`
8. `docs/project_memory.md`
9. `docs/documentation_index.md`

## 6. 最小验收标准

若下一轮继续推进，最低验收标准应为：

1. 受影响目标完成针对性构建，或 docs / Python 工具链完成针对性验证。
2. 最相关回归测试或 smoke 至少完成一轮。
3. 若涉及 supervisor / bundle，至少完成：`python3 -m py_compile`、定向 unittest、一次 `mock` 或 `safe smoke` run dir 导出、一次缺文件场景验证。
4. 新增日志字段和事件名与 `logging_contract.md` 对齐。
5. 不引入高频路径刷文本或共享契约漂移。
6. handoff / nightly / runbook 同步更新。
7. 若涉及核心 C++ 主链改动，收口里必须额外说明：
   - 为什么必须改这个点
   - 为什么这轮只改这个点
   - 做了哪些验证
   - 哪些风险暂时没动

## 7. 次优先级任务

在新的执行原则稳定前，不建议提前展开；稳定后再做：

1. 让 `merge_robot_timeline.py` 更顺滑地消费新的 bundle summary / command hint。
2. 在设备就绪环境里重跑一轮真正进入 `child_process_started` 的 `bench` / safe smoke，并复核 bundle / archive helper 的现场样本。
3. 继续补外围 diagnostics / launcher / GCS 工具链的收口。
4. 三传感器工具链更大范围统一。
5. ROS2 外围消费层和统一日志的对接。
6. ESKF / 导航算法本体优化。

## 8. 下次继续的最小起步顺序

建议按以下顺序接着做：

1. 先读：
   - `/home/wys/orangepi/AGENTS.md`
   - `docs/handoff/CODEX_HANDOFF.md`
   - `docs/handoff/CODEX_NEXT_ACTIONS.md`
   - `docs/runbook/local_debug_and_field_startup_guide.md`
   - `docs/runbook/incident_bundle_guide.md`
   - `docs/architecture/logging_full_chain_audit.md`
   - `docs/interfaces/logging_contract.md`
2. 先确认三个仓的本地工作树状态。
3. 先判断这轮是外围模块工作，还是必须进入核心 C++ 主链。
4. 如果是外围模块，优先做 supervisor / bundle / diagnostics / runbook。
5. 如果是核心 C++ 主链，先写出最小设计和只改一个点的理由，再开始动代码。

## 9. 下次明确不要做的事

1. 不要重新整理整个工作区历史。
2. 不要把“统一日志”做成跨仓一次性大重写。
3. 不要把新事件日志和旧 stdout/stderr 调试语义混成两套互相打架的来源。
4. 不要在没有真实收益前把低频 CSV 换成复杂日志框架。
5. 不要在一轮里同时修 `uwnav_navd`、`nav_viewd`、`ControlGuard`、`ControlLoop` 或 `gcs_server` 的多个核心点。
