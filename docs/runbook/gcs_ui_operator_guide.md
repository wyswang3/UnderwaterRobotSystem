# GCS UI Operator Guide

## 适用范围

本文档描述 2026-03-21 当前基线下的 GCS UI 使用方式。

当前结论：

- TUI 仍是当前完整键盘 teleop 基线。
- GUI 已支持首页总览 preview。
- GUI 还支持一个 read-only ROS2 preview source，用于消费 `/rov/telemetry` mirror。
- Linux 是当前 GUI/TUI 都能稳定验证的主路径。
- Windows 当前提供 GUI preview 与最小诊断路径，但还没有完成现场交付级验证。

## 1. 当前推荐启动顺序

### ROV 侧

完整链路推荐顺序：

1. `uwnav_navd`
2. `nav_viewd`
3. `gcs_server`
4. `pwm_control_program`
5. 如需外围 bridge，再启动 `rov_state_bridge` / `rov_health_monitor`

### 操作员侧

#### Linux GUI preview（UDP 主路径）

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_gui.sh
```

#### Linux GUI ROS2 preview（只读）

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
PYTHONPATH=src python3 -m urogcs.app.gui_main --telemetry-source ros2
```

说明：

- 这条路径要求本机已安装 `rclpy` 和生成后的 `rov_msgs` Python 包。
- 它只消费 mirror topic，不替代当前 UDP teleop。

#### Linux TUI teleop

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh --preflight-only
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh
```

#### Windows GUI preview

```powershell
Set-Location <UnderWaterRobotGCS>
$env:UROGCS_ROV_IP = "<OrangePi_IP>"
.\scripts\run_gui.ps1
```

#### Windows TUI/diagnostic path

```powershell
Set-Location <UnderWaterRobotGCS>
$env:UROGCS_ROV_IP = "<OrangePi_IP>"
.\scripts\run_tui.ps1 -PreflightOnly
.\scripts\run_tui.ps1
```

## 2. preflight 通过后该看到什么

`preflight_check.py` 当前至少会检查：

- Python 版本
- 平台支持说明
- `UROGCS_ROV_IP:UROGCS_ROV_PORT` 可解析
- 本地 UDP 绑定端口可用

通过后输出会明确告诉操作者：

- ROV 侧启动顺序
- GUI / TUI 的下一步入口
- Windows 当前仍属于 preview 还是最小诊断路径

如果 preflight 没过，不要继续进入 GUI/TUI，先停在对应步骤处理。

## 3. 当前 GUI 首页怎么读

首页当前固定有六张状态卡片。

### Connection

主要看：

- `Connected`
- `Connected, waiting status`
- `Telemetry stale`
- `Handshake incomplete`
- `Disconnected`

### Devices

客户应优先识别：

- `Online`
- `Reconnecting`
- `Mismatch`
- `Offline`
- `Degraded`

### Navigation

主要看：

- `Ok`
- `Degraded`
- `Stale`
- `Invalid`

### Control

这是远端权威控制态，不是本地按钮回显。

客户要重点看：

- `Armed / Manual`
- `Disarmed / Manual`
- `Failsafe`
- `E-Stop latched`

### Command

这一张卡片明确把 transport 和 runtime 分开：

- `transport=` 使用本地会话发送 / ACK 结果
- `runtime=` 使用 telemetry 权威 `command_status`

关键规则：

- `acknowledged` 不等于远端已经真正执行成功。
- 真正是否生效，必须继续看 `runtime=` 和 `Control` 卡片。

### Fault Summary

它来自现有 alarm 规则和 advisory health monitor 摘要，不是 GUI 自己编新逻辑。

## 4. 当前 GUI 与 TUI 的边界

### GUI 当前适合做什么

- 看连接状态
- 看设备状态
- 看导航状态
- 看控制状态
- 看命令状态
- 看故障摘要
- 做连接 / 断开入口
- 在 ROS2 preview 中只读查看 mirror 数据

### GUI 当前不做什么

- 不做键盘 teleop 主控制台
- 不做日志导出
- 不做设备串口写回
- 不做 SSH 编排
- 不做故障恢复回灌按钮
- 不做安全裁决

## 5. ROS2 preview 当前边界

当前 ROS2 preview 只做：

- 读 `/rov/telemetry` mirror
- 复用现有 `StatusTelemetry` 压缩语义
- 把 mirror 状态映射到现有 GUI 卡片

当前 ROS2 preview 不做：

- 发送 control intent
- 发送 heartbeat
- 替代 `gcs_server`
- 替代 TUI teleop

## 6. 当前最小安全操作顺序

1. 先看 `Connection` 是否为可用状态。
2. 再看 `Devices` 是否出现 `Mismatch` / `Reconnecting` / `Offline`。
3. 再看 `Navigation` 是否为 `Invalid` / `Stale`。
4. 再看 `Control` 是否处于 `Failsafe` / `E-Stop latched` / `Disarmed`。
5. 如需真正 teleop，切换到 TUI 或 UDP 主路径继续操作。
6. 每次操作后都看 `Command` 和 `Control`，不要只看本地按钮是否点过。

## 7. 当前已知边界

- GUI 当前只有一个首页，没有多页面导航。
- GUI 首页是 preview，不应被描述为完整商业化平台。
- ROS2 preview 仍是 read-only，不应被描述为完整 ROS2 UI backend。
- Windows 路径虽然已有 `run_gui.ps1`，但还没有完成真实现场验证。
- `pyproject.toml` 仍为空，当前不是 packaged installer 基线。
- 如需更细的恢复动作，请继续看 `customer_fault_recovery_guide.md`。
