# Upgrade Strategy

## 1. 当前阶段判断

截至 2026-03-20，项目不应再被定义为“单纯原型开发”，而应定义为：

- P0 可信性基线已基本完成
- P1 联调/日志/replay/重连收口仍在继续
- P2 控制器框架已经起步，但还没有进入 trajectory-ready 阶段

因此，当前阶段目标不是“继续加功能”，而是“先把可信主链收口，再扩能力”。

## 2. 当前阶段目标

当前阶段必须完成的目标：

1. 固化一套跨仓统一的升级参考文档和项目原则。
2. 补齐真实设备重连、重枚举和异常样本验证。
3. 把 replay、incident bundle、compare 工具链从“可用”推进到“可重复执行”。
4. 收紧 shared 契约治理，减少镜像副本带来的漂移风险。
5. 把当前 diagnostics/UI 呈现提升到操作员可快速理解的程度。

## 3. 下一阶段目标

在当前阶段目标完成后，下一阶段才应推进：

1. PID hold-controller 的 HIL/实机验收。
2. Auto reference 契约收口。
3. trajectory/任务层接入前的切模态和回放验证。
4. 外围桥接能力，例如更成熟的 UI backend 或 ROS 2 bridge。

## 4. 先做什么，后做什么

### 现在优先做

1. 真实 IMU/DVL 热插拔和错误设备样本采集。
2. `shared/` 真源治理和兼容性矩阵更新。
3. replay compare 的流程固化与 runbook 化。
4. GCS/TUI 的诊断可读性提升。
5. 现有 PID 框架的 reference/telemetry 语义收口。

### 明确后做

1. 复杂 trajectory tracking。
2. 更高级控制分配器，例如 WLS/QP。
3. 完整图形化大 UI 重做。
4. ROS 2 bridge 大规模引入。
5. 核心主线的语言/框架大迁移。

### 当前明确不建议做

1. 把导航、控制、状态传播主链改造成 ROS 2 原生图。
2. 用 Python 替换车载控制或车载导航主循环。
3. 在实机重连/replay 闭环未稳之前推进更复杂自主功能。
4. 在没有契约升级说明的情况下改动 shared ABI。

## 5. 分阶段验收标准

### 阶段 A：P1 收口

验收标准：

1. 真实硬件至少完成一组正常启动样本和一组断连恢复样本。
2. 设备重枚举时，`NavState -> NavStateView -> Telemetry -> GCS` 诊断链可解释。
3. incident bundle、replay 注入、replay compare 至少能在一组真实样本上重复执行。
4. 文档、runbook、兼容性矩阵与当前代码一致。

### 阶段 B：共享契约与诊断产品化

验收标准：

1. `shared/` 的唯一真源治理方案落地。
2. ABI/version/layout 检查规则明确并可执行。
3. 操作员可直接看到关键 nav/device/timing 诊断，不必先读源码。
4. 关键故障窗口可通过固定 runbook 导出、注入、对照。

### 阶段 C：P2 控制框架深化

验收标准：

1. `Auto` 的 reference 来源明确，不再混淆 hold setpoint 与外部 setpoint。
2. `set_mode(kAuto)`、reference 切换、stale/invalid 导航输入都有回放或集成测试。
3. PID 控制器在 HIL/实机条件下完成最小验收。
4. telemetry 中能区分当前控制器、目标控制器、锁存 setpoint、外部 reference。

### 阶段 D：外围桥接与 UI 提升

验收标准：

1. GUI/ROS 2 bridge 崩溃不会影响控制主线。
2. 外围桥接只消费权威状态，不篡改安全决策。
3. 操作员侧诊断体验明显优于当前纯文本摘要。

## 6. 当前最推荐的升级顺序

1. 先冻结文档与契约基线。
2. 再做真实设备重连/重枚举样本采集和复盘。
3. 再把 replay compare 与 incident bundle 工具链标准化。
4. 然后补 `shared/` 真源治理和兼容性收口。
5. 然后做 GCS/TUI 诊断呈现强化。
6. 最后再推进 PID/HIL、trajectory、外围 ROS 2/UI backend。

## 7. 核心策略原则

后续所有升级都应遵守以下策略：

1. 核心业务主线先稳再扩。
2. 先保证状态语义和安全语义，不先追求花哨 UI。
3. 先保证 replay/日志/联调闭环，再增加更复杂控制。
4. ROS 2 只能作为外围成熟工具路线，不得接管核心安全和执行主链。
5. Python 主要用于测试、日志解析、复盘、工具和 GCS，不用于车载核心执行链替换。
