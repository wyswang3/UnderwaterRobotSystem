# Log Replay Guide

## Current P1 Minimum Closure

Replay is still not a full inject-and-rerun framework, but the project now has a
minimum offline reconstruction path built from four log classes:

1. raw sensor/time trace
   - `nav_timing.bin`
2. nav publish state
   - `nav_state.bin`
3. control status
   - `logs/control/control_loop_*.csv`
4. telemetry and event state
   - `logs/telemetry/telemetry_timeline_*.csv`
   - `logs/telemetry/telemetry_events_*.csv`

`nav.bin` is also consumed as an auxiliary DVL sample log.

## Current Tooling

Primary tools:

- `python3 nav_core/tools/parse_nav_timing.py ...`
- `python3 nav_core/tools/merge_robot_timeline.py ...`

`merge_robot_timeline.py` joins:

- `nav_timing.bin`
- `nav.bin`
- `nav_state.bin`
- control CSV
- telemetry timeline CSV
- telemetry event CSV

into one monotonic event list for incident review.

## Event Window Export

`merge_robot_timeline.py` now supports incident-oriented filtering:

```bash
python3 nav_core/tools/merge_robot_timeline.py \
  --nav-timing /path/to/nav_timing.bin \
  --nav-state /path/to/nav_state.bin \
  --control-log /path/to/control_loop_xxx.csv \
  --telemetry-timeline /path/to/telemetry_timeline_xxx.csv \
  --telemetry-events /path/to/telemetry_events_xxx.csv \
  --event reconnecting \
  --window-before-ms 150 \
  --window-after-ms 350 \
  --csv-out reconnecting_window.csv
```

Supported `--event` anchors:

- `reconnecting`
- `mismatch`
- `stale`
- `invalid`
- `degraded`
- `failsafe`
- `command_rejected`
- `command_failed`
- `command_expired`
- `nav_fault`

Other useful filters:

- `--source control --source telemetry_timeline`
- `--fault-code <code>`
- `--command-status <code>`
- `--from-ns ... --to-ns ...`

## What This Can Already Answer

- when device binding changed state
- whether the main loop consumed, rejected, or stale-dropped a sample
- when nav published invalid/degraded state
- when control rejected Auto / entered failsafe
- when telemetry/UI-facing state reflected the same transition
- which event window should be exported for operator review instead of scanning the full log

## What Is Still Missing

- no binary replay injector yet
- no deterministic re-run of `nav_viewd` / `ControlLoop` from logs
- no long-session viewer beyond CLI summaries
- no IMU raw payload log equivalent to `nav.bin` yet
