# Upgrade Strategy

## 文档状态

- 状态：Authoritative
- 说明：当前生效的系统级基线文档。


## 1. 当前阶段判断

截至 2026-03-21，项目已经完成 P0 契约/时间/状态基线和一轮客户可用性整改，当前应被定义为：

- P0 权威状态与契约基线已经建立
- P1 联调、重连、replay、客户可用性仍在持续收口
- 外围产品化能力开始进入“受控扩展”阶段

因此，当前阶段目标不是继续做大重构，而是：

1. 继续稳住控制、导航、状态传播、执行主链
2. 把外围 UI / 诊断 / 工具能力逐步产品化
3. 只在不破坏 authority 边界的前提下引入新桥接层

## 2. 当前阶段目标

当前阶段必须完成的目标：

1. 固化跨仓统一的升级参考文档和项目原则。
2. 保持客户最小安装、启动、连接、诊断路径可执行。
3. 继续补齐真实设备重连、重枚举和 replay 样本验证。
4. 收紧 `shared/` 契约治理，减少镜像副本漂移风险。
5. 让外围消费层逐步统一到同一套权威状态字段上。
6. 启动 ROS2 外围桥接第一阶段，但只限 mirror / diagnostics / UI backend / logging 入口。

## 3. 下一阶段目标

在当前阶段目标完成后，下一阶段才应推进：

1. ROS2 bridge 的 colcon/package 化和真实 ROS2 runtime 验证。
2. 基于 bridge 的 health monitor、UI backend、rosbag2 录包链路。
3. PID hold-controller 的 HIL/实机验收。
4. Auto reference 契约收口。
5. trajectory/任务层接入前的模态切换和回放验证。

## 4. 先做什么，后做什么

### 现在优先做

1. 真实 IMU/DVL 热插拔和错误设备样本采集。
2. `shared/` 真源治理和兼容性矩阵更新。
3. replay compare 与 incident bundle 的流程固化。
4. GCS/GUI 的诊断可读性提升。
5. 只读 ROS2 mirror 与 bridge 基础。

### 明确后做

1. ROS2 bridge 的写回接口或控制入口包装。
2. 完整 GUI 平台化、远程编排和复杂配置页。
3. 复杂 trajectory tracking。
4. 更高级控制分配器，例如 WLS/QP。
5. 核心主线的语言/框架大迁移。

### 当前明确不建议做

1. 把导航、控制、状态传播主链改造成 ROS2 原生图。
2. 用 ROS2 topic 替换 `ControlIntent`、`NavStateView` 或 PWM/STM32 执行链。
3. 用 Python 或 ROS2 取代车载导航/控制主循环。
4. 在没有契约升级说明的情况下改动 shared ABI。
5. 在外围 bridge 还只是只读 mirror 时，提前承诺完整 ROS2 平台化。

## 5. 分阶段验收标准

### 阶段 A：P1 收口

验收标准：

1. 真实硬件至少完成一组正常启动样本和一组断连恢复样本。
2. `NavState -> NavStateView -> Telemetry -> GCS` 诊断链可解释。
3. incident bundle、replay 注入、replay compare 至少能在一组真实样本上重复执行。
4. 文档、runbook、兼容性矩阵与当前代码一致。

### 阶段 B：共享契约与诊断产品化

验收标准：

1. `shared/` 的唯一真源治理方案落地。
2. ABI/version/layout 检查规则明确并可执行。
3. 操作员可直接看到关键 nav/device/timing 诊断，不必先读源码。
4. 关键故障窗口可通过固定 runbook 导出、注入、对照。

### 阶段 C：客户可用性与 GUI 收口

验收标准：

1. 新用户按文档可以完成最小安装、启动、连接。
2. GUI/TUI 能区分连接、设备、导航、控制、命令和故障摘要。
3. 常见故障至少有一条明确的下一步检查建议。
4. Linux 路径稳定，Windows 差距被记录清楚。

### 阶段 D1：ROS2 外围桥接第一阶段

验收标准：

1. 第一批 `rov_msgs` mirror 消息冻结并形成字段映射文档。
2. 只读 bridge 能镜像 `TelemetryFrameV2`、`NavStateView`、`NavState`。
3. `stamp_ns` / `t_ns` / `age_ms` / `fault_code` / `status_flags` / `command_result` 语义不被 bridge 改写。
4. bridge 崩溃或停掉不会影响控制、导航、执行主链运行。
5. 至少有一组单测或 dry-run 验证可重复执行。

### 阶段 D2：ROS2 外围消费层

验收标准：

1. health monitor、UI backend、rosbag2 等外围消费者只依赖只读 mirror。
2. ROS2 graph 故障不会影响核心链 authority。
3. 外围消费者的时间和 stale 解释与当前契约一致。

## 6. 当前最推荐的升级顺序

1. 先冻结文档与契约基线。
2. 再做真实设备重连/重枚举样本采集和复盘。
3. 再把 replay compare 与 incident bundle 工具链标准化。
4. 然后补 `shared/` 真源治理和兼容性收口。
5. 然后做 GCS/GUI 诊断呈现强化。
6. 再做 ROS2 外围 bridge 的只读 mirror 基础。
7. 最后再推进 ROS2 health monitor / UI backend / rosbag2 等外围消费层。

## 7. 核心策略原则

后续所有升级都应遵守以下策略：

1. 核心业务主线先稳再扩。
2. 先保证状态语义和安全语义，不先追求外围框架统一。
3. 先保证 replay/日志/联调闭环，再增加更复杂控制。
4. ROS2 只能作为外围成熟工具路线，不得接管核心安全和执行主链。
5. Python 主要用于测试、日志解析、复盘、工具、bridge 验证和 GCS，不用于车载核心执行链替换。
