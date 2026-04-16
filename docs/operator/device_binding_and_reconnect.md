# Device Binding And Reconnect

## P0 Current Behavior

`uwnav_navd` no longer treats IMU/DVL as one-shot fixed-port startup dependencies.
The nav main loop now owns a device binder per sensor and supervises:

- stable-path preference
- candidate scan fallback
- identity mismatch rejection
- offline timeout detection
- reconnect backoff and reprobe

## Binding Priority

For both IMU and DVL, the binder resolves ports in this order:

1. configured primary path in `imu.driver.port` / `dvl.driver.port`
   - prefer `/dev/serial/by-id/...` or a dedicated udev symlink
2. configured `binding.candidate_paths`
3. auto-discovered `/dev/serial/by-id/*`
4. auto-discovered `/dev/ttyUSB*` and `/dev/ttyACM*`

## Identity Rules

The binder accepts a device only when the configured identity constraints pass.
Supported constraints:

- `expected_by_id_substring`
- `expected_vid`
- `expected_pid`
- `expected_serial`

If multiple serial devices exist and no identity rule is configured, the binder
refuses auto-binding and enters `MISMATCH` instead of guessing.

## Device States

Current state machine:

- `DISCONNECTED`
  - no matching device found
- `PROBING`
  - scanning `/dev` and `/sys`
- `CONNECTING`
  - a candidate path has been selected and driver init/start is in progress
- `ONLINE`
  - driver is running and the binder trusts the active path
- `MISMATCH`
  - serial devices exist but the identity rules reject them, or binding is ambiguous
- `ERROR_BACKOFF`
  - connect attempt failed; wait `reconnect_backoff_ms` before probing again
- `RECONNECTING`
  - previously online device stopped producing frames or lost its port; reprobe after backoff

## Fault Exposure

The binder state is published into nav semantics in two places:

- `NavState.fault_code`
  - IMU missing/mismatch/disconnect maps to explicit IMU fault codes
- `NavState.status_flags`
  - `NAV_FLAG_IMU_DEVICE_ONLINE`
  - `NAV_FLAG_DVL_DEVICE_ONLINE`
  - `NAV_FLAG_IMU_BIND_MISMATCH`
  - `NAV_FLAG_DVL_BIND_MISMATCH`
  - `NAV_FLAG_IMU_RECONNECTING`
  - `NAV_FLAG_DVL_RECONNECTING`

These then flow through:

- `NavState -> NavStateView`
- `NavStateView -> ControlLoop`
- `TelemetryFrameV2 -> GCS/UI`

## Runtime Supervision

### IMU

The main loop transitions IMU from `ONLINE` to `RECONNECTING` when:

- driver thread stopped
- serial port closed
- no IMU frame arrives within `binding.offline_timeout_ms`

On IMU connectivity change, nav does a conservative reset:

- clear cached IMU/DVL freshness
- reset IMU preprocessor
- reset ESKF to configured initial state
- require alignment again before publishing `valid=1`

### DVL

The main loop transitions DVL from `ONLINE` to `RECONNECTING` when:

- driver thread stopped
- serial port closed
- no DVL frame arrives within `binding.offline_timeout_ms`

On DVL connectivity change:

- clear cached DVL freshness
- keep IMU/ESKF running
- nav falls back to degraded semantics until DVL is fresh again

## Recommended Config Pattern

Example IMU binding fragment:

```yaml
imu:
  driver:
    port: "/dev/serial/by-id/usb-IMU_MAIN"
    binding:
      candidate_paths:
        - "/dev/imu_main"
        - "/dev/ttyUSB0"
      expected_by_id_substring: "IMU_MAIN"
      expected_vid: "10c4"
      expected_pid: "ea60"
      expected_serial: "imu-001"
      offline_timeout_ms: 1000
      reconnect_backoff_ms: 500
```

## Validation Checklist

- unplug sensor and confirm `ONLINE -> RECONNECTING`
- plug the same device back on a different tty number and confirm reprobe succeeds
- plug a wrong USB-serial adapter and confirm `MISMATCH`
- verify `nav_timing.bin` contains `*_device_state` records for the transition
- verify control/GCS show the resulting nav invalid/degraded state rather than stale old data

## P1 Integrated Validation

This round adds two concrete validation layers:

1. PTY-backed driver integration
   - `nav_core_test_serial_reconnect_integration`
   - IMU covers:
     - wrong device first
     - correct device selected later
     - runtime disconnect via PTY EOF
     - node/path change on reconnect
   - DVL covers:
     - real PD6 line ingress over PTY
     - runtime disconnect via PTY EOF
     - reconnect on a new PTY path

2. Control-side pipeline validation
   - `pwmctrl_test_nav_reconnect_pipeline`
   - verifies:
     - device reconnect fault reaches `NavStateView`
     - `nav_viewd` stale policy publishes explicit diagnostic invalid
     - `ControlGuard` rejects Auto when reconnect/stale nav is present
     - telemetry stays aligned with the control decision

## Runtime Disconnect Semantics

Driver loops now treat serial `read()==0` as a real disconnect instead of a benign no-data case.

This matters because PTY close and many USB re-enumeration paths surface as EOF first.
Without this rule the binder would keep seeing an old fd as open and the system would lag before entering `RECONNECTING`.

## Remaining Limits

- hardware-origin timestamps are still not available; device binding is identity-safe,
  but sample time is still host-derived
- there is no automated real-hardware USB re-enumeration test in CI yet
- DVL startup still depends on protocol-level success after bind; binder only proves
  “this is the intended serial device”
