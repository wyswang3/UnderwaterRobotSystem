# P0 Contract Baseline Status

## Completed In This Round

- navigation body kinematics semantics fixed
- control-loop local failsafe override removed
- gateway `StatusTelemetry` upgraded to carry authoritative runtime state
- GCS/TUI updated to consume and display authoritative status fields
- unit tests added for nav kinematics decode and GCS viewmodel/codec behavior

## Remaining P0 Work

- device identity binding and reconnect state machines for IMU/DVL
- explicit time-contract tests for cross-hop age propagation
- stale/invalid propagation tests through `NavState -> nav_viewd -> NavStateView -> ControlLoop`
- reduce high-frequency stdout/stderr in control and guard paths

## Current Risk Position

- pseudo-normal nav body kinematics risk: reduced
- UI false-positive success risk for arm/mode/estop: reduced
- transport/session vs runtime state confusion: reduced
- device binding risk: unchanged
- top-level aggregate build risk: unchanged
