# Nav View Contract

## 文档状态

- 状态：Authoritative
- 说明：当前生效的系统级基线文档。


## 适用范围

当前 `NavStateView` 来源于：

- `shared/msg/nav_state_view.hpp`
- `shared/shm/nav_state_view_shm.hpp`
- `gateway/apps/nav_viewd.cpp`
- `gateway/IPC/nav/nav_view_builder.*`
- `gateway/IPC/nav/nav_view_policy.*`

默认 SHM 名称：

- `/rovctrl_nav_view_v1`

当前 wire/version 基线：

- `kNavStateViewWireVersion = 2`

## 1. 为什么需要 `NavStateView`

`NavStateView` 不是对 `NavState` 的机械拷贝，而是控制侧可消费的导航视图。

它的职责是：

1. 保留导航状态语义。
2. 在 gateway hop 上应用 stale/no-data 策略。
3. 防止控制侧直接依赖估计器内部细节。
4. 避免旧 payload 在 stale/no-data 条件下继续被控制误用。

## 2. 关键字段

当前 `NavStateView` 核心字段包括：

- `version`
- `flags`
- `stamp_ns`
- `mono_ns`
- `age_ms`
- `valid`
- `stale`
- `degraded`
- `nav_state`
- `health`
- `fault_code`
- `sensor_mask`
- `status_flags`
- `pos[3]`
- `vel[3]`
- `rpy[3]`
- `depth_m`
- `omega_b[3]`
- `acc_b[3]`

### `flags` 位

当前 `flags` 主要表达哪些控制面字段在本帧可解释：

- `kHasPosition`
- `kHasVelocity`
- `kHasRPY`
- `kHasDepth`
- `kHasOmegaBody`
- `kHasAccBody`

## 3. 构建规则

当前 gateway 侧应遵守：

1. `stamp_ns` 透传 `NavState.t_ns`。
2. `mono_ns` 表示 gateway 发布该视图的本地 monotonic 时间。
3. `age_ms` 在上游基础上继续累积，不能被静默归零。
4. fresh 且 valid 的上游状态，允许携带完整控制面 payload。
5. stale/no-data 时，必须发布显式诊断帧，而不是保留旧 payload 假装还可用。
6. degraded 状态可以透传，但不能被升级成 OK。

## 4. stale/no-data 规则

这是当前最重要的控制侧契约之一：

- stale/no-data 时，`NavStateView` 仍可以是一帧“有诊断信息的有效传输帧”
- 但它必须是“控制不可用帧”
- 其时间戳、fault、status_flags 可以保留
- 其控制面运动学 payload 不应继续作为可信控制输入使用

## 5. 控制侧消费规则

控制侧当前必须：

1. 读 `NavStateView`，不是直接读 `NavState`。
2. 先看 `valid/stale/degraded/nav_state/fault_code/status_flags`。
3. `valid=1` 且 `stale=0` 才能进入可信导航消费路径。
4. `degraded=1` 仅表示“受限可用”，是否允许进入 Auto 由策略决定。
5. 本地如果再次超出年龄预算，可以进一步把该视图判为 stale。

## 6. UI/遥测关系

UI 不应直接把 `NavStateView` 当作最终用户态来源。

当前推荐关系是：

`NavStateView -> ControlGuard/ControlLoop -> TelemetryFrameV2 -> GCS/TUI`

也就是说，UI 看到的导航可信性最好来自控制已经消费过并重新发布的权威状态。

## 7. ABI 规则

当前 `NavStateView` 需满足：

- standard layout
- trivially copyable
- SHM header magic: `NVW1`
- SHM layout version: `1`

## 8. 文档漂移说明

旧版说法里如果还把导航输入简化成：

- 有快照
- 没快照
- 一个布尔 `nav_present`

那已经不符合当前契约。

当前真实语义必须显式区分：

- stale
- invalid
- degraded
- no-data/diagnostic frame
