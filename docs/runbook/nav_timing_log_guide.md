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

## Current Limits

- this is not yet a full replay format
- there is not yet a dedicated viewer for long timelines
- `publish_mono_ns` is intentionally `0` for consumed/rejected sample records in P0;
  end-to-end replay closure belongs to P1
