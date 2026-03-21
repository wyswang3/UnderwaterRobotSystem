# Codex Handoff

## 当前项目阶段

当前阶段是：在既有 C/C++ 核心控制/导航主链不变的前提下，补外围产品化能力。

当前已落到的 ROS2 范围只有外围桥接第一阶段后半段：

- 第一批 `rov_msgs` mirror 已冻结
- 只读 `rov_state_bridge` 已建立
- advisory health monitor 已落地
- GCS GUI 已支持 read-only ROS2 preview source

项目还没有进入“核心系统整体 ROS2 化”阶段，也不允许进入这个方向。

## 当前最重要的技术结论与边界

1. 核心 authority 不能迁到 ROS2。
   - `nav_core`
   - `nav_daemon_runner`
   - `nav_viewd`
   - `ControlLoop`
   - `ControlGuard`
   - `ControllerManager`
   - PWM/STM32 执行链
   - `gcs_server` 控制入口边界
2. ROS2 当前只允许做外围桥接层、诊断层、UI backend 层、日志/工具层。
3. 时间语义不能漂移。
   - `stamp_ns` / `mono_ns` / `t_ns` 继续保持 `uint64` monotonic / steady 语义
   - `age_ms` 继续保持权威年龄语义，不能改算成 topic latency 或 wall time
4. `fault_code`、`status_flags`、`nav_valid/nav_stale/nav_degraded`、`command_result` 必须按权威字段镜像，不能在 bridge 或 UI 层重算成另一套 authority 语义。
5. `HealthMonitorStatus` 只是外围 advisory 摘要，不是新的安全 authority，也不能回灌核心链。
6. GCS `telemetry_source=ros2` 当前只是只读 preview，不替代 UDP teleop 主路径。

## 各仓库当前状态

### 控制仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`
- 分支：`feature/control-p0-status-telemetry-baseline`
- 关键提交：
  - `8e535ac` `Add advisory ROS2 health monitor preview`
  - `077589c` `Add read-only ROS2 state bridge stage1`
- 工作区：干净

### GCS / UI 仓

- 路径：`/home/wys/orangepi/UnderWaterRobotGCS`
- 分支：`feature/gcs-p0-status-telemetry-alignment`
- 关键提交：
  - `559bf19` `Add ROS2 mirror preview source for GUI`
  - `bfd6be6` `update-in-2026-0321`
- 工作区：干净

### 导航仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`
- 分支：`feature/nav-p0-contract-baseline`
- 关键提交：
  - `2329255` `Refresh navigation readmes for developers`
- 工作区：干净

### 文档仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`
- 分支：`feature/docs-p0-baseline-alignment`
- 关键提交：
  - `bf077a2` `Document ROS2 preview health monitor and GCS source`
  - `401c733` `Document ROS2 bridge stage1 baseline`
- 本轮 `nightly` / `handoff` 更新已纳入当前文档改动
- 工作区目标：干净

## 本轮已完成内容

1. 控制仓新增 `HealthMonitorStatus.msg`、`health_monitor.py`、`ros2_health_node.py` 和对应测试/验证工具。
2. GCS 仓新增 ROS2 mirror -> `StatusTelemetry` / `TelemetrySnapshot` 适配层，并让 GUI 支持 `--telemetry-source ros2`。
3. 已完成本地最小验证：
   - 控制仓 `12` 个 Python 单测通过
   - GCS 仓 `15` 个 Python 单测通过
   - GUI headless ROS2 preview smoke test 通过
4. 文档已同步到当前边界，并新增本交接文档。

## 当前未完成项与已知风险

1. 当前工作机缺少 `ros2`、`colcon`、`rclpy` 和生成后的 `rov_msgs` Python 包。
2. 因此尚未完成：
   - 真实 ROS2 graph 回环验证
   - `colcon build`
   - rosbag2 录包 / 回放
   - 真正的 ROS2 UI backend 运行时部署
   - 故障恢复按钮回灌
3. `/rov/telemetry` preview 路径当前没有独立 transport/session topic，`session_established` / `link_alive` 仍是从 `system.session_state` 做保守推断。
4. 不能把当前阶段描述成“核心系统已完成 ROS2 集成”或“GUI 已是完整商业化平台”。

## 下一步最建议做的 1~3 件事

1. 在有 ROS2 toolchain 的 Linux 主机上补 `rov_msgs` 真生成和 `rclpy` topic 回环验证。
2. 在外围 bridge 基线不变的前提下，补独立 transport/session mirror topic，减少 GCS ROS2 preview 对 `session_state` 的保守推断。
3. 若继续做外围产品化，优先做 rosbag2 只读录包与 health monitor 真发布验证，不要先做写回按钮或 control authority 迁移。

## 下次启动时应优先阅读的文档清单

1. `/home/wys/orangepi/AGENTS.md`
2. `/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/project_memory.md`
3. `/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/architecture/upgrade_strategy.md`
4. `/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/productization/codex_handoff.md`
5. `/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/docs/productization/nightly_upgrade_progress.md`

说明：

- `nightly_upgrade_progress.md` 保留详细过程记录。
- `codex_handoff.md` 保留高密度恢复摘要。
- 后续每轮结束时，两份文档都必须同步更新。
