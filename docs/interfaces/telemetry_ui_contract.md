# Telemetry UI Contract

## UI Design Principle

UI must separate local operator intent from remote authoritative runtime state.

## Required Remote Runtime Fields

- session: `session_established`, `link_alive`
- control: `armed`, `estop`, `mode`, `failsafe_active`
- nav: `nav_valid`, `nav_state`, `nav_stale`, `nav_degraded`
- nav diagnostics: `nav_fault_code`, `nav_status_flags`
- health: `fault_state`, `health_state`, `last_fault_code`
- controllers: `active_controller`, `desired_controller`
- command result: `command_status`, `command_cmd_seq`, `command_fault_code`

## Nav Diagnostic Interpretation

`nav_fault_code` and `nav_status_flags` now come from the authoritative control-core
telemetry frame, which itself mirrors the latest `NavStateView` consumed by control.
UI/TUI must not guess reconnecting or mismatch state locally.

Minimum derived UI labels:

- `reconnecting`
  - `nav_status_flags` contains IMU/DVL reconnecting bits
- `mismatch`
  - `nav_status_flags` contains IMU/DVL bind mismatch bits
- `offline`
  - device fault code indicates not-found/disconnected and no mismatch/reconnecting bit explains it better
- `stale`
  - `nav_stale=1`
- `invalid`
  - `nav_valid=0`
- `degraded`
  - `nav_valid=1` and `nav_degraded=1`

The recommended operator-facing presentation is:

- coarse trust state:
  - `valid/stale/degraded`
- specific reason:
  - `nav_fault_code` name
- device diagnosis:
  - summary derived from `nav_status_flags`

## Required Local Command Fields

- last transmitted command kind and sequence
- pending ACK sequence/kind
- last ACK code and reason

## P0 TUI Baseline

The current TUI should show:

- `[ROV]` session/link/rx-age/status-seq
- `[OP ]` local requested mode/estop/throttle
- `[AUTH]` remote `armed/estop/mode/failsafe/controller`
- `[NAV]` remote nav validity/state/degraded/stale/fault
- `[CMD]` local sent/ACK state plus remote command result state
- `[DOF]` last sent DOF intent
- `[LOG]` last local log line

## P1 Diagnostic Baseline

The current TUI baseline should additionally show:

- `nav_fault=<NavFaultCode name>`
- `diag=<comma-separated nav diagnosis summary>`

This is intentionally minimal but sufficient to distinguish:

- `stale`
- `invalid`
- `degraded`
- `imu_reconnecting` / `dvl_reconnecting`
- `imu_mismatch` / `dvl_mismatch`
- offline device faults inferred from `nav_fault_code`

## Hard Rule

The UI must never imply success of `ARM`, `ESTOP`, or mode switching based only on
key press or packet send. Success is only shown when remote authoritative state or
command result confirms it.
