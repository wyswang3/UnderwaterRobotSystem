# ROS2 Bridge Validation Guide

## 适用范围

本文档给出当前 ROS2 外围桥接阶段的最小验证路径。

当前验证目标是：

1. 确认 mirror 字段与权威状态一致
2. 确认 bridge 是只读旁路，不影响核心链
3. 确认 advisory health monitor 和 GCS ROS2 preview 建立在同一套权威字段之上
4. 在没有 ROS2 toolchain 的机器上也能做 dry-run 和单测

## 1. 环境前提

当前最低要求：

- Linux 主机
- Python 3
- 现有仓库代码已同步

当前机器若缺少下列组件，不影响 dry-run / 单测：

- `ros2`
- `colcon`
- `rclpy`
- 生成后的 `rov_msgs` Python 包

说明：

- 这些组件缺失会阻断真实 ROS2 graph 验证，但不会阻断当前 bridge、health monitor 和 GCS preview 的本地 Python 验证。

## 2. 控制仓代码语法检查

在控制仓执行：

```bash
python3 -m py_compile   ros2_bridge/rov_state_bridge/src/rov_state_bridge/*.py   ros2_bridge/rov_state_bridge/tests/test_*.py   ros2_bridge/rov_state_bridge/tools/*.py
```

预期：

- 无报错退出。

## 3. 控制仓单测验证

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

## 4. bridge deterministic dry-run

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

## 5. health monitor deterministic dry-run

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

## 6. live SHM dry-run

若当前机器上已有控制链在发布 telemetry，可执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 -m rov_state_bridge --backend stdout --once
```

预期：

- bridge 以只读方式从默认 SHM 名称读取现有权威状态
- 输出 JSON line，不修改任何核心运行态

## 7. GCS 代码语法与单测

执行：

```bash
python3 -m py_compile   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/telemetry/ros2_mirror_adapter.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/telemetry/ros2_mirror_source.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui/gui_env.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui/main_window.py   /home/wys/orangepi/UnderWaterRobotGCS/src/urogcs/app/gui_main.py   /home/wys/orangepi/UnderWaterRobotGCS/tests/test_ros2_mirror_adapter.py   /home/wys/orangepi/UnderWaterRobotGCS/tests/test_ros2_mirror_source.py
```

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

当前覆盖点：

- `TelemetryFrameV2` mirror 到 `StatusTelemetry` 的压缩映射
- 现有 `TelemetrySnapshot` / UI viewmodel 复用
- ROS2 runtime 缺失时的错误处理
- 现有 GUI/TUI 逻辑不回归

## 8. GCS headless GUI smoke test

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
- 默认 UDP 路径不回归

## 9. 只读边界验证

当前只读边界依赖这些事实：

1. `ReadOnlyShmReader` 只使用 `O_RDONLY` + `mmap.ACCESS_READ`
2. bridge 没有任何写回 SHM 或网络控制入口
3. health monitor 只消费 mirror topic / dataclass，不做安全裁决
4. GCS ROS2 preview 只把 mirror 映射回现有 UI snapshot，不发送控制命令
5. backend 发布失败只记录在本地错误中

因此：

- 停掉 bridge 或 health monitor，不会影响核心 producer 继续写 SHM
- ROS2 topic 堵塞或 graph 故障，不会回压控制/导航主链
- ROS2 preview UI 只是只读总览入口，不替代当前 UDP teleop 路径

## 10. 当前未覆盖项

本轮尚未覆盖：

- colcon build
- 真实 ROS2 message 生成
- `rclpy` backend runtime publish / subscribe 回环
- `rosbag2` 录包与回放
- 图形化故障恢复按钮真正回灌操作链
- Windows ROS2 runtime 路径

这些属于后续阶段，在当前环境缺少 ROS2 toolchain 时不强行推进。
