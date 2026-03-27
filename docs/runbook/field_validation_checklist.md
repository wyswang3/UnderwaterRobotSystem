# Field Validation Checklist

## 文档状态

- 状态：Authoritative
- 说明：固定当前阶段实机验证前检查项、teleop primary lane 标准流程与常见失败点优先排查顺序。

## 使用前提

当前阶段默认主路径固定为 `teleop primary lane`，默认能力等级固定为 `control_only`。

当前必须坚持以下口径：

1. `control_only` 是当前默认基础版本。
2. `IMU-only` 只能写成 `attitude_feedback`，不是完整导航。
3. `DVL` 是外接可选模块，不是默认启动硬依赖。
4. 当前先把遥控模式稳下来，是为了先形成“可启动、可观察、可记录、可导出”的实机验证底座。

## A. 设备连接检查

1. 检查电源、USB 供电和地线是否稳定。
2. 检查 OrangePi、STM32、串口设备、网口是否按当前实机布线连接。
3. 若接入 DVL，确认它是本轮外接增强模块，而不是默认必选项。
4. 若接入 IMU / Volt32，优先确认物理连接和供电，而不是先猜软件问题。

## B. 串口与身份检查

1. 执行 `ls -l /dev/serial/by-id`。
2. 执行 `python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy off --json`。
3. 必要时再执行 `python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy auto --json`。
4. 如果 `ambiguous=true`，先停在 preflight，不进入导航 preview。
5. 如果当前没有 DVL，只要 `control_only` 路径完整，仍可继续实机遥控验证。

## C. 配置检查

1. 当前默认 profile 应是 `control_only`。
2. 当前默认运行入口应是 `phase0_supervisor.py preflight/start --profile control_only`。
3. 当前默认仍应保持 `pwm_control_program --pwm-dummy`。
4. 若目标是后续导航 preview，先确认 `startup-profiles --json` 的推荐是否已稳定到 `imu_only` 或 `imu_dvl`。

## D. teleop 启动流程

按固定顺序执行：

1. `device-check`
2. `device-scan`
3. `startup-profiles`
4. `preflight`
5. `start`
6. `status`
7. `teleop`
8. `stop`
9. `bundle`

最小执行原则：

1. 没有导航数据时，系统仍应能运行、遥控、记录、导出 bundle。
2. `control_only` 下 `motion_info.state=not_enabled_for_capability` 属于预期。
3. 不要因为 `stale,invalid,NoData` 就把整个系统直接判成 fatal。

## E. 姿态反馈检查（若有 IMU）

1. 先确认 IMU 已识别，不存在 `ambiguous`。
2. 当前只允许把 IMU-only 结论写成 `attitude_feedback`。
3. 重点检查：
   - `roll / pitch / yaw`
   - `gyro`
   - `accel`
4. 若 GUI 没有数值，先看 `phase0_supervisor.py status --json` 与 `control_loop_*.csv`。
5. 若当前仍是 `control_only`，只能写成“IMU 已具备升级前提”，不能写成“当前已进入完整导航”。

## F. 相对导航检查（若有 DVL）

1. 先确认 IMU 检查已经通过。
2. 再确认 DVL 已识别且不处于 `ambiguous`。
3. 当前只允许把 IMU + DVL 写成 `relative_nav`。
4. 重点检查：
   - `velocity`
   - `relative_position`
5. 必须同时注明：绝对定位不可用。

## G. 日志与 bundle 导出

1. 故障后先看：
   - `last_fault_summary.txt`
   - `process_status.json`
   - `supervisor_events.csv`
   - 对应进程 `child_logs`
2. 导出 bundle：
   - `python3 tools/supervisor/phase0_supervisor.py bundle --run-root <run_root> --json`
3. 当前应先看：
   - `bundle_export_ok`
   - `required_ok`
   - `bundle_status`
   - `run_stage`
4. `bundle_status=incomplete` 不等于导出失败；先区分 required 和 optional 缺失。
5. `events.gcs_server.comm_events` 当前仍可能是 optional missing。

## H. 常见失败点与优先排查顺序

1. `preflight` 失败
   - 先看端口、配置路径、权限、`/dev/serial/by-id`。
2. `device-scan ambiguous=true`
   - 先补静态身份快照，不要继续猜设备类型。
3. GUI / status 显示 `stale`
   - 先确认设备是否正在重连，再看 child logs。
4. `format_invalid`
   - 先回到 by-id、binding、样本和 child logs。
5. DVL 缺失
   - 如果当前目标只是 teleop primary lane，允许继续；只是不具备 `relative_nav`。
6. IMU 缺失
   - 当前仍可做 `control_only`，但不能写成 `attitude_feedback`。
7. bundle incomplete
   - 先看 `required_ok`；若为 `true`，通常只是 optional logs 缺失。

## 当前推荐顺序

如果设备还未完全就绪：

1. 先跑 `control_only`。
2. 先稳定 teleop、状态观察、日志和 bundle。
3. 再准备 `imu_only`。
4. 最后准备 `imu_dvl`。
