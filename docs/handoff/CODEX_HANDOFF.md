# CODEX_HANDOFF

## 文档状态

- 状态：Authoritative
- 说明：Codex 当前阶段恢复上下文的高密度交接摘要。

## 1. 当前阶段

当前项目阶段不是“继续堆功能”，而是：

1. 保持控制、导航、状态传播、执行链的 C/C++ 主线可信
2. 先完成文档体系、启动边界、日志边界、工具链边界的收口
3. 在此基础上，再推进 supervisor、三传感器工具链和日志统一的最小实现

当前阶段判断：

- P0 权威状态与契约基线已建立
- P1 bring-up / reconnect / replay / 诊断仍在收口
- 外围 bridge / UI / 工具层允许继续推进，但不得侵入 authority 主链

当前已进入 Phase 0 supervisor 稳定化阶段：

1. 原型不再只是 mock 生命周期验证，而是已经开始对真实 `bench` 环境做安全烟测准备
2. 当前最关键的工作是把 preflight、运行文件和 operator 使用步骤收口为可复现基线
3. 在真实设备未就绪前，允许先把 failure-path 诊断做清楚，但不能把它写成“真实主链已验证完成”

## 2. 当前主目标

当前最高主目标是：

- 先把“项目怎么读、怎么接、怎么继续做”固定下来
- 再做低风险实现收敛，而不是直接大重构

对应当前已冻结的方向：

1. `uwnav_navd` 保持导航 authority
2. `pwm_control_program` 保持控制 authority
3. `gcs_server` 保持通信边界
4. `nav_viewd` 保持导航到控制的桥接边界
5. ROS2 继续只做外围只读 bridge / diagnostics / UI backend 候选
6. 三传感器 Python 链继续定位为工具链，不回灌 authority 主线

当前 Phase 0 supervisor 的直接目标已经收口为：

1. 在继续保持 `--pwm-dummy` 的前提下，为真实 `bench` safe smoke 提供最小可操作入口
2. 在真实设备缺失时，让 preflight 和运行文件能直接给出可读阻塞点
3. 为下一次真实设备到位后的复现提供最小 runbook

## 3. 已完成关键工作

### 3.1 架构与重构设计已冻结

已完成的设计文档：

- `docs/architecture/control_nav_integration_plan.md`
- `docs/architecture/sensor_toolchain_refactor_plan.md`
- `docs/interfaces/logging_contract.md`

这些文档已经明确：

- authority 边界
- supervisor / launcher 角色
- 三传感器工具链公共抽象方向
- 最小统一日志契约
- 分阶段实施顺序

### 3.2 文档体系已标准化

本轮已建立：

- `docs/documentation_index.md`
- `docs/handoff/CODEX_HANDOFF.md`
- `docs/handoff/CODEX_PROGRESS_LOG.md`
- `docs/handoff/CODEX_NEXT_ACTIONS.md`
- `docs/archive/archive_index.md`

并完成：

- 旧文档归档
- 活跃导航专题文档收敛到 `docs/architecture/`
- 权威基线、Working draft、Archived、Obsolete 状态标识收口

### 3.3 Phase 0 supervisor 已从原型推进到“可做安全烟测准备”

当前已落地能力：

1. 最小命令入口
   - `preflight`
   - `start`
   - `status`
   - `stop`
2. 固定启动顺序
   - `uwnav_navd`
   - `nav_viewd`
   - `pwm_control_program`
   - `gcs_server`
3. 固定退出顺序
   - `gcs_server`
   - `pwm_control_program`
   - `nav_viewd`
   - `uwnav_navd`
4. 最小运行文件维护
   - `run_manifest.json`
   - `process_status.json`
   - `last_fault_summary.txt`
   - `supervisor_events.csv`
5. `bench` profile 继续保持：
   - 真实二进制路径
   - 显式配置路径
   - `pwm_control_program --pwm-dummy`
6. `preflight` 本轮已补强到：
   - Python 版本
   - `run_root` 可写
   - `/dev/shm` 可读写
   - 进程工作目录可访问
   - 关键二进制存在且可执行
   - 关键配置文件存在且可读
   - `nav_daemon.yaml` 中设备节点可见性检查
   - `/dev/serial/by-id` 可见性提示
   - `gcs_server` UDP 端口占用检查
   - 已有 active run 检查
7. 已新增最小 operator 说明：
   - `docs/runbook/supervisor_phase0_operator_guide.md`

### 3.4 本轮实际验证结果

本轮已完成：

1. `python3 -m py_compile`：通过
2. `python3 -m unittest discover -s tools/supervisor/tests -p 'test_*.py'`：通过（4 个用例）
3. 真实 `bench` preflight：已执行
4. 真实 `bench` start failure-path：已执行并检查运行文件
5. 手动 `mock` start / status / stop 回归：已执行

本轮真实 `bench` 环境结论（2026-03-23）：

- 当前主机不存在 `/dev/ttyUSB0`
- 当前主机不存在 `/dev/ttyACM0`
- 当前主机不存在 `/dev/serial/by-id`
- 因此真实 `bench` safe smoke 被 preflight 阶段阻塞
- 本轮没有启动真实 authority 进程，这是刻意保持安全边界后的结果，不是漏做

failure-path 运行文件已验证：

- `process_status.json` 正确写成 `supervisor_state=failed`
- `last_fault_summary.txt` 正确写出 `preflight_failed`
- `supervisor_events.csv` 正确记录每一项 preflight 结果
- `run_manifest.json` 正确保留 profile、run 文件路径和预定启停顺序

mock 回归结果：

- detached `start`：通过
- `status --json`：通过
- `stop`：通过
- `supervisor_events.csv` 已验证逆序退出记录为：
  - `gcs_server`
  - `pwm_control_program`
  - `nav_viewd`
  - `uwnav_navd`

## 4. 技术边界

以下边界必须继续严格遵守：

1. 控制、导航、状态传播、执行链核心主线优先保持 C/C++。
2. Python 允许用于：
   - 启动编排
   - 传感器工具链
   - 日志解析
   - 配置检查
   - 非实时辅助模块
3. 不为了“整合”把 authority 链迁到 Python。
4. ROS2 不进入 control / nav authority 主线。
5. `shared/` 是运行时共享契约真实源；文档仓镜像不是唯一真源。
6. 当前 Phase 0 supervisor 仍然只是薄外壳，不得借机改 `uwnav_navd`、`ControlLoop`、`ControlGuard` 或把 `gcs_server` 变成父进程。

## 5. 本轮直接触碰的仓库

本轮直接改动的只有：

- `UnderwaterRobotSystem`
  - 更新 `tools/supervisor/phase0_supervisor.py`
  - 更新 `tools/supervisor/tests/test_phase0_supervisor.py`
  - 新增 `docs/runbook/supervisor_phase0_operator_guide.md`
  - 更新 handoff / progress / next actions / nightly / documentation index
  - 尚未提交

其余主仓本轮未做代码改动。

## 6. 当前风险

1. 真实 `bench` safe smoke 还没有在“设备节点就绪”的环境上成功完成。
2. 当前 preflight 仍然是低风险可见性检查，不是复杂配置语义验证器。
3. 当前还没有统一子进程 stdout / stderr 收口。
4. 当前还没有自动重启策略。
5. 如果后续 host 上的设备路径从固定 `ttyUSB*` / `ttyACM*` 迁到 by-id，supervisor 还需要再对齐最新 bench 配置。

## 7. 下一步最建议做的事

1. 在真实 IMU / DVL 设备就绪后，优先重跑：
   - `preflight --profile bench`
   - `start --profile bench --detach`
   - `status --json`
   - `stop`
2. 继续保持 `pwm_control_program --pwm-dummy`，不要跨出 Phase 0 边界。
3. 若真实 bench 启动成功，再只修 supervisor 自己暴露的问题；优先级应是：
   - 运行文件可读性
   - runbook 补充
   - 视需要再补最小 stdout / stderr 收口
4. 在 Phase 0 supervisor 稳定前，不要提前展开：
   - 三传感器工具链公共外壳抽取
   - 更大范围的统一日志接线

## 8. 下次启动优先阅读顺序

1. `/home/wys/orangepi/AGENTS.md`
2. `docs/handoff/CODEX_HANDOFF.md`
3. `docs/handoff/CODEX_NEXT_ACTIONS.md`
4. `docs/project_memory.md`
5. `docs/architecture/upgrade_strategy.md`
6. 相关接口契约与 runbook，优先：
   - `docs/runbook/supervisor_phase0_operator_guide.md`
   - `docs/runbook/usb_reconnect_bench_plan.md`


## 9. 2026-03-23 导航侧传感器采集工具链防呆收口

本轮新增一条独立于 supervisor 的低风险收口线，只触碰 `Underwater-robot-navigation` 的 Python 采集 / 校验工具，不改 `uwnav_navd` authority 主逻辑。

### 已确认的问题

1. `data/2026-01-06/dvl/` 下的三份 DVL 采集文件都只有表头，没有数据行。
2. 旧采集脚本在“串口缺失 / 坏帧 / 解析 0 帧 / 非数字值”场景下，可见性不足。
3. `imu_data_verifier.py` 温度字段名写错。
4. `volt32_data_verifier.py` 错用了 IMU 时间基。
5. IMU 底层厂家驱动在串口打开失败后仍会启动循环读，导致后台持续刷 `'NoneType' object has no attribute 'write'`。

### 本轮已做的事

1. 新增统一的 Python 采集诊断工具：
   - `uwnav/io/acquisition_diagnostics.py`
   - `uwnav/io/channel_frames.py`
2. 补强 IMU / DVL / Volt32 采集脚本：
   - 为每次 session 落 `*_events_*.csv` 与 `*_session_summary_*.json`
   - 明确记录 `open_failed` / `empty_capture` / `no_parsed_frames` / `runtime_error`
   - 对串口路径缺失、坏行、异常单位、异常通道、解析 0 帧做最小防呆
3. 补强 DVL 串口接口：
   - 增加最小 `on_event` 回调
   - 增加 `stats_dict()`
   - 对 open fail / idle timeout / parse empty / callback error / read error 提供计数与事件
4. 修复 IMU failure-path：
   - `device_model.py` 打开失败时不再启动循环读
   - `IMUReader.open()` 现在会显式抛 `RuntimeError`，让上层能稳定收口为 `open_failed`
5. 修复 verifier 明确 bug：
   - `imu_data_verifier.py` 改为读取 `temperature_c`
   - `volt32_data_verifier.py` 改为 `stamp("volt0", SensorKind.OTHER)`，并复用共享通道解析器

### 本轮验证

已执行：

- `python3 -m py_compile`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- DVL 缺设备失败路径 smoke：通过，已生成 `dvl_capture_events_*.csv` 与 `dvl_capture_session_summary_*.json`
- Volt32 缺设备失败路径 smoke：通过，已生成 `volt_capture_events_*.csv` 与 `volt_capture_session_summary_*.json`
- IMU 缺设备失败路径 smoke：通过，且已确认不再出现后台无限刷屏

### 当前剩余风险

1. 真实硬件就绪时的 IMU / DVL / Volt32 实采 smoke 仍未做。
2. DVL 真实数据仍需结合水池/台架环境验证 `parsed_frames` 与 TB 表是否稳定产生。
3. Volt32 当前只做了“单位识别 + 坏值隔离”，尚未上升到通道语义级校验。
4. 统一日志大收口和三传感器公共模块抽取仍然不要提前展开。


## 10. 2026-01-26 DVL 真实原始样本已接入

新增确认：当前已经拿到一份可用的 DVL 原始采集文件：

- `/home/wys/orangepi/2026-01-26/dvl_raw_lines_20260126_104848.csv`

这份样本与 2026-01-06 的“只有表头”文件不同，包含 35761 条有效 raw 记录，已确认持续出现：

- `SA`
- `TS`
- `BI`
- `BS`
- `BE`
- `BD`

基于这份样本，本轮已把 DVL parser / 映射层收紧为：

1. `parse_lines()` 只从真实数据帧起点切块，不再把 `CZ/CS` 回显和乱码切成伪帧。
2. `_pkt_to_dvldata()` 只放行 `BI/BS/BE/BD/WI/WS/WE/WD`。
3. `SA/TS` 与噪声片段继续保留在 raw logger，但不再污染 parsed/TB。

当前基于真实样本的统计结果：

- motion/distance 帧可稳定识别为：
  - `BD=5916`
  - `BS=5907`
  - `BI=5905`
  - `BE=5905`
- 旧逻辑会误放行的 `S0 / I  / E ` 等伪帧已被压掉。


## 11. 传感器总开关已新增

当前导航侧 Python 采集链已经有一个统一入口：

- `apps/acquire/sensor_capture_launcher.py`

作用：

1. 一次拉起 `imu_logger.py`、`DVL_logger.py`、`Volt32_logger.py`。
2. 统一接收 `SIGINT/SIGTERM`，并向全部子采集脚本发起停机。
3. 额外落一份 launcher 自己的：
   - `sensor_launcher_manifest_*.json`
   - `sensor_launcher_events_*.csv`
   - `sensor_launcher_session_summary_*.json`

当前边界仍然保持：

- launcher 只做进程编排，不改各传感器脚本内部采集逻辑。
- 各传感器自己的 CSV / events / session summary 仍然各自独立落盘。
- 若任一子脚本早退，launcher 会统一停掉剩余子脚本并将本次 run 标记为 `child_failed`。
