# Nightly Upgrade Progress

## 日期

2026-03-21

## 当前目标

本轮目标收敛为：在不触碰 authority 主链的前提下，把 ROS2 外围桥接从“只读 mirror 基础”推进到“advisory health monitor + GCS read-only preview source”，并正式建立会话恢复与交接文档基线。

本轮只做：

1. 在控制仓继续沿用现有 `rov_msgs` / `rov_state_bridge` 边界。
2. 新增 advisory health monitor 核心与可选 ROS2 node wrapper。
3. 在 GCS 仓新增 ROS2 mirror -> `TelemetrySnapshot` 适配层和 preview source。
4. 建立 `docs/productization/codex_handoff.md`，作为后续重启后的优先恢复入口。
5. 保持控制、导航、状态传播、执行链完全不依赖 ROS2。
6. 不进入 rosbag2、写回控制、故障恢复按钮回灌或完整 ROS2 runtime 交付。

## 已完成项

### 控制仓

- 在 `rov_msgs/msg/` 新增 `HealthMonitorStatus.msg`。
- 在 `rov_state_bridge` 包内新增：
  - `health_monitor.py`
  - `ros2_health_node.py`
  - `tests/test_health_monitor.py`
  - `tools/run_health_monitor_validation.py`
- `HealthMonitorStatus` 和 `build_health_monitor_status()` 已建立在现有 mirror 字段之上。
- advisory health monitor 已能输出：
  - `severity`
  - `summary`
  - `recommended_action`
  - `imu/dvl online/reconnecting/mismatch`
  - `nav_valid/nav_stale/nav_degraded`
  - `command_status` / `command_fault_code`
- 该 monitor 明确只做外围摘要，不做安全裁决，不回灌核心链。

### GCS / UI 仓

- 新增 `src/urogcs/telemetry/ros2_mirror_adapter.py`。
- 新增 `src/urogcs/telemetry/ros2_mirror_source.py`。
- GUI 已支持 `--telemetry-source ros2` preview 入口。
- GUI preview path 复用现有：
  - `StatusTelemetry`
  - `TelemetrySnapshot`
  - `ui_viewmodels`
  - `overview_presenter`
- 没有在 GUI 中重写新的协议或状态机。
- 缺少 `rclpy` 时，ROS2 preview 会失败但不崩溃。

### 导航仓

- 本轮无代码改动。
- 继续复用既有 `NavState` / `NavStateView` 契约和导航主链作为只读源。

### 文档仓

- 更新 `rov_msgs_mapping.md`，补充 `HealthMonitorStatus`。
- 更新 `ros2_bridge_validation_guide.md`，补控制仓/GCS 仓新的验证路径。
- 更新 `telemetry_ui_contract.md`，补 GCS ROS2 preview 语义边界。
- 更新 `gcs_ui_operator_guide.md`，补 ROS2 preview 启动方式与边界。
- 新增 `codex_handoff.md`，作为后续会话恢复与交接摘要。
- 更新本进展文档。

## 修改的仓库 / 文件

### 控制仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`

本轮新增 / 更新的关键文件：

- `ros2_bridge/rov_msgs/msg/HealthMonitorStatus.msg`
- `ros2_bridge/rov_state_bridge/src/rov_state_bridge/models.py`
- `ros2_bridge/rov_state_bridge/src/rov_state_bridge/health_monitor.py`
- `ros2_bridge/rov_state_bridge/src/rov_state_bridge/ros2_health_node.py`
- `ros2_bridge/rov_state_bridge/tests/test_health_monitor.py`
- `ros2_bridge/rov_state_bridge/tools/run_health_monitor_validation.py`

### GCS / UI 仓

仓库：`/home/wys/orangepi/UnderWaterRobotGCS`

本轮新增 / 更新的关键文件：

- `src/urogcs/telemetry/ros2_mirror_adapter.py`
- `src/urogcs/telemetry/ros2_mirror_source.py`
- `src/urogcs/app/gui/gui_env.py`
- `src/urogcs/app/gui_main.py`
- `src/urogcs/app/gui/main_window.py`
- `tests/test_ros2_mirror_adapter.py`
- `tests/test_ros2_mirror_source.py`

### 导航仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`

- 本轮无代码改动。

### 文档仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`

本轮更新：

- `docs/interfaces/rov_msgs_mapping.md`
- `docs/runbook/ros2_bridge_validation_guide.md`
- `docs/interfaces/telemetry_ui_contract.md`
- `docs/runbook/gcs_ui_operator_guide.md`
- `docs/productization/nightly_upgrade_progress.md`
- `docs/productization/codex_handoff.md`

## 编译结果

### 控制仓

- `python3 -m py_compile`：通过
  - `ros2_bridge/rov_state_bridge/src/rov_state_bridge/*.py`
  - `ros2_bridge/rov_state_bridge/tests/test_*.py`
  - `ros2_bridge/rov_state_bridge/tools/*.py`

### GCS / UI 仓

- `python3 -m py_compile`：通过
  - `src/urogcs/telemetry/ros2_mirror_adapter.py`
  - `src/urogcs/telemetry/ros2_mirror_source.py`
  - `src/urogcs/app/gui/gui_env.py`
  - `src/urogcs/app/gui/main_window.py`
  - `src/urogcs/app/gui_main.py`
  - 新增测试

### ROS2 工具链状态

- 当前工作机仍缺少 `ros2` / `colcon` / `rclpy` / 生成后的 `rov_msgs` Python 包。
- 因此本轮没有做真实 ROS2 graph 编译、topic 回环或 rosbag2 验证。

## 测试结果

### 控制仓

- `cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`：通过
  - 当前共 `12` 个 Python 单测，结果 `OK`
- `cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge && PYTHONPATH=src python3 tools/run_health_monitor_validation.py`：通过
- 既有 `run_sample_bridge_validation.py` 仍通过。

### GCS / UI 仓

- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`：通过
  - 当前共 `15` 个 Python 单测，结果 `OK`
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --no-auto-connect --quit-after-ms 200`：通过
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --no-auto-connect --telemetry-source ros2 --quit-after-ms 200`：通过
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --telemetry-source ros2 --quit-after-ms 200`：通过
  - 缺少 ROS2 runtime 时失败但不崩溃

## 更新的文档

本轮更新后的参考文档包括：

- `docs/interfaces/rov_msgs_mapping.md`
- `docs/runbook/ros2_bridge_validation_guide.md`
- `docs/interfaces/telemetry_ui_contract.md`
- `docs/runbook/gcs_ui_operator_guide.md`
- `docs/productization/nightly_upgrade_progress.md`
- `docs/productization/codex_handoff.md`

## 本地 Git 收口情况

### 控制仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`
- 分支：`feature/control-p0-status-telemetry-baseline`
- 本轮源码提交：`8e535ac` `Add advisory ROS2 health monitor preview`
- 工作区：干净

### GCS / UI 仓

- 路径：`/home/wys/orangepi/UnderWaterRobotGCS`
- 分支：`feature/gcs-p0-status-telemetry-alignment`
- 本轮源码提交：`559bf19` `Add ROS2 mirror preview source for GUI`
- 工作区：干净

### 导航仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`
- 分支：`feature/nav-p0-contract-baseline`
- 当前参考提交：`2329255` `Refresh navigation readmes for developers`
- 工作区：干净

### 文档仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`
- 分支：`feature/docs-p0-baseline-alignment`
- 当前稳定参考提交：`bf077a2` `Document ROS2 preview health monitor and GCS source`
- 本轮 `nightly` / `handoff` 更新已纳入本次文档改动
- 工作区目标：干净

## 当前阻塞点

- 本机没有 ROS2 toolchain，不能验证真实 `rclpy` 订阅、generated msg、topic graph 和 rosbag2。
- 当前 `/rov/telemetry` preview 路径没有独立 transport session topic，因此 `session_established` / `link_alive` 只能从 `system.session_state` 做保守推断。
- health monitor 目前只做到 advisory summary，还没有真正 ROS2 graph 下的发布回环验证。

## 剩余风险

- 不能把当前 preview 描述成“核心系统已完成 ROS2 集成”。
- 不能把 GCS ROS2 preview 描述成可替代 UDP teleop 主路径。
- 不能把 `HealthMonitorStatus` 描述成安全 authority 或恢复执行入口。
- `rosbag2`、故障恢复按钮、完整 UI backend 仍未完成。

## 下一步建议

1. 在有 ROS2 toolchain 的 Linux 主机上补 generated msg、`rclpy` topic 回环和 `/rov/health_monitor` 真发布验证。
2. 若要继续 UI backend，优先补独立 transport/session mirror，而不是直接扩大控制入口。
3. 若要做 rosbag2，只先录只读 mirror topic，不引入任何写回路径。
4. 故障恢复按钮若后续要做，只能接现有安全入口，不得绕过 `gcs_server` / `ControlIntent` authority。
