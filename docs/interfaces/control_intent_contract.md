# Control Intent Contract

## 文档状态

- 状态：Authoritative
- 说明：当前生效的系统级基线文档。


## 适用范围

当前 `ControlIntent` 来源于：

- `shared/msg/control_intent.hpp`
- `shared/shm/control_intent_shm.hpp`
- `gateway/apps/gcs_server.cpp`
- `pwm_control_program/include/io/input/gcs_shm_input_provider.hpp`

## 1. 当前生产主路径

当前生产主路径是：

```text
GCS
  -> protocol/session
  -> gcs_server
  -> /rovctrl_gcs_intent_v1
  -> GcsShmInputProvider
  -> ControlGuard / ControlLoop
```

## 2. 辅助路径

当前代码中仍存在若干辅助 intent 路径：

- `/rovctrl_intent_local_v1`
- `/rovctrl_intent_auto_v1`
- `/rovctrl_intent_final_v1`
- `/rovctrl_intent_mux_v1`

这些路径主要用于：

- 本地 bench
- 实验性意图仲裁
- 后续自动化扩展预留

它们不应被误写成“当前首选操作主线”。

## 3. 结构字段

当前 `ControlIntent` 主要字段包括：

- `version`
- `flags`
- `cmd_seq`
- `stamp_ns`
- `ttl_ms`
- `source_id`
- `source_prio`
- `request_exit`
- `estop`
- `clear_estop`
- `arm`
- `disarm`
- `mode_request`
- `teleop_dof_cmd`
- `motor_test`

### `mode_request`

当前 `ControlMode` 包括：

- `kNone`
- `kManual`
- `kAuto`
- `kHold`
- `kFailsafe`

### `source_id`

当前 `IntentSource` 包括：

- `kUnknown`
- `kGcs`
- `kLocal`
- `kAuto`
- `kTest`

### `flags`

当前 `IntentFlags` 用于声明 payload 中哪些命令片段有效，例如：

- `kHasEStopCmd`
- `kHasArmCmd`
- `kHasModeRequest`
- `kHasTeleopDof`
- `kHasExitRequest`
- `kHasMotorTest`

## 4. 时间与新鲜度规则

当前必须遵守：

1. `cmd_seq` 对每个 source 都应是单调递增的。
2. `stamp_ns` 应表达源侧 monotonic 时间。
3. 上游 `stamp_ns/cmd_seq/ttl_ms` 不应在下游仲裁时每周期被重写。
4. `ttl_ms=0` 的语义是“使用接收端默认策略”或“策略定义的无限制”，不能靠猜。

这条规则很关键，因为早期系统里曾经出现过每轮改写时间元数据，导致 stale 永远收敛不了的问题。

## 5. 命令生命周期

当前建议统一区分四层状态：

1. `sent`
2. `acked`
3. `accepted/executed`
4. `rejected/expired/failed`

含义：

- `sent`
  - GCS 已经发包
- `acked`
  - gateway/session 已确认收到包
- `accepted/executed`
  - 控制栈已经接受/执行该意图
- `rejected/expired/failed`
  - 控制栈明确给出负结论

硬规则：

- transport ACK 不等于运行时成功

## 6. 安全规则

当前安全边界为：

1. `ControlGuard` 拥有最终安全裁决权。
2. `ControlLoop` 不得绕过或覆盖 `ControlGuard` 的 no-nav/stale/estop/failsafe 决策。
3. `MotorTest` 是显式特例路径，但必须是可诊断、可超时、可回传的受控覆盖路径。

## 7. ABI 与 SHM 规则

当前 `ControlIntent` SHM 头要求：

- magic: `INT1`
- layout version: `1`
- payload version: `1`

并要求：

- standard layout
- trivially copyable

## 8. 文档漂移说明

旧资料中如果把 `/rovctrl_intent_final_v1` 或 `mux` 路径写成当前默认生产主路径，
那已经不够准确。

当前更准确的表述是：

- 生产主路径：`/rovctrl_gcs_intent_v1`
- mux/local/auto 路径：辅助和预留路径
