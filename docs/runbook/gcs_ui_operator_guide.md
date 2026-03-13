# GCS UI Operator Guide

## Reading The Current TUI

- `[ROV]`
  - session/link status and local receive age of the latest remote status
- `[OP ]`
  - local operator intent only
- `[AUTH]`
  - remote authoritative state actually reported by the vehicle stack
- `[NAV]`
  - remote nav trust summary
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
