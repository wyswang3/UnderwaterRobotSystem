# Customer Onboarding Guide

## 适用范围

本文档面向第一次接触 UnderwaterRobotSystem 的客户或现场操作员。

当前最小可用结论：

- 操作员侧基线入口是 `UnderWaterRobotGCS` 源码仓
- 当前不是 packaged installer 基线，最小闭环是 `Python 3.10+ + launcher script + preflight`
- Linux/POSIX 是完整 teleop 基线
- Windows 当前是最小观测/诊断路径

## 1. 第一次使用前需要准备什么

### 操作员电脑

- Python `3.10+`
- `UnderWaterRobotGCS` 仓库工作副本
- 与 ROV 同一局域网
- 已知 OrangePi IP 地址

### ROV 侧

- OrangePi 已开机
- 导航、gateway、控制程序可启动
- 传感器与网络线缆已接好

## 2. 第一次上手的最小闭环

### 第一步：进入 GCS 仓库

Linux/POSIX：

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
```

Windows/PowerShell：

```powershell
Set-Location <UnderWaterRobotGCS>
```

### 第二步：设置目标 IP

Linux/POSIX：

```bash
export UROGCS_ROV_IP=<OrangePi_IP>
```

Windows/PowerShell：

```powershell
$env:UROGCS_ROV_IP = "<OrangePi_IP>"
```

### 第三步：只跑 preflight，不直接进 TUI

Linux/POSIX：

```bash
bash scripts/run_tui.sh --preflight-only
```

Windows/PowerShell：

```powershell
.\scripts\run_tui.ps1 -PreflightOnly
```

如果这里失败，不要继续下一步。

### 第四步：启动 ROV 侧程序

当前推荐顺序：

1. `uwnav_navd`
2. `nav_viewd`
3. `gcs_server`
4. `pwm_control_program`

### 第五步：启动 GCS

Linux/POSIX：

```bash
bash scripts/run_tui.sh
```

Windows/PowerShell：

```powershell
.\scripts\run_tui.ps1
```

## 3. 启动成功后最低限度该看到什么

至少应满足：

- `[CONN] state=connected`
- `[CMD ]` 不停留在 `ack_error(...)`
- `[HINT]` 不是 `vehicle_not_connected`
- 如需进入 Auto，`[NAV ] state=` 不能是 `stale` 或 `invalid`

Linux/POSIX 若要键盘 teleop，还应确认：

- 当前是交互式 TTY
- `[CTRL]` 不处于 `estop` / `failsafe`
- 一次只按一个运动键；组合运动键会被 GCS 忽略
- 切换方向前先松开当前运动键，避免组合运动造成负载尖峰

## 4. 如果卡住，通常卡在哪一步

### 卡在 preflight

常见原因：

- Python 版本不对
- `UROGCS_ROV_IP` 填错
- 本地绑定端口已被其他 GCS 实例占用

处理：

- 修复 Python
- 核对 IP
- 关闭旧实例或改绑定端口

### 卡在没有连接成功

表现：

- 一直没有 CONNECT_ACK
- `[CONN] state=handshaking` 或 `disconnected`

处理：

- 检查网络
- 检查 ROV 侧 `gcs_server` 是否已经启动
- 检查防火墙或错误端口

### 卡在有连接但 telemetry 不可用

表现：

- `[CONN] state=waiting_status` 或 `stale`

处理：

- 检查 `pwm_control_program` 是否真的在产出 telemetry
- 检查 `gcs_server` 是否还活着
- 检查网络抖动或多个 GCS 实例抢占

### 卡在设备或导航状态不健康

表现：

- `[DEV ]` 出现 `reconnecting` / `mismatch` / `device_offline`
- `[NAV ] state=stale` 或 `invalid`

处理：

- 不要继续强行切 Auto
- 先看 `customer_fault_recovery_guide.md`

## 5. 当前 Windows 最小路径怎么理解

Windows 本轮最小可用能力是：

- 启动 GCS
- 建立会话
- 看 telemetry / 诊断 / 命令结果
- 按 runbook 导出日志并回传

当前不承诺：

- 完整键盘 teleop
- GUI 成熟交付
- packaged installer

## 6. 客户卡住时必须导出什么

至少导出：

- GCS 控制台输出
- 一张包含 `[CONN]`、`[DEV ]`、`[NAV ]`、`[CMD ]`、`[HINT]` 的截图
- `nav_timing.bin` 或对应导航时间线产物
- 最近一次 telemetry dump 或 incident timeline

如果是模式切换或命令失败，再补：

- `last_fault_code`
- `command_fault_code`
- 当时的 `remote_mode` / `armed` / `estop` / `failsafe`
