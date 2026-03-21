# GCS UI Operator Guide

## 适用范围

本文档描述 2026-03-21 当前基线下的 GCS UI 使用方式。

当前结论：

- TUI 仍是当前完整键盘 teleop 基线。
- GUI 已进入第一阶段 preview，可作为总览仪表盘首页使用。
- Linux 是当前 GUI/TUI 都能稳定验证的主路径。
- Windows 当前提供 GUI preview 与最小诊断路径，但还没有完成现场交付级验证。

## 1. 当前推荐启动顺序

### ROV 侧

完整链路推荐顺序：

1. `uwnav_navd`
2. `nav_viewd`
3. `gcs_server`
4. `pwm_control_program`

当前主机上可见的控制侧目标包括：

- `/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/build/bin/gcs_server`
- `/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/build/bin/nav_viewd`
- `/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/build/bin/pwm_control_program`

### 操作员侧

#### Linux GUI preview

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_gui.sh
```

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

说明：

- `run_gui.sh` / `run_gui.ps1` 现在会先跑 preflight，再进入 `urogcs.app.gui_main`。
- GUI 当前是“总览仪表盘首页 preview”，不是完整交付平台。
- 如需完整键盘 teleop，当前仍以 TUI 为准。

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

它来自会话状态、`last STATUS age` 和 `link_alive` 的组合显示。

### Devices

客户应优先识别：

- `Online`
- `Reconnecting`
- `Mismatch`
- `Offline`
- `Degraded`

卡片内会继续展开 `IMU=` 与 `DVL=` 的单独状态。

### Navigation

主要看：

- `Ok`
- `Degraded`
- `Stale`
- `Invalid`

卡片细节会保留：

- `state=`
- `health=`
- `diag=`
- `fault=`

### Control

这是远端权威控制态，不是本地按钮回显。

客户要重点看：

- `Armed / Manual`
- `Disarmed / Manual`
- `Failsafe`
- `E-Stop latched`

卡片里还会保留：

- `controller=`
- `desired=`
- `fault_state=`
- `fails=`

### Command

这一张卡片明确把 transport 和 runtime 分开：

- `transport=` 使用 `GcsServiceState` 的本地发送 / ACK 结果
- `runtime=` 使用 telemetry 权威 `command_status`

因此你会看到类似：

- `acknowledged / executed`
- `pending_ack / none`
- `sent / none`
- `ack_invalid_session / failed`

关键规则：

- `acknowledged` 不等于远端已经真正执行成功。
- 真正是否生效，必须继续看 `runtime=` 和 `Control` 卡片。

### Fault Summary

这是当前首页上的最小故障摘要卡。

它来自现有 alarm 规则，不是 GUI 自己编新逻辑。

当前至少会汇总：

- session 未建立
- 链路 stale
- estop
- failsafe
- nav 不可信
- system fault
- command failed
- failure counter 增长

## 4. 当前 GUI 与 TUI 的边界

### GUI 当前适合做什么

- 看连接状态
- 看设备状态
- 看导航状态
- 看控制状态
- 看命令状态
- 看故障摘要
- 做连接 / 断开入口

### GUI 当前不做什么

- 不做键盘 teleop 主控制台
- 不做日志导出
- 不做设备串口写回
- 不做 SSH 编排
- 不做故障恢复中心
- 不做安全裁决

## 5. 当前最小安全操作顺序

1. 先看 `Connection` 是否为 `Connected`。
2. 再看 `Devices` 是否出现 `Mismatch` / `Reconnecting` / `Offline`。
3. 再看 `Navigation` 是否为 `Invalid` / `Stale`。
4. 再看 `Control` 是否处于 `Failsafe` / `E-Stop latched` / `Disarmed`。
5. 如需真正 teleop，切换到 TUI 路径继续操作。
6. 每次操作后都看 `Command` 和 `Control`，不要只看本地按钮是否点过。

## 6. 当前已知边界

- GUI 当前只有一个首页，没有多页面导航。
- GUI 首页是 preview，不应被描述为完整商业化平台。
- Windows 路径虽然已有 `run_gui.ps1`，但还没有完成真实现场验证。
- `pyproject.toml` 仍为空，当前不是 packaged installer 基线。
- 如需更细的恢复动作，请继续看 `customer_fault_recovery_guide.md`。
