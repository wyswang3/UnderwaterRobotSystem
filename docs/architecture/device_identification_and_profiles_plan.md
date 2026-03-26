# Device Identification And Profiles Plan

## 文档状态

- 状态：Authoritative
- 说明：固定启动前设备识别辅助工具、分级启动 profile 设计以及当前最小外围实现；不改核心 C++ authority 主链。

## 1. 背景与边界

当前 bench / 板上 bring-up 的真实问题不是“进程能不能拉起来”，而是：

1. `/dev/ttyUSB0` / `/dev/ttyUSB1` / `/dev/ttyACM0` 会跳变。
2. IMU、Volt32、电压采集卡、DVL、后续 USBL 可能都挂在串口上，但数据格式完全不同。
3. 如果只按固定 tty 路径启动，容易出现“设备节点存在但绑定错设备”的误绑问题。

本轮边界明确如下：

- 不改 `uwnav_navd`、`nav_viewd`、`pwm_control_program`、`gcs_server` 的核心 authority 主链。
- 不把设备识别直接塞进 `uwnav_navd` 主循环。
- 不先改 ESKF / nav_viewd / ControlGuard。
- 先把识别、推荐、拒绝、记录做成外围工具与 preflight gate。

## 2. 真实样本分析结果

### 2.1 本轮实际使用的真实样本

- IMU
  - `offline_nav/data/2026-01-10_pooltest01/imu/imu_raw_log_20260110_192246.csv`
  - `uwnav/drivers/imu/WitHighModbus/logs/imu_raw_data_20240618.csv`
  - `uwnav/drivers/imu/WitHighModbus/Python-WitProtocol.../chs/20220705190138.txt`
- Volt32
  - `uwnav/drivers/imu/WitHighModbus/motor_data_20240618.csv`
- DVL
  - `/home/wys/orangepi/2026-01-26/dvl/dvl_raw_lines_20260126_102520.csv`
  - `offline_nav/data/2026-01-10_pooltest01/dvl/dvl_raw_lines_20260110_192211.csv`

### 2.2 IMU 样本结论

1. 真实导出 CSV 的稳定字段集合已经明确：
   - `AccX/AccY/AccZ`
   - `AsX/AsY/AsZ`
   - `HX/HY/HZ`
   - `AngX/AngY/AngZ`
2. `offline_nav` 样本的时间间隔约 `10.2ms`，符合 `100Hz` 级别采样。
3. `TemperatureC` 列在当前样本中存在但全部为空，说明它可以作为辅助字段，不能作为强规则。
4. 结合 `docs/protocols/imu_witmotion_modbus.md` 与 `imu_driver_wit.cpp`，当前 runtime 主链使用的是 `WIT Modbus-RTU + 轮询`。
5. 因此 IMU 的被动串口采样并不可靠：没有主动轮询时，IMU 可能根本不吐字节。

结论：

- IMU 的“导出样本结构”已经是样本支撑。
- IMU 的“被动 live serial 动态识别”还不是样本支撑，仍应以静态身份白名单为主。
- 旧 `0x55` 连续同步帧只能保留为兼容候选，不能当当前 runtime 主判据。

### 2.3 Volt32 样本结论

1. 真实样本已经确认导出 CSV 稳定使用 `CH0..CH15` 列结构。
2. 当前样本值后缀稳定出现 `V` / `A`，说明 Volt32 的导出数据至少可以强区分“多通道 + 单位后缀”的形态。
3. 结合 `uwnav/io/channel_frames.py` 和 `volt32_data_verifier.py`，现场 live serial 的既有解析语法是 `CHn: value` 文本行。
4. 但本轮没有拿到 Volt32 的原始串口行日志，因此 `CHn:` 只能算 parser-backed / partial 规则，不应包装成完全样本支撑。

结论：

- Volt32 的“导出 CSV 结构 + V/A 后缀”已经是样本支撑。
- Volt32 的“live serial CHn 行语法”是部分样本支撑。
- Volt32 静态 by-id / VID/PID / manufacturer / product 仍需真实现场快照继续收紧。

### 2.4 DVL 样本结论

1. 真实 `dvl_raw_lines` 样本稳定出现：
   - `SA`
   - `TS`
   - `BI`
   - `BS`
   - `BE`
   - `BD`
2. 在 `2026-01-26` 的真实样本里，上述 6 类 token 各自出现约 `7350` 次量级。
3. 在 `0.35s` 滑动窗口中，样本平均能看到约 `5.99` 个不同 token，说明短时被动采样足以做强动态规则。
4. `RawLine CSV` 头和 `SensorID=DVL_H1000` 也来自真实样本，可用于离线样本解释。

结论：

- DVL 的 `SA/TS/BI/BS/BE/BD` reply token 已经可以升级成强动态规则。
- DVL 是当前最适合用被动短采样做动态识别的设备。
- `CS/CZ` 这类命令回显不能单独当成 DVL 识别成功。

### 2.5 静态身份样本缺口

本轮没有拿到足够的真实 `/dev/serial/by-id`、VID/PID、serial、manufacturer、product 快照样本。

因此当前静态规则仍然要分清两层：

1. 候选白名单
   - 可以用于加分
   - 不能宣称“已被真实样本充分验证”
2. 现场必须补采的真实快照
   - 用于后续把 IMU / Volt32 / DVL 的静态绑定继续收紧

## 3. 识别规则校准结果

### 3.1 当前识别顺序

识别顺序固定为两层：

1. 静态身份识别
   - `/dev/serial/by-id`
   - VID / PID
   - serial number
   - manufacturer / product string
   - `device_identification_rules.json` 白名单
2. 动态数据指纹识别
   - 仅在静态证据不足、路径不稳定或存在歧义时才短时采样
   - 这样做是为了尽量避免 preflight 每次都主动扰动串口

### 3.2 当前校准后的规则分级

- `imu`
  - 样本支撑：导出 CSV 字段集合、旧 WIT 文本导出头
  - 部分支撑：live serial 仍主要依赖静态身份，因为当前 runtime 是 Modbus 轮询
  - 兼容候选：旧 `0x55` 连续同步帧
- `volt32`
  - 样本支撑：`CH0..CH15` 导出 CSV 头、`V/A` 值后缀
  - 部分支撑：`CHn:` live serial 文本行
- `dvl`
  - 样本支撑：`SA/TS/BI/BS/BE/BD` reply token、`RawLine CSV` 头、`SensorID=DVL_H1000`
- `usbl`
  - 仍是候选占位规则

### 3.3 置信度与退化行为

当前识别策略已从“低分也给类型”收紧为：

1. `score >= 0.60` 且无歧义，才算可信识别。
2. `score < 0.60` 时，设备类型直接回退为 `unknown`。
3. 若两个高分候选差值在 `0.12` 内，则显式标记 `ambiguous=true`，拒绝自动绑定。
4. `unknown` / `ambiguous` 都不参与 startup profile 的设备计数。

这一步的目的不是追求“识别成功率”，而是优先降低误识别风险。

### 3.4 解释能力

每个设备当前至少输出：

- `static_identity`
- `static_matches`
- `dynamic_probe.best_match`
- `candidate_scores`
- `confidence.score` / `confidence.label`
- `resolution.reason`
- `rule_support`
- `risk_hints`

其中 `rule_support` 会明确提示：

- 当前静态规则是否只是候选白名单
- 当前动态规则是 `sample_backed / partial / candidate_only`
- 为什么某些规则暂时不能硬判

## 4. Profile 设计与结合结论

### 4.1 Profile 集合本轮不改名

当前仍保留：

- `no_sensor`
- `volt_only`
- `imu_only`
- `imu_dvl`
- `imu_dvl_usbl`（预留）
- `full_stack`（预留）

本轮不改 profile 名称，也不改 authority 进程图。

### 4.2 Profile 最小设备集合

- `no_sensor`
  - 没有任何可信识别设备
- `volt_only`
  - 可信识别到 `volt32`
  - 未可信识别到 `imu`
- `imu_only`
  - 可信识别到 `imu`
  - 未可信识别到 `dvl`
- `imu_dvl`
  - 同时可信识别到 `imu` 与 `dvl`

### 4.3 本轮真正改变的是输入，不是矩阵

profile 矩阵本身本轮不需要调整；真正变化的是：

1. 低置信度设备现在会被回退成 `unknown`
2. 歧义设备现在会显式拒绝
3. `recommend_startup_profile` 只基于可信识别结果

因此 profile recommendation / `startup_profile_gate` 的语义比上一轮更保守、更贴近真实样本。

## 5. Supervisor / Preflight 结合方式

`phase0_supervisor.py preflight --profile bench --startup-profile auto` 当前会：

1. 继续执行原有文件、目录、设备节点和端口检查。
2. 额外执行 `device-scan` 汇总。
3. 输出：
   - `device_inventory`
   - `device_recommendations`
   - `startup_profile`
   - `device_binding_ambiguity`
   - `startup_profile_gate`
4. 若识别结果显示当前只能 `no_sensor` / `volt_only`，或存在歧义，则 preflight 直接失败。

当前 gate 规则：

- 只有 `launch_mode=bench_safe_smoke` 的 `startup_profile` 才允许继续做当前 `bench` 链路。
- `ambiguous=true`、`launch_mode=preflight_only`、`launch_mode=reserved` 都会被明确拒绝。

## 6. 当前实现状态与下一步

当前已落地：

1. 静态身份白名单
2. 样本支撑的 DVL 动态指纹
3. 样本支撑的 IMU / Volt32 导出样本识别
4. `device-scan` / `startup-profiles` CLI
5. `bench preflight` 的 startup profile 推荐与 gate
6. `run_manifest / process_status / last_fault_summary` 的识别结果记录
7. 样本驱动的 `test_device_identification.py`

当前仍未落地：

1. IMU 的 live serial 主动探测
2. Volt32 的原始串口行样本驱动校准
3. USBL 真实样本规则
4. `imu_only` / `imu_dvl` 的真正进程图差异化启动
5. 上传 / GUI 集成 / authority 侧深度改造

下一步最合理的顺序是：

1. 先在真实 bench 上补采 `/dev/serial/by-id` / sysfs 快照
2. 再分别验证 `imu_only` 与 `imu_dvl` 的 profile 推荐是否稳定
3. 若继续推进，也只允许讨论 supervisor 侧轻量 launch policy，不提前改核心 authority 主链
