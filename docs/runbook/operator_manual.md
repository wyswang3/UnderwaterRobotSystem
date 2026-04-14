# 操作说明书

## 文档状态

- 状态：Authoritative
- 说明：面向当前阶段操作员与联调人员的最短命令卡；覆盖车端控制侧快速启动、上位机快速启动，以及 IMU/Volt32 现场识别与解析排查口径。

补充入口：

- 面向现场操作员的中文顺序卡：`docs/runbook/香橙派_当前实验_操作员使用说明.md`

## 适用范围

本文档适用于当前默认主路径：

- 车端：`phase0_supervisor.py --profile control_only`
- 上位机：`UnderWaterRobotGCS` TUI
- 只读观察：`UnderWaterRobotGCS` GUI overview

当前不适用：

- 真实 PWM 放权后的作业流程
- 自动控制 / AUTO 放行
- USBL / `full_stack` 现场流程

重要澄清：

- `bash tools/supervisor/run_local_teleop_smoke.sh up` 默认仍是 dummy backend。
- `bash tools/supervisor/run_local_teleop_smoke.sh up-real` 才是当前推荐的真实 STM32 输出入口。
- 如果不显式使用 `up-real`、`restart-real` 或 `phase0_supervisor.py ... --real-pwm`，TUI 指令即使已经到达 `pwm_control_program`，也不会真正发包到 STM32。
- GCS 启动脚本当前支持显式解释器覆盖：`UROGCS_PYTHON_BIN=/abs/path/python3`
- supervisor helper 当前支持显式解释器覆盖：`URO_SUPERVISOR_PYTHON_BIN=/abs/path/python3`

## 1. 当前默认口径

1. 默认 operator lane 固定为 `teleop primary lane`。
2. 默认 active capability 固定为 `control_only`。
3. 当前车端最小可信运行对只有：
   - `pwm_control_program`
   - `gcs_server`
4. 当前推荐操作入口是 TUI；GUI 只做只读状态预览，不作为主 teleop 入口。
5. IMU / DVL / Volt32 当前都不是 `control_only` 启动硬依赖；只有在 `device-scan -> startup-profiles -> preflight --profile bench` 通过后，才允许进入带导航 preview 的 `bench` 路径。

## 2. 车端控制侧快速启动

### 2.0 Python 与环境脚本

当前工作区实测 Python 版本是 `Python 3.11.11`。

如果要手动进入环境，执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
source tools/supervisor/enter_supervisor_env.sh

cd /home/wys/orangepi/UnderWaterRobotGCS
source scripts/enter_gcs_env.sh
```

这两个脚本会优先使用仓库 `.venv/bin/python`；如果 `.venv` 不存在，就继续使用当前 `python3`。

### 2.1 推荐一键方式

进入集成仓：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
```

当前推荐让操作员只记下面 6 个命令：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

bash tools/supervisor/run_local_teleop_smoke.sh up
bash tools/supervisor/run_local_teleop_smoke.sh up-real
bash tools/supervisor/run_local_teleop_smoke.sh doctor
ROV_IP=<OrangePi_IP> bash tools/supervisor/run_local_teleop_smoke.sh teleop
ROV_IP=<OrangePi_IP> bash tools/supervisor/run_local_teleop_smoke.sh gui
bash tools/supervisor/run_local_teleop_smoke.sh down
```

其中：

1. `up` 仍是 dummy backend。
2. `up-real` 是推荐的真实 PWM 启动方式，不再要求操作员记 `REAL_PWM=1`。
3. `doctor` 会给出更短的状态判断和建议下一步。
4. `teleop` / `gui` 会自动切到 GCS 仓并带入 `ROV_IP`。

如果只是本机联调，直接执行：

```bash
bash tools/supervisor/run_local_teleop_smoke.sh up
```

如果要做真实 STM32 输出联调，必须显式改成：

```bash
bash tools/supervisor/run_local_teleop_smoke.sh up-real
```

这条命令会自动完成：

1. `usb_serial_snapshot.py --json`
2. `device-scan --sample-policy off --json`
3. `startup-profiles --json`
4. `preflight --profile control_only --startup-profile auto`
5. `start --profile control_only --detach`
6. `status`

操作员应重点确认：

1. `preflight` 通过。
2. `runtime profile=control_only`。
3. `status` 里 `pwm_backend=dummy` 或 `pwm_backend=stm32` 与当前预期一致。
3. `status` 中至少存在：
   - `pwm_control_program`
   - `gcs_server`
4. `capability=control_only`、`operator_lane=teleop_primary` 属于当前预期。

### 2.2 不使用 helper 的原始命令

如果要手动逐步执行，固定顺序如下：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

python3 tools/supervisor/phase0_supervisor.py preflight \
  --profile control_only \
  --startup-profile auto \
  --real-pwm \
  --run-root /tmp/phase0_supervisor_control_only

python3 tools/supervisor/phase0_supervisor.py start \
  --profile control_only \
  --startup-profile auto \
  --detach \
  --real-pwm \
  --run-root /tmp/phase0_supervisor_control_only \
  --start-settle-s 0.2 \
  --poll-interval-s 0.2 \
  --stop-timeout-s 5.0

python3 tools/supervisor/phase0_supervisor.py status \
  --run-root /tmp/phase0_supervisor_control_only --json
```

### 2.3 查看状态与停止

推荐命令：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

bash tools/supervisor/run_local_teleop_smoke.sh doctor
bash tools/supervisor/run_local_teleop_smoke.sh status
bash tools/supervisor/run_local_teleop_smoke.sh down
```

如果要重启并保留当前操作语义，优先直接执行：

```bash
bash tools/supervisor/run_local_teleop_smoke.sh restart
bash tools/supervisor/run_local_teleop_smoke.sh restart-real
```

若使用原始命令：

```bash
python3 tools/supervisor/phase0_supervisor.py stop \
  --run-root /tmp/phase0_supervisor_control_only \
  --timeout-s 5.0

python3 tools/supervisor/phase0_supervisor.py bundle \
  --run-root /tmp/phase0_supervisor_control_only --json
```

### 2.4 常见问题

如果报 `14550` 端口占用，优先执行：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
bash tools/supervisor/run_local_teleop_smoke.sh doctor
bash tools/supervisor/run_local_teleop_smoke.sh down
pgrep -af "gcs_server|phase0_supervisor.py|pwm_control_program"
```

如果需要看故障文本，优先顺序固定为：

1. `/tmp/phase0_supervisor_*/<date>/<run_id>/last_fault_summary.txt`
2. `/tmp/phase0_supervisor_*/<date>/<run_id>/process_status.json`
3. `/tmp/phase0_supervisor_*/<date>/<run_id>/supervisor_events.csv`
4. `/tmp/phase0_supervisor_*/<date>/<run_id>/child_logs/`

## 3. 上位机快速启动

### 3.1 TUI 主路径

推荐入口已经收进 helper：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
ROV_IP=127.0.0.1 bash tools/supervisor/run_local_teleop_smoke.sh teleop
```

实机联调：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
ROV_IP=<OrangePi_IP> bash tools/supervisor/run_local_teleop_smoke.sh teleop
```

当前操作要求：

1. `teleop` 内部仍会先做 GCS preflight。
2. `preflight` 没过时，不要继续进入 TUI。
3. TUI 才是当前完整键盘 teleop 基线。
4. 如需手动逐步检查，仍可直接进入 `UnderWaterRobotGCS` 执行 `bash scripts/run_tui.sh --preflight-only`。

### 3.1.1 怎么确认是不是已经在打真实 STM32

优先看车端 `status` 输出，而不是只看 TUI 有无按键反馈：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
python3 tools/supervisor/phase0_supervisor.py status --json
```

至少确认以下三点：

1. `pwm_backend=stm32`。
2. `real_pwm=1`。
3. `pwm_control_program` 的命令行里没有 `--pwm-dummy`。

如果这里显示的是 `pwm_backend=dummy`，那么当前链路只能说明：

1. GCS 指令已经到了车端。
2. `pwm_control_program` 已经算出了 PWM。
3. 但还没有真正发包到 STM32。

### 3.2 GUI 只读观察

GUI 只做状态预览，不替代 TUI：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
ROV_IP=<OrangePi_IP> bash tools/supervisor/run_local_teleop_smoke.sh gui
```

当前 GUI 重点只看：

1. `Connection`
2. `Devices`
3. `Motion Info`
4. `Control`
5. `Command`
6. `Fault Summary`

### 3.3 最短双端联调顺序

终端 1：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
bash tools/supervisor/run_local_teleop_smoke.sh restart
```

如果是实机放行前的真实输出联调，终端 1 必须改成：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
bash tools/supervisor/run_local_teleop_smoke.sh restart-real
```

终端 2：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
ROV_IP=<OrangePi_IP> bash tools/supervisor/run_local_teleop_smoke.sh teleop
```

终端 3（可选）：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem
ROV_IP=<OrangePi_IP> bash tools/supervisor/run_local_teleop_smoke.sh gui
```

## 4. 带导航 Preview 的最小顺序

只有在需要做 `imu_only` / `imu_dvl` bench safe smoke 时，才走下面这条链：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem

python3 tools/supervisor/phase0_supervisor.py device-scan --sample-policy auto --json
python3 tools/supervisor/phase0_supervisor.py startup-profiles --json
python3 tools/supervisor/phase0_supervisor.py preflight \
  --profile bench \
  --startup-profile auto \
  --run-root /tmp/phase0_supervisor_bench_smoke
```

只有满足以下条件才允许继续：

1. `recommended_startup_profile.profile` 是 `imu_only` 或 `imu_dvl`。
2. 没有 `ambiguous=true`。
3. `startup_profile_gate=allow`。

之后才允许：

```bash
python3 tools/supervisor/phase0_supervisor.py start \
  --profile bench \
  --startup-profile auto \
  --detach \
  --run-root /tmp/phase0_supervisor_bench_smoke \
  --start-settle-s 0.2 \
  --poll-interval-s 0.2 \
  --stop-timeout-s 5.0
```

如果 `device-scan` 的结论是 `no_sensor`、`volt_only` 或 `ambiguous`，本轮应停在 preflight，不要继续把它写成导航 bring-up 通过。

## 5. 导航侧现场联调注意事项

### 5.1 端口与设备判定口径

当前实机口径要明确：

1. IMU 和电压采集卡长期落在 `ttyUSB0` / `ttyUSB1` 这一对接口里。
2. DVL 当前仍按 `ttyACM0` 路径看待。
3. `nav_daemon.yaml` 当前默认仍写：
   - IMU：`/dev/ttyUSB0`、`230400`、`slave_addr=0x50`
   - DVL：`/dev/ttyACM0`、`115200`
4. 但现场识别不能只依赖配置文件里的固定端口名，更不能把“节点存在”直接当成“设备正确”。

### 5.2 IMU 与 Volt32 的通信特征

当前要按通信特征区分这两个设备：

1. Volt32 / 电压采集卡会主动发送串口文本，典型特征是 `CHn:` 行。
2. IMU 不会像 Volt32 一样被动持续吐文本；它需要我们先下发读寄存器命令，才会回传 Modbus 数据。
3. 当前 workspace 的 IMU 主动探测口径已经固定到：
   - `slave_addr=0x50`
   - `function=0x03`
   - `start_reg=0x34`
   - `count=15`
4. 因此“安静串口没有被动字节”不能直接判定 IMU 不存在。

### 5.3 当前推荐判定机制

当前 supervisor / preflight 侧的推荐策略应这样理解：

1. 先列出 `/dev/serial/by-id`、`ttyUSB0`、`ttyUSB1`、`ttyACM0`。
2. 对有持续 `CHn:` 文本回传的串口，优先判作 Volt32。
3. 对安静的 `ttyUSB*` 串口，在 `230400` 下主动发一次 IMU 读寄存器请求，再看是否形成可解析 Modbus 回包。
4. 只有形成可信绑定后，才允许把设备计入 `imu_only` / `imu_dvl` 的 startup profile 推荐。
5. 如果仍然分不清，结论必须写成 `unknown` 或 `ambiguous`，并停在 preflight。

### 5.4 无法解析时保留 1 到 2 段原始回传

如果串口已经有回传，但当前解析函数不能识别，联调时必须保留原始片段，不要只留下“解析失败”四个字。

当前建议至少保留：

1. 串口路径
2. 波特率
3. 主动探测请求内容
4. 1 到 2 段原始回传的十六进制预览

当前外围工具优先看：

- `device-scan --json` 输出里的：
  - `dynamic_probe.attempts[*].imu_probe_reply_preview_hex`
  - `dynamic_probe.attempts[*].raw_preview_hex`
- 车端导航运行日志：
  - `/tmp/phase0_supervisor_*/<date>/<run_id>/child_logs/uwnav_navd/stderr.log`

这些预览的目的不是替代完整抓包，而是为了在实机现场第一时间判断：

1. 设备根本没回包；
2. 设备有回包，但格式和当前解析函数假设不一致；
3. 设备回包长度、寄存器数量或 CRC 口径与当前实现不一致。

### 5.5 发现 “IMU opened but no parseable frame” 时怎么做

如果日志里出现“串口已打开，但 IMU 没有返回可解析数据”，优先检查：

1. IMU 供电是否正常。
2. RS485 A/B 是否接反或接触不良。
3. 波特率是否真是 `230400`。
4. `slave_addr` 是否仍是 `0x50`。
5. USB-RS485 转接器是否异常。
6. `device-scan --json` 里的原始预览是否已经显示出“有字节但不符合当前解析假设”。

## 6. 当前不建议的做法

1. 不建议操作员手动分别启动 `uwnav_navd`、`nav_viewd`、`pwm_control_program`、`gcs_server` 作为默认流程。
2. 不建议把 GUI 当成主遥控入口。
3. 不建议在 `unknown` / `ambiguous` 设备状态下继续做 `bench` bring-up。
4. 不建议只因为 `ttyUSB0` 或 `ttyUSB1` 存在就认定 IMU 已经绑定正确。
