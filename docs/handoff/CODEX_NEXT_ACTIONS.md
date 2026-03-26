# CODEX_NEXT_ACTIONS

## 文档状态

- 状态：Authoritative
- 说明：定义当前最高优先级任务、允许范围、禁止事项和验收标准，供下一轮 Codex 直接执行。

## 1. 当前最高优先级任务

当前最高优先级任务是：

- 稳住已经落地的日志 Phase B 第一批 C++ 低频结构化事件
- 先补剩余高价值低频点，不扩散到高频日志或 authority 重构
- 为后续状态快照统一和 incident bundle 整合打干净基础

当前已落地范围（2026-03-25）：

- `uwnav_navd`
  - `device_bind_state_changed`
  - `serial_open_failed`
  - `sensor_update_rejected`
  - `nav_publish_state_changed`
- `nav_viewd`
  - `nav_view_decision_changed`
  - `nav_view_publish_failed`
  - `nav_view_source_recovered`
- `ControlGuard`
  - `guard_reject`
  - `guard_failsafe_entered`
  - `guard_failsafe_cleared`
  - `guard_nav_gating_changed`

## 2. 推荐实施顺序

建议按以下顺序推进：

1. phase b.1：在真实 `bench` 或最小可控环境复核新事件日志
   - 检查 `nav_events.csv`
   - 检查 `control_events.csv`
   - 核对字段、路径、事件去重和现场可读性
2. phase b.2：继续补剩余高价值低频事件
   - `pwm_control_program`：controller / allocator / PWM 边界
   - `gcs_server`：command lifecycle / ack / inject 结果
3. phase c：统一低频状态快照
   - `nav_snapshot.csv`
   - `control_snapshot.csv`
   - `comm_snapshot.csv`
4. phase d：incident bundle 自动整合
   - supervisor manifest 统一入口
   - child logs / sensor summary / C++ event logs 自动引用

## 3. 本轮允许范围

下一轮允许做的范围：

1. 继续在日志体系 Phase B / Phase C 范围内推进。
2. 允许改动：
   - `uwnav_navd`
   - `nav_viewd`
   - `pwm_control_program`
   - `gcs_server`
   - supervisor / bundle 相关 Python 工具
3. 允许继续补：
   - 低频结构化事件
   - 低频状态快照
   - manifest / bundle 引用关系
4. 允许继续更新：
   - `docs/architecture/logging_full_chain_audit.md`
   - `docs/interfaces/logging_contract.md`
   - `docs/handoff/CODEX_HANDOFF.md`
   - `docs/handoff/CODEX_PROGRESS_LOG.md`
   - `docs/handoff/CODEX_NEXT_ACTIONS.md`
   - `docs/productization/nightly_upgrade_progress.md`

## 4. 本轮禁止事项

下一轮明确禁止：

1. 不重写 `nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`、`telemetry_timeline_*.csv`。
2. 不把低频事件日志扩成高频文本日志。
3. 不改 shared ABI。
4. 不做 `session_id` 全链路 ABI 贯通。
5. 不展开三传感器重构。
6. 不展开导航模式重构。
7. 不让 ROS2 进入 control / nav authority 主线。
8. 不为 incident bundle 方便而重写 authority 主链目录口径。
9. 不把 supervisor 变成大一统日志平台或超级进程。

## 5. 依赖文档

下一轮实现前必须先对齐：

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/architecture/logging_full_chain_audit.md`
4. `docs/interfaces/logging_contract.md`
5. `docs/project_memory.md`
6. `docs/documentation_index.md`

## 6. 最小验收标准

若下一轮继续推进日志体系，最低验收标准应为：

1. 受影响目标完成针对性构建。
2. 最相关回归测试或 smoke 至少完成一轮。
3. 新增日志字段和事件名与 `logging_contract.md` 对齐。
4. 不引入高频路径刷文本或共享契约漂移。
5. handoff / progress / nightly 同步更新。

## 7. 次优先级任务

在第一批事件日志稳定前，不建议提前展开；稳定后再做：

1. incident bundle 自动整合
2. 跨模块 merge timeline 自动消费 manifest
3. 三传感器工具链更大范围统一
4. ROS2 外围消费层和统一日志的对接

## 8. 下次继续的最小起步顺序

建议按以下顺序接着做：

1. 先读：
   - `/home/wys/orangepi/AGENTS.md`
   - `docs/handoff/CODEX_HANDOFF.md`
   - `docs/handoff/CODEX_NEXT_ACTIONS.md`
   - `docs/architecture/logging_full_chain_audit.md`
   - `docs/interfaces/logging_contract.md`
2. 先确认三个仓的本地工作树状态。
3. 再选择继续哪一条线：
   - 补 `pwm_control_program` / `gcs_server` 低频事件
   - 做 Phase C 状态快照
   - 做 manifest / incident bundle 整合
4. 不管走哪条线，都先复用最小针对性构建和测试，不要先扩框架。

## 9. 下次明确不要做的事

1. 不要重新整理整个工作区历史。
2. 不要把“统一日志”做成跨仓一次性大重写。
3. 不要把新事件日志和旧 stdout/stderr 调试语义混成两套互相打架的来源。
4. 不要在没有真实收益前把低频 CSV 换成复杂日志框架。
