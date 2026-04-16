# Minimum Viable Runtime Profiles

## 文档状态

- 状态：Authoritative
- 说明：固定当前阶段最小可运行路径、导航可选边界，以及 runtime level 与 startup profile 的关系。

## 目的

当前真实设备尚未完全就绪，因此系统需要先收口成“控制侧可独立运行、导航侧可选”的最小可行底座。

本文档只定义当前阶段的运行等级边界，不放宽核心 C++ authority 主链，也不把 reserved profile 提前写成已落地能力。

## 术语区分

1. `runtime level`
   - 指操作员当前选择的运行等级，用来决定最小必启进程、允许能力和禁止能力。
2. `supervisor profile`
   - 指 `phase0_supervisor.py --profile ...` 的具体进程图选择。
3. `startup profile`
   - 指 `device-scan` / `startup-profiles` / `startup_profile_gate` 基于当前设备集合给出的导航 readiness 结论。

当前推荐关系应固定为：

- `runtime level` 决定“系统至少要怎么启动”。
- `startup profile` 只决定“当前导航 readiness 到哪一步”。
- 不允许再把“导航 readiness 不满足”直接解释成“整个系统不能启动”。

## 当前运行等级

### 1. `control_only`

当前状态：已落地，且是默认推荐运行等级。

对应 supervisor profile：`control_only`

必选进程：

- `pwm_control_program`
- `gcs_server`

可选模块：

- `uwnav_navd`
- `nav_viewd`

当前处理方式：

- 导航进程默认不启动。
- `device-scan`、`startup-profiles`、`startup_profile_gate` 仍然执行，但只用于解释导航 readiness。
- `no_sensor`、`volt_only`、设备歧义、静态样本缺口，都不再阻塞最小控制链启动。

允许能力：

- `preflight -> start -> status -> stop -> bundle`
- control + comm bring-up
- 手动控制链路检查
- telemetry / 事件日志 / child logs / incident bundle 导出
- 无导航条件下的 operator path、delivery path、排障链路验证

必须禁用：

- `AUTO`
- 任何依赖 trusted nav 的自动闭环模式
- 把当前 run 写成“导航 ready”或“full stack 已验证”
- 任何真实推进器放权结论

GCS / GUI 当前预期：

- `Motion Info` 当前应显示 `Control Only` 或等价的 capability-aware 提示
- 诊断摘要仍可能出现 `stale,invalid,NoData`，但这不应被直接解释成整个系统 fatal
- 这表示“当前没有启用完整导航 / 当前只运行默认遥控路径”，不是 `control_only` 运行失败

## 2. `control_nav_optional`

当前状态：设计口径已收口，但还不是单独落地的 supervisor process graph。

当前映射方式：

- 默认先走 `control_only`
- 只有在设备就绪、`startup_profile` 稳定指向 `imu_only` / `imu_dvl` 时，才进入现有 `bench` nav preview / safe smoke lane

目标含义：

- control + comm 始终是最低必选项
- nav bring-up 变成条件满足时的可选增强，而不是当前阶段的硬依赖

当前允许能力：

- `control_only` 的全部能力
- 在 IMU / DVL readiness 已明确时做导航 preview / safe smoke

当前仍然禁止：

- 把 `bench` 写成正式 field runtime
- 把 `imu_only` / `imu_dvl` preview 写成 full-stack release
- 把 USBL、多传感器复杂 profile、导航模式分级重构并入当前 lane

## 3. `full_stack_preview`

当前状态：保留设计，不启用。

含义：

- 只作为后续更复杂 profile 的占位 runtime level
- 不作为当前默认路径
- 不作为当前交付承诺

当前不应展开：

- USBL / `imu_dvl_usbl`
- 三传感器大重构
- 更复杂导航模式分级
- ROS2 authority 化

## startup profile 与运行等级映射

当前固定解释：

1. `no_sensor`
   - `navigation_requirement=disabled`
   - `runtime_level_hint=control_only`
2. `volt_only`
   - `navigation_requirement=disabled`
   - `runtime_level_hint=control_only`
3. `imu_only`
   - `navigation_requirement=required`
   - `runtime_level_hint=control_nav_optional`
4. `imu_dvl`
   - `navigation_requirement=required`
   - `runtime_level_hint=control_nav_optional`
5. `imu_dvl_usbl` / `full_stack`
   - 仍是 reserved / preview，不进入当前默认 lane

解释原则：

- `startup profile=no_sensor / volt_only` 只表示“当前导航不启用”。
- `startup profile=imu_only / imu_dvl` 只表示“已经具备进入导航 preview lane 的条件之一”。
- 当前阶段不能把 `startup profile` 直接当成最终 field mode。

## 当前默认推荐

当前默认推荐运行等级固定为：`control_only`

推荐原因：

1. 设备尚未完全就绪时，先保证 control + comm + logging + bundle 的最小产品底座稳定。
2. 导航设备缺失、静态规则仍待补样本时，不应继续把导航当成整个系统的启动硬依赖。
3. 这样可以先收口 operator lane、runbook、incident bundle、delivery baseline，再回头做真实导航 bench。

## 什么时候再把导航恢复为强依赖场景

只有同时满足以下条件，才建议恢复“导航是默认强依赖”的场景：

1. IMU / DVL 的静态身份样本已补齐，静态规则完成收口。
2. `imu_only` 真实 bench 已完成 `start -> status -> stop -> bundle`。
3. `imu_dvl` 真实 bench 已完成 `start -> status -> stop -> bundle`。
4. operator lane、bundle、runbook、GCS 状态展示已在上述两条路径下稳定一致。

在这些条件满足前，导航仍应保持“可选增强模块”的地位，而不是最小产品底座的硬前置条件。

## ControlGuard 与无导航边界

当前外围文档应统一按以下口径解释：

1. `Manual` 可用。
2. `Failsafe` 可用。
3. `AUTO` 依赖 trusted nav，没有导航时必须拒绝或保持禁用。
4. 本轮不改 `ControlGuard` / `ControlLoop` 核心逻辑，只把这条边界明确写进 runbook 与 handoff。
