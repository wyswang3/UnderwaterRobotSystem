# Time Contract

## 适用范围

本文档描述当前系统时间语义基线，覆盖：

- `nav_core` 内部样本时间
- `NavState` / `NavStateView` 共享契约
- `TelemetryFrameV2` 中的导航年龄语义
- `nav_timing.bin` 最小复盘时间线

真实依据：

- `nav_core/app/sample_timing.*`
- `shared/msg/nav_state.hpp`
- `shared/msg/nav_state_view.hpp`
- `shared/msg/telemetry_frame_v2.hpp`

## 1. 单调时间轴原则

当前 stale、freshness、hop 间年龄累积和 replay 排序，统一使用单调时间轴。

规则：

1. 语义时间统一基于 monotonic/steady ns。
2. wall time 只用于日志标记和人工比对，不进入 stale 判定。
3. 下游模块不得把 wall/epoch 时间重新解释成导航状态时间。

## 2. `nav_core` 内部样本时间

当前导航内部会同时保留几类时间字段：

- `sensor_time_ns`
  - 语义样本时间
  - stale/freshness 的首要依据
- `recv_mono_ns`
  - 驱动线程解码/接收该样本的本地时间
- `consume_mono_ns`
  - 主循环真正接受并消费该样本的时间
- `mono_ns`
  - 当前内部统一 monotonic 样本时间
- `est_ns`
  - 内部遗留兼容字段
  - 当前不应被解释成 wall-clock 时间

重要说明：

- `est_ns` 仍存在于 nav 内部结构和工具链里
- 但 `est_ns` 不是当前 shared `NavState` 对外契约字段

## 3. 共享契约中的时间字段

### `NavState`

- `t_ns`
  - 导航状态真正对应的估计时间
  - 不是发布线程的当前时间
- `age_ms`
  - 该状态在 nav 发布时已经累计老化的时间

### `NavStateView`

- `stamp_ns`
  - 透传自 `NavState.t_ns`
  - 表示语义导航时间
- `mono_ns`
  - gateway 本 hop 发布该视图的时间
- `age_ms`
  - 继承上游年龄后，再叠加 gateway hop 本地延迟

### `TelemetryFrameV2`

- `stamp_ns`
  - control-core 发布 telemetry frame 的时间
- `system.nav_age_ms`
  - control 实际看到的导航累计年龄
- `system.heartbeat_age_ms`
  - 会话/链路新鲜度，不等同于导航语义时间

### SHM header 时间

各 SHM header 中的 `mono_ns/wall_ns` 是发布器写该块共享内存的时间，
属于传输/落盘元数据，不替代 payload 中的语义时间字段。

## 4. 当前 stale 规则

当前系统统一遵循以下规则：

1. 导航主循环使用 `now - sensor_time_ns` 判断样本是否新鲜。
2. 主循环只消费严格更新的样本；重复样本和乱序样本应被拒绝。
3. `age_ms` 必须跨 hop 累加，不能在转发同一语义状态时被静默清零。
4. 下游不能因为“刚读到 SHM”就把旧状态重新解释为新状态。
5. `t_ns == 0` 的状态不得被解释为可信导航，只能用于极端负路径或 replay fallback 语义对照。

## 5. `nav_timing.bin` 基线

当前最小时间线闭环依赖 `nav_timing.bin`。

它至少应回答：

- 样本是否重复或乱序
- stale 是由语义样本年龄还是本地消费延迟引起
- `sensor -> recv -> consume -> publish` 各阶段延迟分布
- 设备绑定状态何时变化
- 导航何时进入 `invalid/degraded/stale`

当前 `TimingTracePacketV1` 关键字段包括：

- `kind`
- `flags`
- `sensor_time_ns`
- `recv_mono_ns`
- `consume_mono_ns`
- `publish_mono_ns`
- `age_ms`
- `fault_code`

当前最小解析器：

- `nav_core/tools/parse_nav_timing.py`

## 6. UI 和日志消费规则

1. UI 可以显示 age/delay，但不应把 `t_ns/stamp_ns` 渲染成日历时间。
2. GCS/UI 应优先看 `nav_age_ms`、`nav_valid`、`nav_stale`、`nav_degraded` 和 `nav_state`。
3. 现场诊断时，链路年龄和导航年龄必须分开看。

## 7. 当前遗留债务

当前仍有几项明确时间债务：

1. `NavState.t_ns` 命名仍有历史负担，未来更适合统一为 `stamp_ns`。
2. `est_ns` 仍残留在 nav 内部代码和工具里，需要后续有计划退场。
3. 当前 IMU/DVL 还没有稳定的硬件原生时间源，很多 `sensor_time_ns` 仍是主机侧推导值。
4. 无设备负路径下的 `t_ns == 0` 样本，只能做语义传播验证，不能做精确节奏重建。

## 8. 文档漂移说明

旧版时间文档中如果把 `est_ns` 当作 shared `NavState` 对外字段来讲，
那已经不符合当前共享契约；当前对外语义以 `t_ns`、`stamp_ns`、`age_ms` 为准。
