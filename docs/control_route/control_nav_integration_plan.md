# Control And Navigation Integration Plan

## 文档状态

- 状态：Working draft
- 说明：当前设计方向或阶段性方案已冻结，但尚未全部实施。


## 1. 文档目标

本文档用于冻结下一阶段“控制与导航整合 + 通信链路统一拉起”设计边界。

本文档只定义：

- 进程职责与 authority 边界
- supervisor / launcher 的最小职责
- 启动顺序、依赖检查、失败恢复原则
- 本轮绝不能破坏的核心主链

本文档不直接授权：

- 改写控制主循环
- 改写导航估计算法
- 用 Python 或 ROS2 接管核心 authority
- 把 `gcs_server` 改造成一体化大进程

## 2. 当前真实入口与 Authority 边界

### 2.1 控制侧真实入口

当前控制侧真实入口是 `pwm_control_program`。

职责边界：

- 读取控制意图
- 读取 `NavStateView`
- 由 `ControlGuard` 做最终安全裁决
- 进行控制计算、分配、PWM 输出
- 生成权威 `TelemetryFrameV2`

结论：

- `pwm_control_program` 是控制 authority
- `ControlGuard` 是最终安全裁决 authority
- 本轮重构不得绕过该链路

### 2.2 导航侧真实入口

当前导航侧真实入口是 `uwnav_navd`。

职责边界：

- IMU / DVL 在线读取与设备绑定
- 预处理与状态估计
- 发布 `NavState`
- 写 `nav.bin`、`nav_timing.bin`、`nav_state.bin`

结论：

- `uwnav_navd` 是导航 authority
- 本轮重构不得把在线传感器主链回退成 Python authority

### 2.3 通信链路真实入口

当前通信链路真实入口不是单一进程，而是两部分：

- `gcs_server`：会话、UDP、控制命令接入、telemetry 下发
- `nav_viewd`：`NavState -> NavStateView` 投影与 stale 语义桥接

结论：

- `gcs_server` 是通信边界，不是控制 authority
- `nav_viewd` 是导航到控制的桥接进程，不是导航 authority

### 2.4 Telemetry authority

当前运行态 telemetry authority 是 `TelemetryFrameV2`，其上游发布者是 `pwm_control_program`。

结论：

- UI、ROS2、脚本工具都只能消费 authority telemetry
- 本轮不得在外围层再造一套“更真”的运行态状态机

## 3. 当前可信主链

当前线上可信主链如下：

```text
GCS
  -> gcs_server
  -> /rovctrl_gcs_intent_v1
  -> pwm_control_program
  -> PwmClient / STM32

IMU / DVL
  -> uwnav_navd
  -> /rov_nav_state_v1
  -> nav_viewd
  -> /rovctrl_nav_view_v1
  -> pwm_control_program

pwm_control_program
  -> /rovctrl_telemetry_v2
  -> gcs_server
  -> GCS
```

其中：

- `uwnav_navd` 负责导航估计 authority
- `nav_viewd` 负责控制可消费视图
- `pwm_control_program` 负责控制 authority 与 telemetry authority
- `gcs_server` 负责远端会话与传输边界

## 4. 目标进程图

目标形态不是合并主链，而是在现有主链外增加一个薄 supervisor：

```text
supervisor / launcher
  -> preflight
  -> uwnav_navd
  -> nav_viewd
  -> pwm_control_program
  -> gcs_server
  -> optional sidecars
       - sensor tools
       - ROS2 read-only mirror
       - incident helpers
```

设计意图：

- supervisor 统一拉起与观察进程
- supervisor 不进入控制和导航算法内部
- sidecar 只做只读消费或工具辅助
- authority 继续由现有 C/C++ 主链承担

## 5. 为什么采用 Supervisor，而不是让 gcs_server 吞并所有职责

“通信链路统一拉起控制端和导航端”可行，但必须收敛为 supervisor / launcher 方案，而不是把生命周期管理塞进 `gcs_server`。

原因如下：

1. `gcs_server` 崩溃不应拖垮导航与控制主链。
2. `gcs_server` 的职责是通信边界，不是 authority owner。
3. 进程管理、依赖检查、日志汇聚属于运维与产品化职责，不应和会话逻辑硬耦合。
4. 若把所有职责塞进 `gcs_server`，通信故障会放大为全链路故障，回归风险过高。

结论：

- 通信链路适合作为统一拉起的观察视角
- 不适合作为统一 authority 容器

## 6. Supervisor / Launcher 最小职责

supervisor 只负责以下事项：

1. preflight 检查
2. 按顺序拉起进程
3. 关键依赖可见性检查
4. 记录运行 manifest
5. 统一日志目录
6. 失败重启与退出策略
7. 输出最近一次故障摘要

supervisor 明确不负责：

1. 计算控制输出
2. 计算导航状态
3. 替代 `ControlGuard`
4. 替代 `NavState` / `NavStateView` / `TelemetryFrameV2`
5. 直接发送业务控制命令

## 7. 最小启动时序

建议固定以下顺序：

```text
1. preflight
2. uwnav_navd
3. nav_viewd
4. pwm_control_program
5. gcs_server
6. optional sidecar/tools
```

### 7.1 preflight

检查内容：

1. 配置文件存在性与可读性
2. 关键 SHM 名称一致性
3. 串口设备路径或 `by-id` 可见性
4. 日志目录可写性
5. 必需二进制存在性
6. 关键配置参数冲突检查

失败策略：

- preflight 失败时不启动核心进程
- 输出可读错误摘要
- 生成单次启动失败 manifest

### 7.2 先启动 uwnav_navd

原因：

- 导航状态是后续 `nav_viewd` 与控制侧的重要依赖
- 即使 `Manual` 模式不强依赖导航，bring-up 仍应先建立可诊断的 nav path

注意：

- supervisor 只判断导航进程是否启动，不判断导航数值是否“正确”
- 导航是否有效由现有健康语义和后续 runbook 判断

### 7.3 再启动 nav_viewd

原因：

- `nav_viewd` 是控制侧消费导航的唯一桥接层
- 先让 `NavState -> NavStateView` 路径稳定，可以减少控制侧 bring-up 歧义

### 7.4 再启动 pwm_control_program

原因：

- 控制主循环应在 nav path 已建立后再进入运行态
- 可以让 `Manual` 和 `Auto` 的前置状态更清楚地暴露在 telemetry 中

### 7.5 最后启动 gcs_server

原因：

- 避免 GCS 过早连接却看到车载主链尚未建立的混乱状态
- 先让车载 authority 进程起来，再开放远端交互更稳妥

### 7.6 optional sidecar / tools

仅在主链稳定后启动，例如：

- ROS2 read-only mirror
- incident helper
- 传感器采集工具链
- bench / verifier 脚本

## 8. 依赖检查与运行状态约束

### 8.1 依赖检查

建议 supervisor 只做“存在性和连通性”检查，不做业务语义推断。

最小检查项：

- `uwnav_navd` 可执行文件存在
- `nav_viewd` 可执行文件存在
- `pwm_control_program` 可执行文件存在
- `gcs_server` 可执行文件存在
- 配置文件路径存在
- 关键串口路径可见或 `by-id` 解析成功
- 日志目录存在且可写

### 8.2 进程状态分类

建议 supervisor 输出统一的最小状态：

- `not_started`
- `starting`
- `running`
- `retrying`
- `stopped`
- `failed`

说明：

- 这些状态只描述进程生命周期
- 不替代导航健康、控制健康或通信健康语义

## 9. 失败恢复与重启策略

### 9.1 基本原则

1. 各核心进程独立重启，不做“一崩全杀”。
2. 通信进程故障不应停掉导航与控制。
3. 导航故障应通过现有 stale/invalid 语义传到控制，而不是被 supervisor 隐藏。
4. supervisor 负责记录与拉起，不负责篡改安全决策。

### 9.2 推荐重启策略

- `uwnav_navd`
  - 允许自动重启
  - 记录最近 N 次失败原因与时间窗口
- `nav_viewd`
  - 允许自动重启
  - 重启期间控制侧继续按现有 stale 语义处理
- `pwm_control_program`
  - 允许有限次数自动重启
  - 超阈值后转人工确认，避免执行链持续抖动
- `gcs_server`
  - 允许自动重启
  - 不应影响车载主链继续运行

### 9.3 退出策略

建议按逆序退出：

```text
sidecar -> gcs_server -> pwm_control_program -> nav_viewd -> uwnav_navd
```

理由：

- 先断外围，后停 authority 进程
- 避免停机过程中出现大量误导性连接/断连事件

## 10. 运行产物设计

每次启动至少生成以下产物：

1. `run_manifest.json`
2. `process_status.json`
3. `last_fault_summary.txt`

建议字段：

- `run_id`
- `start_wall_time`
- `mono_start_ns`
- `config_paths`
- `binary_paths`
- `device_paths`
- `pid`
- `exit_code`
- `restart_count`
- `last_failure_reason`

## 11. 本轮绝不能破坏的模块

以下模块必须保持现有职责和运行语义稳定：

1. `uwnav_navd`
2. `nav_viewd`
3. `pwm_control_program`
4. `ControlGuard`
5. `PwmClient` / PWM / STM32 执行链
6. `gcs_server`
7. `shared/` 下的运行时契约

原因：

- 这些模块构成当前可信主链
- 当前阶段目标是“收边界、稳 bring-up、减耦合”，不是重写主链

## 12. 实施边界与验收要点

本设计只授权后续做以下低风险收敛：

1. 新增 supervisor / launcher
2. 固化 preflight 检查
3. 固化启动顺序与退出顺序
4. 统一运行 manifest 和日志目录
5. 补充对应 runbook 和 nightly 文档

本设计明确不授权以下高风险动作：

1. 合并 `uwnav_navd` 与 `pwm_control_program`
2. 把 `gcs_server` 改成超级进程
3. 让 ROS2 成为 control/nav 主线
4. 为了迎合 launcher 改写 `shared/` ABI
5. 把控制 authority 迁到 Python

最小验收标准：

1. 核心 4 个进程可按顺序被拉起和停止。
2. 任一单进程重启不会导致其余核心进程被误停。
3. run manifest 和最近一次故障摘要可稳定生成。
4. 现有 `NavState -> NavStateView -> Telemetry -> GCS` 主链语义不变。
