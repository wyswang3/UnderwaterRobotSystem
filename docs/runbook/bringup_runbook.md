# Bring-up Runbook

## Current P0 Bring-up Order

1. start nav daemon and confirm `NavState` starts at `UNINITIALIZED/ALIGNING`
2. start `nav_viewd`
3. start `pwm_control_program`
4. start gateway `gcs_server`
5. start GCS/TUI

## Operator Checks

- remote session established and link alive
- remote `armed=0` after startup
- remote `mode` is explicit and not inferred from UI default
- nav state is visible as `Invalid/Aligning/Ok/Degraded`
- no command is treated as applied until remote status confirms it

## Current Limitation

This runbook does not yet cover device rebinding or log replay. Those belong to
later P0/P1 work.
