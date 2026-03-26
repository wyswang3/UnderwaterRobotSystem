# Customer Fault Recovery Guide

## 适用范围

本文档只覆盖当前客户最常遇到、且当前 UI/TUI 已能直接识别的故障。

## 1. 快速判断原则

先看顺序：

1. `[CONN]`
2. `[DEV ]`
3. `[NAV ]`
4. `[CTRL]`
5. `[CMD ]`
6. `[HINT]`

`[HINT]` 会给出一条当前最阻断操作的建议，但日志导出仍要结合前五行一起看。

## 2. 故障与恢复动作

| 画面信号 | 当前意味着什么 | 先检查什么 | 下一步动作 | 需要导出的日志 |
| --- | --- | --- | --- | --- |
| `[HINT] blocked=vehicle_not_connected` | GCS 还没有可靠连上 ROV | `UROGCS_ROV_IP`、网络、`gcs_server` | 不要继续发命令；先恢复网络或启动 `gcs_server` | GCS 控制台日志 |
| `[DEV ] ... reconnecting` | 设备曾在线，现在正在重连 | 传感器供电、USB 线、设备是否重新枚举 | 等待几秒；若持续不恢复，重新插拔并记录时间点 | `nav_timing.bin`、telemetry 截图 |
| `[DEV ] ... mismatch` | 接入的串口设备身份不符合绑定规则 | 是否插错设备、by-id/serial 是否匹配 | 不要继续 Auto；换回正确设备后再重试 | `nav_timing.bin`、设备信息截图 |
| `[DEV ] ... device_offline` | 当前没有检测到该设备在线 | 电源、线缆、USB 枚举 | 恢复设备在线前只保留安全模式 | `nav_timing.bin`、telemetry 截图 |
| `[NAV ] state=stale` | 导航数据年龄过大，不应继续当作可信闭环输入 | `uwnav_navd`、`nav_viewd`、telemetry freshness | 不进 Auto；先恢复 freshness | `nav_timing.bin`、timeline、GCS 日志 |
| `[NAV ] state=invalid` | 导航当前不可信，可能在对齐中或设备异常 | `nav_fault`、`diag`、设备状态 | 保持 Manual/Failsafe；先查根因 | `nav_timing.bin`、telemetry 截图 |
| `[CMD ] runtime=failed/rejected/expired` | 命令没有被控制主线成功应用 | `command_fault_code`、`last_fault_code`、`remote_mode` | 不要只重发；先满足前置条件再重试 | GCS 日志、telemetry 截图 |
| `[HINT] blocked=mode_switch_failed` | 模式切换请求已发出，但远端没切过去 | `remote_mode`、nav trust、estop、arm | 先留在远端当前模式，查明阻断条件 | GCS 日志、telemetry 截图 |
| `[CTRL] state=estop` | 远端仍在急停状态 | 现场是否安全、clear estop 是否被接受 | 安全确认后再 clear estop | GCS 日志、telemetry 截图 |
| `[CTRL] state=failsafe` | 控制主线已进入 failsafe | 链路、导航、guard 状态 | 先恢复根因，不要继续强行控制 | GCS 日志、timeline |

## 3. 客户恢复时不要做的事

- 不要只因为本地按键按下去，就认为模式已经切成功
- 不要在 `stale` / `invalid` / `mismatch` 下继续强推 Auto
- 不要在不知道 `estop` 是否解除的情况下继续发 DOF
- 不要只导出一段自然语言描述，不附带截图和日志

## 4. 客户回传信息的最小包

最小回传包建议包含：

- 故障发生时间
- GCS 截图，至少覆盖 `[CONN]`、`[DEV ]`、`[NAV ]`、`[CMD ]`、`[HINT]`
- GCS 控制台输出
- `nav_timing.bin`
- 如已做时间线导出，再附 incident timeline
