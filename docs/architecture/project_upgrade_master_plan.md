# Project Upgrade Master Plan

## Scope

This document is the project-level baseline for upgrading `UnderwaterRobotSystem`
from a functional prototype into a trustworthy multi-repo system.

Current audited code baseline:

- `Underwater-robot-navigation`: `46d693e` on `feature/nav-p0-contract-baseline`
- `OrangePi_STM32_for_ROV`: `dd2143f` on `feature/control-p0-status-telemetry-baseline`
- `UnderWaterRobotGCS`: `d8d8687` on `feature/gcs-p0-status-telemetry-alignment`

## Phase Plan

### P0: Trust Baseline

Goals:

- unify time and state semantics across nav, control, telemetry, and UI
- stop publishing pseudo-normal nav body kinematics
- remove local control-loop safety override paths
- make GCS/UI consume authoritative runtime state instead of gateway guesses

Delivered in this subphase:

- `NavState.omega_b/acc_b` now mirror the latest IMU measurement when available
- `pwm_control_program` no longer locally overrides Guard failsafe for no-nav teleop
- gateway `StatusTelemetry` now carries authoritative `armed`, `failsafe`, nav,
  fault, and command-result state from `TelemetryFrameV2`
- GCS/TUI now renders local operator intent separately from remote authoritative
  runtime state and command-result state

Still open in P0:

- root `shared/` is still outside standalone Git management
- real-hardware USB re-enumeration automation is still missing
- telemetry/UI does not yet expose device-binding detail fields directly

## Shared Contract Handling

For the current workspace layout:

- runtime code consumes the root-level `shared/`
- this repo now keeps a mirrored `shared/` tree under Git on
  `feature/docs-p0-baseline-alignment`
- docs and compatibility tracking must update the mirrored `shared/`
  in the same change set as any contract refresh

This is an interim arrangement. P1 should replace it with a proper standalone
shared-contract repo or submodule.

### P1: Bring-up, Logging, Replay, and Build Closure

Goals:

- raw sensor / nav / control / fault-event log closure
- replay of stale/fault propagation and GCS command outcomes
- one documented intent mainline
- standalone and aggregate build/test closure

### P2: Maintainability and Architecture Refinement

Goals:

- split oversized files by policy / transport / state machine / logging
- unify SHM header style and ABI checks
- continue time system normalization
- extend operator UI and replay tooling

## Non-Goals For This Round

- no broad subsystem rewrite
- no new autonomy features
- no new device drivers
- no UI visual redesign beyond trustworthy status semantics
