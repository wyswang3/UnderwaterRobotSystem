# GCS UI Operator Guide

## 文档状态

- 状态：Authoritative
- 说明：当前生效的系统级基线文档。


## 适用范围

本文档描述 2026-03-21 当前基线下的 GCS UI 使用方式。

当前结论：

- TUI 仍是当前完整键盘 teleop 基线。
- GUI 已支持可操作主界面：
  - 通过 UDP command lane 做 `ESTOP / clear ESTOP / ARM / DISARM / mode switch / DOF apply`
  - 通过 ROS2 mirror source 提供更完整的执行链 / 导航细节页
- GUI 还支持一个 ROS2 mirror source，用于消费 `/rov/telemetry` mirror，并可选显示 `/rov/health_monitor` 的 advisory 恢复建议。
- Linux 是当前 GUI/TUI 都能稳定验证的主路径。
- Windows 当前提供 GUI preview 与最小诊断路径，但还没有完成现场交付级验证。

GCS 启动脚本当前固定遵循以下解释器优先级：

1. `UROGCS_PYTHON_BIN`
2. `UnderWaterRobotGCS/.venv/bin/python`
3. `python3`
4. `python`

如果需要手动进入环境，可先执行：

```bash
cd <UnderWaterRobotGCS repo root>
source scripts/enter_gcs_env.sh
```

补充说明：

- 实际分机部署时，GCS 应在上位机的 `UnderWaterRobotGCS` 仓运行，OrangePi 侧只负责车端 runtime。
- `tools/supervisor/run_local_teleop_smoke.sh teleop/gui` 仅适用于本机同时检出两个仓库的联调工作区，不作为实际部署基线。

## 1. 当前推荐启动顺序

### ROV 侧

当前默认推荐顺序：

1. `phase0_supervisor.py preflight --profile control_only`
2. `phase0_supervisor.py start --profile control_only --detach`
3. 由 supervisor 启动：
   - `pwm_control_program`
   - `gcs_server`
4. 只有在 `imu_only` / `imu_dvl` readiness 稳定后，才切到 `bench` nav preview lane
5. 如需外围 bridge，再启动 `rov_state_bridge` / `rov_health_monitor`

### 操作员侧

#### Linux GUI（UDP command lane + 默认 telemetry）

```bash
cd <UnderWaterRobotGCS repo root on the upper computer>
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_gui.sh
```

如需显式打开 GCS 会话调试日志，只允许按需追加：

```bash
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_gui.sh --debug-session
```

#### Linux GUI ROS2 detail path（UDP command lane + ROS2 detail telemetry）

```bash
. /opt/ros/humble/setup.bash
. <OrangePi_STM32_for_ROV repo root>/ros2_bridge/install/setup.bash
cd <UnderWaterRobotGCS repo root>
PYTHONPATH=src python3 -m urogcs.app.gui_main --telemetry-source ros2
```

说明：

- 这条路径要求 `ros2_bridge` 已先完成 `colcon build`，并且当前 shell 已 source 对应 `install/setup.bash`。
- 若本机同时存在 conda Python 与 ROS2 Humble system Python，需使用能正确导入生成后 `rov_msgs` 的那一套环境。
- 若 ROS2 图中同时存在 `/rov/health_monitor`，GUI 会在 `Fault Summary` 和页脚里显示 advisory 摘要与建议恢复动作。
- GUI 里的控制按钮仍然走 UDP command lane，不走 ROS2 写回。
- ROS2 只负责补充执行链和导航细节观测，不替代当前 UDP teleop。

#### Linux TUI teleop

```bash
cd <UnderWaterRobotGCS repo root on the upper computer>
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh --preflight-only
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh
```

如需显式打开 GCS 会话调试日志，只允许按需追加：

```bash
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh --debug-session
```

说明：

- 键盘 teleop 当前按产品安全约束只接受一个运动键；组合运动键会被上位机忽略。
- 会话调试默认关闭；只有显式传 `--debug-session` 或设置 `UROGCS_SESSION_DEBUG=1` 时才输出握手 / UDP 调试日志。
- 这条约束的原因不是 UI 限制，而是为了避免组合运动带来的运动学歧义和瞬时电池/推进器负载尖峰。
- 操作建议是“先松开当前运动键，再按下下一个运动键”，不要把 `W/A/Q/H/...` 这类运动键同时按住。

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

## 3. 当前 GUI 页面怎么读

GUI 当前固定分为几个主要页面：

- `Overview`
- `Operate`
- `Execution`
- `Navigation`
- `Power`

其中 `Overview` 仍保留六张核心状态卡，供操作者第一眼判断当前系统是否可操作。

### Connection

主要看：

- `Connected`
- `Connected, waiting status`
- `Telemetry stale`
- `Handshake incomplete`
- `Disconnected`

### Devices

客户应优先识别：

- `IMU + DVL`
- `IMU Only`
- `Control Only`
- `Reconnecting`
- `Mismatch`

说明：

- `DVL` 当前是外接可选模块，不是默认启动硬依赖。
- `Volt32` 当前仍应结合 supervisor `device-scan` / `status` 解读，不应把 GUI 缺失直接判成设备离线。

### Motion Info

当前 GUI 已把原 `Navigation` 卡片收口成 `Motion Info`。

主要看：

- `Control Only`
- `Attitude Feedback`
- `Relative Nav`

判读原则：

- `Control Only` 不代表系统失败，只表示当前不宣称运动反馈。
- `Attitude Feedback` 只代表 IMU-only 的姿态反馈，不代表完整导航。
- `Relative Nav` 只代表 IMU + DVL 的速度与短时相对运动，不代表绝对定位。
- 只有 runtime nav 当前 `fresh + valid` 时，GUI/TUI 才应把 `Motion Info` 升级成 `Attitude Feedback` 或 `Relative Nav`；单纯设备在线但导航输出失效时，界面应继续保守显示 `Control Only`。

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

它来自现有 alarm 规则和 advisory health monitor 摘要，不是 GUI 自己编新逻辑。ROS2 preview 下若收到 `/rov/health_monitor`，这里还会附带 `recommended_action`。

## 4. 当前 Operate 页怎么读

`Operate` 页是当前 GUI 的主操作面。

它当前提供：

- `ESTOP`
- `Clear ESTOP`
- `ARM`
- `DISARM`
- `Manual / Auto / Failsafe`
- 6DOF 数值输入
- `Apply DOF`
- `Zero DOF`
- `Live Send`

硬规则：

1. GUI 本地按钮只代表“命令请求已发送”，不代表远端已经执行成功。
2. 真正是否生效，仍必须继续看：
   - `Control`
   - `Command`
   - `Execution`
3. `Live Send` 只改变 GUI 的发送方式，不改变下位机 authority 和安全裁决。

## 5. 当前 Execution / Navigation / Power 页边界

### Execution

当前设计目标是把操作员最关心的执行链放在同一个页面：

- requested DOF
- applied DOF
- `thruster_cmd[8]`
- `pwm_duty[8]`
- STM32 / PWM link health
- latest command result

说明：

- 这些细节当前优先依赖 ROS2 mirror 的完整 `TelemetryFrameV2`。
- 若只走紧凑 UDP `StatusTelemetry`，GUI 仍可操作，但这页会退化成“需要 ROS2 detail telemetry”。
- 当前还没有“每一帧 PWM 已被 STM32 明确执行确认”的逐帧回执字段；页面当前只能显示链路级健康、发送统计和最新命令结果。

### Navigation

当前把导航信息按层次拆开：

- trust gate
- attitude / depth
- position / velocity

操作员读法仍应保持：

1. 先看 `valid / stale / degraded`
2. 再看 `fault / status_flags`
3. 最后再看姿态、速度、位置数值

### Power

当前 `Power` 页先只承认以下真实边界：

- Volt32 已在导航侧用于采集与日志
- 但电机电流 / 功率当前还没有稳定进入统一 UI telemetry 契约

当前页面会先固定展示后续显示规则：

- `displayed_current_a = raw_sensor_current * 40`
- 电机母线电压固定按 `24 V`
- 当前采样到的电压通道只是分压测量，不应直接当成电机母线绝对电压

## 6. 当前 GUI 与 TUI 的边界

### GUI 当前适合做什么

- 看连接状态
- 看设备状态
- 看导航状态
- 看控制状态
- 看命令状态
- 看故障摘要
- 做连接 / 断开入口
- 做 `ESTOP / ARM / mode / DOF` 操作
- 在 ROS2 detail path 中查看 mirror 细节数据

### GUI 当前不做什么

- 不做键盘 teleop 主控制台
- 不做日志导出
- 不做设备串口写回
- 不做 SSH 编排
- 不做故障恢复回灌按钮
- 不做安全裁决
- 不做 `uwnav_navd` 进程内热切换；DVL policy 仍按“外围命令 + 配置写入 + 重启 nav preview lane”执行

## 7. ROS2 preview 当前边界

当前 ROS2 preview 只做：

- 读 `/rov/telemetry` mirror
- 可选读 `/rov/health_monitor` advisory topic
- 复用现有 `StatusTelemetry` 压缩语义
- 把 mirror 状态映射到现有 GUI 卡片和恢复建议文案

当前 ROS2 preview 不做：

- 发送 control intent
- 发送 heartbeat
- 替代 `gcs_server`
- 替代 TUI teleop

## 8. 当前最小安全操作顺序

1. 先看 `Connection` 是否为可用状态。
2. 再看 `Devices` 是否出现 `Mismatch` / `Reconnecting` / `Offline`。
3. 再看 `Motion Info` 与 `Navigation` 页里的 trust gate 是否为 `Invalid` / `Stale` / `Degraded`。
4. 再看 `Control` 是否处于 `Failsafe` / `E-Stop latched` / `Disarmed`。
5. 如需 `ESTOP / ARM / mode / DOF` 操作，可以直接在 GUI `Operate` 页执行。
6. 如需启用 DVL，只能在确认换能器已经处于水中环境后，再在 `Operate -> DVL Policy -> Enable DVL` 中确认弹窗。
7. DVL policy 下发后会重启 `uwnav_navd + nav_viewd` 预览链；操作员必须观察 `Devices / Motion Info / Navigation` 是否重新回到期望状态。
8. 如需连续键盘 teleop，再切到 TUI；当前 GUI 不是键盘主控制台。
9. 每次操作后都看 `Command`、`Control` 和 `Execution`，不要只看本地按钮是否点过。

## 9. 无机器人时的本地 smoke test

在没有真实机器人连接时，当前仍可以做一轮最小本地验证。

推荐目标：

- 验证 GUI 的 `Enable DVL` 会先弹出“已在水中环境”确认框
- 验证 GUI 取消后不会发送命令
- 验证 GCS UDP 命令链能收到 `DVL_POLICY` ACK
- 验证 `dvl_policy_enabled` 会随 enable / disable 翻转
- 验证“未确认在水中环境就启用 DVL”会被车端拒绝

当前已做过的一轮本地基线是：

- GUI 单测覆盖了：
  - enable 需要确认弹窗
  - cancel 不发送命令
  - disable 不弹窗
- 本机 `gcs_server` + 本机 GCS service 的 UDP smoke 已验证：
  - handshake 可建立
  - enable DVL 后 ACK=`OK`，并且 `dvl_policy_enabled=1`
  - disable DVL 后 ACK=`OK`，并且 `dvl_policy_enabled=0`
  - 若 `submerged_confirmed=0` 直接请求 enable，则 ACK=`BAD_FORMAT`

注意：

- 这类本地 smoke 默认只验证 GUI / 协议 / ACK / policy state 语义
- 若使用 mock helper，它不等价于真实 `nav_lane_manager.py` 对 `uwnav_navd + nav_viewd` 的重启效果
- 真正的 DVL runtime health 仍必须在真实导航链和真实水下环境里确认

## 10. 当前已知边界

- GUI 当前已经是多页面操作面，但仍处于工程化完善阶段，不应被描述为完整商业化平台。
- ROS2 detail path 当前只负责补充细节观测，不负责命令写回，也不替代 UDP command lane。
- Windows 路径虽然已有 `run_gui.ps1`，但还没有完成真实现场验证。
- `pyproject.toml` 仍为空，当前不是 packaged installer 基线。
- `Power` 页当前仍未接入稳定的 Volt32 实时数值契约，因此只能先显示量纲与换算规则。
- GUI 已接入 `Disable DVL / Enable DVL` operator control；启用 DVL 前必须经过“已在水中环境”确认弹窗。
- DVL policy 当前不是热切换；车端执行的是“更新 nav 配置 + 重启 nav preview lane”，因此切换期间导航预览会短暂中断。
- GUI 当前展示的 `dvl_policy` 是 operator desired policy，不等价于 DVL runtime health；是否真正可用于相对导航，仍要看 `DVL online / nav_valid / nav_degraded / nav_fault_code`。
- 如需更细的恢复动作，直接按 `operator_manual.md` 里的“卡住时的最短恢复顺序”执行，并结合 GUI/TUI 当前远端状态判断。
