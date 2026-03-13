# Nav View Contract

## Purpose

`NavStateView` is the control-facing projection of navigation state. It exists to
decouple estimator internals from control consumption rules.

## Consumer Rules

- `valid=1` is required before a controller may treat nav as trusted
- `stale=1` means the current snapshot must be rejected even if fields are present
- `degraded=1` means the view is usable only by policies that explicitly allow
  degraded navigation
- `nav_state` and `health` are operator-visible summary fields and must agree with
  `valid/stale/degraded/fault_code`

## Control Implication

- `ControlGuard` and `ControlLoop` must key their protection logic off the
  projected nav view semantics, not off partial field presence
- UI must expose nav validity and nav state independently; a non-empty pose does
  not imply trusted nav
