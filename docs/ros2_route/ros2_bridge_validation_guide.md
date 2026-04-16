# ROS2 Bridge Validation Guide

## 适用范围

本文档给出 2026-03-21 当前基线下 ROS2 外围桥接的最小到完整本机验证路径。

当前验证目标是：

1. 确认 mirror 字段与权威 shared contract 一致。
2. 确认 bridge / health monitor / GCS preview 都是只读旁路。
3. 确认 `rov_msgs` 已能通过 `colcon build` 生成并被 ROS2 graph 正常使用。
4. 确认 `/rov/telemetry`、`/rov/health`、`/rov/nav_view`、`/rov/nav_state_raw`、`/rov/health_monitor` 可发布、订阅、录包、回放。
5. 明确哪些项已在本机验证，哪些仍需要真机与现场联调。

## 1. 环境前提

当前最低要求：

- Linux 主机
- `/opt/ros/humble`
- `colcon`
- `ros2`
- 现有仓库代码已同步

当前工作区有一个关键环境注意事项：

- 若当前 shell 落在 conda Python 3.11 环境中，`rosidl` 生成阶段可能找不到 ROS2 Humble 依赖的 `lark`。
- 本机已验证通过的构建路径使用系统 Python：`/usr/bin/python3`。
- 因此，真实 ROS2 build / graph / rosbag 验证都应使用：`PATH=/usr/bin:/bin:$PATH` 并显式 source ROS2 setup。

说明：

- 若本机缺少 `ros2` / `colcon` / `rclpy` / 生成后的 `rov_msgs` Python 包，则仍可执行 dry-run 与 source-only 单测，但不能宣称完成真实 ROS2 graph 验证。

## 2. ROS2 Workspace Build

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge
PATH=/usr/bin:/bin:$PATH . /opt/ros/humble/setup.bash
colcon build --event-handlers console_direct+   --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3
. install/setup.bash
```

预期：

- `colcon list` 能看到 `rov_msgs` 和 `rov_state_bridge`
- `colcon build` 成功完成
- `install/` 下出现生成后的 `rov_msgs` 接口与 `rov_state_bridge` 可执行入口

当前本机已验证通过。

## 3. 生成消息与包入口验证

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge
PATH=/usr/bin:/bin:$PATH . /opt/ros/humble/setup.bash
. install/setup.bash
ros2 interface show rov_msgs/msg/HealthMonitorStatus
ros2 pkg executables rov_state_bridge
```

补充验证：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge
PATH=/usr/bin:/bin:$PATH . /opt/ros/humble/setup.bash
. install/setup.bash
/usr/bin/python3 rov_state_bridge/tools/run_ros2_graph_validation.py
```

这个脚本额外检查：

- 生成后的 `rov_msgs.msg.*` 顶层字段名与 `rov_state_bridge.models.*` 一致
- `/rov/telemetry`
- `/rov/health`
- `/rov/nav_view`
- `/rov/nav_state_raw`
- `/rov/health_monitor`

当前本机已验证通过，且 `/rov/health_monitor.summary == "device_reconnecting"`。

## 4. 控制仓代码语法检查

在控制仓执行：

```bash
python3 -m py_compile   ros2_bridge/rov_state_bridge/src/rov_state_bridge/*.py   ros2_bridge/rov_state_bridge/tests/test_*.py   ros2_bridge/rov_state_bridge/tools/*.py
```

预期：

- 无报错退出。

## 5. 控制仓单测验证

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

当前覆盖点：

- 字段映射正确性
- `age_ms` / `fault_code` / `status_flags` 等语义保留
- 只读 SHM/file-backed 读取
- ABI/layout 尺寸一致性
- 发布失败不影响其他 topic
- advisory health monitor 的摘要和建议动作

## 6. Bridge Deterministic Dry-Run

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 tools/run_sample_bridge_validation.py
```

预期至少看到：

- `/rov/telemetry`
- `/rov/health`
- `/rov/nav_view`
- `/rov/nav_state_raw`

关键字段检查：

- `/rov/telemetry.payload.stamp_ns == 123456789`
- `/rov/telemetry.payload.system.nav_age_ms == 88`
- `/rov/telemetry.payload.system.nav_fault_code == 42`
- `/rov/nav_view.payload.age_ms == 55`
- `/rov/nav_view.payload.status_flags == 52`
- `/rov/nav_state_raw.payload.t_ns == 999`
- `/rov/nav_state_raw.payload.status_flags == 86`

## 7. Health Monitor Deterministic Dry-Run

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 tools/run_health_monitor_validation.py
```

预期至少看到：

- `summary == "failsafe_active"`
- `severity == 3`
- `nav_fault_code == 12`
- `nav_stale == 1`
- `imu_reconnecting == 1`
- `recommended_action` 为人工恢复建议，而不是控制指令

## 8. ROS2 Graph 发布/订阅验证

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge
PATH=/usr/bin:/bin:$PATH . /opt/ros/humble/setup.bash
. install/setup.bash
/usr/bin/python3 rov_state_bridge/tools/run_ros2_graph_validation.py
```

验证方式：

- 使用 file-backed 临时源，而不是写回任何真实 SHM
- 直接启动 install 后的 `rov_state_bridge` 和 `rov_health_monitor`
- 本地 collector 订阅 5 个 topic 并检查关键字段

当前本机已验证通过。

## 9. Rosbag2 录包与回放验证

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge
PATH=/usr/bin:/bin:$PATH . /opt/ros/humble/setup.bash
. install/setup.bash
/usr/bin/python3 rov_state_bridge/tools/run_rosbag_validation.py
```

预期：

- `ros2 bag info` 中出现：
  - `/rov/telemetry`
  - `/rov/health`
  - `/rov/nav_view`
  - `/rov/nav_state_raw`
  - `/rov/health_monitor`
- replay 后 collector 再次收到上述 topic

当前本机已验证通过；本机样本录包统计为每个 topic 47 条记录。

## 10. Live SHM Dry-Run

若当前机器上已有控制链在发布 telemetry，可执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 -m rov_state_bridge --backend stdout --once
```

预期：

- bridge 以只读方式从默认 SHM 名称读取现有权威状态
- 输出 JSON line，不修改任何核心运行态

## 11. GCS 代码语法与单测

执行：

```bash
python3 -m py_compile   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/telemetry/ros2_mirror_adapter.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/telemetry/ros2_mirror_source.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui/gui_env.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui/main_window.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui/overview_presenter.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui_main.py   /home/wys/orangepi/UnderWaterRobotGCS/tests/test_ros2_mirror_adapter.py   /home/wys/orangepi/UnderWaterRobotGCS/tests/test_ros2_mirror_source.py   /home/wys/orangepi/UnderWaterRobotGCS/tests/test_gui_overview_presenter.py
```

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

当前覆盖点：

- `TelemetryFrameV2` mirror 到 `StatusTelemetry` 的压缩映射
- 现有 `TelemetrySnapshot` / UI viewmodel 复用
- `/rov/health_monitor` advisory 摘要与恢复建议在 GUI 中的显示
- ROS2 runtime 缺失时的错误处理
- 现有 GUI/TUI 逻辑不回归

## 12. GCS Headless GUI Smoke Test

默认 UDP 路径：

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --no-auto-connect --quit-after-ms 200
```

ROS2 preview 路径：

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --no-auto-connect --telemetry-source ros2 --quit-after-ms 200
```

ROS2 preview auto-connect 缺少 runtime 时：

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --telemetry-source ros2 --quit-after-ms 200
```

预期：

- GUI 能正常启动和退出
- 缺少 `rclpy` 时，ROS2 preview 失败但不崩溃
- 若 ROS2 图上同时存在 `/rov/health_monitor`，Fault Summary / footer 应显示 advisory 文案
- 默认 UDP 路径不回归

## 13. 只读边界验证

当前只读边界依赖这些事实：

1. `ReadOnlyShmReader` 只使用 `O_RDONLY` + `mmap.ACCESS_READ`
2. bridge 没有任何写回 SHM 或网络控制入口
3. health monitor 只消费 mirror topic / dataclass，不做安全裁决
4. GCS ROS2 preview 只把 mirror 映射回现有 UI snapshot，不发送控制命令
5. backend 发布失败只记录在本地错误中
6. graph / rosbag 验证都使用 file-backed 临时源，不依赖修改核心 producer

因此：

- 停掉 bridge 或 health monitor，不会影响核心 producer 继续写 SHM
- ROS2 topic 堵塞或 graph 故障，不会回压控制/导航主链
- ROS2 preview UI 只是只读总览入口，不替代当前 UDP teleop 路径

## 14. 当前未覆盖项

本轮尚未覆盖：

- 真实设备上的 ROS2 sidecar 部署
- live nav/control 主链运行时的长期稳定性与时序抖动测量
- 操作员通过 GUI 修改控制命令的 ROS2 写回路径
- 独立 transport/session mirror topic
- 独立的 `/rov/events` topic
- Windows ROS2 runtime 路径
- 真机条件下 `ControlGuard` / `nav_daemon` / reconnect bench 与 ROS2 sidecar 共存验证

这些项仍属于后续阶段；当前只能宣称完成了本机 `colcon build`、generated msg、graph 和 rosbag 的外围验证。