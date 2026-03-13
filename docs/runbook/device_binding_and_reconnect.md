# Device Binding And Reconnect

## Current State

This is still an open P0 item.

- IMU and DVL binding are not yet fully hardened by stable identity
- USB re-enumeration risk remains
- reconnect state machine and hard-fault behavior are not yet standardized

## Required End State

- stable path preference, e.g. `/dev/serial/by-id`
- VID/PID/serial verification
- mismatch => hard-fault and clear operator-visible status
- explicit reconnect states: `DISCONNECTED`, `DISCOVERING`, `BOUND`, `FAULT`

## Until Implemented

Treat device path changes as unsafe events and require manual verification before
trusting nav again.
