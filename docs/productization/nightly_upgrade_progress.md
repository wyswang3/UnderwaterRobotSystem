# Nightly Upgrade Progress

## 日期

2026-03-21

## 当前目标

本轮目标严格收敛为 ROS2 外围桥接第一阶段：冻结第一批 `rov_msgs`、建立只读状态 bridge、完成最小验证。

本轮只做：

1. 以现有 `shared/msg/*` 和接口契约为真源，冻结第一批 `rov_msgs` mirror 消息。
2. 落一个只读 bridge，把权威 SHM 状态镜像到外围 topic。
3. 补齐字段映射、时间语义、只读边界和最小验证文档。
4. 保持核心控制、导航、状态传播、执行链完全不依赖 ROS2。

## 已完成项

- 在控制仓新增 `ros2_bridge/` 边界目录。
- 新增第一批 `rov_msgs/msg/*.msg`：
  - `TelemetryFrameV2.msg`
  - `NavStateView.msg`
  - `NavState.msg`
  - `HealthSummary.msg`
  - `CommandResult.msg`
  - `EventRecord.msg`
  - `ControlIntentState.msg`
  - `MotorTestState.msg`
  - `ControlState.msg`
  - `SystemState.msg`
- 新增 `rov_state_bridge` Python bridge：
  - `layouts.py`
  - `mapping.py`
  - `shm_reader.py`
  - `publisher_backend.py`
  - `bridge.py`
  - `cli.py`
- bridge 已支持三类 backend：
  - `recording`
  - `stdout`
  - `ros2`（本地仅做可选实现，未在当前环境跑通）
- 默认 bridge topic 已固定：
  - `/rov/telemetry`
  - `/rov/health`
  - `/rov/nav_view`
  - `/rov/nav_state_raw`
- 默认只读数据源已固定：
  - `/rovctrl_telemetry_v2`
  - `/rovctrl_nav_view_v1`
  - `/rov_nav_state_v1`
- 新增 `tools/run_sample_bridge_validation.py`，用于没有 ROS2 runtime 时的 deterministic dry-run。
- 新增并跑通最小单测，覆盖：
  - 字段映射正确性
  - 只读 SHM 读取
  - ABI/layout 尺寸一致性
  - 发布失败隔离

## 修改的仓库 / 文件

### 控制仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`

本轮新增 / 更新的关键文件：

- `ros2_bridge/README.md`
- `ros2_bridge/rov_msgs/msg/*.msg`
- `ros2_bridge/rov_state_bridge/src/rov_state_bridge/*.py`
- `ros2_bridge/rov_state_bridge/tests/test_mapping.py`
- `ros2_bridge/rov_state_bridge/tests/test_bridge.py`
- `ros2_bridge/rov_state_bridge/tests/test_shm_reader.py`
- `ros2_bridge/rov_state_bridge/tests/test_layout_contracts.py`
- `ros2_bridge/rov_state_bridge/tools/run_sample_bridge_validation.py`

说明：

- 控制仓本轮只新增外围 bridge 代码，不修改控制主循环、PWM、gateway authority 边界。

### 导航仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`

- 本轮无代码改动。
- 本轮只继续复用既有 `NavState` 契约和导航主链作为只读源。

### GCS / UI 仓

仓库：`/home/wys/orangepi/UnderWaterRobotGCS`

- 本轮无代码改动。
- 当前只把 ROS2 bridge 视为未来 UI backend 的外围输入，不改现有 GCS 状态来源。

### 文档仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`

本轮更新：

- `docs/architecture/upgrade_strategy.md`
- `docs/interfaces/telemetry_ui_contract.md`
- `docs/productization/nightly_upgrade_progress.md`
- `docs/architecture/ros2_bridge_stage1_plan.md`
- `docs/interfaces/rov_msgs_mapping.md`
- `docs/runbook/ros2_bridge_validation_guide.md`

说明：

- 文档仓同时保留上一轮 `ros2_refactor_assessment.md`，作为本轮实施依据。

## 编译结果

### 控制仓

- `python3 -m py_compile`：通过
  - `ros2_bridge/rov_state_bridge/src/rov_state_bridge/*.py`
  - `ros2_bridge/rov_state_bridge/tests/test_*.py`
  - `ros2_bridge/rov_state_bridge/tools/run_sample_bridge_validation.py`

### ROS2 工具链状态

- 当前工作机缺少 `ros2` / `colcon` / `rclpy` / 生成后的 `rov_msgs` Python 包。
- 因此本轮没有做真实 ROS2 graph 编译或 topic 回环验证。
- 这属于环境限制，不属于 bridge 设计边界改变。

## 测试结果

- `cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`：通过
- 当前 `rov_state_bridge` 共运行 `9` 个 Python 单测，结果 `OK`
- `cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge && PYTHONPATH=src python3 tools/run_sample_bridge_validation.py`：通过
  - 成功发布 `/rov/telemetry`、`/rov/health`、`/rov/nav_view`、`/rov/nav_state_raw`
  - `stamp_ns` / `t_ns` / `age_ms` / `fault_code` / `status_flags` 与样本源一致
- `cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge && PYTHONPATH=src python3 -m rov_state_bridge --backend stdout --once`：通过
  - 在当前机器已有 live telemetry SHM 时可直接输出 mirror JSON

## 更新的文档

本轮更新后的参考文档包括：

- `docs/architecture/upgrade_strategy.md`
- `docs/interfaces/telemetry_ui_contract.md`
- `docs/productization/nightly_upgrade_progress.md`
- `docs/architecture/ros2_bridge_stage1_plan.md`
- `docs/interfaces/rov_msgs_mapping.md`
- `docs/runbook/ros2_bridge_validation_guide.md`

## 本地 Git 收口情况

### 控制仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`
- 分支：`feature/control-p0-status-telemetry-baseline`
- 工作区：待收口

### 导航仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`
- 分支：`feature/nav-p0-contract-baseline`
- 工作区：干净

### GCS / UI 仓

- 路径：`/home/wys/orangepi/UnderWaterRobotGCS`
- 分支：`feature/gcs-p0-status-telemetry-alignment`
- 工作区：未改动

### 文档仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`
- 分支：`feature/docs-p0-baseline-alignment`
- 工作区：待收口

## 当前阻塞点

- 本地环境缺少完整 ROS2 toolchain，无法完成 colcon build 和真实 ROS2 topic 订阅回环。
- 当前 stage1 只冻结 `.msg` 文件和 Python bridge，还没有 package.xml / CMake / installer 级收口。

## 剩余风险

- 不能把当前 bridge 描述成“ROS2 已接管系统”。
- `HealthSummary` 是从 `TelemetryFrameV2.system` 派生的紧凑镜像，不是新的 authority。
- `ControlIntent` 仍然不能作为 ROS2 权威控制通道。
- 当前默认只验证了 Linux 上的 `/dev/shm` 只读路径。

## 下一步建议

1. 在有 ROS2 toolchain 的 Linux 主机上补 colcon / generated msg / `rclpy` 真实发布验证。
2. 基于当前 mirror topic 做 health monitor 和 UI backend，只消费只读 topic。
3. 若需要外围服务接口，先从 bench / diagnostics action 或 service 开始，不碰 authority 控制入口。
4. 后续若要引入 rosbag2，也必须先保持 `stamp_ns` / `age_ms` 原语义不变。
