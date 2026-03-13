# Telemetry UI Contract

## UI Design Principle

UI must separate local operator intent from remote authoritative runtime state.

## Required Remote Runtime Fields

- session: `session_established`, `link_alive`
- control: `armed`, `estop`, `mode`, `failsafe_active`
- nav: `nav_valid`, `nav_state`, `nav_stale`, `nav_degraded`
- health: `fault_state`, `health_state`, `last_fault_code`
- controllers: `active_controller`, `desired_controller`
- command result: `command_status`, `command_cmd_seq`, `command_fault_code`

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

## Hard Rule

The UI must never imply success of `ARM`, `ESTOP`, or mode switching based only on
key press or packet send. Success is only shown when remote authoritative state or
command result confirms it.
