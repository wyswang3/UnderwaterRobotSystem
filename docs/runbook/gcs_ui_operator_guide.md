# GCS UI Operator Guide

## Reading The Current TUI

- `[ROV]`
  - session/link status and local receive age of the latest remote status
- `[OP ]`
  - local operator intent only
- `[AUTH]`
  - remote authoritative state actually reported by the vehicle stack
- `[NAV]`
  - remote nav trust summary plus specific diagnosis
- `[CMD]`
  - local sent/ACK state plus remote command-result state
- `[DOF]`
  - last DOF intent sent by the operator

## Important Interpretation Rule

If `[OP ]` and `[AUTH]` disagree, the vehicle has not yet applied the operator
request or has rejected it.

Examples:

- local `mode=Auto`, remote `mode=Manual`
  - request sent, not yet applied
- local estop cleared, remote `estop=1`
  - estop still latched on the vehicle side
- local `ARM` just sent, remote `armed=0`
  - arm request not yet applied or rejected

## How To Read `[NAV]`

The P1 TUI `NAV` line now carries three layers:

- trust state
  - `valid/stale/degraded`
- fault name
  - `nav_fault=<...>`
- diagnosis summary
  - `diag=stale,imu_reconnecting`
  - `diag=invalid,dvl_mismatch`
  - `diag=degraded`

Interpretation examples:

- `stale=1` and `diag=invalid,imu_reconnecting`
  - navigation is currently unusable because the IMU path is reconnecting
- `valid=0` and `diag=invalid,dvl_mismatch`
  - the device identity is wrong, not just late
- `valid=1` and `diag=degraded`
  - control may still run in a limited mode

## Command Status Rule

`[CMD]` continues to separate:

- local send
- session ACK
- remote runtime result

If `[CMD] runtime=Failed` while `[AUTH]` and `[NAV]` show a nav fault, the command
reached the vehicle stack but was refused by runtime protection.
