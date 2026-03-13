# nav_timing Log Guide

## Purpose

`nav_timing.bin` is the P0 minimum trace for answering:

- when a sample was taken
- when the driver received it
- when the nav main loop consumed or rejected it
- when nav published a state derived from it
- when IMU/DVL binding changed state

It is the first tool to use when investigating:

- stale triggering
- duplicate or out-of-order samples
- old snapshot reuse
- reconnect behavior
- unexplained nav invalid/degraded transitions

## Record Layout

Each record is `TimingTracePacketV1` and is 48 bytes.

Fields:

- `version`
- `kind`
- `flags`
- `sensor_time_ns`
- `recv_mono_ns`
- `consume_mono_ns`
- `publish_mono_ns`
- `age_ms`
- `fault_code`

Kinds:

- `imu_consumed`
- `dvl_consumed`
- `nav_published`
- `imu_rejected`
- `dvl_rejected`
- `imu_device_state`
- `dvl_device_state`

## Parser Usage

```bash
python3 nav_core/tools/parse_nav_timing.py /path/to/nav_timing.bin
```

JSON output:

```bash
python3 nav_core/tools/parse_nav_timing.py /path/to/nav_timing.bin --json
```

Unified minimal timeline:

```bash
python3 nav_core/tools/merge_robot_timeline.py \
  --nav-timing /path/to/nav_timing.bin \
  --nav-bin /path/to/nav.bin \
  --nav-state /path/to/nav_state.bin \
  --control-log /path/to/control_loop_xxx.csv \
  --telemetry-timeline /path/to/telemetry_timeline_xxx.csv \
  --telemetry-events /path/to/telemetry_events_xxx.csv
```

Windowed incident export:

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

## What To Look For

### Sample ordering

- `duplicates`
  - repeated `sensor_time_ns` within IMU or DVL families
- `out_of_order`
  - a sample time moved backwards relative to previously seen data

### Freshness

- `stale_flag_records`
  - records where `stale` is explicitly set
- `imu_rejected` / `dvl_rejected`
  - samples the main loop refused to use

### Latency

- `sensor_to_recv`
  - driver-side acquisition/transport delay
- `recv_to_consume`
  - main-loop backlog or scheduling delay
- `consume_to_publish`
  - currently mostly meaningful on nav publish/device-state records

### Device transitions

Look for:

- `imu_device state=...`
- `dvl_device state=...`

Common sequences:

- `CONNECTING -> ONLINE`
- `ONLINE -> RECONNECTING -> CONNECTING -> ONLINE`
- `PROBING -> MISMATCH`

### Cross-stage timeline alignment

`merge_robot_timeline.py` is the current P1 minimum closure tool.
It joins:

- `nav_timing.bin`
- `nav.bin`
- `nav_state.bin`
- control CSV
- telemetry timeline CSV
- telemetry event CSV

Use it to answer:

- did device state change before nav went invalid?
- did stale trigger in nav_viewd before control rejected Auto?
- did telemetry/UI-facing state change after control entered failsafe?

## Half-Real Validation Procedure

Current P0 validation method:

1. generate or capture `nav_timing.bin`
2. run the parser
3. confirm the report includes:
   - duplicate/out-of-order detection
   - stale rejected samples
   - device reconnect events
   - stage latency distribution

This was validated in the local environment with a synthetic trace containing:

- IMU duplicate sample
- IMU out-of-order sample
- DVL stale rejection
- IMU `CONNECTING -> ONLINE`
- DVL `RECONNECTING`
- degraded and stale `nav_published` records
- control CSV row showing Auto rejected on stale nav
- telemetry timeline and event rows showing the same transition

Observed merged timeline summary in the local fixture:

- sources: `nav_timing`, `nav_bin`, `nav_state`, `control`, `telemetry_timeline`, `telemetry_events`
- ordered transitions showed:
  - DVL sample arrival
  - IMU consume / nav publish
  - device reconnect event
  - stale rejection
  - control failsafe row
  - telemetry event + command result rows

## P1 Half-Bench Validation

This round also validated a kept fixture generated from real logger/test code paths:

- nav side
  - `test_nav_diagnostic_fixture` wrote `nav_timing.bin` and `nav_state.bin`
- control side
  - `test_control_loop_logger` wrote a real control CSV row with `failsafe=1`
- telemetry side
  - `test_telemetry_timeline_logger` wrote real timeline/event CSV files with
    `nav_fault_code=12`, `nav_status_flags=0x0600`, and `command_status=Failed`

Observed results from the merged `reconnecting` window:

- `selected_events=13`
- sources present:
  - `nav_timing`
  - `nav_state`
  - `control`
  - `telemetry_timeline`
  - `telemetry_events`
- highlighted anchors included:
  - `imu_device state=RECONNECTING`
  - telemetry rows tagged `failsafe,invalid,reconnecting,mismatch,command_failed`
  - control row tagged `failsafe,invalid,reconnecting`

Observed results from the merged `command_failed` window:

- `selected_events=7`
- sources present:
  - `telemetry_timeline`
  - `telemetry_events`
- runtime failure and command-result rows aligned within the same narrow window

## Current Limits

- this is not yet a full replay format
- there is not yet a dedicated viewer for long timelines
- `publish_mono_ns` is intentionally `0` for consumed/rejected sample records in P0;
  end-to-end replay closure belongs to P1
- `nav.bin` currently only carries processed DVL samples, not full IMU raw payloads
