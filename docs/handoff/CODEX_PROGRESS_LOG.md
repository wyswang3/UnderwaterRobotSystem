# CODEX_PROGRESS_LOG

## 文档状态

- 状态：Authoritative
- 说明：按时间顺序记录 Codex 每轮完成事项、验证方式、阻塞点、文档更新与 Git 收口情况。

## 2026-03-27（本机 teleop / PWM 命令卡与本地提交准备）

### 完成内容

- 把终端 1 推荐顺序收成 `tools/supervisor/run_local_teleop_smoke.sh` 的 `up / status / down` helper。
- `local_teleop_smoke_checklist.md` 已补：
  - helper `up` 为什么会直接返回 shell
  - `14550` 端口占用时如何 `down + pgrep`
  - 带 TUI 的最短 teleop / PWM 联调命令卡
  - `logs/pwm/pwm_log_*.csv` 与 `ch*_cmd` / `ch*_applied` 的查看方式
- `local_debug_and_field_startup_guide.md` 已同步写入本机 PWM 观察入口和 `--pwm-dummy-print` 最短命令。
- `documentation_index.md` 已把本机 smoke 清单更新成当前最直接的命令入口。

### 验证结果

- `bash -n tools/supervisor/run_local_teleop_smoke.sh`：通过
- `cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem && bash tools/supervisor/run_local_teleop_smoke.sh help`：通过
- `cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem && python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_local_smoke --json`：通过，并确认当前 run 的 `child_logs_dir`、`motion_info.path` 与 `pwm_control_program` 命令行都已指向本机可读的 PWM / control 日志

### 阻塞点

1. 真实 IMU / DVL / Volt32 仍未完成实机闭环。
2. `comm_events.csv` 仍未在 `gcs_server` 落地。
3. 当前 helper 默认是 `--pwm-dummy`；如果需要真实推进器输出，必须由单独现场安全流程放行。

### 文档更新

- 更新了 `local_teleop_smoke_checklist.md`、`local_debug_and_field_startup_guide.md`、`documentation_index.md`。

### Git 收口

- 本轮变更已整理到可按仓本地提交的状态。
- 未执行 `git push`。

## 2026-03-27（teleop 诊断显示、实机 checklist 与 `comm_events.csv` 最小设计准备）

### 完成内容

- 继续只触碰 supervisor / GCS 低频只读显示 / runbook / handoff / interface docs，不碰核心 authority 主链。
- `phase0_supervisor.py status --json` 的 `sensor_inventory` 已增加更适合 operator 的诊断字段，能直接表达：
  - `not_present`
  - `optional_missing`
  - 当前设备用于哪些 capability level
- GCS GUI 现在会把 IMU / DVL 的低频诊断状态翻译成更适合实机调试的文字，不再只显示粗粒度 `device_offline`。
- 已新增 `docs/runbook/field_validation_checklist.md`，把实机前检查、teleop 流程、姿态反馈检查、relative nav 检查、bundle 导出和常见失败点顺序固定下来。
- 已把 `comm_events.csv` 的最小字段、最小事件集合和 bundle 接入路径写进权威文档，先完成设计准备，不强行进入高风险实现。

### 验证结果

- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor`：通过（14 个用例）
- `python3 -m py_compile tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m unittest tests.test_telemetry_viewmodels tests.test_gui_overview_presenter`：通过（7 个用例）
- `python3 -m py_compile src/urogcs/telemetry/ui_viewmodels.py src/urogcs/app/gui/overview_presenter.py tests/test_telemetry_viewmodels.py tests/test_gui_overview_presenter.py`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && QT_QPA_PLATFORM=offscreen bash scripts/run_gui.sh --no-auto-connect --quit-after-ms 200`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m urogcs.tools.preflight_check --rov-ip 127.0.0.1 --skip-bind-check`：通过
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile control_only --startup-profile auto --run-root /tmp/phase0_supervisor_field_prep_smoke`：通过
- `python3 tools/supervisor/phase0_supervisor.py start --profile control_only --startup-profile auto --detach --run-root /tmp/phase0_supervisor_field_prep_smoke --start-settle-s 0.2 --poll-interval-s 0.2 --stop-timeout-s 5.0`：通过
- `python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_field_prep_smoke --json`：通过，并确认 `sensor_inventory` 已输出 `count/state/note/required_for_levels/visibility`
- `python3 tools/supervisor/phase0_supervisor.py stop --run-root /tmp/phase0_supervisor_field_prep_smoke --timeout-s 5.0`：通过
- `python3 tools/supervisor/phase0_supervisor.py bundle --run-root /tmp/phase0_supervisor_field_prep_smoke --json`：通过，并确认 `run_stage=child_process_stopped_after_start`、`bundle_export_ok=true`、`required_ok=true`
- `git diff --check`：`UnderwaterRobotSystem` 与 `UnderWaterRobotGCS` 均通过

### 阻塞点

1. 真实 IMU / DVL / Volt32 实机验证仍未完成。
2. `comm_events.csv` 当前仍停留在最小设计准备，未落地到 `gcs_server`。
3. `open_failed` / `permission_denied` 仍缺稳定的 runtime 只读状态源。

### 文档更新

- 更新了 `teleop_primary_operator_lane.md`、`local_debug_and_field_startup_guide.md`、`documentation_index.md`。
- 新增了 `field_validation_checklist.md`。
- 更新了 handoff / progress / next actions / nightly。

### Git 收口

- 本轮同时修改了 `UnderwaterRobotSystem` 与 `UnderWaterRobotGCS`。
- 未执行 `git push`。

## 2026-03-27（teleop primary lane 商业化收口继续推进）

### 完成内容

- 继续只触碰 `UnderwaterRobotSystem` 的 supervisor / incident bundle / runbook，以及 `UnderWaterRobotGCS` 的只读状态表达，不触碰核心 C++ authority 主链。
- 在 `tools/supervisor/incident_bundle.py` 修正 bundle 阶段判定：stop 后导出不再误写成 `child_process_started`，而是明确写成 `child_process_stopped_after_start`。
- 在 bundle summary / CLI 输出中新增并固定：
  - `bundle_export_ok`
  - `bundle_status_meaning=artifact_completeness`
  - optional 缺失不等于 bundle 导出失败
- 在 `UnderWaterRobotGCS` 收紧 capability wording：
  - IMU / DVL 只表示 observation-level hint
  - 不再把在线传感器条件误写成 runtime authority 已升级
- 在 runbook / handoff / nightly 进一步冻结 Linux bring-up baseline：
  - 默认主路径 = teleop primary lane
  - 默认 profile = `control_only`
  - 默认 active capability = `control_only`
  - 默认必选模块 = `pwm_control_program + gcs_server`

### 验证结果

- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor tools.supervisor.tests.test_bundle_archive`：通过（15 个用例）
- `python3 -m py_compile tools/supervisor/incident_bundle.py tools/supervisor/phase0_supervisor.py tools/supervisor/bundle_archive.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m unittest tests.test_telemetry_viewmodels tests.test_gui_overview_presenter`：通过（6 个用例）
- `cd /home/wys/orangepi/UnderWaterRobotGCS && QT_QPA_PLATFORM=offscreen bash scripts/run_gui.sh --no-auto-connect --quit-after-ms 200`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m urogcs.tools.preflight_check --rov-ip 127.0.0.1 --skip-bind-check`：通过
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile control_only --startup-profile auto --run-root /tmp/phase0_supervisor_commercial_lane_smoke`：通过
- `python3 tools/supervisor/phase0_supervisor.py start --profile control_only --startup-profile auto --detach --run-root /tmp/phase0_supervisor_commercial_lane_smoke ...`：通过
- `python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_commercial_lane_smoke --json`：通过
- `python3 tools/supervisor/phase0_supervisor.py stop --run-root /tmp/phase0_supervisor_commercial_lane_smoke --timeout-s 5.0`：通过
- `python3 tools/supervisor/phase0_supervisor.py bundle --run-root /tmp/phase0_supervisor_commercial_lane_smoke --json`：通过，并确认 `run_stage=child_process_stopped_after_start`、`bundle_export_ok=true`

### 阻塞点

1. 真实 `imu_only` / `imu_dvl` bench 仍未完成。
2. `comm_events.csv` 仍未落地。
3. GCS 当前 capability 仍是 observation-level hint，不是来自 supervisor runtime 的 authoritative 升级信号；如果后续要彻底收口，需要新的跨进程状态来源。
4. 真实设备静态身份样本仍不足。

### 文档更新

- 已把 Linux bring-up / config baseline、bundle completeness 语义、设备未就绪时推荐工作方式同步到 runbook / handoff / nightly。
- 已把“设备就绪后按 `imu_only -> imu_dvl` 恢复验证”继续写死到 handoff / next actions。

### Git 收口

- 本轮同时修改了 `UnderwaterRobotSystem` 与 `UnderWaterRobotGCS`。
- 未执行 `git push`。

## 2026-03-27（teleop primary lane 与 motion/status 观察面收口）

### 完成内容

- 继续只触碰 `UnderwaterRobotSystem` 的 supervisor / GCS / runbook / handoff，不触碰核心 C++ authority 主链。
- 在 `tools/supervisor/device_profiles.py` 明确补出 capability level / summary / expected motion fields：
  - `control_only`
  - `attitude_feedback`
  - `relative_nav`
  - `full_stack_preview`
- 在 `tools/supervisor/phase0_supervisor.py` 增加 teleop primary lane 相关输出：
  - `sensor_inventory`
  - `capability`
  - `operator_lane`
  - `motion_info`
- 把 `control_only` 的 motion 信息解释收紧为：
  - `motion_info.state=not_enabled_for_capability` 属于预期
  - 不再把它写成字段映射失败
- 在 `UnderWaterRobotGCS` 收口只读状态表达：
  - GUI `Navigation` 卡片改为 `Motion Info`
  - `Devices` / `Motion Info` 卡片改成 capability-aware 文案
  - footer 明确 TUI 是 teleop 主入口、GUI 只是只读 observer
- 修正了 GCS preflight 的启动顺序 drift，不再默认要求“先起导航再起控制”。
- 新增：
  - `docs/architecture/teleop_primary_operator_lane.md`
- 更新：
  - `docs/documentation_index.md`
  - `docs/runbook/local_debug_and_field_startup_guide.md`
  - `docs/runbook/gcs_ui_operator_guide.md`
  - `docs/handoff/CODEX_HANDOFF.md`
  - `docs/handoff/CODEX_NEXT_ACTIONS.md`
  - `docs/productization/nightly_upgrade_progress.md`

### 验证结果

- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor`：通过（13 个用例）
- `python3 -m py_compile tools/supervisor/device_profiles.py tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m unittest tests.test_telemetry_viewmodels tests.test_gui_overview_presenter`：通过（6 个用例）
- `cd /home/wys/orangepi/UnderWaterRobotGCS && QT_QPA_PLATFORM=offscreen bash scripts/run_gui.sh --no-auto-connect --quit-after-ms 200`：通过
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile control_only --startup-profile auto --run-root /tmp/phase0_supervisor_teleop_primary_smoke`：通过
- `python3 tools/supervisor/phase0_supervisor.py start --profile control_only --startup-profile auto --detach --run-root /tmp/phase0_supervisor_teleop_primary_smoke ...`：通过
- `python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_teleop_primary_smoke --json`：通过
- `python3 tools/supervisor/phase0_supervisor.py stop --run-root /tmp/phase0_supervisor_teleop_primary_smoke --timeout-s 5.0`：通过
- `python3 tools/supervisor/phase0_supervisor.py bundle --run-root /tmp/phase0_supervisor_teleop_primary_smoke --json`：通过

### 阻塞点

1. 当前 GUI 仍没有新增 UDP 数值姿态/速度协议，因此数值 motion snapshot 仍主要依赖 supervisor `status --json` 与 `control_loop_*.csv`。
2. `attitude_feedback` / `relative_nav` 当前仍主要是升级能力定义和外围表达，真实激活仍依赖后续 `imu_only` / `imu_dvl` bench。
3. `comm_events.csv` 仍未落地。
4. 真实设备静态身份样本仍不足。

### 文档更新

- 已把“遥控路径优先”“IMU-only 不是完整导航”“DVL 是可选增强”“GUI/TUI/supervisor status 分工”写入新的 architecture / runbook / handoff / nightly 基线。
- 已把 `gcs_ui_operator_guide.md` 和 GCS preflight wording 同步到新的 teleop 主路径，避免继续漂移。

### Git 收口

- 本轮同时修改了 `UnderwaterRobotSystem` 与 `UnderWaterRobotGCS`。
- 未执行 `git push`。

## 2026-03-27（`control_only` 最小可运行路径与导航可选收口）

### 完成内容

- 继续只触碰 `UnderwaterRobotSystem` 的 supervisor / preflight / runbook / handoff，不触碰核心 C++ authority 主链。
- 在 `tools/supervisor/device_profiles.py` 明确补出：
  - `navigation_requirement`
  - `runtime_level_hint`
  并让 `startup-profiles --json` 直接暴露当前 startup profile 与运行等级的关系。
- 在 `tools/supervisor/phase0_supervisor.py` 新增并固定 `control_only`：
  - 作为当前默认 supervisor profile
  - `preflight` / `start` / `_run` 默认改为 `control_only`
  - `control_only` 只启动 `pwm_control_program + gcs_server`
  - `device-scan` / `startup_profile_gate` 在 `control_only` 下只表达导航 readiness，不再把导航缺失当成 fatal
- 在 `tools/supervisor/tests/test_phase0_supervisor.py` 补最小回归：
  - `control_only` preflight
  - `control_only` 下歧义设备识别仅作为 warning / info，不阻塞启动
- 新增：
  - `docs/architecture/minimum_viable_runtime_profiles.md`
- 更新：
  - `docs/documentation_index.md`
  - `docs/runbook/local_debug_and_field_startup_guide.md`
  - `docs/handoff/CODEX_HANDOFF.md`
  - `docs/handoff/CODEX_NEXT_ACTIONS.md`
  - `docs/productization/nightly_upgrade_progress.md`

### 验证结果

- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor`：通过（11 个用例）
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile control_only --run-root /tmp/phase0_supervisor_control_only_smoke`：通过
- `python3 tools/supervisor/phase0_supervisor.py start --profile control_only --detach --run-root /tmp/phase0_supervisor_control_only_smoke --start-settle-s 0.2 --poll-interval-s 0.2 --stop-timeout-s 5.0`：通过
- `python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_control_only_smoke --json`：通过，并确认只拉起 `pwm_control_program` 与 `gcs_server`
- `python3 tools/supervisor/phase0_supervisor.py stop --run-root /tmp/phase0_supervisor_control_only_smoke --timeout-s 5.0`：通过
- `python3 tools/supervisor/phase0_supervisor.py bundle --run-root /tmp/phase0_supervisor_control_only_smoke --json`：通过，并确认 nav 相关缺失键属于 optional

### 阻塞点

1. 当前仍未补到新的真实 IMU / DVL / Volt32 静态身份样本。
2. `imu_only` / `imu_dvl` 真实 bench 仍未完成。
3. GCS / GUI 当前虽然已经能显示 `Invalid / stale,invalid,NoData`，但“导航未启用”的 operator wording 仍可继续优化。
4. `control_nav_optional` 目前还是设计映射，不是独立落地的 supervisor process graph。

### 文档更新

- 已把“当前默认运行等级 = `control_only`”写入 architecture / runbook / handoff / nightly。
- 已明确：没有导航时可以做什么、不能做什么、什么时候才恢复把导航作为强依赖场景。

### Git 收口

- 本轮代码与文档改动只在 `UnderwaterRobotSystem`
- 未执行 `git push`

## 2026-03-27（商业化升级审查与路线图）

### 完成内容

- 基于当前最新代码、runbook、handoff、nightly 和阶段成果，对 UnderwaterRobotSystem 做了一轮“面向商业化落地”的项目审查。
- 新增：
  - `docs/architecture/commercialization_review.md`
- 更新：
  - `docs/documentation_index.md`
  - `docs/handoff/CODEX_HANDOFF.md`
  - `docs/handoff/CODEX_NEXT_ACTIONS.md`
  - `docs/productization/nightly_upgrade_progress.md`
- 审查结论已明确：
  1. 当前系统更接近 `bench-safe` 工程集成平台，而不是现场可稳定交付的商业化产品。
  2. 已具备产品化基础的模块主要在 supervisor、incident bundle、TUI 基线、GUI overview preview、device gate 和日志骨架。
  3. 当前最大商业化短板主要是：真实设备闭环不足、交付路径未冻结、`comm_events.csv` 缺失、文档与提示口径存在小范围漂移。
  4. 下一轮应优先收口：真实 `imu_only` / `imu_dvl` bench、operator path、delivery / config baseline。

### 验证结果

- 本轮为 docs-only 审查与路线设计。
- 已对最新 supervisor、GCS、runbook、handoff、logging contract、nightly 进行只读核对。
- 未做新的构建、单测、真机、ROS2 graph 或 replay 运行时验证。

### 阻塞点

1. 真实设备样本与 `imu_only` / `imu_dvl` bench 仍未完成。
2. `gcs_server` 命令链结构化日志仍未补齐。
3. 交付级安装 / 打包 / 版本治理仍未冻结。
4. authoritative 文档与启动提示仍有小范围漂移，需要后续继续收口。

### 文档更新

- 新增商业化审查文档，作为下一轮非导航侧产品化收口的总参考。
- 已把“先做什么、后做什么、暂缓什么”的路线图同步到 handoff / next actions / nightly。
- 已把 `documentation_index.md` 的总体基线与运行 runbook 列表对齐到当前真实执行入口。

### Git 收口

- 本轮变更只在 `UnderwaterRobotSystem` 文档仓。
- 未执行 `git push`。

## 2026-03-27（真实设备规则成熟度与 bench 前准备收口）

### 完成内容

- 继续只触碰 `UnderwaterRobotSystem` 的 supervisor / preflight / runbook / handoff，不触碰核心 C++ authority 主链。
- 在 `tools/supervisor/device_identification_rules.json` 增加字段级静态成熟度和缺失样本说明：
  - `/dev/serial/by-id`
  - `vendor_id`
  - `product_id`
  - `serial`
  - `manufacturer`
  - `product`
- 在 `tools/supervisor/device_identification.py` 增加：
  - `rule_catalog`
  - `rule_maturity_summary`
  - `static_sample_gap_summary`
  - `rule_support.static_fields`
  - `rule_support.sample_gaps`
- 在 `tools/supervisor/phase0_supervisor.py preflight` 增加：
  - `device_rule_maturity`
  - `device_static_sample_gaps`
- 补最小回归：
  - `tools/supervisor/tests/test_device_identification.py`
  - `tools/supervisor/tests/test_phase0_supervisor.py`
- 更新：
  - `docs/architecture/device_identification_and_profiles_plan.md`
  - `docs/runbook/local_debug_and_field_startup_guide.md`
  - `docs/handoff/CODEX_HANDOFF.md`
  - `docs/handoff/CODEX_NEXT_ACTIONS.md`
  - `docs/productization/nightly_upgrade_progress.md`

### 验证结果

- `python3 -m py_compile tools/supervisor/device_identification.py tools/supervisor/device_profiles.py tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_device_identification.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
- `python3 -m unittest tools.supervisor.tests.test_device_identification tools.supervisor.tests.test_phase0_supervisor`：通过（20 个用例）
- `python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json`：通过，并确认新增 `rule_catalog` / `rule_maturity_summary` / `static_sample_gap_summary`
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --startup-profile auto --run-root /tmp/phase0_supervisor_device_rule_prep`：按预期失败，但已确认新增 `device_rule_maturity` / `device_static_sample_gaps` 输出

### 阻塞点

1. 当前仍没有新增真实 `/dev/serial/by-id` / sysfs 静态快照，因此 IMU / Volt32 / DVL 静态规则仍不能升级成强绑定规则。
2. IMU live serial 主动探测仍未实现。
3. Volt32 仍缺真实 live `CHn:` 原始行样本。
4. `imu_only` / `imu_dvl` 仍未完成真实 bench `start -> status -> stop -> bundle` 全链路样本。

### 文档更新

- 已把“已验证规则 / 候选规则 / 仍需样本”的口径写入 architecture / runbook / handoff / nightly。
- 已明确为什么下一步优先做 `imu_only` / `imu_dvl`，以及为什么暂时不推进 USBL 和更复杂 profile。

### Git 收口

- 本轮代码与文档改动只在 `UnderwaterRobotSystem`
- 未执行 `git push`

## 2026-03-21

### 完成内容

- 冻结 ROS2 外围 bridge 第一阶段边界
- 补只读 `rov_state_bridge`、advisory health monitor、GCS ROS2 preview 路径
- 建立早期 `codex_handoff.md` 和 `nightly_upgrade_progress.md` 的交接方式

### 验证结果

- 进行了 Python 单测、GUI headless smoke test 与部分 dry-run 验证
- 未完成真实 ROS2 graph / rosbag2 / colcon 运行时验证

### 阻塞点

- 缺少 ROS2 toolchain
- 缺少 generated `rov_msgs` / `rclpy` 环境

### 文档更新

- ROS2 bridge / GCS preview / UI 契约相关文档同步

### Git 收口

- 当时各代码仓已有本地提交
- 文档仓同步到 ROS2 preview 与 handoff 基线

## 2026-03-22（专项审查与设计冻结）

### 完成内容

- 完成“控制与导航整合 + 通信链路统一拉起 + 三传感器工具链去屎山化 + 日志统一”专项审查
- 新增：
  - `docs/architecture/control_nav_integration_plan.md`
  - `docs/architecture/sensor_toolchain_refactor_plan.md`
  - `docs/interfaces/logging_contract.md`

### 验证结果

- 本轮为 docs-only 设计收口
- 仅进行了静态代码与文档阅读，无编译、无真机、无 rosbag2 验证

### 阻塞点

- supervisor 尚未实现
- 统一事件日志尚未真正落地
- 三传感器现场脚本使用情况未完全盘点

### 文档更新

- 设计边界、分阶段实施路线图和最小日志契约已冻结

### Git 收口

- 文档仓有新增设计文档，未提交

## 2026-03-22（文档体系标准化）

### 完成内容

- 建立标准文档目录结构：
  - `architecture`
  - `interfaces`
  - `runbook`
  - `productization`
  - `handoff`
  - `archive`
- 固定 Codex 交接体系：
  - `CODEX_HANDOFF.md`
  - `CODEX_PROGRESS_LOG.md`
  - `CODEX_NEXT_ACTIONS.md`
- 新增：
  - `docs/documentation_index.md`
  - `docs/archive/archive_index.md`
- 归档旧文档：
  - `system_overview.md`
  - `Project_Quality_Audit_Chinese_Explanation.md`
  - `first_dive_checklist.md`
  - `repo_local_change_summary_20260312.md`
  - 历史测试计划与报告
- 将活跃导航专题文档收敛到 `docs/architecture/`
- 为关键基线文档补状态标识
- 更新 `AGENTS.md` 的文档阅读顺序与优先级

### 验证结果

- 本轮为 docs-only 重构
- 已核对 docs 树、主要引用关系和 docs 仓工作树状态
- 未进行构建与运行时验证

### 阻塞点

- 仍需后续人工补充少量历史外链迁移
- 旧 `codex_handoff.md` 路径仍保留为过渡跳转，尚未完全退出所有使用习惯

### 文档更新

- 建立统一索引、archive 索引、handoff 三件套
- 夜间进展文档同步到新的文档体系收口状态

### Git 收口

- `UnderwaterRobotSystem` 文档仓：有未提交文档改动
- 其余主仓未做本轮文档改动

## 2026-03-23（实施前准备细化）

### 完成内容

- 基于现有交接文档与设计冻结文档，继续细化：
  - `supervisor / launcher`
  - 三传感器工具链去屎山化
  - 最小统一日志
- 将下一步实施顺序收口为三段：
  - 先做薄 supervisor 外壳和运行产物
  - 再做三传感器公共外壳抽取
  - 最后补 manifest 驱动的最小统一日志接线
- 明确最小可落地边界：
  - `run_manifest.json`
  - `process_status.json`
  - `last_fault_summary.txt`
  - `supervisor_events.csv`
  - 三传感器公共 `writer / timestamp / config` 外壳
- 更新：
  - `docs/handoff/CODEX_HANDOFF.md`
  - `docs/handoff/CODEX_NEXT_ACTIONS.md`
  - `docs/productization/nightly_upgrade_progress.md`

### 验证结果

- 本轮为 docs-only 收口
- 已回读：
  - `CODEX_HANDOFF.md`
  - `CODEX_NEXT_ACTIONS.md`
  - `project_memory.md`
  - `upgrade_strategy.md`
  - `control_nav_integration_plan.md`
  - `sensor_toolchain_refactor_plan.md`
  - `logging_contract.md`
- 未进行构建、单测、真机、ROS2 graph 或 replay 运行时验证

### 阻塞点

1. 三传感器现场真实入口脚本、参数兼容和默认输出目录仍缺少完整盘点。
2. supervisor 和事件日志的最小 schema 方向已明确，但还没有实现态样例可回归。
3. 文档仓当前存在较多未提交改动，后续实现时要避免和历史文档整理混淆。

### 文档更新

- handoff 已从“设计冻结”进一步推进到“实施前准备已细化”
- next actions 已改为优先执行低风险、外围、可回归验证的切口
- nightly progress 已同步更新到当前准备阶段

### Git 收口

- `UnderwaterRobotSystem` 文档仓：仅继续更新 handoff / progress / nightly 文档，未提交
- 未执行 `git push`

## 2026-03-23（Phase 0 supervisor 原型实现）

### 完成内容

- 在系统级集成仓新增 Phase 0 薄 supervisor / launcher 原型：
  - `tools/supervisor/phase0_supervisor.py`
- 新增 targeted test：
  - `tools/supervisor/tests/test_phase0_supervisor.py`
- 新增最小能力：
  - `preflight`
  - `start`
  - `status`
  - `stop`
- 新增最小运行文件：
  - `run_manifest.json`
  - `process_status.json`
  - `last_fault_summary.txt`
  - `supervisor_events.csv`
- 固定 Phase 0 profile：
  - `bench`：真实二进制 + 显式配置路径 + `--pwm-dummy`
  - `mock`：只用于 detached lifecycle 验证
- 更新 `.gitignore`：
  - 忽略 `reports/supervisor_runs/`

### 验证结果

- `python3 -m py_compile`：通过
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --run-root /tmp/phase0_supervisor_preflight --skip-port-check`：通过
- `python3 -m unittest discover -s tools/supervisor/tests -p 'test_*.py'`：通过
- 手动 mock CLI smoke：
  - `start --profile mock --detach`：通过
  - `status --run-root /tmp/phase0_supervisor_manual2 --json`：通过
  - `stop --run-root /tmp/phase0_supervisor_manual2 --timeout-s 5.0`：通过
- 未进行真实 `bench` 启动烟测、真机、ROS2 graph 或 replay 验证

### 阻塞点

1. 真实 `bench` 启动烟测尚未执行。
2. 当前 preflight 仍未覆盖真实设备路径 / by-id 可见性和更深层配置语义检查。
3. 当前未实现进程自动重启策略，也未统一子进程 stdout / stderr 收口。

### 文档更新

- `CODEX_HANDOFF.md` 已切换为“Phase 0 原型已落地”语义
- `CODEX_NEXT_ACTIONS.md` 已改为优先稳住 Phase 0 supervisor，而不是同步展开后三个方向
- `nightly_upgrade_progress.md` 已同步记录本轮代码落地与验证

### Git 收口

- `UnderwaterRobotSystem` 集成仓：新增 supervisor 工具、测试、`.gitignore` 与 handoff 文档更新，未提交
- 未执行 `git push`

## 2026-03-23（Phase 0 supervisor 安全烟测与可操作性补强）

### 完成内容

- 修复 `phase0_supervisor.py preflight` 命令中的 `NameError`。
- 补强 `preflight`：
  - `/dev/shm` 可读写检查
  - 进程工作目录可访问检查
  - 关键配置文件可读性检查
  - `nav_daemon.yaml` 中设备节点可见性检查
  - `/dev/serial/by-id` 可见性提示
- 新增最小 operator runbook：
  - `docs/runbook/supervisor_phase0_operator_guide.md`
- 补充 targeted unittest：
  - preflight CLI 回归
  - 设备路径提取纯函数测试
- 执行真实 `bench` 环境检查，并验证 preflight 失败时的运行文件落盘。
- 回归 mock detached lifecycle，确认 start / status / stop 与逆序退出未回退。

### 验证结果

- `python3 -m py_compile`：通过
- `python3 -m unittest discover -s tools/supervisor/tests -p 'test_*.py'`：通过（4 个用例）
- `python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --run-root /tmp/phase0_supervisor_bench_smoke`：执行完成，明确报出设备阻塞
- `python3 tools/supervisor/phase0_supervisor.py start --profile bench --detach --run-root /tmp/phase0_supervisor_bench_smoke ...`：执行完成，因 preflight 失败返回 1，但四个运行文件已正确生成
- `python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_bench_smoke --json`：通过，状态为 `failed`
- 手动 mock smoke：
  - `start --profile mock --detach`：通过
  - `status --json`：通过
  - `stop --timeout-s 5.0`：通过
  - `supervisor_events.csv` 已验证逆序退出顺序正确

### 阻塞点

1. 真实 `bench` 当前被设备级 preflight 阻塞：
   - `/dev/ttyUSB0` 缺失
   - `/dev/ttyACM0` 缺失
   - `/dev/serial/by-id` 缺失
2. 当前还没有在“设备已就绪”的环境上完成真实 authority 进程启动。
3. 当前仍未实现子进程 stdout / stderr 收口和自动重启策略。

### 文档更新

- 更新：
  - `docs/handoff/CODEX_HANDOFF.md`
  - `docs/handoff/CODEX_PROGRESS_LOG.md`
  - `docs/handoff/CODEX_NEXT_ACTIONS.md`
  - `docs/productization/nightly_upgrade_progress.md`
  - `docs/documentation_index.md`
- 新增：
  - `docs/runbook/supervisor_phase0_operator_guide.md`

### Git 收口

- `UnderwaterRobotSystem` 集成仓：继续只更新 `tools/supervisor/` 与文档，未提交
- 未执行 `git push`


## 2026-03-23（导航侧传感器采集工具链防呆与报错收口）

### 完成内容

- 读取并确认实验数据：`Underwater-robot-navigation/data/2026-01-06/dvl/` 下 3 份 DVL 文件均为“只有表头、无数据行”。
- 新增共享诊断与多通道解析工具：
  - `uwnav/io/acquisition_diagnostics.py`
  - `uwnav/io/channel_frames.py`
- 补强采集脚本：
  - `apps/acquire/imu_logger.py`
  - `apps/acquire/DVL_logger.py`
  - `apps/acquire/Volt32_logger.py`
- 补强 DVL/IMU 底层 Python 驱动：
  - `uwnav/drivers/dvl/hover_h1000/io.py`
  - `uwnav/drivers/imu/WitHighModbus/device_model.py`
  - `uwnav/sensors/imu.py`
- 修复 verifier 明确错误：
  - `apps/tools/imu_data_verifier.py`
  - `apps/tools/volt32_data_verifier.py`

### 核心效果

1. 三类采集脚本现在都会为每次运行落：
   - `*_events_*.csv`
   - `*_session_summary_*.json`
2. DVL/IMU/Volt32 的 failure-path 不再只是空文件或终端滚屏，而是能明确写出：
   - `open_failed`
   - `empty_capture`
   - `no_parsed_frames`
   - `runtime_error`
3. Volt32 现在能区分：
   - 通道行格式错误
   - 非数字值
   - 异常单位
   - 超出配置范围的通道号
4. IMU 打开失败时不再触发底层无限刷 `'NoneType' object has no attribute 'write'`。

### 验证结果

- `python3 -m py_compile`：通过
- `python3 -m unittest discover -s tests -p 'test_*.py'`：通过（4 个用例）
- `python3 apps/acquire/DVL_logger.py --port /tmp/not_a_dvl --data-root /tmp/uwnav_sensor_smoke_dvl --raw-only --stat-every 0`：通过，session summary 状态为 `open_failed`
- `python3 apps/acquire/Volt32_logger.py --port /tmp/not_a_volt --data-root /tmp/uwnav_sensor_smoke_volt --stat-every 0 --debug-raw-sniff 0`：通过，session summary 状态为 `open_failed`
- `python3 apps/acquire/imu_logger.py --port /tmp/not_an_imu --data-root /tmp/uwnav_sensor_smoke_imu2 --stat-every 0`：通过，session summary 状态为 `open_failed`，且无后台刷屏

### 阻塞点

1. 当前没有真实 IMU / DVL / Volt32 设备可用于硬件在环 smoke。
2. DVL 的 `2026-01-06` 样本仍然没有可用数据行，因此还不能从历史样本验证解析字段质量。
3. 统一日志扩面与三传感器公共模块抽取仍应后置。

### Git 收口

- `Underwater-robot-navigation`：新增 / 修改 Python 采集、诊断、校验与测试文件，未提交
- 未执行 `git push`


## 2026-03-23（DVL 真实样本接入后的 parser 收口）

### 新输入

- 新增真实 DVL raw 样本：`/home/wys/orangepi/2026-01-26/dvl_raw_lines_20260126_104848.csv`
- 行数：`35761`
- 已确认包含持续出现的 `SA / TS / BI / BS / BE / BD`

### 本轮修正

- 更新 `uwnav/drivers/dvl/hover_h1000/protocol.py`
  - `parse_lines()` 改为只按真实数据帧起点切块
  - 不再把命令回显和噪声片段切成伪帧
- 更新 `uwnav/drivers/dvl/hover_h1000/io.py`
  - `_pkt_to_dvldata()` 只接收 `BI/BS/BE/BD/WI/WS/WE/WD`
  - `SA/TS` 与噪声不再下沉到 parsed/TB
- 新增 `tests/test_dvl_protocol.py`

### 基于真实样本的结果

- 修正后 parser 统计：
  - `BD=5916`
  - `BS=5907`
  - `SA=5905`
  - `BI=5905`
  - `BE=5905`
  - `TS=5889`
- 修正后真正进入 `DVLData` 的只剩：
  - `BD=5916`
  - `BS=5907`
  - `BI=5905`
  - `BE=5905`
- 旧逻辑误放行的 `CZ/CS` 回显、`S0/I /E ` 等伪帧已不再进入 `DVLData`。

### 验证结果

- `python3 -m py_compile uwnav/drivers/dvl/hover_h1000/protocol.py uwnav/drivers/dvl/hover_h1000/io.py tests/test_dvl_protocol.py`：通过
- `python3 -m unittest discover -s tests -p 'test_*.py'`：通过（9 个用例）


## 2026-03-23（传感器总开关 launcher 落地）

### 完成内容

- 新增 `apps/acquire/sensor_capture_launcher.py`
- 新增 `tests/test_sensor_capture_launcher.py`

### 能力边界

1. 一次统一启动 `IMU + DVL + Volt32` 三套采集脚本。
2. 支持统一传入：
   - `data-root`
   - 子脚本日志等级
   - 子脚本统计周期
   - 各传感器串口/波特率等最小参数
3. launcher 自己会写：
   - `sensor_launcher_manifest_*.json`
   - `sensor_launcher_events_*.csv`
   - `sensor_launcher_session_summary_*.json`
4. 任一子脚本早退时，launcher 会停止剩余子脚本并把总 run 标记为 `child_failed`。

### 验证结果

- `python3 -m py_compile apps/acquire/sensor_capture_launcher.py tests/test_sensor_capture_launcher.py`：通过
- `python3 -m unittest tests.test_sensor_capture_launcher`：通过（3 个用例）
- launcher 假串口 smoke：
  - `python3 apps/acquire/sensor_capture_launcher.py --data-root /tmp/uwnav_launcher_smoke --imu-port /tmp/not_an_imu --dvl-port /tmp/not_a_dvl --volt-port /tmp/not_a_volt --child-stat-every 0 --launcher-stat-every 0`
  - 结果：launcher manifest / summary 已生成，状态为 `child_failed`，并已记录各子进程退出码

## 2026-03-23（本次会话收口：恢复本地提交并整理工作区）

### 完成内容

1. 恢复此前为了整理工作区而临时收起的本地改动。
2. 按仓整理为可继续提交 / 推送的本地 Git 提交，而不是继续留在 `stash`。
3. 清理 `ros2_bridge` 生成物与 Python `__pycache__` 干扰项，使主工作区重新回到干净状态。

### 本次确认的本地提交

- `Underwater-robot-navigation`
  - 分支：`feature/nav-p0-contract-baseline`
  - 本地提交：`3f12bfc`
  - 说明：`Harden sensor capture tooling and add launcher`
- `UnderwaterRobotSystem`
  - 分支：`feature/docs-p0-baseline-alignment`
  - 本地提交：`a60dccd`
  - 说明：`Align baseline docs and add phase0 supervisor`

### 本次额外回归验证

- 导航仓：
  - `python3 -m py_compile`：通过
  - `python3 -m unittest discover -s tests -p 'test_*.py'`：通过（12 个用例）
  - `sensor_capture_launcher.py` 假串口 smoke：重新执行，结果仍为 `child_failed`，符合预期 failure-path
- 集成 / 文档仓：
  - `python3 -m py_compile tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
  - `python3 -m unittest discover -s tools/supervisor/tests -p 'test_*.py'`：通过（4 个用例）
  - `phase0_supervisor.py start --profile mock --detach -> status --json -> stop`：重新执行，通过

### 工作区状态

在补记本条日志前，以下 4 个主仓 `git status --short` 均为空：

1. `Underwater-robot-navigation`
2. `OrangePi_STM32_for_ROV`
3. `UnderwaterRobotSystem`
4. `UnderWaterRobotGCS`

### 对下次继续的意义

1. 当前已经不需要再从 `stash` 恢复状态。
2. 下次可以直接从两个本地提交对应的分支继续推进。
3. supervisor 与传感器工具链两条线都已经有可回放的最小验证基线。



## 2026-03-25（日志 Phase B 第一批 C++ 低频事件落地）

### 完成内容

- 在 `Underwater-robot-navigation` 的 `uwnav_navd` 落地最小 `nav_events.csv` 写入路径。
- 新增 `uwnav_navd` 第一批低频事件：
  - `device_bind_state_changed`
  - `serial_open_failed`
  - `sensor_update_rejected`
  - `nav_publish_state_changed`
- 在 `OrangePi_STM32_for_ROV` 的 `nav_viewd` 落地最小 `nav_events.csv` 写入路径。
- 新增 `nav_viewd` 第一批低频事件：
  - `nav_view_decision_changed`
  - `nav_view_publish_failed`
  - `nav_view_source_recovered`
- 在 `ControlGuard` 增加低频事件回调，并在 `control_loop_run.cpp` 进程边界落地 `control_events.csv`。
- 新增 `ControlGuard` 第一批低频事件：
  - `guard_reject`
  - `guard_failsafe_entered`
  - `guard_failsafe_cleared`
  - `guard_nav_gating_changed`
- 补 `test_v1_closed_loop` 最小事件回调回归。

### 验证结果

- `cmake --build .../nav_core/build --target uwnav_navd`：通过
- `cmake --build .../OrangePi_STM32_for_ROV/build --target nav_viewd pwm_control_program test_v1_closed_loop test_nav_view_policy`：通过
- `.../build/bin/test_v1_closed_loop`：通过
- `.../build/bin/test_nav_view_policy`：通过
- `.../nav_core/build/test_serial_reconnect_integration`：通过

### 阻塞点

1. `pwm_control_program` 其余 controller / allocator / PWM 边界事件还没补进 `control_events.csv`。
2. `gcs_server` 的 `comm_events.csv` 仍未落地。
3. 新的 `nav_events.csv` / `control_events.csv` 还没有接入 supervisor manifest 与 incident bundle。
4. 真实 `bench` / 实机环境尚未验证新的事件日志收口。

### 文档更新

- 更新 `logging_full_chain_audit.md`：标明 Phase B 第一批已落地范围与剩余缺口。
- 更新 `logging_contract.md`：对齐已落地事件名、字段和 `nav_events.csv` / `control_events.csv` 最小口径。
- 更新 handoff / next actions / nightly，避免继续沿用“不要改 ControlGuard”这类已过期限制。

### Git 收口

- `Underwater-robot-navigation`、`OrangePi_STM32_for_ROV`、`UnderwaterRobotSystem` 均有未提交本地改动
- 未执行 `git push`


## 2026-03-26（外围排障闭环 Phase 1：incident bundle 最小自动整合）

### 完成内容

- 只触碰 `UnderwaterRobotSystem` 的 supervisor / tooling / runbook，不触碰核心 C++ 主链 authority 行为。
- 新增 `tools/supervisor/incident_bundle.py`，按固定目录导出：
  - supervisor run files
  - `child_logs/`
  - `events/`
  - `nav/`
  - `control/`
  - `telemetry/`
- `phase0_supervisor.py` 新增 `bundle` 子命令，支持 latest run、`--run-dir`、`--bundle-dir`、`--json`。
- 新增 `bundle_summary.json` / `bundle_summary.txt`。
- 固定 required / optional / incomplete 规则，并在 summary 里显式列出 `missing_required_keys` / `missing_optional_keys`。
- 新增 `docs/runbook/incident_bundle_guide.md`，并更新 `local_debug_and_field_startup_guide.md`，把“运行 -> 记录 -> 导出 -> 反馈 -> 复现”闭环写清楚。

### 验证结果

- `python3 -m py_compile tools/supervisor/phase0_supervisor.py tools/supervisor/incident_bundle.py tools/supervisor/tests/test_phase0_supervisor.py`：通过
- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor`：通过（7 个用例）
- 真实 `mock start -> stop -> bundle --json`：通过
  - 已确认默认输出到 `<run_dir>/bundle/<timestamp>/`
  - 已确认高频日志缺失时返回 `bundle_status=incomplete`
  - 已确认 `missing_required_keys=[]`

### 当前剩余风险

1. 当前 bundle 还是目录导出，不带压缩归档或上传能力。
2. supervisor 目前只给出 `merge_robot_timeline` 的 `ready` / `command_hint`，还没有直接一键代跑 merge。
3. 真实 `bench` / 实机环境下还没有用新的 bundle 导出流程跑一轮现场反馈演练。
4. `gcs_server` 的 `comm_events.csv` 在未落地前，会长期处于 optional missing。

### Git 收口

- 本轮实际代码与文档改动只在 `UnderwaterRobotSystem`
- 未执行 `git push`


## 2026-03-26（真实 bench run dir bundle 验证与最小归档 helper）

### 完成内容

- 在真实主机执行 `preflight --profile bench --run-root /tmp/phase0_supervisor_bench_smoke`，确认当前仍被 `bench_device_ttyUSB0` / `bench_device_ttyACM0` 阻塞。
- 执行一次真实 `start --profile bench --detach`，拿到 run dir：
  - `/tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835`
- 从该真实 `run_dir` 执行 `bundle --run-dir ... --json`，复核 `bundle_summary`、missing keys、child logs、events、高频日志收集结果。
- 新增 `tools/supervisor/bundle_archive.py`，把现有 bundle 目录最小打成同级 `.tar.gz`。
- 新增 `tools/supervisor/tests/test_bundle_archive.py`。
- 更新 `incident_bundle_guide.md` 与 `local_debug_and_field_startup_guide.md`，明确 preflight-failed 样本的 bundle 判读与归档 helper 用法。
- 修复 `tools/supervisor/tests/test_phase0_supervisor.py` 中一处未闭合字符串，恢复定向单测可执行性。

### 验证结果

- `python3 -m py_compile tools/supervisor/tests/test_phase0_supervisor.py tools/supervisor/bundle_archive.py tools/supervisor/tests/test_bundle_archive.py`：通过
- `python3 -m unittest tools.supervisor.tests.test_phase0_supervisor tools.supervisor.tests.test_bundle_archive`：通过（10 个用例）
- 真实 `phase0_supervisor.py bundle --run-dir /tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835 --json`：通过
  - `required_ok=true`
  - `bundle_status=incomplete`
  - `run_stage=preflight_failed_before_spawn`
  - 已正确收集 4 个 supervisor run files 和 8 个零字节 `child_logs`
  - `events/nav/control/telemetry` 缺失符合 failure-path 预期
- 真实 `bundle_archive.py --bundle-dir /tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835/bundle/20260326_202046 --json`：通过
  - 产出 `/tmp/phase0_supervisor_bench_smoke/2026-03-26/20260326_201943_37835/bundle/20260326_202046.tar.gz`
  - `archive_size_bytes=5037`

### 当前剩余风险

1. 本机仍缺真实 `bench` 设备节点，尚未拿到真正进入 `child_process_started` 的 safe smoke 样本。
2. `gcs_server` 的 `comm_events.csv` 未落地前，相关 artifact 仍会长期处于 optional missing。
3. 当前只做本地 `.tar.gz` 归档，不做上传或问题单集成。

### Git 收口

- 本轮实际代码与文档改动只在 `UnderwaterRobotSystem`
- 未执行 `git push`

## 2026-03-26（设备识别规则按真实样本校准）

### 完成内容

- 只触碰 `UnderwaterRobotSystem` 的 supervisor / tooling / runbook，不触碰核心 C++ authority 主链。
- 读取并分析真实样本：
  - IMU：`imu_raw_log_20260110_192246.csv`、`imu_raw_data_20240618.csv`、WIT 历史文本样本
  - Volt32：`motor_data_20240618.csv`
  - DVL：`dvl_raw_lines_20260126_102520.csv`、`dvl_raw_lines_20260110_192211.csv`
- 确认 IMU 当前 runtime 主链实际使用 `WIT Modbus-RTU` 轮询，因此被动采样不能再当 IMU 主判据。
- 把 `tools/supervisor/device_identification.py` 重写为更严格的“样本支撑 / partial / candidate_only”三层识别：
  - DVL：`SA/TS/BI/BS/BE/BD` 强动态规则
  - Volt32：`CH0..CH15` 导出 CSV + `V/A` 后缀样本规则，`CHn:` live 行保留 partial
  - IMU：导出 CSV 字段集合样本规则，旧 `0x55` 同步帧降为兼容候选
- 新增更严格的退化行为：
  - `score < 0.60` 直接回退 `unknown`
  - 高分接近候选显式标记 `ambiguous`
  - 输出 `resolution.reason`、`resolution.top_candidate`、`rule_support`
- 更新 `device_identification_rules.json`，写入样本支撑等级与剩余缺口。
- 新增样本夹具 `tools/supervisor/tests/fixtures/`，并把 `test_device_identification.py` 改成样本驱动验证。

### 验证结果

- `python3 -m py_compile tools/supervisor/device_identification.py tools/supervisor/device_profiles.py tools/supervisor/phase0_supervisor.py tools/supervisor/tests/test_device_identification.py`：通过
- `python3 -m unittest tools.supervisor.tests.test_device_identification`：通过（10 个用例）

### 当前剩余风险

1. 还没有真实 `/dev/serial/by-id` / sysfs 快照去继续收紧静态白名单。
2. IMU live serial 主动探测仍未实现，当前仍需要依赖强静态身份才能稳推 `imu_only`。
3. Volt32 还缺原始串口行日志，因此 live `CHn:` 规则仍是 partial。
4. USBL 仍没有真实样本。

### Git 收口

- 本轮实际代码与文档改动只在 `UnderwaterRobotSystem`
- 未执行 `git push`

