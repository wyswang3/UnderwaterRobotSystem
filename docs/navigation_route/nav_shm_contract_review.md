# NavState / NavView SHM 契约审查

## 1. 当前链路

当前跨进程链路是两段式：

1. `nav_core` 发布 `NavState` 到 `nav_state` SHM
2. `gateway/nav_viewd` 读取 `NavState`，再发布 `NavStateView` 到 `nav_view` SHM
3. `pwm_control_program` 只读取 `NavStateView`

因此，存在两份契约：

- 原始导航契约：`NavState`
- 控制消费契约：`NavStateView`

## 2. 当前发现的问题

### 2.1 NavState SHM ABI 曾经漂移

审查时发现：

- `nav_core` 端 `NavStatePublisher` 使用了私有 header/layout
- `gateway` 端 `NavStateSubscriberShm` 使用 `shared/shm/nav_state_shm.hpp`
- 两者字段顺序和 metadata 不一致

这会导致读端按 canonical 契约拒绝该 SHM。

本轮已修复：

- `NavStatePublisher` 统一切换到 `shared/shm/nav_state_shm.hpp`

### 2.2 SHM 名称默认值曾不统一

审查时存在两套默认值：

- 导航配置：`/rov_nav_state_v1`
- gateway 默认：`/rovctrl_nav_state_v1`

本轮已修正：

- gateway `NavStateSubscriberShm` 默认输入切到 `/rov_nav_state_v1`
- `nav_viewd` 默认输入也切到 `/rov_nav_state_v1`

### 2.3 NavState 语义曾不足

旧版 `NavState` 只有：

- `t_ns`
- 数值状态
- `health`
- `status_flags`

本轮已补齐：

- `valid`
- `stale`
- `degraded`
- `nav_state`
- `fault_code`
- `sensor_mask`
- `age_ms`

### 2.4 NavStateView 已升级到控制消费语义

本轮 `NavStateView` v2 提供：

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
- 数值字段

已修复的问题：

- 不再借用 `reserved1` 透传 `status_flags`
- `status_flags` 成为正式字段
- `fault_code` 和 `sensor_mask` 成为正式字段

### 2.5 stale 判定已统一成逐 hop 累积

- `NavState` 自带 `stale + age_ms`
- `nav_viewd` 在 publish `NavStateView` 时重算当前 hop 的 `age_ms`
- 控制侧 `NavViewShmSource` 继续叠加本地 hop 延迟，并在超 budget 时强制置 `stale=1`

现在的统一语义：

- `stamp_ns`: 该状态对应的真实估计时间
- `mono_ns`: 当前 hop 发布这帧 SHM 的时间
- `age_ms`: 到当前消费者为止已经累积的总 age
- `stale`: 当前消费者看到的最终超时结论

## 3. 建议的统一契约

## 3.1 原始 NavState SHM

建议保持 canonical seqlock header：

- `magic`
- `layout_ver`
- `payload_ver`
- `payload_size`
- `payload_align`
- `seq`
- `mono_ns`
- `wall_ns`

这一层不再允许任何模块自定义 header。

## 3.2 NavState payload 当前定义

本轮已经落地：

- `t_ns`/`stamp_ns`
- `valid`
- `stale`
- `degraded`
- `nav_state`
- `fault_code`
- `sensor_mask`
- `status_flags`

## 3.3 NavStateView 作为控制契约

`NavStateView` 现在已经明确是“控制可消费契约”，字段如下：

- `version`
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
- 运动学字段

### 3.4 控制侧读取契约

控制读取时必须遵守：

- 先检查 `version`
- 再检查 `valid`
- 再检查 `stale`
- 再检查 `fault_code`
- 最后按模式检查 `status_flags`

不能再依赖“只要读到数值就默认可用”。

## 4. 控制侧当前保护缺口

当前控制侧的主要缺口：

- `NavViewShmSource` 把 `invalid`、`stale` 和 `no-data` 全部折叠成 `false`
- `ControlState` 只保留 `nav_valid` 和 `nav_status_flags`
- 控制器大多只看 `nav_valid`

建议最少扩展 `ControlState`：

- `nav_health`
- `nav_fault_code`
- `nav_age_ms`
- `nav_stale`
- `nav_degraded`

## 5. 当前版本化策略

- `NavState` SHM payload version 已升级到 `2`
- `NavStateView` wire version 已升级到 `2`
- 控制侧读取契约现在按以下顺序执行：
  1. ABI/version 校验
  2. 读取 `valid/stale/nav_state/fault_code`
  3. 再按模式消费 `status_flags/sensor_mask`

后续建议：

- 若新增更多 fault code，继续保持 payload version 显式递增
- 若引入日志/回放协议，也复用同一套状态字段定义
