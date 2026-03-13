# Incident Timeline Usage

## Goal

Use `merge_robot_timeline.py` as the minimum incident-review tool before the
project has a full replay injector.

It is meant to answer:

- what happened first
- which layer turned invalid/stale/failsafe
- whether telemetry/UI reflected the same cause

## Inputs

Minimum useful set:

- `nav_timing.bin`
- `nav_state.bin`
- `control_loop_*.csv`
- `telemetry_timeline_*.csv`
- `telemetry_events_*.csv`

Optional:

- `nav.bin`

## Common Commands

Full merged list:

```bash
python3 nav_core/tools/merge_robot_timeline.py \
  --nav-timing nav_timing.bin \
  --nav-state nav_state.bin \
  --control-log control_loop.csv \
  --telemetry-timeline telemetry_timeline.csv \
  --telemetry-events telemetry_events.csv
```

Reconnect incident window:

```bash
python3 nav_core/tools/merge_robot_timeline.py \
  --nav-timing nav_timing.bin \
  --nav-state nav_state.bin \
  --control-log control_loop.csv \
  --telemetry-timeline telemetry_timeline.csv \
  --telemetry-events telemetry_events.csv \
  --event reconnecting \
  --window-before-ms 150 \
  --window-after-ms 350 \
  --csv-out reconnecting_window.csv
```

Command failure window:

```bash
python3 nav_core/tools/merge_robot_timeline.py \
  --nav-timing nav_timing.bin \
  --nav-state nav_state.bin \
  --control-log control_loop.csv \
  --telemetry-timeline telemetry_timeline.csv \
  --telemetry-events telemetry_events.csv \
  --event command_failed \
  --window-before-ms 20 \
  --window-after-ms 40
```

## Reading Output

- `*`
  - highlighted anchor event matching `--event`
- `tags=...`
  - normalized diagnosis labels used for filtering
- `source`
  - one of `nav_timing`, `nav_state`, `control`, `telemetry_timeline`, `telemetry_events`

## Current Limits

- this is still offline review only
- the tool does not re-inject logs into `nav_viewd` or `ControlLoop`
- long sessions still need external slicing before review
