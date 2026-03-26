# CODEX_PROGRESS_LOG

## 文档状态

- 状态：Authoritative
- 说明：按时间顺序记录 Codex 每轮完成事项、验证方式、阻塞点、文档更新与 Git 收口情况。

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
