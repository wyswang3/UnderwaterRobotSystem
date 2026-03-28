# Teleop Primary Operator Lane

## 文档状态

- 状态：Authoritative
- 说明：固定当前阶段默认 operator lane、能力等级定义，以及 TUI / GUI / supervisor status 的分工。

## 目标

当前阶段先把系统收口成“没有完整导航也能稳定运行的遥控与调试平台”。

因此当前权威口径固定为：

1. 遥控路径是唯一默认主路径。
2. 导航是可选增强，不是当前系统生死依赖。
3. IMU-only 只能解释成姿态反馈，不能写成完整导航。
4. DVL 是外接可拆模块，不是默认启动硬依赖。

## 当前默认 operator lane

默认顺序固定为：

1. `device-check`
2. `device-scan`
3. `startup-profiles`
4. `preflight`
5. `start`
6. `status`
7. `teleop`
8. `stop`
9. `bundle`

当前执行分工：

- 车端运行基线：`phase0_supervisor.py --profile control_only`
- 遥控入口：`UnderWaterRobotGCS` TUI
- 只读观察入口：`UnderWaterRobotGCS` GUI overview
- 结构化调试快照：`phase0_supervisor.py status --json`

## 能力等级定义

### 1. `control_only`

当前状态：已落地，也是默认激活能力。

含义：

- 当前只保证 control + comm bring-up、遥控、日志记录和 bundle 导出。
- 不宣称姿态反馈、相对导航或绝对定位。
- 没有导航数据时系统仍然可以运行，不应直接被判成 fatal。

当前允许：

- `preflight -> start -> status -> teleop -> stop -> bundle`
- Manual
- Failsafe
- child logs / telemetry timeline / control loop / incident bundle

当前必须禁用：

- `AUTO`
- 任何 nav-dependent 自动闭环
- 任何“导航 ready / full stack validated”结论

### 2. `attitude_feedback`

当前状态：已完成定义与外围表达；当前仍属于升级能力，不是默认激活能力。

触发条件：

- `startup_profile=imu_only`
- IMU 可识别
- 当前 lane 明确切到允许导航 preview 的路径时，才把这一级当成当前激活能力

含义：

- 只能提供姿态角、角速度、加速度这类姿态反馈与运动分析信息
- 不能写成“导航正常”
- 不能写成“位置可用”

推荐观察字段：

- `roll / pitch / yaw`
- `gyro`
- `accel`

### 3. `relative_nav`

当前状态：已完成定义与外围表达；当前仍属于升级能力，不是默认激活能力。

触发条件：

- `startup_profile=imu_dvl`
- IMU + DVL 可识别
- 当前 lane 明确切到允许导航 preview 的路径时，才把这一级当成当前激活能力

含义：

- 只能提供速度与短时相对运动信息
- 不能写成“绝对定位可用”
- 不能把它包装成 full-stack release

推荐观察字段：

- `roll / pitch / yaw`
- `gyro`
- `accel`
- `velocity`
- `relative_position`

### 4. `full_stack_preview`

当前状态：保留占位，不展开。

当前不应并入默认 lane 的原因：

- USBL 真实样本仍不足
- 更复杂 profile 仍未完成真实 bench 收口
- 会显著扩大调试变量和 operator 误解风险

## 当前阶段如何解释“激活能力”和“升级前提”

当前必须区分两个概念：

1. `active capability`
   - 指当前 runtime 真正已经激活的能力等级。
2. `device-ready capability`
   - 指当前设备集合已经具备的升级前提。

因此：

- `control_only` lane 下，即使识别到了 IMU 或 IMU + DVL，也不能直接把当前 active capability 写成 `attitude_feedback` 或 `relative_nav`。
- 这时最多只能写成：设备已经具备升级前提，但当前默认 lane 仍固定为 `control_only`。

## 当前运动信息观察面

当前阶段固定使用三层观察面：

1. TUI
   - 遥控主入口
   - 负责实际 teleop 操作
2. GUI overview
   - 只读状态 / motion observer
   - 负责显示当前能力等级、IMU/DVL 在线状态和保守的 motion 文案
3. `phase0_supervisor.py status --json`
   - 结构化调试入口
   - 当前可直接暴露：
     - `sensor_inventory`
     - `capability`
     - `operator_lane`
     - `motion_info`

说明：

- 当前 UDP `STATUS` 协议不扩面，不新增姿态/速度数值字段。
- 若需要读取结构化 motion snapshot，优先复用 `control_loop_*.csv` 和 supervisor `status --json`。
- GUI 当前只做保守表达，不把 IMU-only 包装成完整导航。

## 为什么 DVL 不是默认启动依赖

1. DVL 是外接可拆模块，现场存在未连接、晚连接、单独更换和重枚举情况。
2. 当前默认目标先是“系统能稳定遥控与调试”，不是“默认进入更强导航能力”。
3. 因此 DVL 当前只能作为 `relative_nav` 的增强条件，而不是 `control_only` 的启动硬依赖。

## 当前传感器诊断与低频观察口径

当前阶段必须把“能直接显示的低频诊断”与“仍需回到 preflight / child logs 才能确认的错误”分开。

当前已落地、可直接在 GUI / supervisor status 里稳定表达的低频状态包括：

1. `online`
2. `not_present`
3. `format_invalid`
4. `stale`
5. `optional_missing`
6. `not_enabled`

当前应这样理解：

- `online`
  - 当前传感器在线，可继续看对应的低频状态与 motion 文案。
- `not_present`
  - 当前没有识别到对应设备，或当前 runtime 没有报告该设备在线。
- `format_invalid`
  - 当前更多等价于 bind mismatch / status mismatch；实机前应优先回到 `device-scan`、`/dev/serial/by-id`、child logs 核对。
- `stale`
  - 当前设备可能在线，但状态老化或重连未稳定；不要立刻写成“设备完全不可用”。
- `optional_missing`
  - 当前设备缺失，但 teleop primary lane 允许继续。典型场景就是外接 DVL 未接。
- `not_enabled`
  - 当前 lane 没有启用对应观察能力；典型场景是 `control_only` 下的 motion info。

当前仍不能在默认 GUI / STATUS 里稳定区分、需要回到 preflight / child logs / supervisor faults 才能确认的状态包括：

1. `open_failed`
2. `permission_denied`
3. 更细粒度的 `format_invalid` 原因

因此当前权威解释是：

- GUI / STATUS 负责低频只读观察。
- `preflight`、`last_fault_summary.txt`、`child_logs/` 负责更底层的打开失败、权限、格式细节。

## `comm_events.csv` 最小排障链准备

当前阶段不把 `comm_events.csv` 扩成复杂通信平台，只冻结最小排障链。

建议最小落点：

1. 运行时路径：`logs/<YYYY-MM-DD>/<run_id>/comm/comm_events.csv`
2. bundle 内路径：`events/gcs_server/comm_events.csv`
3. 写入原则：
   - 只记低频生命周期事件
   - 不按每个 STATUS 包高频刷屏
   - 一条事件只回答一个问题：链路状态、命令发送、ACK、超时、结果

建议最小字段：

1. `mono_ns`
2. `wall_time`
3. `event`
4. `severity`
5. `session_id`
6. `link_state`
7. `tx_seq`
8. `ack_seq`
9. `intent_cmd_seq`
10. `command_kind`
11. `command_status`
12. `result`
13. `detail`

建议最小事件集合：

1. `comm_link_state`
2. `session_state_changed`
3. `command_sent`
4. `command_ack`
5. `command_ack_timeout`
6. `command_result`

当前建议如何接入 operator / 排障路径：

1. `bundle` 继续把它当作 `events.gcs_server.comm_events` optional artifact。
2. runbook 里把它放到 `child_logs` 之后、`control_events.csv` 同级的位置。
3. GUI 当前不直接消费 `comm_events.csv`，先保持只读状态面；排障时由 operator / developer 回到 bundle 与 runbook 手工核对。
4. 若后续进入最小实现，优先只做 `gcs_server` 单点、低频 CSV 落地，不并行改多个核心模块。

## 什么时候再恢复导航为强依赖场景

只有以下条件都满足，才建议恢复“导航是默认强依赖”的口径：

1. IMU / DVL 静态身份样本补齐。
2. `imu_only` 真实 bench 已完成 `start -> status -> stop -> bundle`。
3. `imu_dvl` 真实 bench 已完成 `start -> status -> stop -> bundle`。
4. GCS / runbook / supervisor status 的能力表达已经稳定一致。
