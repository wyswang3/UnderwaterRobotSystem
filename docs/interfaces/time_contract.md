# Time Contract

## Current P0 Baseline

This baseline uses one monotonic time axis end-to-end for freshness, stale checks,
cross-hop age accumulation, and replay ordering.

- `sensor_time_ns`
  - the sample timestamp itself
  - expressed on the monotonic/steady timeline used by navigation
  - if hardware does not expose a device timestamp yet, driver code may backfill it
    with a latency-corrected estimate
- `recv_mono_ns`
  - when the driver thread decoded/accepted the sample
- `consume_mono_ns`
  - when the nav main loop actually accepted and used the sample
- `mono_ns`
  - canonical monotonic sample timestamp used by estimator ordering and freshness
  - must match `sensor_time_ns` in the current baseline
- `est_ns`
  - legacy compatibility field
  - current baseline requires it to mirror `mono_ns`
  - it must not be interpreted as UNIX wall-clock time

## State-Level Semantics

- `NavState.t_ns`
  - semantic state timestamp
  - the fused state corresponds to this time, not to the publish thread time
- `NavState.age_ms`
  - cumulative age of `t_ns` at nav publish time
- `NavStateView.stamp_ns`
  - forwarded semantic nav state timestamp
- `NavStateView.mono_ns`
  - gateway publish time for that hop
- `NavStateView.age_ms`
  - cumulative age after the gateway hop
- `TelemetryFrameV2.stamp_ns`
  - control-core publish timestamp for that telemetry frame
- `TelemetryFrameV2.system.nav_age_ms`
  - cumulative nav age seen by control after local SHM consumption

## Main-Thread Freshness Rules

The nav main loop now uses sensor timing explicitly instead of “latest sample exists”.

- IMU/DVL freshness is checked from `now_mono_ns - sensor_time_ns`
- main loop only consumes strictly newer samples
- duplicate samples and out-of-order samples are dropped
- `consume_mono_ns` is filled only when the main loop actually accepts the sample
- `NavState.valid/stale/degraded` is derived from consumed sample timing, not merely
  from driver arrival timing

## Unified Stale Rule

All stale decisions in the P0 baseline follow the same rule:

1. sample freshness uses `sensor_time_ns`
2. state age uses `publish_mono_ns - stamp_ns`
3. downstream hops add their local transport/read delay to inherited `age_ms`
4. no hop may silently reset `age_ms` to zero while forwarding the same state

This means a late-arriving sample can still be stale even if `recv_mono_ns` and
`consume_mono_ns` are recent.

## Logging Baseline

Navigation now writes a timing trace file `nav_timing.bin` that records:

- sample time
- driver receive time
- main-loop consume time
- nav publish time
- cumulative age and fault summary

This is not the full replay/logging closure yet. It is the minimum P0 trace needed
to explain delayed samples, stale propagation, and state publication timing.

## Telemetry and UI Rules

- UI link age uses local status-packet receive time only
- UI must not render `est_ns`, `t_ns`, or `stamp_ns` as calendar time
- UI/state consumers must treat `nav_age_ms`, `nav_valid`, `nav_stale`,
  `nav_degraded`, and `nav_state` as the authoritative navigation freshness summary

## Remaining Time Debt

- `NavState.t_ns` still carries legacy naming debt and should become `stamp_ns`
  in a later compatibility pass
- `est_ns` still exists in nav/control internals and needs a dedicated deprecation plan
- hardware-origin timestamps for IMU/DVL are not available yet, so `sensor_time_ns`
  is still estimated from host receive time plus configured latency when needed
- wall/epoch alignment is still out of scope for P0 and must not be mixed into stale logic
