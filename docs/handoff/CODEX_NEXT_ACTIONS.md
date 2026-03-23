# CODEX_NEXT_ACTIONS

## 文档状态

- 状态：Authoritative
- 说明：定义当前最高优先级任务、允许范围、禁止事项和验收标准，供下一轮 Codex 直接执行。

## 1. 当前最高优先级任务

当前最高优先级任务是：

- 继续稳住已经落地的 Phase 0 薄 supervisor / launcher
- 在真实设备就绪后补完成一组真正的 `bench` safe smoke
- 在此之前，不要把失败留给子进程黑盒输出；优先让 preflight、运行文件和 runbook 把问题说清楚

当前已知真实阻塞（2026-03-23）：

- `/dev/ttyUSB0` 缺失
- `/dev/ttyACM0` 缺失
- `/dev/serial/by-id` 缺失

## 2. 推荐实施顺序

建议按以下顺序推进：

1. phase 0.4：在设备已就绪环境重跑真实 `bench` safe smoke
   - 继续使用显式配置路径
   - 继续使用 `--pwm-dummy`
   - 依次验证 `preflight -> start -> status -> stop`
2. phase 0.5：只修真实 smoke 暴露的 supervisor 自身问题
   - `preflight`
   - 启停顺序
   - `process_status.json`
   - `last_fault_summary.txt`
   - `supervisor_events.csv`
3. phase 0.6：如真实 smoke 已通过，再考虑最小外围补强
   - 仅在确有必要时补最小 stdout / stderr 收口
   - 只更新 runbook 和状态文件可读性

## 3. 本轮允许范围

下一轮允许做的范围：

1. 只在 `tools/supervisor/` 及其必要外围配套内继续迭代
2. 允许继续收敛：
   - `preflight` 检查项
   - 启动顺序与退出顺序
   - `run_manifest.json`
   - `process_status.json`
   - `last_fault_summary.txt`
   - `supervisor_events.csv`
3. 允许做最小验证：
   - 设备就绪后的真实 `bench` safe smoke
   - `mock` detached lifecycle 回归
   - Python 语法检查与 targeted unittest
4. 允许继续更新：
   - `docs/handoff/CODEX_HANDOFF.md`
   - `docs/handoff/CODEX_PROGRESS_LOG.md`
   - `docs/handoff/CODEX_NEXT_ACTIONS.md`
   - `docs/productization/nightly_upgrade_progress.md`
   - `docs/runbook/supervisor_phase0_operator_guide.md`

## 4. 本轮禁止事项

下一轮明确禁止：

1. 不重写 `uwnav_navd`
2. 不重写 `pwm_control_program`
3. 不重写 `gcs_server`
4. 不改 `ControlLoop` / `ControlGuard`
5. 不把 `gcs_server` 变成父进程或超级进程
6. 不让 Python 取代 control / nav authority
7. 不让 ROS2 进入 control / nav authority 主线
8. 不为 supervisor 方便而改 shared ABI
9. 不同步展开三传感器工具链公共外壳抽取
10. 不把日志统一演变成全链路高频日志大改
11. 不引入自动重启策略

## 5. 依赖文档

下一轮实现前必须先对齐：

1. `docs/handoff/CODEX_HANDOFF.md`
2. `docs/runbook/supervisor_phase0_operator_guide.md`
3. `docs/runbook/usb_reconnect_bench_plan.md`
4. `docs/architecture/control_nav_integration_plan.md`
5. `docs/documentation_index.md`
6. `/home/wys/orangepi/AGENTS.md`

## 6. 最小验收标准

若下一轮继续推进 Phase 0，最低验收标准应为：

1. `preflight --profile bench` 在设备就绪环境可通过
2. 至少完成一组真实 `bench` 的 `start -> status -> stop`，并继续保持 `--pwm-dummy`
3. `run_manifest.json`、`process_status.json`、`last_fault_summary.txt`、`supervisor_events.csv` 持续稳定生成
4. `status` 与 `stop` 对 detached run 可重复使用
5. 若环境仍不允许真实启动，必须明确记录绝对日期和具体阻塞点
6. 文档与 handoff 同步更新

## 7. 次优先级任务

在 Phase 0 supervisor 稳定前，不建议提前展开；稳定后再做：

1. 最小 stdout / stderr 收口
2. 三传感器工具链公共外壳抽取
3. 更大范围的统一日志接线
4. 进程自动重启策略
5. ROS2 外围 bridge 消费层与 manifest / incident bundle 的对接


## 8. 如果下一轮继续导航侧传感器工具链

允许做的事：

1. 在真实 IMU / DVL / Volt32 设备就绪后，分别完成最小 hardware-in-the-loop smoke。
2. 核对 `*_session_summary_*.json` 与 `*_events_*.csv` 是否能稳定解释：
   - 打不开串口
   - 有 raw 无 parsed
   - 空采集
   - 非数字值 / 异常单位 / 异常通道
3. 只在必要时继续补最小 runbook，不扩展到统一日志大改。

禁止做的事：

1. 不改 `uwnav_navd` authority 主逻辑。
2. 不把三传感器工具链抽成大一统框架。
3. 不为工具链方便而改 shared ABI 或 control / nav 主链。
4. 不把本轮防呆收口演变成全链路日志系统重写。


## 9. DVL 下一步最小建议

1. 用 `/home/wys/orangepi/2026-01-26/dvl_raw_lines_20260126_104848.csv` 做一次离线 replay/compare，确认 `parsed_csv` 与 TB 行数符合预期。
2. 若后续再拿到同批次 `parsed` 或 `speed_min_tb` 文件，可直接核对 `BI/BS/BE/BD` 映射是否漂移。
3. 在没有新增强证据前，不要为了 `SA/TS` 去扩展 DVLData/TB 结构。


## 10. 传感器总开关下一步建议

1. 在真实 IMU / DVL / Volt32 设备就绪后，优先用 `apps/acquire/sensor_capture_launcher.py` 做一轮整套 smoke。
2. 先验证 launcher summary、各传感器 summary、以及 CSV 是否同时稳定落盘。
3. 在没有新增需求前，不要把 launcher 膨胀成 supervisor 或统一日志平台。
