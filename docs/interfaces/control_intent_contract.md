# Control Intent Contract

## Intent Path

Current production path:

`GCS command -> gateway session/gcs_server -> SHM control intent -> pwm_control_program`

## Command State Layers

- `sent`
  - GCS transmitted a packet
- `acknowledged`
  - gateway/session transport ACK was received for the transmitted packet
- `accepted`
  - control telemetry reports `CommandResultCode::Accepted`
- `executed`
  - control telemetry reports `CommandResultCode::Executed`
- `rejected/expired/failed`
  - control telemetry reports the corresponding runtime result

## P0 Control Safety Rule

`ControlLoop` must not locally override `ControlGuard` safety decisions. The guard
owns the authoritative decision for no-nav / stale-input / estop / failsafe cases.

As of control commit `677266c`, the no-nav teleop demo override path has been
removed from `control_loop_run.cpp`.
