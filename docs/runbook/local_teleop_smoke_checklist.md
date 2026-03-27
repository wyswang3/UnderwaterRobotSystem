# Local Teleop Smoke Checklist

## 文档状态

- 状态：Authoritative
- 说明：固定当前阶段本机 `control_only` / `teleop primary lane` 的最小测试顺序，适合设备未完全就绪时先做本地 smoke。

## 适用范围

本清单用于以下场景：

1. 本机先回归 `control_only` 默认主路径。
2. 验证 `teleop primary lane` 是否仍可启动、遥控、观察、记录和导出 bundle。
3. 设备尚未完全就绪，暂不进入 `bench` nav preview。

当前默认口径：

1. 默认主路径：`teleop primary lane`
2. 默认能力等级：`control_only`
3. `IMU-only` 只能写成 `attitude_feedback`
4. `DVL` 是外接可选模块，不是本机默认硬依赖

## A. 测试前准备

### A.1 终端分工

建议至少开 3 个终端：

1. 终端 1：车端 supervisor helper
2. 终端 2：GCS TUI
3. 终端 3：GCS GUI（只读，可选）

### A.2 当前预期

如果本机没有 IMU / DVL / Volt32，以下现象都属于预期：

1. `startup_profile=no_sensor` 或 `volt_only`
2. `capability=control_only`
3. `motion_info.state=not_enabled_for_capability`
4. `sensor_inventory` 里 `imu=not_present`
5. `sensor_inventory` 里 `dvl=optional_missing`
6. bundle 里 `events.gcs_server.comm_events` 仍可能是 optional missing

## B. 终端 1：一键启动 helper

进入集成仓：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
```

推荐直接使用 helper：

```bash
bash tools/supervisor/run_local_teleop_smoke.sh up
```

这条命令会按当前权威顺序自动执行：

1. `usb_serial_snapshot.py --json`
2. `device-scan --sample-policy off --json`
3. `startup-profiles --json`
4. `preflight --profile control_only --startup-profile auto`
5. `start --profile control_only --detach`
6. `status`
7. `sleep 1` 后再抓 `status --json`，尽量避开刚 detach 的瞬时状态

检查点：

1. `preflight` 应通过。
2. 输出里应出现 `runtime profile=control_only`。
3. `status` 里应看到：
   - `profile=control_only`
   - `operator_lane=teleop_primary`
   - `capability=control_only`
   - `motion_info=not_enabled_for_capability`
4. 子进程里至少有：
   - `pwm_control_program`
   - `gcs_server`

### B.1 helper 常用命令

```bash
bash tools/supervisor/run_local_teleop_smoke.sh up
bash tools/supervisor/run_local_teleop_smoke.sh status
bash tools/supervisor/run_local_teleop_smoke.sh down
```

可选环境变量：

```bash
RUN_ROOT=/tmp/phase0_supervisor_local_smoke_alt ROV_IP=127.0.0.1 STATUS_DELAY_S=1.0 bash tools/supervisor/run_local_teleop_smoke.sh up
```

### B.2 helper 为什么会直接返回

`bash tools/supervisor/run_local_teleop_smoke.sh up` 内部实际调用的是 `phase0_supervisor.py start --detach`。因此它在打印完一轮 `status` / `status --json` 后就会把 shell 控制权还给你，这不是车端退出。

如果要确认车端仍在运行，优先执行：

```bash
bash tools/supervisor/run_local_teleop_smoke.sh status
pgrep -af "gcs_server|phase0_supervisor.py|pwm_control_program"
```

### B.3 如果报 14550 端口占用

典型报错：

```text
[ERR] gcs_bind: cannot bind 0.0.0.0:14550 ([Errno 98] Address already in use)
```

当前优先处理顺序：

1. 先执行 `bash tools/supervisor/run_local_teleop_smoke.sh down`。
2. 再执行 `pgrep -af "gcs_server|phase0_supervisor.py|pwm_control_program"` 确认旧进程是否已经退出。
3. 如果之前用了自定义 `RUN_ROOT`，必须带同一个 `RUN_ROOT` 再跑一次 `down`。

## C. 终端 2：GCS TUI 本机测试

进入 GCS 仓：

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
```

先做 preflight-only：

```bash
UROGCS_ROV_IP=127.0.0.1 bash scripts/run_tui.sh --preflight-only
```

检查点：

1. preflight 应通过。
2. 输出里应明确写出：
   - ROV side default lane 是 `control_only`
   - `pwm_control_program + gcs_server` 是最小运行对

再启动 TUI：

```bash
UROGCS_ROV_IP=127.0.0.1 bash scripts/run_tui.sh
```

检查点：

1. TUI 能正常启动。
2. 可以建立最小 teleop 会话。
3. 当前阶段只做安全键盘输入检查，不把它当成自动控制验证。

### C.1 带遥控联调的最短命令卡

如果只想保留“车端 + TUI”两端联调，最短顺序就是：

```bash
# 终端 1
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
bash tools/supervisor/run_local_teleop_smoke.sh down
bash tools/supervisor/run_local_teleop_smoke.sh up

# 终端 2
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=127.0.0.1 bash scripts/run_tui.sh
```

当前这条最短链路验证的是：

1. TUI 指令能否到达车端。
2. `gcs_server + pwm_control_program` 能否在 `--pwm-dummy` 下稳定联动。
3. PWM 是否已经在车端被正确计算并写入日志。

## D. 终端 3：GCS GUI 只读观察

```bash
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=127.0.0.1 bash scripts/run_gui.sh
```

检查点：

1. GUI 能正常启动。
2. `Devices` / `Motion Info` 卡片能打开。
3. 没有导航数据时，应看到类似：
   - `Control Only`
   - `not_present`
   - `optional_missing`
   - `stale / invalid / NoData`
4. 这些状态当前只能解释成：
   - 系统仍在 `control_only`
   - 没有完整导航不等于系统无法运行

### D.1 在哪里看 PWM 反馈

当前 helper 默认起的是 `pwm_control_program --pwm-dummy`，所以本机最直接的 PWM 反馈主要不在终端里刷，而是在日志里。

优先查看：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV
ls -t logs/pwm/pwm_log_*.csv | head -n 1
```

然后对最新文件做持续观察：

```bash
tail -f /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/logs/pwm/<latest_pwm_log>.csv
```

关键列：

1. `ch1_cmd` 到 `ch8_cmd`：控制链算出来准备下发的 PWM。
2. `ch1_applied` 到 `ch8_applied`：当前 backend 实际应用的 PWM。

如果只想本机直接看终端里的 PWM 打印，而不带 teleop 联调，可以单独执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV/build/bin
./pwm_control_program --no-teleop --pwm-dummy --pwm-dummy-print
```

这条命令只验证车端 PWM 计算链，不驱动真实推进器。

## E. 停止与 bundle 导出

回到终端 1，直接执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
bash tools/supervisor/run_local_teleop_smoke.sh down
```

检查点：

1. `stop` 应成功。
2. `bundle_export_ok=true`
3. `required_ok=true`
4. `run_stage=child_process_stopped_after_start`
5. `bundle_status=incomplete` 目前通常只表示 optional artifacts 缺失，不等于 bundle 导出失败

## F. 出问题先看哪里

优先顺序固定为：

1. `/tmp/phase0_supervisor_local_smoke/<date>/<run_id>/last_fault_summary.txt`
2. `/tmp/phase0_supervisor_local_smoke/<date>/<run_id>/process_status.json`
3. `/tmp/phase0_supervisor_local_smoke/<date>/<run_id>/supervisor_events.csv`
4. `/tmp/phase0_supervisor_local_smoke/<date>/<run_id>/child_logs/`
5. `bash tools/supervisor/run_local_teleop_smoke.sh status`
6. `bundle --json` 输出里的：
   - `bundle_export_ok`
   - `required_ok`
   - `bundle_status`
   - `run_stage`

## G. 当前通过标准

本机 `control_only` smoke 可判定为通过，需要同时满足：

1. helper 的 `up` 通过
2. `status` 能看到 `control_only`
3. TUI 能启动
4. GUI 能启动（可选但推荐）
5. helper 的 `down` 通过
6. `bundle` 导出成功

## H. 当前不在本清单内的内容

以下内容不属于这份本机 smoke 清单：

1. `bench` nav preview
2. `imu_only` 真实姿态反馈验证
3. `imu_dvl` 真实相对导航验证
4. 自动控制主路径
5. USBL / `full_stack`
6. ROS2 新能力

如果设备就绪，下一步顺序仍然固定为：

1. `imu_only`
2. `imu_dvl`
