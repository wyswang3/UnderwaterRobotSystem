# System Main Dataflow

## Authoritative Mainline

Current control mainline:

`GCS UDP -> gcs_server -> /rovctrl_gcs_intent_v1 -> GcsShmInputProvider -> ControlGuard -> ControllerManager / ControlLoop -> PwmClient -> STM32 -> TelemetryFrameV2 -> gcs_server -> StatusTelemetry -> GCS/TUI`

Current navigation mainline:

`IMU / DVL -> nav_daemon_runner -> NavState SHM -> nav_viewd -> NavStateView SHM -> ControlLoop`

## Authority Rules

- `ControlGuard` is the authority for arm / estop / failsafe gating.
- `TelemetryFrameV2` is the authority for runtime control, nav-health, and command
  result state exported to GCS.
- gateway session state is authoritative only for transport/session flags such as
  `session_established` and `link_alive`.
- GCS/TUI must not infer `armed`, `mode`, `failsafe`, or nav trust from local key
  events. Those fields must come from the latest telemetry status path.

## Dataflow Notes

- `NavState` is the estimator-facing publication.
- `NavStateView` is the control-facing, filtered, stale-aware snapshot.
- `StatusTelemetry` is a compact GCS-facing projection of the latest
  `TelemetryFrameV2` plus gateway session state.
- UI must display local command intent and remote applied state as separate fields.

## Known Current Limits

- top-level aggregate CMake is still not the trustworthy integration entrypoint
- device binding/reconnect is not yet hardened
- replay closure is not complete yet
