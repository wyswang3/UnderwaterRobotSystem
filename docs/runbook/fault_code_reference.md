# Fault Code Reference

## Control Fault Codes In Telemetry

Current shared fault codes of interest for UI and telemetry:

- `0`: none
- `1`: comm fault
- `2`: session fault
- `3`: intent stale
- `4`: nav untrusted
- `5`: PWM link down
- `6`: STM32 link down
- `7`: illegal state transition
- `8`: arm precondition failed
- `9`: motor test violation
- `10`: config error
- `11`: controller unavailable
- `12`: controller compute failed
- `13`: PWM step failed

## UI Rule

When `fault_state=1`, the UI must display both the summary fault flag and the
numeric `last_fault_code`. Do not collapse them into a single generic "fault".
