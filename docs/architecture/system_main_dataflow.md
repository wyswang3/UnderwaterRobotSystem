# System Main Dataflow

## 适用范围

本文档定义当前系统主数据流基线。它以当前代码为准，不以早期规划图为准。

关键源码入口：

- `UnderWaterRobotGCS/src/urogcs/core/service.py`
- `OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp`
- `Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_runner.cpp`
- `OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp`
- `OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp`

## 1. 上位机指令流

当前生产主链路：

```text
GCS TUI
  -> urogcs.core.service
  -> session_client / protocol encode
  -> UDP
  -> gateway/gcs_server
  -> /rovctrl_gcs_intent_v1
  -> GcsShmInputProvider
  -> ControlGuard
  -> ControllerManager / ControlLoop
  -> ThrusterAllocator / teleop_mixer
  -> PwmClient
  -> orangepi_send
  -> STM32
```

说明：

- 当前可信主路径是 `GCS -> gcs_server -> /rovctrl_gcs_intent_v1`
- `teleop_local`、`intentd`、`/rovctrl_intent_local_v1`、`/rovctrl_intent_auto_v1`
  和 `mux/final` 路径仍然存在，但更偏 bench/实验，不是当前首选操作主线

## 2. 导航数据流

当前导航主链路：

```text
IMU / DVL
  -> DeviceBinder / drivers
  -> imu_rt_preprocessor / dvl_rt_preprocessor
  -> OnlineEstimator / ESKF
  -> nav_runtime_status
  -> NavStatePublisher
  -> /rov_nav_state_v1
  -> nav_state.bin + nav_timing.bin
```

说明：

- `NavState` 是导航估计侧权威发布
- `NavState` 中数值字段不是唯一重点，`valid/stale/degraded/fault_code`
  才是控制消费前必须先看的语义字段

## 3. 控制主循环数据流

导航进入控制的主链路：

```text
/rov_nav_state_v1
  -> gateway/nav_viewd
  -> stale/no-data policy
  -> /rovctrl_nav_view_v1
  -> NavViewShmSource
  -> ControlGuard
  -> ControllerManager / ControlLoop
```

控制主循环完整汇流：

```text
/rovctrl_gcs_intent_v1
  + /rovctrl_intent_mux_v1   (辅助/实验路径)
  + /rovctrl_nav_view_v1
    -> pwm_control_program
    -> ControlGuard
    -> controller compute
    -> thruster allocation
    -> PwmClient
    -> PWM/STM32 execution
```

当前关键规则：

- `Manual` 不强依赖导航
- `Auto` 需要可信导航
- 最终安全裁决在 `ControlGuard`
- 最终执行安全仍在 `PwmClient` 和底层 PWM 安全层

## 4. Telemetry / UI 反馈流

当前权威状态反馈链：

```text
pwm_control_program
  -> TelemetryFrameV2
  -> /rovctrl_telemetry_v2
  -> gateway/gcs_server status adapter
  -> StatusTelemetry
  -> UDP
  -> GCS session client
  -> TUI viewmodels
```

权威性边界：

- `TelemetryFrameV2` 是控制运行态、导航健康态、命令结果态的上游权威源
- gateway session 只对传输/会话字段负责，例如 `session_established`、`link_alive`
- GCS/TUI 不允许依据本地按键或本地默认值猜测 `armed`、`mode`、`failsafe`

## 5. 日志与复盘流

当前最小复盘闭环：

```text
nav_timing.bin
  + nav_state.bin
  + control_loop_*.csv
  + telemetry_timeline_*.csv
  + telemetry_events_*.csv
    -> merge_robot_timeline.py
    -> incident bundle
    -> uwnav_nav_replay
    -> nav_viewd
    -> pwm_control_program --pwm-dummy
    -> replay_compare.py
```

作用：

- 定位 stale、invalid、reconnecting、command_failed 这类故障窗口
- 验证故障是否沿 `NavState -> NavView -> Control -> Telemetry -> GCS`
  正确传播

## 6. 主链路权威规则

1. 导航估计权威源：`NavState`
2. 控制消费权威导航视图：`NavStateView`
3. 控制安全权威：`ControlGuard`
4. 运行态权威遥测：`TelemetryFrameV2`
5. 传输/会话权威：gateway session

## 7. 当前已知限制

1. 顶层聚合 CMake 还不是可信集成入口。
2. `shared/` 仍存在运行时真源和镜像副本并存的问题。
3. `teleop_local` / `intentd` 路径仍在代码中，但不是当前主操作基线。
4. replay 仍然是最小可验证闭环，不是完整原始帧级重放平台。
