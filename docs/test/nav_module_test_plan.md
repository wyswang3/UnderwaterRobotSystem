# 导航模块测试计划

## 目标

测试计划围绕三类高风险问题设计：

1. IMU 串口跳变与重连
2. 传感器缺失、时间戳过期、未初始化下的状态语义
3. 日志、SHM、控制侧读取的一致性

## 本轮已执行

已新增并执行：

- `nav_core_test_nav_runtime_status`
  - 覆盖冷启动未初始化
  - 覆盖 ALIGNING 不再输出 `valid=1`
  - 覆盖 IMU stale -> `INVALID`
  - 覆盖 DVL 缺失 -> `DEGRADED`
- `gateway_test_nav_view_builder`
  - 覆盖 invalid NavState 不再向控制面暴露旧 payload
  - 覆盖 degraded NavState 的语义透传
- `pwmctrl_test_v1_closed_loop`
  - 覆盖 Guard 拒绝 `ALIGNING` Auto
  - 覆盖 Guard 允许 `DEGRADED` 但健康的 Auto
- `pwmctrl_test_nav_view_shm_source`
  - 覆盖 SHM source 不再把 invalid/stale 折叠成 no-data
  - 覆盖控制侧本地 age 超预算后强制置 stale

说明：

- `pwmctrl_test_nav_view_shm_source` 在默认沙箱里因为 POSIX SHM 创建权限受限失败
- 在非沙箱环境重跑后通过，因此该测试结果有效，但运行环境要求需在文档中注明

## 1. 单元测试建议

### 1.1 IMU 设备发现

新增测试点：

- 单一稳定路径打开成功
- 主路径不存在时，能否切换到候选路径
- 设备存在但属性不匹配时拒绝绑定
- 打开成功但长时间无有效帧时返回明确错误

建议实现方式：

- 抽象 `SerialPortEnumerator`
- 用 fake `/dev` 清单和 fake 设备属性做单测

### 1.2 ESKF 输入完整性

新增测试点：

- `last_propagate_time == 0` 时 `NavState` 不能被标记为 valid`
- IMU 缺失时 `health/fault_code` 正确
- DVL 缺失时进入 degraded，不是静默继续 OK
- 时间戳倒退或 dt 超界时不输出有效导航状态
- 非有限数值出现时进入 invalid

### 1.3 NavView 构建与控制侧消费

新增测试点：

- `NavState.nav_state in {kUninitialized,kAligning,kInvalid}` 时 `NavStateView.valid==0`
- `status_flags` 能从 `NavState -> NavStateView -> ControlState` 正确透传
- `stale`、`invalid` 和 `no-data` 不会再被错误折叠成同一类输入

## 2. 集成测试建议

### 2.1 IMU 串口跳变模拟

目标：

- 验证 `/dev/ttyUSB0` 断开后重枚举成 `/dev/ttyUSB1` 时系统表现

建议方法：

- 使用 `pty` 或 USB 串口仿真器模拟两个端口
- 启动后先把数据源绑定到 `ttyUSB0`
- 运行中关闭 `ttyUSB0` 并把同一设备身份切到 `ttyUSB1`

期望结果：

- 日志记录旧端口失效
- 状态切到 `degraded` 或 `invalid`
- 若启用重发现，应自动绑定新端口
- 恢复后给出恢复事件日志

### 2.2 传感器缺失/时间戳过期

场景矩阵：

- IMU 全缺失
- DVL 全缺失
- 深度计全缺失
- IMU 正常但 DVL 长时间无更新
- 传感器时间戳冻结
- 传感器时间戳突跳

期望结果：

- 不允许继续输出“合法 0 状态”
- `health/valid/stale/fault_code` 必须与场景一致
- 控制模块必须能识别不可用原因

### 2.3 NavState valid/stale/fault 行为

建议覆盖：

- 初始启动阶段
- 对准未完成
- 正常运行
- DVL 降级
- IMU 失效
- SHM 中断

检查项：

- `NavState`
- `NavStateView`
- 控制侧 `ControlState`
- 遥测中的 `nav_valid/nav_health/nav_stale/nav_state`

本轮已完成最小覆盖：

- `NavState` 状态机单测
- `NavViewBuilder` 语义单测
- `NavViewShmSource` stale/invalid SHM 行为单测
- `ControlGuard` Auto 保护单测

## 3. 控制保护测试建议

### 3.1 控制侧无效导航保护

场景：

- `valid=0`
- `stale=1`
- `fault_code!=0`
- `ESKF_OK` 缺失

期望：

- Auto 模式拒绝使用导航闭环
- 模式降级逻辑被触发
- 遥测记录明确原因

### 3.2 旧快照保护

场景：

- `nav_viewd` 遇到 stale/no-data 时发布显式 invalid 诊断帧

期望：

- 控制器不得使用旧 payload 继续闭环
- stale 诊断帧的运动学 payload 必须清空
- 日志要能区分“桥接层 stale”和“导航源本身 invalid”

## 4. 日志一致性测试

### 4.1 事件与状态一致性

检查以下事件是否都能在日志中看到：

- 设备发现
- 设备打开失败
- 设备身份不匹配
- 传感器超时
- 初始化完成
- 进入降级
- 恢复正常
- SHM 发布失败

### 4.2 日志与 SHM 时间戳一致性

检查：

- `NavState.stamp_ns`
- SHM header `mono_ns`
- `NavStateView.stamp_ns`
- 控制侧 `age_ms_local`

要求：

- 各字段语义一致
- 能用脚本回放出完整时间线

## 5. 回放测试建议

建议建立最小回放工具，支持：

- 回放 IMU 原始帧
- 回放 DVL 原始帧
- 注入缺测、延迟、乱序、串口断开事件
- 记录生成的 `NavState/NavStateView`

回放用例至少包括：

- 冷启动无 IMU
- 冷启动有 IMU 无 DVL
- DVL 中途掉线
- IMU 中途掉线
- IMU 设备路径跳变

## 6. 落地顺序

### P0

- 先补导航状态机测试
- 再补控制保护测试
- 最后补串口跳变模拟测试

### P1

- 增加日志一致性测试
- 增加 SHM 版本兼容测试

### P2

- 建立标准化回放数据集
- 接入 CI 夜间回放
