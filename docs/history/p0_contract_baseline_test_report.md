# P0 Contract Baseline Test Report

## Build Verification

### Navigation

- configure:
  - `cmake -S Underwater-robot-navigation/nav_core -B /tmp/uwsys-nav-p0-build -DNAV_CORE_BUILD_TESTS=ON`
- built targets:
  - `uwnav_navd`
  - `test_nav_runtime_status`
- result: passed

### Control / Gateway

- configure:
  - `cmake -S OrangePi_STM32_for_ROV -B /tmp/uwsys-control-p0-build -DROV_BUILD_TESTS=ON -DPWMCTRL_BUILD_TESTS=ON`
- built targets:
  - `pwm_control_program`
  - `test_session`
  - `test_v1_closed_loop`
- result: passed

### GCS

- syntax check:
  - `python3 -m py_compile ...`
- unit tests:
  - `PYTHONPATH=src python3 -m unittest discover -s tests`
- result: passed

## Test Cases Added / Strengthened

- nav body kinematics use latest IMU sample
- nav body kinematics zero when no IMU sample is available
- gateway status adapter exposes authoritative runtime status fields
- GCS codec decodes new authoritative status layout
- GCS codec remains backward-compatible with legacy compact status payload
- GCS dashboard/alarm layer reflects remote nav/failsafe/command-result state

## Known Gaps

- no automated regression yet for `nav_viewd` stale propagation
- no automated regression yet for device reconnect and USB re-enumeration
- no control-loop harness yet that directly proves the removed demo override path
- no replay test closure yet
