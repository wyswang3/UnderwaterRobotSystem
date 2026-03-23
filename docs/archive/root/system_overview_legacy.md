
````markdown
# 水下机器人控制与导航系统总览（system_overview.md）

> ⚓ **目标一句话说明**  
> 本项目围绕一套 8 推进器 ROV，构建了：  
> - 底层 PWM 驱动与安全控制  
> - 统一时间基下的导航数据采集与融合  
> - 上层控制算法（Teleop / MPC / RL）的接口与预留架构  

---

## 1. 代码仓库与模块划分

当前工程由三个主要模块组成，它们可以放在同一个顶层目录下协同工作：

```text
ROV-System/
├─ OrangePi_STM32_for_ROV/        ← 底层 PWM 驱动 & Teleop 控制
│  └─ pwm_control_program/        ← 键盘控制、PWM 控制层、安全机制、PWM 日志
│
├─ Underwater-robot-navigation/   ← 导航与传感器数据采集（IMU、DVL、USBL...）
│  └─ uwnav/                      ← drivers / fusion / timebase / logging
│
└─ control_algorithms/            ← 控制算法层（MPC / RL / 轨迹跟踪，预留）
   ├─ mpc_controller/             ← 未来 MPC 控制器实现
   └─ rl_controller/              ← 未来 RL 控制器实现
````

> 💡 **命名约定**
> 现有仓库名称保持不变，以减少对既有代码和协作者的影响。
> 协作时通过顶层的 `system_overview.md` 把三大模块“逻辑捆绑”。

---

## 2. 硬件整体架构

> 🧱 **一图看懂硬件链路**

```text
[操作员 PC]
    │ (SSH / Teleop key)
    ▼
[Orange Pi / 香橙派]
    ├─ 以太网 → [STM32 PWM 板] → [ESC × 8] → [推进器 × 8]
    ├─ USB/串口 → [IMU]
    ├─ 以太网/串口 → [DVL]
    └─ 其他接口 → [USBL / 深度计 / 电流电压采集等]

[上位机] ←(日志拷贝 / 分析)← [Orange Pi]
```

* **STM32**
  只负责 PWM 输出与基础安全（如硬件急停），不做复杂控制。
* **Orange Pi**
  负责：

  * 键盘 Teleop → PWM 命令 → 通过 UDP 下发到 STM32
  * 传感器数据采集（IMU/DVL/...）
  * 统一时间基 & 日志记录
  * 将来运行 MPC / RL 等控制算法。
* **操作员 PC**
  主要用于：

  * 登陆 Orange Pi
  * 启动 Teleop / 采集进程
  * 实验结束后拷贝日志，做离线分析与网络训练。

---

## 3. 软件分层架构

> 🧩 **自上而下三层：控制算法层 → 导航感知层 → PWM 执行层**

### 3.1 PWM 执行层（Execution Layer）

所在目录：

* `OrangePi_STM32_for_ROV/pwm_control_program/`

核心职责：

1. **键盘 Teleop**

   * `pwm_teleop_main.cpp`
   * `pwm_teleop_keys.[h|cpp]`
     接收键盘按键，构造“期望推进器占空比模式”（前进/后退/横移/转向/升沉）。

2. **PWM 控制层（安全缓冲层）**

   * `pwm_control.[h|c]`
     对上层给出的“目标占空比”进行：
   * 限斜率（Rate Limiter）
   * 禁止突然反向（Reverse Protection）
   * 占空比范围保护（5%–10%）
   * A/B 分组交替更新（电流冲击削峰）
   * 软急停（Emergency Stop）

3. **UDP 传输与 STM32 接口**

   * `libpwm_host.[h|c]`
     把“安全处理后的 8 通道占空比”打包为 UDP 帧发送给 STM32，STM32 侧再映射为真正的 PWM 输出。

> 🔐 **关键点：**
> 上层算法永远不直接碰 STM32，所有 PWM 必须经过 `pwm_control` 的安全保护。

---

### 3.2 导航与传感器层（Navigation & Sensing Layer）

所在目录：

* `Underwater-robot-navigation/uwnav/`

核心模块：

1. **统一时间基（timebase）**

   路径示例：

   * `uwnav/timebase/timebase.[h|cpp]`
   * `OrangePi_STM32_for_ROV/pwm_control_program/external/timebase/`

   定义统一的时间接口和时间戳结构：

   ```cpp
   namespace uwnav::timebase {

   int64_t  now_ns();          // monotonic ns
   TimePoint now();

   enum class SensorKind { IMU, DVL, USBL, OTHER };

   struct Stamp {
       std::string   sensor_id;        // "imu0", "dvl0", "usbl0"
       SensorKind    kind;
       int64_t       host_time_ns;
       std::optional<int64_t> sensor_time_ns;
       int64_t       latency_ns;
       int64_t       corrected_time_ns;
   };

   Stamp stamp(...);

   } // namespace uwnav::timebase
   ```

   PWM 控制进程使用简化接口：

   ```cpp
   double  t_epoch_s = 0.0;
   int64_t t_mono_ns = 0;
   timebase_now(&t_epoch_s, &t_mono_ns);
   ```

2. **传感器驱动（Drivers）**

   * `uwnav/drivers/imu/...`

     * 负责串口/Modbus 读取 IMU 数据、去噪、格式化输出 CSV。
   * `uwnav/drivers/dvl/hover_h1000/...`

     * 解析 DVL 协议，提供“速度 + 质量标志”的精简表。
   * 其他传感器（USBL、深度计、电压电流采集）可按相同模式接入。

3. **数据融合与定位（Fusion / ESKF / KF）**

   * `uwnav/fusion/eskf.*`

     * 利用 IMU + DVL (+ USBL/深度) 做状态估计（位置、速度、姿态）。
   * 输出位姿时间序列，为上层控制算法提供“当前状态”。

---

### 3.3 控制算法层（Control Layer）

所在目录（规划中）：

* `control_algorithms/`

职责规划：

1. **Teleop 模式（已实现）**

   * 键盘 → `pwm_teleop_keys` → `pwm_control` → STM32
   * 主要用于：调试、单轴验证、安全测试与早期带载实验。

2. **MPC / 轨迹跟踪控制**

   计划结构：

   ```text
   control_algorithms/
   ├─ mpc_controller/
   │  ├─ mpc_config.yaml
   │  ├─ mpc_model.[h|cpp]         ← A, B, Q, R 等矩阵
   │  ├─ mpc_solver.[h|cpp]        ← 求解器封装（qpOASES / OSQP / 自己写）
   │  ├─ mpc_node.cpp              ← 订阅状态 & 生成目标 PWM / 推力
   ```

   典型循环逻辑：

   1. 从 `uwnav` 获取当前状态估计 `(x, y, z, roll, pitch, yaw, vx, vy, vz, ...)`
   2. 结合期望轨迹，构造 MPC 优化问题
   3. 得到期望加速度 / 推力 / 角速度指令
   4. 通过控制接口转换为每个推进器的“目标占空比模式”
   5. 写入 `pwm_control` 作为新的目标占空比，交由底层平滑执行。

3. **RL / 数据驱动控制（未来增强）**

   * 使用导航模块 + PWM 日志作为训练数据
   * 在仿真环境中训练策略网络
   * 通过与 `pwm_control` 的接口约束，保证实际落地时不破坏硬件。

> 🎯 **设计哲学**
> 控制算法层永远在“理想世界”下算控制量，所有工程细节（限斜率、电流保护、AB 分组、电压跌落）都封装在 `pwm_control` 和硬件层。

---

## 4. 时间基与日志对齐策略

> 🕒 **所有数据都要讲“同一种语言”：统一时间**

### 4.1 时间源

* 使用 `std::chrono::steady_clock` 作为单调时间基
* 导航 timebase 提供统一接口：

  * `now_ns()` / `now()`
  * `timebase_now(double* t_epoch_s, int64_t* t_mono_ns)`

### 4.2 日志字段约定

无论是 IMU / DVL / PWM，统一使用以下基础字段：

* `t_epoch_s`

  * Unix 时间戳，单位秒（double，带小数）
  * 方便人类读懂“这是哪天哪一刻”的数据
* `t_mono_ns`

  * 单调时间，单位纳秒（int64）
  * 用于严格排序、插值、对齐多个传感器与 PWM

PWM 日志示例（`logs/pwm_teleop_YYYY-MM-DD_HH-MM-SS.csv`）：

```csv
t_epoch_s,t_mono_ns,ch1_pct,ch2_pct,ch3_pct,ch4_pct,ch5_pct,ch6_pct,ch7_pct,ch8_pct
1732670400.123456,987654321000,7.500000,7.500000,9.000000,9.000000,7.500000,7.500000,7.500000,7.500000
...
```

IMU / DVL 日志只要遵守同样的前两列，即可实现统一对齐。

---

## 5. 典型运行流程（实验时怎么用）

> ▶️ **从带电上水到实验结束，一次完整流程**

1. **上电 & 连接**

   * 连接 ROV 电池 / 电源
   * 保证 DVL 供电逻辑正确（水下开机）
   * PC 通过 SSH 登录 Orange Pi

2. **启动传感器采集进程（导航仓库）**

   在 `Underwater-robot-navigation` 中：

   * 启动 IMU 采集：

     ```bash
     python -m uwnav.apps.acquire.imu_logger ...
     ```
   * 启动 DVL 采集：

     ```bash
     python -m uwnav.apps.acquire.dvl_logger ...
     ```

3. **启动 PWM Teleop 控制进程**

   在 `OrangePi_STM32_for_ROV/pwm_control_program` 中：

   ```bash
   ./pwm_teleop 192.168.2.16 8000 100 1
   # IP=STM32 板子 IP，ctrl_hz=100Hz，hb=1Hz
   ```

   * 键盘测试推进器
   * 实验过程中自动记录 `logs/pwm_teleop_*.csv`

4. **实验结束 & 收尾**

   * 按键 ESC 退出 Teleop
   * 停止 IMU/DVL 采集进程
   * 断电前使用 `pwm_ctrl_emergency_stop` 自动归中
   * 从 Orange Pi 拷贝所有日志到 PC，进行离线分析/训练。

---

## 6. 模块间接口约定（协作须知）

> 📑 **让不同子项目、不同开发者可以对接的“契约”**

1. **时间与日志格式**

   * 所有日志必须包含：`t_epoch_s, t_mono_ns`
   * 文件命名推荐：

     * `logs/imu_raw_YYYYMMDD_HHMMSS.csv`
     * `logs/dvl_speed_YYYYMMDD_HHMMSS.csv`
     * `logs/pwm_teleop_YYYYMMDD_HHMMSS.csv`

2. **PWM 控制接口**

   * 控制算法层只调用：

     * `pwm_ctrl_set_target_pct(ch, pct)`
     * 或 `pwm_ctrl_set_targets_mask(mask, pct_array)`
   * 不允许直接绕过 `pwm_control` 写 UDP/STM32。

3. **状态接口（给控制算法）**

   由导航模块对外提供统一结构，例如：

   ```cpp
   struct ROVState {
       double t_epoch_s;
       int64_t t_mono_ns;
       double pos[3];   // x,y,z
       double vel[3];   // vx,vy,vz
       double euler[3]; // roll,pitch,yaw
   };
   ```

   控制算法层只关心这类高层状态，不直接操作 IMU/DVL 底层细节。

---

## 7. 对协作者的建议与后续规划

> 🤝 **新同学接手时可以按下面顺序熟悉**

1. 阅读本文件 `system_overview.md`，了解整体结构。
2. 在 `pwm_control_program` 中：

   * 看 `PWM.md`（PWM 控制层与 AB 分组、安全机制说明）
   * 看 `pwm_teleop_usage.md`（如何用键盘控制进行实验）
   * 浏览 `pwm_control.[h|c]` / `pwm_teleop_main.cpp` 实现。
3. 在 `Underwater-robot-navigation` 中：

   * 看 `timebase` 模块
   * 了解 IMU/DVL 采集脚本结构与日志格式。
4. 在 `control_algorithms` 中：

   * 阅读 MPC / RL 设计文档与接口说明
   * 按统一接口获取状态、下发 PWM 目标。

> 🔭 **后续可以演进的方向**

* 把 MPC 控制器和 Teleop 抽象成统一的“控制源接口”，由一个调度器选择当前模式。
* 引入“实验场景描述”配置文件，自动启动对应的传感器采集与控制流程。
* 在离线分析脚本中封装一套标准化的“多日志对齐 + 可视化工具”。

---

若你愿意，下一步我们可以再补一份更偏工程使用向的
`docs/experiment_workflow.md`：专门写“如何在实验池里做一次完整实验”的步骤说明。
这样研发同学和实验同学的分工也会更清晰。

```
```
