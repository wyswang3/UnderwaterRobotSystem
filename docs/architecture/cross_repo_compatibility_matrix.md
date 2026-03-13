# Cross-Repo Compatibility Matrix

## P0 Status/Telemetry Baseline

| Repo | Branch | Commit | Purpose |
| --- | --- | --- | --- |
| `Underwater-robot-navigation` | `feature/nav-p0-contract-baseline` | `46d693e` | Device binding, reconnect, nav timing diagnostics |
| `OrangePi_STM32_for_ROV` | `feature/control-p0-status-telemetry-baseline` | `dd2143f` | `nav_viewd` daemon stale policy + control-side validation |
| `UnderWaterRobotGCS` | `feature/gcs-p0-status-telemetry-alignment` | `d8d8687` | GCS/TUI authoritative status rendering |

## Contract Expectations

- gateway `StatusTelemetry` wire size: `80` bytes
- legacy GCS decode compatibility: accepted for older `56` byte status payloads
- `TelemetryFrameV2` remains the upstream semantic source for runtime state
- GCS UI expects:
  - `armed`
  - `mode`
  - `failsafe_active`
  - `nav_valid/nav_state/nav_stale/nav_degraded`
  - `fault_state/health_state`
  - `command_status/command_cmd_seq`

## Integration Note

The docs repo commit should be treated as a compatibility manifest for the three
code repos above. If any of the listed commits changes, update this file in the
same change set as the docs refresh.

## Shared Contract Mirror

`UnderwaterRobotSystem/shared` inside this repo is now the version-controlled
mirror of the runtime shared contract used by the nav/control codebases.

- source-of-truth at runtime still lives in the workspace root `shared/`
- this repo keeps the mirrored copy under Git for review, docs alignment, and SHA tracking
- before entering P1, the root `shared/` should be promoted into a real standalone Git repo
  or submodule to eliminate the remaining manual sync step
