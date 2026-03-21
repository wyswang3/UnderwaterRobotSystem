# ROS2 Refactor Assessment

## 适用范围

本文档基于 2026-03-21 当前工作区代码与现有基线文档，对 UnderwaterRobotSystem 的 ROS2 迁移适配性做一次收敛评估。

证据来源主要包括：

- `AGENTS.md`
- `docs/architecture/upgrade_strategy.md`
- `docs/architecture/system_main_dataflow.md`
- `docs/interfaces/time_contract.md`
- `docs/interfaces/control_intent_contract.md`
- `docs/interfaces/nav_state_contract.md`
- `docs/interfaces/nav_view_contract.md`
- `docs/interfaces/telemetry_ui_contract.md`
- `shared/msg/*`
- `OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp`
- `OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp`
- `OrangePi_STM32_for_ROV/pwm_control_program/*`
- `Underwater-robot-navigation/nav_core/*`
- `UnderWaterRobotGCS/src/urogcs/*`
- `OrangePi_STM32_for_ROV/docs/architecture/ros2_bridge_plan.md`

评估目标不是把项目“整体 ROS2 化”，而是识别：

1. 哪些模块适合迁移到 ROS2。
2. 哪些模块只适合做 ROS2 镜像或桥接。
3. 哪些模块必须保留现有 C/C++ + SHM/UDP 主链。
4. 迁移时如何不破坏现有控制、导航和安全闭环。

## 1. 执行结论

当前项目**不适合做整体 ROS2 重构**。

原因很明确：

- 机器人侧核心主链已经围绕 `C/C++ + shared contracts + SHM + 本地安全裁决` 建立。
- `nav_core`、`nav_viewd`、`pwm_control_program`、`orangepi_send` 已经把 stale、valid、degraded、failsafe、PWM 安全等语义钉在本地链路里。
- 现有时间语义以 monotonic/steady ns 为核心，且要求 hop 间累计年龄，不能简单替换成 ROS 时间语义。
- 现有 AGENTS 和升级策略都明确限制：ROS2 只能用于外围成熟 UI/诊断/工具模块，不得接管控制、导航、状态传播和执行主线。

因此推荐结论是：

- **保留核心运行时架构不变。**
- **把 ROS2 定位为外围桥接层，而不是主控内核。**
- **优先迁移 UI backend、诊断聚合、日志/rosbag、状态镜像、bench 工具。**
- **禁止把 ControlGuard、nav_daemon、nav_viewd、PWM/STM32 执行链迁移成 ROS2 主图。**

## 2. 功能模块划分

### 2.1 核心算法与安全主链模块

下列模块属于核心算法或核心安全主链，建议保留现有架构：

| 模块 | 位置 | 当前职责 | 当前通信/依赖 | ROS2 结论 |
| --- | --- | --- | --- | --- |
| 导航运行时 | `Underwater-robot-navigation/nav_core` | 设备驱动、预处理、ESKF、导航状态发布、时间日志 | 串口、配置、`NavState` SHM、bin log | 不迁移 |
| 设备绑定与重连状态机 | `nav_core/app/device_binding.*` + `nav_daemon_runner.cpp` | 串口探测、身份匹配、重连/错绑诊断 | Linux 串口、sysfs、驱动生命周期、导航主循环 | 不迁移 |
| 控制主循环 | `OrangePi_STM32_for_ROV/pwm_control_program` | 输入收敛、安全裁决、控制器、分配、PWM 输出、权威 telemetry | `ControlIntent` SHM、`NavStateView` SHM、PWM backend | 不迁移 |
| 安全裁决 | `pwm_control_program/src/control_core/control_guard.cpp` | estop/arm/ttl/nav 信任性/模式切换收口 | 直接消费导航语义与 intent TTL | 不迁移 |
| 导航控制视图桥 | `gateway/apps/nav_viewd.cpp` | `NavState` 到 `NavStateView` 的 stale/no-data 策略应用 | `NavState` SHM -> `NavStateView` SHM | 不迁移 |
| 执行链 | `orangepi_send` + STM32 path | 最终下发 PWM/心跳/链路维护 | 串口/板端接口 | 不迁移 |
| 机器人侧会话边界 | `gateway/apps/gcs_server.cpp` | GCS UDP 会话与 SHM 边界桥接 | UDP + `ControlIntent` SHM + telemetry SHM | 不替换为 ROS2 主路径 |

这些模块的共同点是：

- 直接参与闭环控制、导航可信性或最终执行。
- 依赖严格的本地时间和 stale 语义。
- 依赖共享内存 ABI、Linux 串口和本地失败隔离。
- 一旦让 ROS2 成为它们的权威运行时，会把 DDS/QoS/图状态引入主安全链。

### 2.2 外围功能模块

下列模块属于外部功能、外围支撑或产品化层，适合评估 ROS2：

| 模块 | 位置 | 当前职责 | ROS2 适配性 | 建议 |
| --- | --- | --- | --- | --- |
| 状态镜像/遥测扇出 | `shared/msg/*` + telemetry consumers | 把权威运行态发布给外部系统 | 高 | 优先迁移为只读 bridge |
| 健康监控/诊断聚合 | telemetry + alarms + event history | 汇总 session/nav/fault/设备状态 | 高 | 适合做 ROS2 monitor 节点 |
| UI backend / 操作员前端后端 | `UnderWaterRobotGCS/src/urogcs/app/*` | 展示、操作编排入口、状态解释 | 高 | 适合做 ROS2 consumer/backend |
| 日志、rosbag、复盘集成 | `nav_core/tools/*`、control telemetry logs | 导出、录包、对照、incident bundle | 高 | 适合迁移或桥接 |
| MotorTest 编排包装 | `ControlIntent` 中的 motor test 能力 | bench/诊断类动作入口 | 中高 | 适合 ROS2 action/service 包装 |
| 外围配置/巡检工具 | Python tools / preflight / snapshot | 巡检、环境检查、非实时工具 | 中高 | 适合放在 ROS2 工具层 |
| 设备状态可视化 | `DeviceBinder` 状态、USB 快照 | 给客户看设备在线/错绑/重连 | 中 | 适合做状态镜像，不适合迁核心 binder |
| 通信后台聚合 | UI backend / websocket / dashboards | 给上层 UI 或远端监控统一出口 | 中高 | 适合迁移为 ROS2 backend |

### 2.3 灰区模块

这类模块不能简单归类为“能迁”或“不能迁”，需要拆层看：

#### 设备管理

- **设备状态观察、诊断展示、USB 身份快照**：适合迁到 ROS2 外围层。
- **真实串口探测、身份匹配、driver start/stop、重连回退策略**：不适合第一阶段迁移。

原因：`DeviceBinder` 不是单纯 UI 配置模块，而是 `nav_daemon_runner.cpp` 主循环里的一部分，直接决定 IMU/DVL 是否能上线、何时进入 reconnecting/mismatch/offline，并影响 `NavState` 与 `NavStatusFlags`。

#### 通信管理

- **操作员侧消息聚合、UI backend、远程监控出口**：适合 ROS2。
- **机器人侧 GCS 会话、ACK、心跳、`ControlIntent` 注入边界**：不建议用 ROS2 替换。

原因：当前 `gcs_server` 是明确的 `UDP <-> SHM` 边界桥。如果让 ROS2 直接接管控制入口，就会把 DDS 图状态、QoS 和 bridge 故障引入控制主线。

## 3. ROS2 适配性分析

### 3.1 ROS2 能带来的实际收益

对于外围模块，ROS2 的优势是明确的：

1. **模块化发布/订阅更自然**
   - 状态镜像、健康监控、UI backend、日志管线可以减少点对点定制接口。
2. **更好的可扩展性**
   - 后续若接 Web UI、rviz 风格诊断页、远程监控面板，ROS2 更容易扩展。
3. **标准化消息与录包能力**
   - `rosbag2` 对状态镜像、事件复盘、演示回放有价值。
4. **诊断类工具生态更成熟**
   - 对健康汇总、topic 观察、外围工具链集成有帮助。

但这些收益主要发生在外围层，不发生在闭环控制内核。

### 3.2 ROS2 不适合作为核心主线的原因

1. **时间语义不匹配**
   - 当前系统 stale/freshness 统一使用 monotonic/steady ns。
   - `NavState.age_ms`、`NavStateView.age_ms`、`TelemetryFrameV2.system.nav_age_ms` 都要求跨 hop 累积，不能在 bridge 中重算成“刚收到 topic 所以是 fresh”。
2. **安全边界已经在本地收口**
   - `ControlGuard`、`nav_viewd`、PWM/STM32 执行链已经是最终裁决路径。
   - ROS2 更适合观察和编排，不适合成为 अंतिम安全 authority。
3. **通信模型不同**
   - 当前核心路径依赖 SHM ABI、固定布局、单机失败隔离、UDP 会话边界。
   - ROS2/DDS 适合解耦，但会引入 QoS、发现、buffer/backpressure 和 graph lifecycle 问题。
4. **设备管理与 Linux 运行时强绑定**
   - `DeviceBinder`、IMU/DVL 驱动和 sysfs/tty 逻辑不是一个抽象总线层，而是实时导航运行时的一部分。

## 4. 接口契约检查

### 4.1 当前契约与 ROS2 的兼容性结论

当前共享契约整体上**适合做 ROS2 message mirror**，但**不适合直接用 ROS2 替换现有 ABI/SHM 契约**。

原因：

- `shared/msg/*` 基本都采用 standard-layout / trivially-copyable / 版本号 + 固定字段布局。
- 这些结构非常适合成为 ROS2 IDL 的语义源。
- 但 ROS2 message 不是当前 SHM ABI 的直接替代品，不能拿 topic 直接替换原有共享内存入口。

### 4.2 各契约的建议处理方式

| 契约 | 当前角色 | ROS2 兼容性 | 建议 |
| --- | --- | --- | --- |
| `TelemetryFrameV2` | 控制权威运行态输出 | 高 | 优先做 mirror topic |
| `NavState` | 导航权威输出 | 中高 | 可做调试/记录 topic，不替代主链 |
| `NavStateView` | 控制侧导航消费视图 | 高 | 可做只读 topic，不替代控制输入 |
| `ControlIntent` | 控制入口契约 | 低 | 不作为 ROS2 权威控制通道 |
| `time_contract` | monotonic 时间/年龄语义 | 中 | 需显式保留 `uint64` monotonic 字段，不改成 ROS wall time |

### 4.3 需要特别注意的兼容点

#### `TelemetryFrameV2`

这是最适合做 ROS2 镜像的契约。

建议：

- 保留 `stamp_ns`、`session_state`、`active_mode`、`nav_valid/nav_stale/nav_degraded`、`fault/health`、`last_command_result`、event history 等字段。
- 不要在 ROS2 bridge 里重新发明一套更“漂亮”的状态语义。
- 如果拆 topic，也应保持与原字段一一对应。

#### `NavState` / `NavStateView`

可以发布到 ROS2，但要注意：

- `stamp_ns`/`t_ns` 仍应保留为单调时间字段，不要强转成日历时间后再作为权威时间解释。
- `age_ms` 不能在 ROS2 consumer 侧静默归零。
- `NavStateView` 的 stale/no-data 语义是控制侧契约，不应让 ROS2 consumer 二次改写后再回灌控制。

#### `ControlIntent`

`ControlIntent` 可以有一个 ROS2“外围请求接口”，但它不应成为直接控制链。

更稳的方式是：

- ROS2 action/service 仅做操作员工具入口。
- 最终仍由现有 gateway / GCS protocol / SHM provider 注入现有控制链。
- ROS2 侧如果崩溃，控制主线必须完全不受影响。

## 5. 通信方式检查

当前系统的核心通信方式是：

- **单机核心链**：SHM
- **GCS 与车端**：UDP 会话协议
- **复盘/日志**：bin log + CSV + Python tools

这与 ROS2 的兼容关系如下。

### 5.1 适合接入 ROS2 的方式

- 在 SHM 之上增加**只读 bridge**，把 `TelemetryFrameV2`、`NavState`、`NavStateView` 镜像到 topic。
- 在日志和事件层之上增加 rosbag/diagnostics/export。
- 在 UI/backend 层消费 ROS2 topic，而不是让 UI 直接读控制内部结构。

### 5.2 不适合的方式

- 用 ROS2 topic 直接替换 `/rovctrl_gcs_intent_v1`。
- 用 ROS2 topic 直接替换 `/rovctrl_nav_view_v1` 供控制消费。
- 让 `pwm_control_program` 依赖 ROS2 graph 才能进入正常运行。
- 让 ROS2 节点承担最终 estop、arm、mode 裁决。

## 6. 依赖与耦合分析

### 6.1 高耦合核心链

#### `nav_daemon_runner.cpp`

当前导航守护进程把这些东西放在一个运行时主线上：

- `DeviceBinder`
- `ImuDriverWit` / `DvlDriver`
- `ImuRtPreprocessor` / `DvlRtPreprocessor`
- `EskfFilter`
- `NavStatePublisher`
- `BinLogger`

这说明：

- 设备管理、驱动、算法、发布和日志不是松散拼接，而是共同维护同一套时间语义和状态机。
- 直接把设备管理或发布中心改成 ROS2 native，会波及主循环和日志闭环。

#### `nav_viewd.cpp`

`nav_viewd` 不是简单的“格式转换器”。它负责把 `NavState` 变成控制可消费的 `NavStateView`，并在 stale/no-data 时明确清掉不可信运动学 payload。

这类语义属于控制安全边界，建议保留在现有本地进程里。

#### `pwm_control_program`

`pwm_control_program` 当前把：

- GCS intent SHM
- nav view SHM
- `ControlGuard`
- `ControllerManager`
- 分配与 PWM
- `TelemetryFrameV2`

收在一条闭环主线上。

它与 ROS2 的正确关系应该是“发布给 ROS2 观察”，而不是“被 ROS2 驱动”。

### 6.2 低耦合外围层

#### GCS UI 层

`UnderWaterRobotGCS` 当前已经分出：

- `session/`：会话与 UDP
- `core/service.py`：业务友好接口
- `telemetry/model.py` + `ui_viewmodels.py`：状态解释层
- `app/tui`、`app/gui`：前端

这意味着 UI 层已经具备比较好的边界：

- 可以继续直接走当前 GCS 协议。
- 也可以在未来增加一个 ROS2 consumer/backend，而不强迫改动控制主线。

#### 工具链

`usb_serial_snapshot.py`、`parse_nav_timing.py`、`merge_robot_timeline.py`、`replay_compare.py` 这类工具天然更适合做桥接和外围集成，不会直接冲击闭环安全。

## 7. 建议迁移优先级

### P1：优先迁移

1. **`rov_msgs` 语义镜像层**
   - 从 `shared/msg/*` 生成或手工维护等价 ROS2 msg。
   - 第一批至少包含 telemetry、nav status、fault/event、health。
2. **只读状态 bridge**
   - `TelemetryFrameV2` -> `/rov/telemetry`
   - `NavStateView` -> `/rov/nav_view`
   - `NavState` -> `/rov/nav_state_raw` 或调试 topic
3. **健康监控/诊断聚合节点**
   - 汇总 session、nav stale/degraded、设备 mismatch/reconnecting、fault/event。
4. **UI backend consumer**
   - 给未来 GUI/Web UI 提供统一 topic 输入。

### P2：次优先迁移

1. **rosbag / replay 外围集成**
   - 录制 ROS2 topics，辅助演示和外部分析。
2. **MotorTest 外围 service/action**
   - 只作为 bench/诊断入口，底层仍走现有安全链。
3. **设备状态可视化与巡检接口**
   - 把 `DeviceBinder` 状态和 USB 身份快照作为 ROS2 诊断信息发布。

### P3：暂缓或只做桥接

1. **GCS 通信边界**
   - 可做 ROS2 backend mirror，但不替换 `gcs_server`。
2. **配置与启动编排**
   - 可以在外围层做 launch/ops 工具，但不侵入控制内核。

### 禁止项

以下内容当前不应列入 ROS2 重构范围：

- `nav_core` 变成 ROS2 native 导航图
- `nav_viewd` 被 ROS2 节点替换
- `ControlGuard` / `ControlLoop` 迁到 ROS2 executor
- `PWM/STM32` 执行链进入 ROS2
- 让 ROS2 变成最终 estop / arm / mode authority

## 8. 实施计划

### 阶段 0：契约冻结与映射设计

输出：

- `rov_msgs` 消息清单
- 字段映射表
- QoS 草案
- monotonic 时间映射规则

硬规则：

- `stamp_ns`/`t_ns` 保持 `uint64` monotonic 字段
- `age_ms` 保留，不在 bridge 中重算
- `fault_code`、`status_flags`、`command result` 不丢语义

### 阶段 1：只读 bridge 落地

实现：

- `rov_state_bridge`
- `rov_nav_bridge`
- `rov_telemetry_bridge`

验收：

- bridge 崩溃不影响 `pwm_control_program`、`nav_daemon`、`gcs_server`
- topic 延迟和丢包不会回压主链
- 关键状态与 SHM 原值一致

### 阶段 2：健康与 UI backend

实现：

- `rov_health_monitor`
- `rov_operator_ui_backend`

验收：

- UI 只消费 ROS2 外围状态，不新增安全裁决
- 连接/设备/导航/控制/命令/故障字段与现有 telemetry 语义一致

### 阶段 3：工具与 bench 服务

实现：

- `rov_motor_test_server`
- replay / rosbag / diagnostic export 集成

验收：

- 所有 bench 服务都经过现有安全链
- 不允许绕过 `ControlGuard`

## 9. 当前文档漂移与风险提示

当前至少有两处文档与代码不完全一致，做 ROS2 方案时不能忽略：

1. `docs/interfaces/telemetry_ui_contract.md` 仍写着 `src/urogcs/app/gui_main.py` 为空。
   - 但当前 GCS 仓已经存在可运行的 PySide6 GUI 入口。
   - 这不影响 ROS2 边界结论，但说明 UI 现状比旧文档更前进。
2. `pwm_control_program/docs/gcs/gcs_control_and_telemetry_protocol.md` 仍以较早期 `TelemetryFrameV1` 逻辑模型表述为主。
   - 当前系统级权威状态基线已经是 `TelemetryFrameV2` + `telemetry_ui_contract.md`。
   - 后续若做 ROS2 消息设计，应以 `shared/msg/telemetry_frame_v2.hpp` 为真源，不应以旧 V1 描述做消息来源。

## 10. 最终建议

当前最合理的 ROS2 路线不是“把系统重写成 ROS2 项目”，而是：

1. 先把 `shared/msg/*` 变成外围 ROS2 message mirror 的语义真源。
2. 优先做只读状态 bridge、健康监控和 UI backend。
3. 把日志、rosbag、bench 工具逐步接到 ROS2 外围层。
4. 明确禁止 ROS2 接管控制、导航、状态传播和执行主线。

一句话总结：

**ROS2 适合成为 UnderwaterRobotSystem 的外围产品化总线，不适合成为当前机器人的核心控制总线。**
