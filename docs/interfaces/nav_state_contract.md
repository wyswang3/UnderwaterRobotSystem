# Nav State Contract

## NavState Core Semantics

- `pos_ned`, `vel_ned`, `rpy`, `quat_nb`
  - estimator nominal state
- `omega_b`, `acc_b`
  - latest measured body-frame IMU angular velocity and linear acceleration
  - must not contain estimator bias terms
- `valid`
  - `1` only when the nav snapshot is trusted for downstream consumers
- `stale`
  - `1` when semantic age exceeded allowed freshness limits
- `degraded`
  - `1` when nav remains publishable but with reduced sensor support or health
- `fault_code`
  - explicit reason why nav is invalid or degraded

## Runtime State Ladder

- `UNINITIALIZED`
  - no trustworthy IMU path yet
- `ALIGNING`
  - IMU path present but alignment/bias readiness incomplete
- `OK`
  - trusted nav, usable by control
- `DEGRADED`
  - usable with restrictions
- `INVALID`
  - must not be consumed as trusted control input

## P0 Change

As of nav commit `1402cd7`, `omega_b/acc_b` are sourced from the latest IMU sample
when available and zeroed otherwise. This closes the prior pseudo-normal output
path where ESKF bias values were exported as body kinematics.
