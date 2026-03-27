# Local Debug And Field Startup Guide

## 文档状态

- 状态：Authoritative
- 说明：固定当前阶段本地调试、safe smoke、现场前检查和日志导出流程；不放宽核心 C++ authority 主链边界。

## 适用范围

本文档覆盖两类活动：

1. 本地调试
2. 板上 bring-up / 实地实验前启动准备

本文档面向以下运行链：

- `tools/supervisor/phase0_supervisor.py`
- `uwnav_navd`
- `nav_viewd`
- `pwm_control_program`
- `gcs_server`
- incident bundle / replay / merge timeline 工具

本文档当前不覆盖：

- 真实推进器放权后的作业流程
- ESKF / 融合算法调参步骤
- ROS2 外围消费层的完整现场流程

## 当前边界

1. `uwnav_navd`、`nav_viewd`、`ControlGuard`、`ControlLoop`、`gcs_server` 核心行为，以及 `NavState / NavStateView / TelemetryFrameV2` 语义相关部分，统一视为核心 C++ 主链高风险区域。
2. 本地调试优先验证：preflight、运行文件、child logs、结构化低频事件、高频日志可导出性，以及 failure-path 是否清楚。
3. 当前阶段不为了“方便调试”直接改 authority 逻辑或放宽安全边界。
4. 当前默认推荐运行等级已经切换到 `control_only`；没有导航设备时，系统仍应能完成 `preflight -> start -> status -> stop -> bundle`。
5. `control_only`、`mock`、本地 dry-run、`bench` safe smoke、以及设备未完成现场放行动作前的板上启动，默认继续保持 `pwm_control_program --pwm-dummy`。
6. 若后续必须改核心 C++ 主链，只允许单模块、单小点、单轮最小回归，不允许顺手重构。

## A. 本地调试

### A.1 先选调试模式

当前建议先在以下四种模式里选一种开始，并默认优先 `control_only`：

1. `control_only`
   - 当前默认最小可运行路径。
   - 适合没有导航设备、导航设备暂未收口、或当前只需要验证 control + comm + logging + bundle 的情况。
2. `bench preflight / safe smoke`
   - 只在 IMU / DVL 设备就绪、startup profile 稳定指向 `imu_only` / `imu_dvl` 时使用。
   - 目标仍是导航 preview / safe smoke，不是现场放权。
3. `mock`
   - 适合本机无设备时只验证 supervisor 生命周期、运行文件和 stop 顺序。
4. replay / incident review
   - 适合不碰设备时验证日志传播链和事故窗口。

### A.1.1 先做设备识别和 startup profile 判定

进入集成仓后，先固定按以下顺序判断串口与 profile：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
python3 tools/supervisor/phase0_supervisor.py startup-profiles --json
```

使用原则：

1. 先用 `--sample-policy off` 看静态身份，不急着打开串口。
2. 如果静态身份不足、当前是 `ttyUSB* / ttyACM*` 不稳定路径，才允许补一轮：

```bash
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy auto --json
```

3. 若输出 `ambiguous=true`，结论仍应写成“停在 preflight / 独立采样”，不要继续当成可信导航 bring-up。
4. 若推荐 `startup_profile=no_sensor` 或 `volt_only`，当前只表示“导航未启用 / 导航 readiness 不满足”；允许继续走 `control_only`，但不要继续把它写成 `bench` safe smoke。

### A.1.2 当前样本支撑规则怎么判读

当前 `device-scan` 输出需要这样解释：

1. `dvl`
   - `SA/TS/BI/BS/BE/BD` 已经由真实 `dvl_raw_lines` 样本支撑，可把它当强动态规则。
2. `volt32`
   - `CH0..CH15` 导出 CSV 结构和 `V/A` 后缀已经由真实样本支撑。
   - 现场 live serial 的 `CHn:` 行语法仍是部分样本支撑，不要写成“已完全校准”。
3. `imu`
   - 真实样本已经支撑导出 CSV 字段集合。
   - 但当前 runtime 主链走 `WIT Modbus-RTU` 轮询，被动采样可能无字节；如果静态白名单不足，应保持 `unknown`，不要硬判。
4. `usbl`
   - 本轮仍是候选占位规则。

操作员最应该先看：

- `resolution.reason`
- `candidate_scores`
- `rule_support`
- `risk_hints`

如果 `resolution.reason=score_below_floor` 或 `ambiguous=true`，结论应写成“未形成可信绑定”，而不是“识别失败后继续猜测设备类型”。

### A.2 `control_only` / `mock` / `bench` safe smoke 怎么跑

进入集成仓：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
```

当前默认先做 `control_only` preflight：

```bash
python3 tools/supervisor/phase0_supervisor.py preflight   --profile control_only   --startup-profile auto   --run-root /tmp/phase0_supervisor_control_only
```

说明：

- `control_only` 是当前默认最小可运行路径，导航缺失不再被当成整个系统 fatal。
- `--startup-profile auto` 仍会根据当前设备集合给出 `no_sensor / volt_only / imu_only / imu_dvl ...`，但在 `control_only` 下这些结果只表示导航 readiness，不直接阻塞 control + comm。
- `device-scan` / `startup-profile` / `startup_profile_gate` 仍然保留在 preflight 输出里，供后续 bench 判断和样本补齐。

当前 Linux bring-up / config baseline 固定为：

1. 默认 operator lane 固定为：`device-check -> device-scan -> startup-profiles -> preflight -> start -> status -> teleop -> stop -> bundle`。
2. 默认 profile 固定为：`control_only`。
3. 默认 active capability 固定为：`control_only`；当前已经成熟到可直接使用。
4. 当前已定义但仍待真实 bench 验证的增强能力是：
   - `attitude_feedback`：需要 `imu_only` 真实 bench
   - `relative_nav`：需要 `imu_dvl` 真实 bench
5. `full_stack_preview` 仍只是预留口径，不属于当前 Linux bring-up baseline。
6. 当前必选模块只有：`pwm_control_program`、`gcs_server`。
7. 当前可选增强模块包括：
   - IMU：用于后续 `attitude_feedback`
   - DVL：外接可拆模块，只用于后续 `relative_nav`，不是默认启动硬依赖
   - Volt32：辅助电源观测设备，不是当前 teleop primary lane 的启动硬依赖
8. 设备未就绪时，推荐继续停在 `control_only`；设备就绪后，再按 `imu_only -> imu_dvl` 的顺序恢复 bench nav preview。

默认 operator lane：

```bash
python3 tools/supervisor/phase0_supervisor.py start   --profile control_only   --startup-profile auto   --detach   --run-root /tmp/phase0_supervisor_control_only   --start-settle-s 0.2   --poll-interval-s 0.2   --stop-timeout-s 5.0

python3 tools/supervisor/phase0_supervisor.py status   --run-root /tmp/phase0_supervisor_control_only   --json

python3 tools/supervisor/phase0_supervisor.py stop   --run-root /tmp/phase0_supervisor_control_only   --timeout-s 5.0

python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_control_only   --json
```

补充说明：

- 当前 `control_only` 实际只启动 `pwm_control_program + gcs_server`。
- 当前 `control_only` 仍默认保持 `pwm_control_program --pwm-dummy`。
- `status` / `bundle` 里没有 `uwnav_navd` / `nav_viewd` 和相关 nav 日志属于预期，不应写成缺失故障。
- GCS / GUI 当前应显示 `Motion Info=Control Only` 或等价 capability-aware 提示；诊断摘要可能仍出现 `stale,invalid,NoData`，但这不应被解释成 `control_only` lane 失败。

无设备或只做 supervisor 生命周期回归时，可继续使用 `mock`：

```bash
python3 tools/supervisor/phase0_supervisor.py start   --profile mock   --detach   --run-root /tmp/phase0_supervisor_mock

python3 tools/supervisor/phase0_supervisor.py status   --run-root /tmp/phase0_supervisor_mock   --json

python3 tools/supervisor/phase0_supervisor.py stop   --run-root /tmp/phase0_supervisor_mock   --timeout-s 5.0

python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_mock   --json
```

只有在 `bench` preflight 通过、且 startup profile 明确指向 `imu_only` / `imu_dvl` 后，才允许做 `bench` safe smoke：

```bash
python3 tools/supervisor/phase0_supervisor.py preflight   --profile bench   --startup-profile auto   --run-root /tmp/phase0_supervisor_bench_smoke
python3 tools/supervisor/phase0_supervisor.py start   --profile bench   --startup-profile auto   --detach   --run-root /tmp/phase0_supervisor_bench_smoke   --start-settle-s 0.2   --poll-interval-s 0.2   --stop-timeout-s 5.0
```

说明：

- 当前 `bench` profile 仍是导航 preview / safe smoke，不是默认 operator lane。
- 当前 `bench` profile 仍默认保持 `pwm_control_program --pwm-dummy`。
- 若 `bench` preflight 因设备未就绪失败，结论必须写成“failure-path 诊断已验证”，不能写成“authority 主链已验证通过”。

### A.3 supervisor 运行文件怎么看

当前最重要的运行文件有 5 类：

1. `run_manifest.json`
   - 看这次 run 的静态描述、路径、固定启停顺序、child log 路径，以及 `startup_profile / device_identification` 摘要。
2. `process_status.json`
   - 看当前 supervisor 状态、每个子进程状态、PID、exit code、最近故障字段，以及当前被选中的 `startup_profile`。
3. `last_fault_summary.txt`
   - 操作员第一眼故障摘要入口。
4. `supervisor_events.csv`
   - 看 preflight、start、stop、fallback stop 的完整时间线。
5. `child_logs/<process>/stdout.log|stderr.log`
   - 看单个进程自己的滚动输出。

建议排查顺序固定为：

1. `last_fault_summary.txt`
2. `process_status.json`
3. `supervisor_events.csv`
4. 对应进程的 `child_logs`

### A.4 child logs 怎么看

推荐 detached 模式配合 `--child-output capture` 使用，这样每个进程会有独立的 sidecar：

- `child_logs/uwnav_navd/stdout.log`
- `child_logs/uwnav_navd/stderr.log`
- `child_logs/nav_viewd/stdout.log`
- `child_logs/nav_viewd/stderr.log`
- `child_logs/pwm_control_program/stdout.log`
- `child_logs/pwm_control_program/stderr.log`
- `child_logs/gcs_server/stdout.log`
- `child_logs/gcs_server/stderr.log`

使用原则：

1. 先看 supervisor 运行文件定位是哪一个进程失败。
2. 再只打开对应进程的 `stdout/stderr`，不要一上来同时翻所有文本日志。
3. 如果 child log 和结构化事件日志语义冲突，以当前代码路径和结构化事件为准，再回头检查文本是否过时。

### A.5 本地没有设备时怎么验证

当前推荐最小无设备验证顺序：

1. 先运行：

```bash
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
python3 tools/supervisor/phase0_supervisor.py startup-profiles --json
```

2. 跑 `preflight --profile control_only --startup-profile auto`，确认导航缺失不会阻塞最小控制链。
3. 跑一轮 `control_only start -> status -> stop -> bundle`，确认 control + comm 进程、运行文件和 bundle 导出正常。
4. 如果只想回归 supervisor 自身生命周期，再补一轮 `mock start -> status -> stop`。
5. 对受影响仓执行最相关的最小构建 / 单测 / smoke。
6. 如果需要验证传播语义，改走 replay / merge timeline，而不是伪造“本地无设备也等于导航现场验证通过”。

### A.6 最小回归怎么做

当前统一按改动类型选回归，不混做：

1. docs-only
   - 复核文档交叉引用、命令、路径和结论表述。
2. 外围模块改动
   - 运行对应 Python 单测、语法检查或工具 smoke。
   - 若涉及 supervisor / incident bundle，至少做一轮 `mock start -> stop -> bundle`，并确认 `bundle_summary` 的缺失提示符合预期。
3. 核心 C++ 主链改动
   - 先说明为什么必须改。
   - 一次只改一个核心模块的一个小点。
   - 至少构建受影响目标。
   - 至少运行最相关单测或最小 smoke。
   - 收口时必须明确：为什么只改这个点、做了哪些验证、哪些风险暂时没动。

## B. 实际工作 / 实地实验启动

### B.1 板子上设备就位前检查项

上板或现场前，至少先确认：

1. 工作目录、配置文件和二进制路径正确。
2. `run_root` 可写。
3. `/dev/shm` 可读写。
4. 没有上一次残留的 active run。
5. `gcs_server` 预期端口没有被旧进程占用。
6. 当前供电、网络和 SSH 会话稳定。
7. 当前阶段仍以 safe startup 为目标，不把本次启动当作算法调参入口。

### B.2 串口和 by-id 如何确认

板子上优先确认四层视图：

```bash
ls -l /dev/serial/by-id
ls -l /dev/ttyUSB* /dev/ttyACM*
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
```

至少核对：

- `path`
- `canonical_path`
- `vendor_id`
- `product_id`
- `serial`
- `manufacturer`
- `product`
- `device_type`
- `confidence`
- `recommended_binding`
- `ambiguous`

如果当前目标是 `bench` 导航 preview，且 `by-id` 不存在、目标串口不出现，或者 `device-scan` 给出 `ambiguous=true / startup_profile=no_sensor / startup_profile=volt_only`，先停在 preflight，不进入导航 authority 进程启动。

如果当前目标只是 `control_only`，`startup_profile=no_sensor / volt_only` 只表示“导航未启用 / 导航 readiness 不满足”，不阻塞最小控制链。

补充说明：

- 如果 IMU 只有静态候选但 `dynamic_probe` 没拿到字节，不要直接写成 IMU 故障；当前更可能是 Modbus 轮询设备的被动采样特性。
- 如果 DVL 命中 `SA/TS/BI/BS/BE/BD` 多类 token，可优先信任动态识别结果。
- 若 `device_type=unknown` 但 `resolution.top_candidate` 存在，必须把 top candidate 和 score 一起记录，方便后续 bench 复核。
- 当前 `device-scan --json` 已会额外给出 `rule_catalog`、`rule_maturity_summary` 和 `static_sample_gap_summary`，可直接用来区分“已经较成熟的规则”和“仍需补样本的规则”。

### B.2.1 真实 bench 静态身份样本先怎么补

如果本轮目标是把静态身份规则继续收紧，建议先固定补 3 份材料：

```bash
ls -l /dev/serial/by-id
python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
```

记录要求：

1. `ls -l /dev/serial/by-id`
   - 记录软链接名和指向的 `ttyUSB* / ttyACM*`。
2. `usb_serial_snapshot.py --json`
   - 记录 `path / canonical_path / vendor_id / product_id / serial`。
3. `device-scan --sample-policy off --json`
   - 记录 `manufacturer / product / rule_catalog / static_sample_gap_summary`。

如果设备会重枚举，建议至少补两次：

1. 一次是当前稳定连接状态。
2. 一次是重新插拔、端口变化后的第二次快照。

### B.2.2 `imu_only` bench 验证前需要检查什么

1. IMU 设备至少要在静态视图里可见：
   - `/dev/serial/by-id` 或明确的 `ttyUSB* / ttyACM*`
   - `vendor_id / product_id / serial / manufacturer / product`
2. `device-scan --sample-policy off --json` 至少应满足：
   - 能看到 IMU 候选
   - `rule_maturity_summary` 明确显示 `imu static=candidate_only dynamic=partial`
   - `static_sample_gap_summary` 已知还缺哪些静态样本
3. 如静态身份仍不足、路径又不稳定，才允许再补一轮：

```bash
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy auto --json
```

4. `startup-profiles --json` 和 `preflight --profile bench --startup-profile auto` 必须都指向 `imu_only` 或至少不再停留在 `no_sensor / volt_only`。
5. `preflight` 若仍卡在静态身份缺口，应写成“IMU bench 前准备未完成”，不要把它包装成 IMU runtime 故障。

### B.2.3 `imu_dvl` bench 验证前需要检查什么

1. IMU 侧沿用 `imu_only` 的全部静态检查项。
2. DVL 侧至少要满足：
   - 静态视图可见
   - 如需要动态判定，`device-scan --sample-policy auto --json` 能稳定命中 `SA/TS/BI/BS/BE/BD`
3. `device-scan --json` 里应重点核对：
   - `rule_maturity_summary` 出现 `dvl static=candidate_only dynamic=sample_backed`
   - DVL 没有进入 `ambiguous`
4. `startup-profiles --json` 和 `preflight --profile bench --startup-profile auto` 必须都稳定指向 `imu_dvl`。
5. 如果 DVL 动态 token 识别稳定，但静态身份还没补齐，当前结论应写成“`imu_dvl` bench 可准备、静态规则仍待收口”，而不是“所有 DVL 规则都已完全闭环”。

### B.3 启动顺序

当前阶段固定的默认 operator lane 是：`control_only`

默认顺序固定为：

1. 设备检查
   - `ls -l /dev/serial/by-id`
   - `ls -l /dev/ttyUSB* /dev/ttyACM*`
   - `usb_serial_snapshot.py --json`
2. `device-scan --sample-policy off --json`
3. 如静态信息不足，再做 `device-scan --sample-policy auto --json`
4. `startup-profiles --json`
5. `preflight --profile control_only --startup-profile auto`
   - 只有可信识别到的设备才会参与 profile 计数；`unknown` / `ambiguous` 都不会被当成可用导航设备。
   - `startup_profile=no_sensor / volt_only` 在这里不再阻塞最小控制链，只表示导航未启用。
6. `start --profile control_only --detach`
7. `status --json`
8. `teleop`
9. `stop`
10. `bundle --json`

推荐命令顺序：

先用 helper 跑本机 `control_only` smoke：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
bash tools/supervisor/run_local_teleop_smoke.sh up
bash tools/supervisor/run_local_teleop_smoke.sh status
bash tools/supervisor/run_local_teleop_smoke.sh down
```

补充说明：

- `run_local_teleop_smoke.sh up` 内部调用的是 `phase0_supervisor.py start --detach`；helper 打印完一轮 `status` 后直接返回 shell 属于预期，不等于车端退出。
- 如果出现 `[ERR] gcs_bind: cannot bind 0.0.0.0:14550 ([Errno 98] Address already in use)`，优先用同一个 `RUN_ROOT` 执行 `bash tools/supervisor/run_local_teleop_smoke.sh down`，再用 `pgrep -af "gcs_server|phase0_supervisor.py|pwm_control_program"` 确认旧进程是否还在。
- 当前 helper 默认仍保持 `pwm_control_program --pwm-dummy`。本机最直接的 PWM 反馈在 `OrangePi_STM32_for_ROV/logs/pwm/pwm_log_*.csv`，重点看 `ch*_cmd` 与 `ch*_applied`。
- 如果只想本机看 PWM 计算链本身，不带 teleop，可直接执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/build/bin
./pwm_control_program --no-teleop --pwm-dummy --pwm-dummy-print
```

如果需要逐条查看原始命令，再按下面的手动顺序执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

python3 /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py --json
python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json
python3 tools/supervisor/phase0_supervisor.py startup-profiles --json
python3 tools/supervisor/phase0_supervisor.py preflight --profile control_only --startup-profile auto --run-root /tmp/phase0_supervisor_control_only
python3 tools/supervisor/phase0_supervisor.py start --profile control_only --startup-profile auto --detach --run-root /tmp/phase0_supervisor_control_only
python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_control_only --json

cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh --preflight-only
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh
UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_gui.sh

cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
python3 tools/supervisor/phase0_supervisor.py stop --run-root /tmp/phase0_supervisor_control_only --timeout-s 5.0
python3 tools/supervisor/phase0_supervisor.py bundle --run-root /tmp/phase0_supervisor_control_only --json
```

只有在 IMU / DVL 设备就绪、`startup_profile` 稳定指向 `imu_only` / `imu_dvl` 时，才允许切到可选的 `bench` nav preview lane：

```bash
python3 tools/supervisor/phase0_supervisor.py preflight --profile bench --startup-profile auto --run-root /tmp/phase0_supervisor_bench_smoke
python3 tools/supervisor/phase0_supervisor.py start --profile bench --startup-profile auto --detach --run-root /tmp/phase0_supervisor_bench_smoke
python3 tools/supervisor/phase0_supervisor.py status --run-root /tmp/phase0_supervisor_bench_smoke --json
python3 tools/supervisor/phase0_supervisor.py stop --run-root /tmp/phase0_supervisor_bench_smoke --timeout-s 5.0
python3 tools/supervisor/phase0_supervisor.py bundle --run-root /tmp/phase0_supervisor_bench_smoke --json
```

当前推荐顺序的目的，是先把“最小控制链是否稳定、导航 readiness 是否明确、什么时候才允许进入 nav preview”说清楚，再进入更高风险的 bench 验证。


### B.3.1 `control_only` / 无导航运行边界

当前代码与文档口径应统一按以下方式解释：

1. 可用能力：
   - `pwm_control_program` 与 `gcs_server` 的 bring-up
   - `preflight -> start -> status -> stop -> bundle`
   - Manual 控制链路检查
   - Failsafe
   - telemetry / child logs / incident bundle / failure-path 诊断
2. 必须禁用或拒绝：
   - `AUTO`
   - 任何依赖 trusted nav 的自动闭环模式
   - 把当前 run 写成“导航 ready”或“full stack validated”
3. GCS / GUI 当前预期：
   - `Motion Info` 当前应显示 `Control Only` 或等价 capability 提示
   - 诊断摘要可能仍显示 `stale,invalid,NoData`
   - 这表示“当前没有启用完整导航”，不应把整个系统直接判成 fatal
4. `startup_profile_gate` 当前解释：
   - `no_sensor` / `volt_only` 只表示导航未启用
   - `ambiguous` 只阻止导航 preview，不阻止最小 control + comm lane
5. `ControlGuard` 边界当前不改代码，只在外围文档明确：
   - `Manual` 可用
   - `Failsafe` 可用
   - `AUTO` 必须依赖 trusted nav

### B.3.2 当前能力等级怎么解释

当前阶段必须统一按以下口径解释能力等级：

1. `control_only`
   - 当前默认激活能力。
   - 只保证最小控制链、遥控、日志和 bundle。
   - 不宣称姿态反馈、相对导航或绝对定位。
2. `attitude_feedback`
   - 只表示 IMU-only 下的姿态反馈能力。
   - 允许写成姿态角、角速度、加速度可观察。
   - 不允许写成完整导航。
3. `relative_nav`
   - 只表示 IMU + DVL 下的速度与短时相对运动能力。
   - 不允许写成绝对定位。
4. `full_stack_preview`
   - 只保留预留口径，当前不展开。

额外约束：

- `control_only` lane 下，即使设备已经具备 IMU 或 IMU + DVL，也只能把它写成“device-ready upgrade target”，不能写成当前 active capability 已升级。
- 当前默认 lane 仍然是 `control_only`。

### B.3.3 遥控状态下如何看运动信息

当前推荐按以下三层观察面配合使用：

1. TUI
   - 负责实际 teleop。
2. GUI overview
   - 负责只读显示当前能力等级、IMU / DVL 在线状态、保守的 motion 文案。
   - 当前卡片语义已经收口为：
     - `Devices`：看 IMU / DVL 在线状态和 capability
     - `Motion Info`：看 `control_only / attitude_feedback / relative_nav`
3. `phase0_supervisor.py status --json`
   - 负责结构化调试快照。
   - 当前至少可看到：
     - `sensor_inventory`
     - `capability`
     - `operator_lane`
     - `motion_info`

当前如何判读：

1. `control_only`
   - `motion_info.state=not_enabled_for_capability` 属于预期。
   - 这表示当前 lane 没有启用姿态 / 相对运动快照，不是系统 fatal。
2. `attitude_feedback`
   - 应重点观察 `roll / pitch / yaw`、`gyro`、`accel`。
   - 若当前 GUI 还没有数值，不要直接写成系统故障；先看 `status --json` 与 `control_loop_*.csv`。
3. `relative_nav`
   - 可再增加 `velocity`、`relative_position`。
   - 必须同时注明“绝对定位不可用”。

额外说明：

- 当前 GUI 不扩 UDP `STATUS` 协议，不直接显示新的姿态/速度数值字段。
- 若需要读结构化 motion snapshot，优先使用 supervisor `status --json`。
- `DVL` 当前是外接可选模块，不应因为缺失就把默认遥控路径直接判成失败。

### B.3.4 当前传感器诊断状态怎么解释

当前阶段应按以下口径看传感器低频诊断：

1. GUI / `status --json` 当前可以稳定表达：
   - `online`
   - `not_present`
   - `format_invalid`
   - `stale`
   - `optional_missing`
   - `not_enabled`
2. 当前这些状态的优先解释应固定为：
   - `online`：当前设备在线，可继续看 capability 和 motion info
   - `not_present`：当前没有设备或没有在线信号
   - `format_invalid`：优先回到 `device-scan`、`/dev/serial/by-id`、child logs 看绑定和样本
   - `stale`：先等低频状态稳定，再决定是否重启或重插
   - `optional_missing`：当前 lane 允许继续，典型场景是 DVL 未接
   - `not_enabled`：当前 lane 没启用该类观察能力，不是系统 fatal
3. `open_failed`、`permission_denied` 当前仍主要在这些路径暴露：
   - `preflight`
   - `last_fault_summary.txt`
   - `child_logs/<process>/stderr.log`
4. 因此当前排障顺序必须是：
   - 先看 GUI / `status --json` 的低频状态
   - 再看 `preflight` / `last_fault_summary.txt`
   - 最后看 child logs 和 bundle

### B.4 哪些模式必须保持 `--pwm-dummy`

当前阶段以下场景都必须保持 `--pwm-dummy`：

1. `control_only`。
2. `mock` 生命周期回归。
3. 本地 dry-run。
4. `bench` safe smoke。
5. 设备刚接好、只验证 bring-up / 日志 / 诊断传播、还没有明确推进器放行结论的板上启动。

本文档不授权真实 PWM 放权；若需要进入真实推进器输出，必须由单独的现场安全流程和放行结论覆盖。

### B.5 哪些日志要提前准备

进入现场前，至少预留并确认以下日志入口：

1. supervisor `run_root`
2. `child_logs/`
3. 导航高频日志：`nav_timing.bin`、`nav_state.bin`
4. 控制高频日志：`control_loop_*.csv`
5. telemetry 日志：`telemetry_timeline_*.csv`、`telemetry_events_*.csv`
6. 低频结构化事件：`nav_events.csv`、`control_events.csv`、`comm_events.csv`（当前 `comm_events.csv` 仍可能是 optional missing）
7. `usb_serial_snapshot.py` 的现场快照输出
8. `device-scan --sample-policy off|auto --json` 的静态/动态识别输出

补充说明：

- 如果当前 run 是 `control_only`，`nav_events.csv`、`nav_timing.bin`、`nav_state.bin`、`uwnav_navd` / `nav_viewd` child logs 缺失都属于预期，不要把它们当成 bundle 导出失败。
- `comm_events.csv` 当前规划位置是 `logs/<date>/<run_id>/comm/comm_events.csv`，bundle 内对应 `events/gcs_server/comm_events.csv`。
- 当前 `comm_events.csv` 未落地前，`events.gcs_server.comm_events` 长期处于 optional missing 属于预期。
- 如果当前 run 是 `bench` nav preview，才应把导航相关日志视作需要重点核对的输入。

### B.6 出问题先看哪些文件

推荐现场排查入口固定为：

1. `last_fault_summary.txt`
2. `process_status.json`
3. `supervisor_events.csv`
4. 对应进程的 `child_logs/<process>/stdout.log|stderr.log`
5. `nav_events.csv` / `control_events.csv`
6. `nav_timing.bin` / `nav_state.bin`
7. `control_loop_*.csv` / `telemetry_timeline_*.csv` / `telemetry_events_*.csv`

含义：

- 前 4 项先回答“哪个进程、在哪个阶段、为什么失败”。
- 低频结构化事件再回答“状态为什么切换”。
- 高频日志最后回答“详细时序和传播窗口是什么”。

### B.7 如何导出日志和 incident bundle

当前 Phase 1 已支持最小自动导出，不再要求先手工拼 supervisor run files。

建议在以下时机立刻导出：

1. `preflight` 失败后。
2. `bench` safe smoke 异常退出后。
3. `mock` 生命周期回归异常后。
4. 操作员准备反馈问题前。
5. 清理 `/tmp`、覆盖 `run_root` 或重启板子前。

默认导出最近一次 run：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_bench_smoke
```

如果要拿机器可读 summary：

```bash
python3 tools/supervisor/phase0_supervisor.py bundle   --run-root /tmp/phase0_supervisor_bench_smoke   --json
```

如果要指定某一次 run 或指定 bundle 目录：

```bash
python3 tools/supervisor/phase0_supervisor.py bundle   --run-dir /path/to/run_dir   --bundle-dir /tmp/incident_bundle_case01
```

默认输出位置：

1. `<run_dir>/bundle/<YYYYMMDD_HHMMSS>/bundle_summary.json`
2. `<run_dir>/bundle/<YYYYMMDD_HHMMSS>/bundle_summary.txt`
3. 同目录下的 `supervisor/`、`child_logs/`、`events/`、`nav/`、`control/`、`telemetry/`

当前规则：

1. required 只包含 `run_manifest.json`、`process_status.json`、`last_fault_summary.txt`、`supervisor_events.csv`。
2. child logs、`nav_events.csv`、`control_events.csv`、`comm_events.csv`、`nav_timing.bin`、`nav_state.bin`、`control_loop_*.csv`、`telemetry_*` 都属于 optional。
3. `bundle_export_ok=1` 只表示 bundle 目录与摘要已经成功写出；它不等于 artifacts 已经齐全。
4. `bundle_status` 当前只表达 artifact completeness；如果 `required_ok=true` 且 `bundle_status=incomplete`，通常只是 optional artifacts 缺失，而不是 bundle 导出失败。
5. `missing_required_keys` / `missing_optional_keys` 会直接告诉你缺什么。
6. `merge_robot_timeline.ready=false` 只表示 replay 输入还不完整，不等于 bundle 导出失败。
7. 如果 `run_stage=child_process_stopped_after_start`，应解释为“当前 run 曾真正启动 authority 子进程，但导出时已经停止”，适合做事后复盘。
8. 如果 `run_stage=preflight_failed_before_spawn` 且 `required_ok=true`，应解释为“bundle 导出成功，但真实 bench safe smoke 被 preflight 阻塞”；此时零字节 child logs 和缺失的 `events/nav/control/telemetry` 都属于预期结果。

导出后先看：

1. `bundle_summary.txt`
2. `supervisor/last_fault_summary.txt`
3. `supervisor/process_status.json`
4. `supervisor/supervisor_events.csv`
5. `child_logs/<process>/stdout.log|stderr.log`
6. `events/` 下的结构化低频事件
7. `nav/`、`control/`、`telemetry/` 下的高频日志

如果 `bundle_summary.json` 里的 `merge_robot_timeline.ready=true`，再继续用 `command_hint` 或手动执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation/nav_core
python3 tools/merge_robot_timeline.py   --nav-timing /path/to/nav_timing.bin   --nav-state /path/to/nav_state.bin   --control-log /path/to/control_loop_xxx.csv   --telemetry-timeline /path/to/telemetry_timeline_xxx.csv   --telemetry-events /path/to/telemetry_events_xxx.csv   --bundle-dir /tmp/replay_bundle_case01
```

若要只切事故窗口，可增加：

```bash
  --event reconnecting   --window-before-ms 150   --window-after-ms 350
```

更完整的 bundle 目录与规则说明，统一看：

- `docs/runbook/incident_bundle_guide.md`

如果 bundle 已经导出、只需要压缩归档当前样本，可执行：

```bash
python3 tools/supervisor/bundle_archive.py   --bundle-dir /path/to/run_dir/bundle/20260326_202046
```

默认输出为同级 `<bundle_dir>.tar.gz`；这个 helper 只做本地压缩，不会重新导出 bundle，也不会上传。

## 当前阶段结论写法

1. 只完成 `control_only` 最小链路时，必须写：
   - “`control_only` 最小 control + comm + bundle 路径已验证，导航当前未启用 / 非强依赖。”
2. 只完成本地 mock / preflight / failure-path 时，必须写：
   - “本地/bench failure-path 已验证，未进入真实 authority 放行。”
3. 只完成日志导出和 replay 时，必须写：
   - “已验证传播语义/事故窗口，不等同于真实现场闭环。”
4. 只有在设备就绪、safe smoke 完整跑完且结论明确时，才允许写：
   - “bench safe smoke 已完成。”
5. 没有单独现场安全流程前，不得把本文件解释成“真实推进器输出放行指南”。
