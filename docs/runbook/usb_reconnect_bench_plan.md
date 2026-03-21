# USB Reconnect Bench Plan

## 适用范围

本文档定义当前 USB/by-id/udev 重连台架验证基线。

目标不是一次性覆盖所有极端情况，而是把最关键的重连语义、诊断传播和日志留存流程标准化。

## 1. 当前为什么要做这件事

当前软件侧已经具备：

- 设备绑定状态机
- 稳定路径优先和候选路径扫描
- `/dev/serial/by-id` 扫描
- `VID/PID/serial/by-id substring` 身份过滤
- mismatch / reconnecting / backoff 状态传播
- PTY 半实物集成测试

但还缺少：

- 真实设备重枚举样本
- 错设备先出现、正确设备后出现的系统级样本
- by-id 软链接重建延迟样本

## 2. 当前最小工具链

### 设备快照工具

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/usb_serial_snapshot.py --json
```

作用：

- 记录 `/dev/serial/by-id`
- 记录 `ttyUSB*` / `ttyACM*`
- 读取 sysfs 里的 `idVendor/idProduct/serial`
- 让日志和 binder 状态有真实设备视图可追

### 运行时观测工具

- `uwnav_navd`
- `nav_viewd`
- `telemetry_dump`
- `pwm_control_program --pwm-dummy`

### 日志工具

- `parse_nav_timing.py`
- `merge_robot_timeline.py`
- `replay_compare.py`

## 3. 建议验证场景

### 场景 A：正常启动

目标：

- 正确设备正常上线
- binder 进入 `ONLINE`
- `NavState -> NavView -> Telemetry` 为正常可信链路

### 场景 B：同一设备断开后换新节点重枚举

目标：

- 例如从 `ttyUSB0` 变成 `ttyUSB1`
- binder 能从旧节点失效过渡到重探测和恢复
- 诊断链能反映 reconnecting/offline/recovered

### 场景 C：`/dev/serial/by-id` 延迟出现

目标：

- 验证候选扫描与 by-id 回归是否一致
- 确认不会因为短暂无 by-id 就永久卡死在错误状态

### 场景 D：错设备先出现

目标：

- 同 VID/PID 但 serial 不同的设备不能被误接收为目标设备
- UI/telemetry 能看到 mismatch

### 场景 E：无设备负路径

目标：

- 系统在完全无设备时进入明确 fault/reconnecting 语义
- incident bundle 和 replay compare 至少可用作负路径验证

## 4. 推荐执行步骤

### 步骤 1：记录基线快照

在接设备前运行：

```bash
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json > baseline_before.json
```

### 步骤 2：接入设备并再次快照

```bash
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json > baseline_after.json
```

至少比对：

- `path`
- `canonical_path`
- `vendor_id`
- `product_id`
- `serial`

### 步骤 3：启动最小运行链

推荐最小链：

1. `uwnav_navd`
2. `nav_viewd`
3. `pwm_control_program --pwm-dummy`
4. `telemetry_dump` 或 GCS TUI

### 步骤 4：执行拔插/重枚举动作

每次动作后都保留：

- 一次 `usb_serial_snapshot.py` 输出
- `nav_timing.bin`
- `nav_state.bin`
- `control_loop_*.csv`
- `telemetry_timeline_*.csv`
- `telemetry_events_*.csv`

### 步骤 5：导出事故窗口

对异常窗口执行：

```bash
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/merge_robot_timeline.py   --nav-timing /path/to/nav_timing.bin   --nav-state /path/to/nav_state.bin   --control-log /path/to/control_loop_xxx.csv   --telemetry-timeline /path/to/telemetry_timeline_xxx.csv   --telemetry-events /path/to/telemetry_events_xxx.csv   --event reconnecting   --bundle-dir /tmp/reconnect_case01
```

## 5. 最小验收标准

至少满足以下条件才算当前阶段通过：

1. 断连时 binder 状态切换可在日志中看到。
2. 断连后 `NavState` 不再伪装成正常可用状态。
3. `nav_viewd` 和 `ControlGuard` 能把故障继续传播到 telemetry。
4. GCS/TUI 或 `telemetry_dump` 能看见对应 fault/diagnosis。
5. 能导出 incident bundle，并至少完成一次 replay/compare。

## 6. 当前已知环境限制

1. 如果当前主机没有真实 IMU/DVL，就只能先做负路径样本。
2. 无设备样本常出现 `NavState::t_ns == 0`，这时 replay 更适合做语义验证，不适合做精确定时验证。
3. PTY 集成测试通过，不代表真实 USB/udev 时序已经完全闭环。

## 7. 当前阶段结论标准

如果这轮台架只完成了：

- PTY 测试
- 无设备样本
- 文档/runbook 收口

那么结论应该写成：

- 软件状态机和诊断传播已经基本成立
- 真实 USB 重枚举闭环仍待实机样本确认

不要把“软件逻辑看起来正确”写成“实机重连已完全验证”。
