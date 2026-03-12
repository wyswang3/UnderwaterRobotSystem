# 导航故障处理整改方案

## 目标

把当前导航模块从“数值输出优先”改成“状态语义优先”：

- 无有效输入时不输出可被误用的合法导航状态
- 任何降级、过期、未初始化、故障都必须显式编码
- 控制模块能明确知道是否可控、为什么不可控、应该怎么退化

## 本轮已落地

- `shared::msg::NavState` 增加了 `valid/stale/degraded/nav_state/fault_code/sensor_mask/age_ms`
- `NavRunState` 已收敛为：
  - `kUninitialized`
  - `kAligning`
  - `kOk`
  - `kDegraded`
  - `kInvalid`
- `NavFaultCode` 当前已实现：
  - `kEstimatorUninitialized`
  - `kAlignmentPending`
  - `kImuNoData`
  - `kImuStale`
  - `kEstimatorNumericInvalid`
  - `kNavOutputStale`
  - `kNavViewStale`
  - `kNoData`
- `nav_core` 发布前已增加显式门控：
  - 无 IMU
  - 对准未完成
  - 首次传播未建立
  - IMU stale
  - ESKF 数值非有限
  以上场景均不再发布 `valid=1`
- `DVL` 缺失已改为 `kDegraded + valid=1 + degraded=1`，不再伪装成 `OK`
- `nav_viewd` stale/no-data 时会发布显式 invalid 诊断帧，并清空控制面运动学 payload
- `ControlGuard` 的 Auto 模式现在要求同时满足：
  - `valid=1`
  - `stale=0`
  - `fault_code=kNone`
  - `nav_state in {kOk,kDegraded}`
  - `IMU_OK + ALIGN_DONE + ESKF_OK`

## 1. 建议的统一状态模型

### 1.1 NavHealth

保留粗粒度枚举，但语义必须固定：

- `UNINITIALIZED`
  - 尚未完成最小初始化条件
  - 包括刚启动、还没收到足够 IMU、对准未完成
- `OK`
  - 控制允许使用
  - 关键传感器 fresh，滤波器数值正常
- `DEGRADED`
  - 仍可输出，但必须由控制按模式判定是否可用
  - 例如 DVL 丢失但 IMU 仍在传播
- `INVALID`
  - 当前状态不可用于闭环控制

### 1.2 已实现的显式字段

本轮已经在 `NavState` / `NavStateView` 中统一为：

- `stamp_ns` / `t_ns`
- `age_ms`
- `valid`
- `stale`
- `degraded`
- `nav_state`
- `fault_code`
- `sensor_mask`
- `status_flags`

### 1.3 建议的 fault code 分层

本轮先落地最小可用 fault code，后续仍建议扩展到分层编码：

- `1xxx` 设备接入
  - `1001 IMU_PORT_NOT_FOUND`
  - `1002 IMU_OPEN_FAILED`
  - `1003 IMU_DEVICE_BUSY`
  - `1004 IMU_IDENTITY_MISMATCH`
  - `1101 DVL_PORT_NOT_FOUND`
- `2xxx` 数据新鲜度
  - `2001 IMU_NO_DATA`
  - `2002 IMU_STALE`
  - `2101 DVL_NO_DATA`
  - `2102 DVL_STALE`
  - `2201 DEPTH_NO_DATA`
  - `2202 DEPTH_STALE`
- `3xxx` 估计器状态
  - `3001 ALIGN_NOT_DONE`
  - `3002 ESKF_UNINITIALIZED`
  - `3003 ESKF_DT_INVALID`
  - `3004 ESKF_COV_DIVERGED`
  - `3005 ESKF_NUMERIC_INVALID`
- `4xxx` 输出与 IPC
  - `4001 NAV_SHM_PUBLISH_FAILED`
  - `4002 NAV_VIEW_STALE`
  - `4003 CONTRACT_VERSION_MISMATCH`

## 2. 建议的导航状态机

### 2.1 推荐状态

当前已经落地为：

1. `kUninitialized`
2. `kAligning`
3. `kOk`
4. `kDegraded`
5. `kInvalid`

### 2.2 状态迁移条件

- `kUninitialized -> kAligning`
  - 已收到 IMU，但 bias/对准或首次传播尚未完成
- `kAligning -> kOk`
  - 最小初始化完成
  - 至少包括 IMU 传播已建立，且若启用静止零偏估计则 `ALIGN_DONE`
- `kOk -> kDegraded`
  - DVL/深度等辅助观测缺失，但 IMU 仍 fresh
- `kOk/kDegraded -> kInvalid`
  - IMU stale
  - 数值非有限
  - 协方差明显发散

## 3. 传感器输入完整性检查

### 3.1 IMU

必须检查：

- 端口是否存在
- 是否成功打开
- 是否持续收到字节流
- 是否持续收到合法帧
- 最后有效帧时间
- 设备身份是否匹配

当 IMU 不满足最小条件时：

- `health = UNINITIALIZED` 或 `INVALID`
- `valid = 0`
- `fault_code = IMU_*`
- 禁止输出可被控制直接消费的导航有效状态

### 3.2 DVL

必须区分：

- 未接入
- 已接入但无底锁
- 有底锁但速度被门控拒绝
- 时间戳 stale

这几类不能都折叠成“DVL 不好使”。

### 3.3 深度计

当前在线主链路没有深度计接入，应明确标记：

- 不是“深度正常但值为 0”
- 而是“深度源未接入”

## 4. NavState / NavView 发布语义

### 4.1 发布红线

以下情况禁止 `valid=1`：

- `last_propagate_time == 0`
- 初始化/对准未完成
- IMU stale
- 关键字段非有限
- 估计器明确数值异常

### 4.2 降级语义

以下情况允许发布，但必须是 `degraded=1`：

- DVL 缺失，仅惯导传播
- 深度计缺失但控制模式不依赖深度
- 更新时间超过 soft threshold 但未超过 hard threshold

### 4.3 stale 语义

必须统一两类时间：

- `stamp_ns`
  - 状态对应的融合时间
- `mono_ns`
  - 当前 hop 发布到 SHM 的时间
- `age_ms`
  - 当前 hop 发布时，`stamp_ns` 相对 `mono_ns` 的总老化时间

当前约定：

- nav 进程发布 `NavState` 时先计算一次 `age_ms`
- gateway 发布 `NavStateView` 时重新按本 hop `mono_ns` 更新 `age_ms`
- control 侧读取 `NavStateView` 时继续把本地 hop 延迟叠加到 `age_ms`
- stale 判断最终以 `age_ms` 和 `stale` 位为准，不再三处各算各的

## 5. 控制侧保护逻辑

控制模块应明确区分：

- `no_data`
- `invalid`
- `degraded`
- `stale`

不应只剩一个 `nav_valid`。

建议控制消费逻辑：

- Manual 模式
  - 可在 `nav invalid` 下继续工作，但不得使用导航闭环量
- Auto 模式
  - 必须要求 `valid=1`
  - 必须检查 `fault_code == 0`
  - 按模式决定是否要求 `DVL_OK`、`DEPTH_OK`
- Failsafe 模式
  - 可不依赖导航，但必须记录触发原因

## 6. 渐进式落地顺序

### P0

- 已完成：补 `valid/stale/fault_code/nav_state/sensor_mask` 语义
- 已完成：未初始化或 IMU 缺失时禁止输出 `valid=1`
- 已完成：控制侧 Auto 模式增加无效导航保护
- 未完成：IMU 设备身份识别和稳定路径

### P1

- 把 `NavHealthMonitor` 真正接入主链路
- 完善事件日志
- 完善 `sensor_mask` 与 fault code 文档

### P2

- 增加诊断界面
- 增加回放驱动的自动化故障注入
- 支持参数热更新和在线诊断
