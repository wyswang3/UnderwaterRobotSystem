# Cross-Repo Compatibility Matrix

## 当前工作区兼容性基线

截至 2026-03-20，当前工作区主基线为：

| Repo | Branch | Commit | Role |
| --- | --- | --- | --- |
| `Underwater-robot-navigation` | `feature/nav-p0-contract-baseline` | `2329255` | 导航运行时、重连、日志/replay 工具 |
| `OrangePi_STM32_for_ROV` | `feature/control-p0-status-telemetry-baseline` | `c23d83d` | gateway、控制主循环、权威 telemetry |
| `UnderWaterRobotGCS` | `feature/gcs-p0-status-telemetry-alignment` | `3e2cb04` | GCS/TUI 权威状态渲染 |
| `UnderwaterRobotSystem` | `feature/docs-p0-baseline-alignment` | `054ea73` | 系统级文档与镜像基线 |

## 当前兼容性预期

- `TelemetryFrameV2` 仍是运行态语义上游真源
- gateway `StatusTelemetry` 仍需兼容当前 GCS 的状态解码
- GCS 当前必须能看到：
  - `armed`
  - `mode`
  - `failsafe_active`
  - `nav_valid/nav_state/nav_stale/nav_degraded`
  - `nav_fault_code/nav_status_flags`
  - `fault_state/health_state`
  - `command_status/command_cmd_seq`

## 当前同步规则

1. 如果 nav/control/GCS 任何一个仓库的共享契约或状态语义发生变化，
   本文件必须同步更新。
2. 如果升级任务跨多个仓库，文档仓提交必须记录与代码仓相匹配的分支/提交点。
3. 如果只是局部实验分支，不要把实验性 commit 写进这里冒充系统基线。

## Shared Contract 说明

当前仍是双位置形态：

- 运行时真源：
  - `/home/wys/orangepi/UnderwaterRobotSystem/shared`
- 文档/评审镜像：
  - `/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/shared`

这仍然是一个过渡方案。后续应收敛为单一真实源仓库或正式子模块。
