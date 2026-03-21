# Log Replay Guide

## 适用范围

当前 replay/复盘基线不是“完整原始帧级重放平台”，而是 P1 阶段最小可验证闭环。

它的目标是回答：

1. 故障在什么时候发生。
2. 故障有没有沿 `NavState -> NavView -> Control -> Telemetry -> GCS` 正确传播。
3. replay 后关键状态签名是否与原始事故窗口一致。

## 1. 当前最小输入集合

当前推荐至少准备四类日志：

1. 导航时间线
   - `nav_timing.bin`
2. 导航状态
   - `nav_state.bin`
3. 控制日志
   - `control_loop_*.csv`
4. 遥测日志
   - `telemetry_timeline_*.csv`
   - `telemetry_events_*.csv`

常见来源：

- 导航仓日志目录
- 控制仓 `./logs/control`
- 控制仓 `./logs/telemetry`

## 2. 第一步：先看 `nav_timing.bin`

先用：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/parse_nav_timing.py --input /path/to/nav_timing.bin
```

这一阶段重点回答：

- 有没有 duplicate/out-of-order 样本
- stale 是不是由语义样本年龄触发
- `sensor -> recv -> consume -> publish` 延迟是否异常
- 设备绑定状态何时变化

## 3. 第二步：合并统一时间线

当前统一时间线工具：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/merge_robot_timeline.py   --nav-timing /path/to/nav_timing.bin   --nav-state /path/to/nav_state.bin   --control-log /path/to/control_loop_xxx.csv   --telemetry-timeline /path/to/telemetry_timeline_xxx.csv   --telemetry-events /path/to/telemetry_events_xxx.csv   --bundle-dir /tmp/replay_bundle_case01
```

如果只想导出故障窗口，可增加：

```bash
  --event reconnecting   --window-before-ms 150   --window-after-ms 350
```

常见 `--event` 值包括：

- `reconnecting`
- `mismatch`
- `stale`
- `invalid`
- `degraded`
- `failsafe`
- `command_rejected`
- `command_failed`
- `command_expired`
- `nav_fault`

## 4. 第三步：做 replay 注入

导出 incident bundle 后，再按 [replay_injection_guide.md](./replay_injection_guide.md) 运行：

- `nav_viewd`
- `pwm_control_program --pwm-dummy`
- `uwnav_nav_replay`

当前注入层级选在 `NavState`，不是原始 IMU/DVL 帧级。

## 5. 第四步：做 replay compare

当前关键状态对照工具：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/replay_compare.py   --incident-bundle /tmp/replay_bundle_case01   --replay-control-log /path/to/replay/control_loop_xxx.csv   --replay-telemetry-timeline /path/to/replay/telemetry_timeline_xxx.csv   --replay-telemetry-events /path/to/replay/telemetry_events_xxx.csv
```

重点不是逐字节 diff，而是看：

- nav fault/stale/invalid 是否还在同类窗口出现
- control 是否仍然拒绝 Auto 或进入 failsafe
- telemetry/GCS 面向操作员的关键信号是否一致

## 6. 当前这套流程能回答什么

当前最小闭环已经能回答：

1. 设备绑定何时切换状态。
2. 导航主循环到底是消费了样本、拒绝了样本，还是因为 stale 放弃了样本。
3. `NavState` 进入 invalid/degraded 后，`nav_viewd` 和控制侧是否同步进入保护路径。
4. telemetry/GCS 是否看到同样的 fault 和状态变化。
5. 哪个窗口值得导出 incident bundle，而不是盲看整段日志。

## 7. 当前还不能回答什么

当前仍然不能把这套系统描述成：

- 完整原始传感器帧级 replay
- 完整命令链逐帧重建
- 高精度 publish cadence 还原平台

尤其在 `NavState::t_ns == 0` 的负路径样本下，当前更适合做“语义传播验证”，
不适合宣称“时序精确复现”。

## 8. 当前使用建议

1. 先做时间线归类，再决定是否需要 replay。
2. 先验证 fault/stale/invalid 传播语义，不要一上来就追求全链逐帧一致。
3. 真实台架样本优先级高于纯合成样本。
4. 如果 incident bundle 来自无设备常量样本，要在结论里明确说明 replay 只验证传播语义。
