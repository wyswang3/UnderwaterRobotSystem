# Replay Injection Guide

## 文档状态

- 状态：Authoritative
- 说明：当前生效的系统级基线文档。


## 适用范围

当前最小 replay 注入层级不是原始 IMU/DVL 帧，而是 `NavState`。

当前注入链定义为：

```text
nav_state_window.bin
  -> /rov_nav_state_v1
  -> nav_viewd
  -> /rovctrl_nav_view_v1
  -> pwm_control_program
  -> TelemetryFrameV2
  -> GCS/TUI 或 compare 日志
```

这样选层级的原因是：

1. 复用现有 `NavState` 日志，不额外发明中间格式。
2. 保留 `nav_viewd` 的 stale/no-data hop 语义。
3. 下游 control、telemetry、GCS 都走真实消费链。

## 1. 所需工具

### 注入器

- `uwnav_nav_replay`

### 下游进程

- `nav_viewd`
- `pwm_control_program --pwm-dummy`
- 可选：`telemetry_dump`
- 可选：GCS TUI

### 对照工具

- `replay_compare.py`

## 2. 输入形式

当前 `uwnav_nav_replay` 支持：

- `--nav-state-bin <path>`
- `--incident-bundle <dir>`

如果使用 incident bundle，默认读取：

- `<dir>/nav_state_window.bin`

## 3. 最小执行流程

### 步骤 1：准备 incident bundle

先按 [log_replay_guide.md](./log_replay_guide.md) 导出故障窗口。

### 步骤 2：启动 `nav_viewd`

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV
./build/bin/nav_viewd   --nav-state-shm /rov_nav_state_v1   --nav-view-shm /rovctrl_nav_view_v1
```

### 步骤 3：启动控制侧

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV
./build/bin/pwm_control_program --no-teleop --pwm-dummy --pwm-dummy-print
```

### 步骤 4：注入事故窗口

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
./build/bin/uwnav_nav_replay   --incident-bundle /tmp/replay_bundle_case01   --nav-state-shm /rov_nav_state_v1   --speed 1.0
```

### 步骤 5：观察下游

当前推荐至少观察一项：

- `telemetry_dump`
- GCS TUI
- replay 后落盘的 control/telemetry CSV

## 4. 当前重点验证项

当前 replay 最值得验证的是：

1. `fault_code/status_flags/valid/stale/degraded` 是否完整下传到 control。
2. `nav_viewd` 是否在 replay 间隙生成显式 stale/no-data 诊断帧。
3. `ControlGuard` 是否做出与原始事故窗口同类的拒绝/降级/failsafe 决策。
4. telemetry/GCS 是否继续反映同样的 fault 与状态变化。
5. `replay_compare.py` 是否判定关键状态签名一致。

## 5. 当前边界

当前 replay 仍有几个硬边界：

1. 输入是 `NavState`，不是原始 IMU/DVL 帧。
2. 节奏近似主要来自相邻 `t_ns` 差值，不是原始 publish header 的精确还原。
3. 更适合验证“故障传播语义”，不适合验证“高精度调度重建”。

## 6. `t_ns == 0` 样本的特殊说明

在无设备负路径样本里，`nav_state.bin` 可能包含大量 `NavState::t_ns == 0` 记录。

当前最小策略是：

- 从 incident bundle 里选代表帧作为 replay 输入
- 重点验证下游是否看到同类 invalid/stale/fault 结果
- 不把这类 replay 结果写成“精准重建原始时序”

如果 `incident_summary.json` 出现类似：

- `selection_mode = "constant_zero_t_ns_fallback"`

就应在结论里明确：

- 这次 replay 是语义对照，不是时序重建

## 7. 当前不建议做的事

当前阶段不建议：

1. 把 replay 平台扩成完整 GUI 产品。
2. 在没有真实样本闭环前直接上原始 IMU/DVL 帧级 replay。
3. 把 command/session/reply 全塞进同一个大回放器。
4. 用 replay 结果替代真实 USB 重连实测。
