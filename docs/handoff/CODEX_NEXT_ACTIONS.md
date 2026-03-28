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

## 0.30 2026-03-27 真实 bench 前准备当前状态

当前已经新增并确认：

1. `device-scan --json` 已能直接输出：
   - `rule_catalog`
   - `rule_maturity_summary`
   - `static_sample_gap_summary`
2. `preflight --profile bench --startup-profile auto` 已能直接输出：
   - `device_rule_maturity`
   - `device_static_sample_gaps`
3. 当前规则成熟度应按以下口径执行：
   - IMU：静态规则仍全是 `candidate_only`，动态规则仍是 `partial`
   - DVL：动态规则已是 `sample_backed`，静态规则仍全是 `candidate_only`
   - Volt32：导出样本支撑已足够，但 live `CHn:` 仍是 `partial`，静态规则仍全是 `candidate_only`
4. 当前没有新增真实 `/dev/serial/by-id` / sysfs 样本，因此本轮不应宣称“静态规则已完成收口”。

因此下一轮最优先做：

1. 在真实 bench 上补采：
   - `/dev/serial/by-id`
   - `vendor_id / product_id / serial`
   - `manufacturer / product`
2. 按固定顺序验证：
   - `imu_only`
   - `imu_dvl`
3. 继续只在 supervisor / preflight / runbook 侧推进，不改核心 authority 主链。
4. 暂时不推进 USBL、`imu_dvl_usbl` 或 `full_stack`。

## 0.35 2026-03-27 商业化审查后的执行优先级

当前总体判断：

1. 项目已经具备 `bench-safe` 集成平台与 operator preview 基础，但还不是现场可稳定交付的商业化产品。
2. 下一轮应先把“真实 bench + operator path + delivery path”收口，再考虑任何新的核心链路增强。

因此下一轮按以下顺序执行：

1. 如果真实设备已就绪：
   - 先补静态身份快照
   - 再做 `imu_only` 真实 bench `start -> status -> stop -> bundle`
   - 再做 `imu_dvl` 真实 bench `start -> status -> stop -> bundle`
2. 如果真实设备暂未就绪：
   - 先修正 GCS preflight 与 runbook / supervisor 的启动顺序口径漂移
   - 先收口 `documentation_index.md` 与新基线 runbook 的引用关系
   - 再补 Linux / Windows 依赖与启动边界说明
3. 在外围收口稳定前，只允许把 `comm_events.csv` 当成“下一个候选核心小点”做最小设计或最小实现，不允许并行改多个核心 C++ 模块。
4. 下一轮若继续做商业化收口，优先顺序固定为：
   - 真实设备闭环
   - operator path
   - delivery / config baseline
   - command / comm observability
5. 暂不推进：
   - USBL、`imu_dvl_usbl`、`full_stack`
   - 导航融合 / ESKF 大改
   - ROS2 写回或 authority 化
   - GUI 平台化重做

## 0.60 2026-03-27 当前本机执行口径：优先使用 helper 和最短 PWM 联调命令卡

在真实设备未完全就绪前，当前本机默认执行方式继续固定为：先用 helper 跑 teleop primary lane，再按需要查看 PWM 日志，不扩新主路径。

因此当前默认顺序固定为：

1. 终端 1 优先使用：`bash tools/supervisor/run_local_teleop_smoke.sh up|status|down`。
2. 如果 helper `up` 返回 shell，不要直接判失败；它使用的是 `start --detach`。真正状态以 `run_local_teleop_smoke.sh status` 和 `pgrep -af "gcs_server|phase0_supervisor.py|pwm_control_program"` 为准。
3. 如果出现 `14550` 端口占用，优先：
   - 用同一个 `RUN_ROOT` 执行 `run_local_teleop_smoke.sh down`
   - 再查 `pgrep`
4. 当前本机 PWM 反馈优先看：
   - `OrangePi_STM32_for_ROV/logs/pwm/pwm_log_*.csv`
   - 重点列：`ch*_cmd`、`ch*_applied`
5. 如果只想本机验证 PWM 计算链，不带 teleop，可单独执行：
   - `./pwm_control_program --no-teleop --pwm-dummy --pwm-dummy-print`
6. 设备就绪后恢复顺序仍固定为：
   - `imu_only`
   - `imu_dvl`

额外要求：

- 当前继续默认停在 `control_only`。
- `IMU-only` 继续只解释成 `attitude_feedback`。
- `DVL` 继续只解释成外接可选增强。

## 0.55 2026-03-27 下一轮继续执行口径：先完成实机前 checklist 与最小 comm 排障链

当前由于真实设备仍未完全就绪，下一轮继续只做 teleop primary lane 的实机前准备，不扩新主路径。

因此下一轮优先顺序固定为：

1. 保持默认主路径不变：teleop primary lane。
2. 保持默认能力等级不变：`control_only`。
3. 当前继续把 IMU / DVL 只当成增强观察条件：
   - `attitude_feedback`
   - `relative_nav`
4. 若继续补代码，只允许做这些外围小点：
   - `comm_events.csv` 的最小低频落地
   - supervisor / GUI 诊断 wording
   - runbook / checklist / bundle 指南
5. 若设备就绪，恢复验证顺序固定为：
   - `imu_only`
   - `imu_dvl`
6. 当前继续禁止：
   - 自动控制主路径扩面
   - 导航融合 / ESKF 大改
   - USBL / `full_stack`
   - ROS2 authority 化

额外要求：

- `open_failed` / `permission_denied` 没有稳定 runtime 状态源之前，不要在 GUI 里伪造细粒度原因。
- `comm_events.csv` 一旦开始实现，也只允许先做 `gcs_server` 单点、低频 CSV，不并行扩多个核心模块。

## 0.50 2026-03-27 下一轮继续执行口径：先做 teleop primary lane 商业化收口

当前由于真实设备仍未就绪，下一轮继续只做非导航侧商业化收口，不新增主路径。

因此下一轮按以下顺序执行：

1. 当前默认主路径继续固定为 teleop primary lane：
   - `device-check -> device-scan -> startup-profiles -> preflight -> start -> status -> teleop -> stop -> bundle`
2. 当前默认能力等级继续固定为：`control_only`。
3. 当前已成熟、可直接使用的能力只有：
   - `control_only`
   - teleop primary lane
   - bundle export / bundle triage 新语义
4. 当前已定义、但还不能写成“已实机闭环”的能力只有：
   - `attitude_feedback`
   - `relative_nav`
5. 当前仍只保留为预留能力的是：
   - `full_stack_preview`
6. 若设备仍未就绪，下一轮优先做：
   - 继续补 Linux delivery / config baseline
   - 继续补 operator wording / Motion Info 说明
   - 继续补 `comm_events.csv` 的最小设计或最小实现准备
7. 若设备已就绪，恢复顺序固定为：
   - 静态身份快照补采
   - `imu_only`
   - `imu_dvl`
8. 当前继续禁止：
   - 自动控制主路径扩面
   - 导航融合 / ESKF 大改
   - USBL / `full_stack`
   - ROS2 authority 化

额外要求：

- GCS / GUI 当前 capability 只能解释成 observation-level hint，不得包装成 runtime authority 已升级。
- bundle `incomplete` 必须继续解释成 artifact completeness，不得再写成 bundle 导出失败。

## 0.45 2026-03-27 当前默认执行口径：teleop primary lane 优先

当前由于真实设备仍未完全就绪，下一轮执行优先级已经进一步收口为：先把“遥控 + 状态观察 + 日志导出 + bundle”这条主路径做成唯一稳定 operator lane。

因此下一轮按以下顺序执行：

1. 默认只围绕当前 teleop primary lane 推进：
   - `device-check`
   - `device-scan`
   - `startup-profiles`
   - `preflight`
   - `start`
   - `status`
   - `teleop`
   - `stop`
   - `bundle`
2. 当前 capability 口径必须固定为：
   - `control_only`：当前默认激活能力
   - `attitude_feedback`：IMU-only 升级能力，不得写成完整导航
   - `relative_nav`：IMU + DVL 升级能力，不得写成绝对定位
   - `full_stack_preview`：继续保留，不展开
3. 若设备仍未就绪，下一轮最值得做的是：
   - 继续补 GCS wording / operator guidance
   - 继续补 bundle 摘要 / status 文案
   - 继续补 Linux delivery / config baseline
4. 若设备已就绪，再按固定顺序恢复：
   - 静态身份快照补采
   - `imu_only`
   - `imu_dvl`
5. 当前继续禁止：
   - 自动控制主路径扩面
   - 导航融合 / ESKF 大改
   - USBL / `full_stack`
   - ROS2 authority 化
   - GUI 平台化重写

额外要求：

- 任何输出都必须明确区分 `active capability` 和 `device-ready capability`。
- 不允许因为“IMU / IMU + DVL 已识别”就把 `control_only` runtime 误写成当前已经进入姿态反馈或相对导航。

## 0.40 2026-03-27 当前默认执行口径：先收口 `control_only`

当前由于真实导航设备暂未就绪，默认执行口径已经切换为：先把 `control_only` 做成唯一稳定 operator lane，再把导航当成条件满足时的可选增强模块。

因此从下一轮开始，按以下规则执行：

1. `control_only` 是当前默认运行等级。
2. `bench` 不再是默认启动路径，只是 nav preview / safe smoke lane。
3. `startup_profile=no_sensor / volt_only` 不再被解释成“整个系统 fatal”；当前只表示导航未启用或导航 readiness 不满足。
4. 只有在静态身份样本补齐、`imu_only` / `imu_dvl` 真实 bench 完成后，才恢复把导航当成强依赖场景。

因此下一轮最优先顺序固定为：

1. 如果设备仍未就绪：
   - 继续围绕 `control_only` 做 operator lane / runbook / bundle / delivery baseline 收口
   - 允许继续补极小 supervisor / preflight / GCS 提示
   - 不再把“导航未起”当成默认阻塞项
2. 如果设备已就绪：
   - 先补静态身份快照
   - 再做 `imu_only` 真实 bench
   - 再做 `imu_dvl` 真实 bench
3. 暂不推进：
   - USBL、`imu_dvl_usbl`、`full_stack`
   - 导航融合 / ESKF 大改
   - ROS2 authority 化
   - GUI 平台化重写

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
