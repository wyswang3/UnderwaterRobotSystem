# ROS2 Bridge Validation Guide

## 适用范围

本文档给出 ROS2 外围桥接第一阶段的最小验证路径。

本阶段验证目标是：

1. 确认 mirror 字段与权威状态一致
2. 确认 bridge 是只读旁路，不影响核心链
3. 在没有 ROS2 toolchain 的机器上也能做 dry-run

## 1. 环境前提

当前 stage1 最低要求：

- Linux 主机
- Python 3
- 现有仓库代码已同步

当前机器若缺少下列组件，不影响 stage1 dry-run：

- `ros2`
- `colcon`
- `rclpy`
- 生成后的 `rov_msgs` Python 包

说明：

- 这些组件缺失会阻断真实 ROS2 graph 验证，但不会阻断 stage1 单测和 stdout/recording backend 验证。

## 2. 代码语法检查

在控制仓执行：

```bash
python3 -m py_compile   ros2_bridge/rov_state_bridge/src/rov_state_bridge/*.py   ros2_bridge/rov_state_bridge/tests/test_*.py   ros2_bridge/rov_state_bridge/tools/run_sample_bridge_validation.py
```

预期：

- 无报错退出。

## 3. 单测验证

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

## 4. deterministic dry-run

执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 tools/run_sample_bridge_validation.py
```

该脚本会：

1. 创建临时 file-backed snapshot
2. 模拟 telemetry / nav_view / nav_state 三类权威源
3. 通过只读 bridge 发布到 recording backend
4. 输出 JSON 摘要

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

## 5. live SHM dry-run

若当前机器上已有控制链在发布 telemetry，可执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/ros2_bridge/rov_state_bridge
PYTHONPATH=src python3 -m rov_state_bridge --backend stdout --once
```

预期：

- bridge 以只读方式从默认 SHM 名称读取现有权威状态
- 输出 JSON line，不修改任何核心运行态

## 6. 只读边界验证

当前只读边界依赖三条事实：

1. `ReadOnlyShmReader` 只使用 `O_RDONLY` + `mmap.ACCESS_READ`
2. bridge 没有任何写回 SHM 或网络控制入口
3. backend 发布失败只记录在 bridge 本地错误列表中

因此：

- 停掉 bridge，不会影响核心 producer 继续写 SHM
- bridge topic 堵塞或 ROS graph 故障，不会回压控制/导航主链

## 7. 当前未覆盖项

本轮尚未覆盖：

- colcon build
- 真实 ROS2 message 生成
- `rclpy` backend runtime publish
- ROS2 topic subscribe / rosbag2 回环
- Windows 路径

这些属于后续阶段，在当前环境缺少 ROS2 toolchain 时不强行推进。
