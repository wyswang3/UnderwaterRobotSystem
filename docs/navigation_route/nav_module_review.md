# 导航模块专项审查

## 审查范围

本次审查聚焦以下链路：

- `UnderwaterRobotSystem/Underwater-robot-navigation/nav_core`
- `UnderwaterRobotSystem/shared/msg`
- `UnderwaterRobotSystem/shared/shm`
- `UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway`
- `UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program`

目标是回答三个问题：

1. IMU 串口在 Orange Pi 上发生 `/dev/ttyUSB0 -> /dev/ttyUSB1` 跳变时，当前实现能否稳定发现、识别、重连。
2. ESKF 在传感器缺失、时间戳过期、未初始化时，是否仍在静默输出“看似合法”的数值状态。
3. 导航日志、NavState SHM、NavStateView、控制侧读取语义是否一致、可诊断、可保护控制闭环。

## 1. 导航模块现状梳理

### 1.1 主流程

当前在线导航主链路如下：

`uwnav_navd`
-> `nav_daemon.cpp`
-> `run_nav_daemon(...)`
-> `nav_daemon_runner.cpp`
-> `ImuDriverWit` / `DvlDriver`
-> `SharedSensorState`
-> `ImuRtPreprocessor` / `DvlRtPreprocessor`
-> `EskfFilter`
-> `NavStatePublisher`
-> `gateway/nav_viewd`
-> `NavViewPublisherShm`
-> `pwm_control_program`

### 1.2 关键文件

- 主入口：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon.cpp`
- 主循环：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_runner.cpp`
- IMU 驱动：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/drivers/imu_driver_wit.cpp`
- DVL 驱动：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/drivers/dvl_driver.cpp`
- IMU 预处理：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/preprocess/imu_rt_preprocessor.cpp`
- DVL 预处理：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/preprocess/dvl_rt_preprocessor.cpp`
- ESKF：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/eskf_*.cpp`
- NavState SHM 发布：`UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/io/nav_state_publisher.cpp`
- NavState 协议：`UnderwaterRobotSystem/shared/msg/nav_state.hpp`
- NavState SHM 契约：`UnderwaterRobotSystem/shared/shm/nav_state_shm.hpp`
- Gateway 桥接：`UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/nav/*.cpp`
- 控制侧读取：`UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/io/nav/*.cpp`
- 控制主循环导航接入：`UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_nav.cpp`

### 1.3 线程与进程关系

- `uwnav_navd` 进程内至少有 3 条执行链：
  - 主线程执行 `run_main_loop`
  - IMU 后台线程执行串口轮询
  - DVL 后台线程执行串口读取
- `gateway/nav_viewd` 是独立进程，负责 `NavState -> NavStateView`
- `pwm_control_program` 是独立进程，只消费 `NavStateView`

当前没有统一的跨进程健康状态机，只是每一层自己做一部分“valid / stale / age”判断。

### 1.4 输入与输出链路

- IMU：串口驱动回调把最新 `ImuFrame` 写入 `SharedSensorState.last_imu`
- DVL：串口驱动回调把最新 `DvlRawSample` 写入 `SharedSensorState.last_dvl_raw`
- 主循环每周期只读取“最新一帧”，不是严格队列消费
- ESKF 每周期从最新 IMU 做传播，从最新 DVL 新帧做更新
- `NavState` 每个周期都会发布
- `nav_viewd` 把 `NavState` 变成 `NavStateView`
- 控制侧只读取 `NavStateView`

### 1.5 与控制模块接口关系

实际控制接口不是直接读取 `NavState`，而是：

`NavState SHM`
-> `nav_viewd`
-> `NavStateView SHM`
-> `NavViewShmSource`
-> `ControlLoop`

因此，导航输出可信度最终能否被控制正确理解，取决于 3 层契约是否一致：

- `NavState` 的 `health/status_flags`
- `NavStateView` 的 `valid/health/reserved1`
- 控制侧 `read_latest()` 与 `ControlGuard`

## 2. 专项问题审查

### 2.1 IMU 串口跳变问题

#### 当前实现

- `nav_daemon.yaml` 将 IMU 端口直接配置为 `/dev/ttyUSB0`
- `ImuDriverWit::openPort()` 只尝试打开单一 `port_`
- 串口断开后，后台线程只会重试同一个路径
- 启动日志只打印逻辑路径，不打印物理身份信息

#### 已识别缺陷

1. 存在对单一路径的硬依赖。
2. 不支持多候选串口扫描。
3. 不支持基于 `udev`、稳定符号链接、`by-id`、VID/PID/serial 的设备身份识别。
4. 不支持 `/dev/ttyUSB0` 失效后自动发现 `/dev/ttyUSB1`。
5. 没有“打开成功但不是目标 IMU”的身份校验。
6. 错误提示只到 `open()/tcgetattr()/read()/select()`，没有统一错误码和状态输出。
7. 操作员无法从日志中确认最终绑定的是哪个物理 USB 设备。

#### 触发条件

- IMU USB 设备重枚举
- 多个 USB 串口设备同时存在
- IMU 插拔、供电抖动、USB Hub 重置
- 系统重启后枚举顺序变化

#### 对闭环影响

- 启动失败
- 运行中永久断连
- 错绑到非 IMU 串口
- 控制模块拿不到可信导航或拿到错误设备输出

#### 风险等级

高

### 2.2 ESKF 传感器缺失静默输出问题

#### 当前实现

- `EskfFilter` 构造时直接按配置初值 `reset(x0)`，初值默认接近零
- 第一帧 IMU 传播只更新时间戳并返回 `false`
- 主循环每个周期都执行 `eskf_to_nav_state()`
- `eskf_to_nav_state()` 默认把 `NavHealth` 设为 `OK`，把 `status_flags` 设为 `IMU_OK`
- 只有 IMU 超时才把 `health` 改成 `INVALID`

#### 已识别缺陷

1. 未完成初始化时仍输出数值型状态。
2. 初始化默认状态和“真实有效状态”没有分离。
3. 没有显式 `uninitialized / stale / degraded / fault` 状态机。
4. `NavState` 没有 `fault_code`、`stale`、`valid` 等显式语义。
5. `NavStatusFlags` 中定义了 `NAV_FLAG_ESKF_OK`、`NAV_FLAG_ALIGN_DONE`，但主链路没有填。
6. `ImuRtPreprocessor` 的 `bias_ready` 仅存在于内部状态，没有进入外部健康语义。
7. DVL 缺测只会清 `DVL_OK` 位，不会形成明确降级事件。
8. 当前在线主链路没有深度计输入，也没有深度缺测处理。
9. 协方差发散、数值异常、观测长期拒绝没有外显到控制接口。
10. `NavHealthMonitor` 和 `OnlineEstimator` 里已有更丰富健康语义，但默认构建关闭，且未接入 `nav_daemon` 主链路。

#### 触发条件

- 刚启动、尚未收到有效 IMU 传播
- IMU 数据持续无效或预处理长期拒绝
- DVL 长时间缺失
- 传感器时间戳卡住
- 只有惯导传播、无外部修正
- 预处理 bias 长期未 ready

#### 对闭环影响

- 控制可能把零位置、零速度、零姿态当成“合法状态”
- 自动模式可能在未初始化时启动
- DVL 丢失后退化过程不透明
- 现场诊断只能看到数值，无法知道是否可信

#### 风险等级

高

### 2.3 日志与共享内存契约问题

#### 当前实现

- 配置层定义了 `log_imu_raw/log_dvl_raw/log_imu_processed/log_eskf_state/log_eskf_update/log_health_report`
- 运行时 `BinLogger` 只打开一个 `nav.bin`
- 主循环里实际只看到 `bin_logger->write(&dvl_sample, sizeof(dvl_sample))`
- `NavStatePublisher` 原实现使用了私有 SHM 布局
- Gateway 读端使用 `shared/shm/nav_state_shm.hpp` 的 canonical 布局
- `nav_viewd` 默认订阅 `/rovctrl_nav_state_v1`
- `nav_daemon.yaml` 默认发布 `/rov_nav_state_v1`
- `nav_viewd` 在 stale 时可保留 `last_good_view` 的数值 payload，但把 `valid=0`
- 控制侧 `NavViewShmSource` 遇到 stale 或 invalid 直接返回 `false`

#### 已识别缺陷

1. 配置声明的日志层级与实际写盘行为不一致。
2. 缺少原始传感器到达、丢包、初始化状态切换、故障事件日志。
3. 当前日志不适合直接做事件复盘和状态机分析。
4. 审查时发现 `NavStatePublisher` 的 SHM 布局与共享契约不一致，读端会按 canonical 契约拒绝。
5. `nav_state` SHM 名称默认值在导航端和 gateway 端不一致。
6. `NavStateView` 只有 `valid/health`，缺少明确的 `fault_code/sensor_mask/stale_reason`。
7. 控制侧把 invalid/stale 与 no-data 折叠成一个 `false`，语义损失过大。
8. 审查时发现控制侧曾错误读取 `v.flags` 作为 `nav_status_flags`，而真实状态位在 `reserved1`。
9. `ControlState` 只保留 `nav_valid` 和 `nav_status_flags`，没有 `nav_health/nav_age/fault_code`。

#### 触发条件

- 任意导航发布异常
- SHM ABI 漂移
- SHM 名称配置不一致
- stale 保留上一次有效 payload
- 控制侧只看 `nav_valid`

#### 对闭环影响

- 控制层可能看不到真正故障原因
- 旧快照可能继续停留在数据面
- 现场很难区分“当前无数据”“旧数据”“数据无效”“状态降级”

#### 风险等级

高

## 3. 并发与时序风险

### 3.1 串口断连/重连

- IMU/DVL 驱动线程都只会在原路径上重连
- 如果设备重枚举到新路径，驱动线程会进入永久失败重试
- 主循环继续运行，但输入状态可能保持为最后一帧或空

### 3.2 旧传感器数据复用

- `SharedSensorState` 只保存最新一帧
- 主循环按“最新快照”拉取，无法区分中间丢了多少帧
- DVL 只靠 `last_used_dvl_ns` 避免重复消费，但没有完整队列语义

### 3.3 NavState 过期仍被看见

- `nav_viewd` stale 时允许继续发布旧 `last_good_view` 数值
- 控制侧若有模块忽略 `valid`，仍可能看到旧位置/速度/姿态

### 3.4 stale/valid 语义跨模块不一致

- `NavState` 没有显式 stale
- `nav_viewd` 用 SHM header 发布时间算 stale
- 控制侧 `NavViewShmSource` 用本地时间再次做 age gate
- 结果是“stale”在三层里不是同一语义

### 3.5 时间戳不一致

- `NavState.t_ns` 表示导航状态时间
- SHM header `mono_ns` 表示发布时间
- `NavStateView.stamp_ns`、`mono_ns`、控制本地 `age_ms_local` 又是另一组时间
- 目前没有统一文档规定控制应该以哪一个字段作为“可控性”判断主时间

### 3.6 CPU 调度影响

- 主循环、IMU 线程、DVL 线程完全靠各自 sleep/select 调度
- 没有统一的输入事件驱动顺序保证
- 在高负载时可能出现“先发布旧 NavState，再收到新传感器”的周期性反转

## 4. 风险等级排序

1. ESKF 未初始化或输入缺失时静默输出数值状态，高风险。
2. IMU 串口路径跳变后无法重新发现设备，高风险。
3. SHM 契约和名称不统一导致导航状态无法稳定传递，高风险。
4. 控制侧把导航有效性折叠成单布尔值，中高风险。
5. 日志只留数值不留事件，不利于故障复盘，中风险。

## 5. 本轮最小修复

本轮只做了两项低风险修复，不改变整体算法行为：

1. `NavStatePublisher` 改为使用 `shared/shm/nav_state_shm.hpp` 的 canonical SHM 布局和 metadata。
2. 控制侧 `ControlLoop` 改为从 `NavStateView.reserved1` 读取上游 `status_flags`，不再误读 `flags` 字段。

仍未修复但必须进入 P0 的问题：

- IMU 稳定设备路径与重枚举处理
- 未初始化/缺测/过期时的显式状态机
- `NavState/NavStateView` 的 fault/stale/degraded 统一语义
- 控制侧对无效导航的保护逻辑和降级策略

## 6. 结论

当前导航模块的主要问题不是“算法完全不可用”，而是工程语义不够显式：

- 设备绑定不稳定
- 输入缺失时故障不可见
- 状态可信度没有完整外显
- 日志不能支撑快速复盘
- SHM 契约和控制保护逻辑不够稳

后续整改方向必须坚持四个关键词：

- 显式状态
- 显式故障
- 显式新鲜度
- 显式日志
