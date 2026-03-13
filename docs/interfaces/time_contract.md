# Time Contract

## Baseline Definitions

- `stamp_ns`
  - semantic timestamp of the state or command itself
  - for nav and telemetry, this is the state sample time carried through the hop
- `mono_ns`
  - publisher-local monotonic timestamp captured when a process publishes or copies
    a snapshot into SHM
- `est_ns`
  - estimator-derived measurement time inside nav processing
  - current implementation must be treated as monotonic-domain sample time, not as
    UNIX wall-clock time
- `age_ms`
  - consumer-visible age of the semantic state relative to `stamp_ns`
  - must not silently reset to zero when the same state is forwarded across hops

## Required Usage Rules

- stale checks must be based on monotonic time deltas, never wall clock
- UI link age should be based on local receive time of status packets
- UI must not display `t_ns` or `est_ns` as real-world calendar timestamps
- replay tooling must preserve `stamp_ns` and per-hop publish times separately

## Current P0 Alignment

- GCS/TUI now displays local telemetry receive age using local monotonic time
- gateway `StatusTelemetry.t_ns` carries the control telemetry `stamp_ns`
- the naming debt around `est_ns` remains and must be cleaned up in a later P0/P1
  pass
