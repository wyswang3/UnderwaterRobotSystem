# Nav State Contract

## 文档状态

- 状态：Authoritative
- 说明：当前生效的系统级基线文档。


## 适用范围

当前 `NavState` 真正来源于：

- `shared/msg/nav_state.hpp`
- `shared/shm/nav_state_shm.hpp`

默认 SHM 名称：

- `/rov_nav_state_v1`

## 1. 结构字段基线

当前 shared `NavState` 对外字段包括：

- `t_ns`
- `pos[3]`
- `vel[3]`
- `rpy[3]`
- `depth`
- `omega_b[3]`
- `acc_b[3]`
- `age_ms`
- `valid`
- `stale`
- `degraded`
- `nav_state`
- `health`
- `fault_code`
- `sensor_mask`
- `status_flags`

## 2. 数值字段语义

### 运动学输出

- `pos[3]`
  - 当前导航位置
- `vel[3]`
  - 当前导航速度
- `rpy[3]`
  - 当前姿态角
- `depth`
  - 深度值

### 体坐标高频量

- `omega_b[3]`
  - 当前最新 IMU 角速度测量
- `acc_b[3]`
  - 当前最新 IMU 线加速度测量

当前硬规则：

- `omega_b/acc_b` 必须表达真实可解释的 IMU 测量语义
- 不允许继续把估计器 bias 或伪正常默认值包装成可用体速度量

## 3. 状态语义字段

### 生命周期状态

`nav_state` 当前使用 `NavRunState`：

- `kUninitialized`
- `kAligning`
- `kOk`
- `kDegraded`
- `kInvalid`

### 粗粒度健康状态

`health` 当前使用 `NavHealth`：

- `UNINITIALIZED`
- `OK`
- `DEGRADED`
- `INVALID`

### 故障原因

`fault_code` 当前使用 `NavFaultCode`，典型包括：

- `kImuNoData`
- `kImuStale`
- `kNavOutputStale`
- `kImuDeviceMismatch`
- `kDvlDisconnected`

### 传感器/状态 bitmask

- `sensor_mask`
  - 当前这帧确认 fresh/usable 的传感器集合
- `status_flags`
  - 更细粒度的状态位，例如：
    - `NAV_FLAG_IMU_OK`
    - `NAV_FLAG_DVL_OK`
    - `NAV_FLAG_ALIGN_DONE`
    - `NAV_FLAG_IMU_BIND_MISMATCH`
    - `NAV_FLAG_IMU_RECONNECTING`

## 4. 发布规则

当前应遵守：

1. `valid=1` 才表示该帧可被下游当作可信导航使用。
2. `stale=1` 时，即使数值字段非零，也不能被当作新鲜状态。
3. `degraded=1` 表示“受限可用”，不是“等同 OK”。
4. `age_ms` 必须来自语义状态时间，不是发布线程当前时间随手重置。
5. `nav_state`、`health`、`fault_code` 必须与 `valid/stale/degraded` 保持一致。

## 5. 消费规则

控制和下游消费者必须先看：

1. `valid`
2. `stale`
3. `degraded`
4. `nav_state`
5. `fault_code`
6. `status_flags`

然后才看数值字段。

明确禁止：

- 根据非零 `pos/vel/rpy` 推断导航可信
- 只根据 `health==OK` 推断控制可直接使用
- 忽略 `fault_code/status_flags` 做布尔折叠

## 6. ABI 与 SHM 规则

当前 `NavState` 契约要求：

- trivially copyable
- standard-layout/POD 风格传输
- SHM header 使用：
  - magic: `NAV1`
  - layout version: `1`
  - payload version: `2`

任何 ABI 变更都必须同步影响：

- nav 发布侧
- gateway 订阅侧
- control 消费侧
- 对应文档和兼容性矩阵

## 7. 文档漂移说明

旧版文档中如果还写着：

- `pos_ned`
- `vel_ned`
- `quat_nb`

那已经和当前 shared `NavState` 不一致。

当前真实契约只公开：

- `pos[3]`
- `vel[3]`
- `rpy[3]`

并没有在 shared `NavState` 中继续公开四元数字段。
