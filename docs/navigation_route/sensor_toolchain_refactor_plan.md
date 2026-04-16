# Sensor Toolchain Refactor Plan

## 文档状态

- 状态：Working draft
- 说明：当前设计方向或阶段性方案已冻结，但尚未全部实施。


## 1. 文档目标

本文档用于冻结“导航侧 Python 三传感器工具链去屎山化”设计边界。

本文档聚焦以下范围：

- IMU 工具链
- DVL 工具链
- Volt32 / 第三传感器工具链
- 读取、解析、时间戳、记录、目录与配置的公共抽象

本文档明确不做：

- 改写 `uwnav_navd` 的在线 IMU / DVL authority 主链
- 把三传感器 Python 工具链升级成新的线上导航 authority
- 一次性重命名或推倒所有现有脚本

## 2. 设计原则

### 2.1 核心原则

1. 在线 control / nav authority 继续留在 C/C++ 主链。
2. Python 工具链只负责采集、验证、日志、后处理和非实时辅助。
3. 先收边界和重复逻辑，再逐步替换脚本内部实现。
4. 兼容现有脚本入口，避免现场工作流立刻失效。

### 2.2 为什么这样设计

原因不是“Python 不行”，而是当前项目的稳定性约束已经很明确：

- 在线 IMU / DVL 主链已经在 `uwnav_navd` 中形成 authority 路径
- Python 侧更适合承担采集工具链、数据验证和日志导出
- 若为了“整合”把 authority 再搬回 Python，只会扩大时间语义和设备重连风险

## 3. 当前三传感器链路现状

### 3.1 IMU 链路

当前主要入口：

- `apps/acquire/imu_logger.py`
- `apps/tools/imu_data_verifier.py`
- `uwnav/sensors/imu.py`

当前链路：

```text
串口打开
  -> IMUReader / DeviceModel
  -> 回调入队
  -> 后台线程消费
  -> RealTimeIMUFilter
  -> callback
  -> raw/filt/timebase CSV
```

当前职责分布：

- 串口打开：`uwnav/sensors/imu.py`
- 线程 / 循环读取：`uwnav/sensors/imu.py`
- 解析与滤波：`uwnav/sensors/imu.py` + vendor model
- 时间戳：脚本层 `stamp("imu0", SensorKind.IMU)`
- CSV 落盘：一部分在 `imu.py`，一部分在脚本层
- 目录组织：脚本层自行处理
- 配置读取：脚本参数和模块默认值混用

当前问题：

1. 设备生命周期、滤波、回调、CSV 落盘揉在一个模块里。
2. 脚本层和模块层都能写日志，职责重复。
3. 路径与目录逻辑没有统一收口。

### 3.2 DVL 链路

当前主要入口：

- `apps/acquire/DVL_logger.py`
- `apps/tools/dvl_data_verifier.py`
- `uwnav/drivers/dvl/hover_h1000/io.py`
- `uwnav/drivers/dvl/hover_h1000/protocol.py`

当前链路：

```text
串口打开
  -> DVLSerialInterface 读线程
  -> 原始帧回调
  -> protocol 解析
  -> parsed 回调
  -> raw/parsed/minimal CSV
```

当前职责分布：

- 串口打开：`io.py`
- 线程 / 循环读取：`io.py`
- 解析：`protocol.py`
- 时间戳：脚本层 `stamp("dvl0", SensorKind.DVL)`
- CSV 落盘：`io.py` 和脚本层并存
- 目录组织：脚本层自行处理
- 配置读取：脚本参数、命令序列和模块默认值混用

当前问题：

1. `io.py` 同时承担 transport、command、callback、logger、数据类等职责。
2. 启停命令序列和采集逻辑混在脚本里，不利于复用。
3. 原始日志、解析日志和 timebase 记录没有统一抽象。

### 3.3 Volt32 / 第三传感器链路

当前主要入口：

- `apps/acquire/Volt32_logger.py`
- `apps/tools/volt32_data_verifier.py`
- `uwnav/drivers/imu/WitHighModbus/serial_io_tools.py`

当前链路：

```text
串口打开
  -> SerialReaderThread
  -> 文本行回调
  -> 脚本内解析 CHx:value
  -> 通道聚合
  -> timebase 打点
  -> rolling CSV
```

当前职责分布：

- 串口打开：复用 `serial_io_tools.py`
- 线程 / 循环读取：复用 `serial_io_tools.py`
- 解析：脚本内直接解析
- 时间戳：脚本层 `stamp("volt0", SensorKind.OTHER)`
- CSV 落盘：脚本自带 `RollingCSVWriter`
- 目录组织：脚本层自行处理
- 配置读取：脚本参数和默认值混用

当前问题：

1. Volt32 还没有自己的驱动边界，脚本承担了准运行时职责。
2. 通用串口线程藏在 IMU vendor 目录里，层次不对。
3. 通道聚合和落盘都难以复用。

## 4. 当前重复逻辑清单

三个传感器工具链存在以下重复逻辑：

1. 串口打开与后台读取线程
2. 设备异常时的停止 / 退出逻辑
3. `stamp(...)` 时间戳打点
4. CSV 文件打开、滚动、flush
5. 日期目录和输出目录组织
6. 脚本参数解析与默认值回填
7. raw 与 parsed 两类记录的命名和字段拼接
8. 采集开始 / 停止 / 错误事件的文本输出

结论：

- 当前真正需要重构的不是“算法”，而是工具链的公共外壳
- 若不先提炼公共外壳，后续每加一个传感器都会继续复制一套屎山

## 5. 目标边界设计

### 5.1 保留不动的部分

以下部分应继续保留各自职责：

- `uwnav_navd` 在线 IMU / DVL authority 主链
- 传感器专属 parser 逻辑
- 传感器专属安全命令序列
- `uwnav/io/timebase.py`
- `uwnav/io/data_paths.py`

### 5.2 优先提炼为公共模块的部分

建议新增或收敛以下公共模块：

1. `serial_transport`
2. `record_writer`
3. `timestamped_record`
4. `sensor_launcher_config`
5. `parser boundary`

设计意图如下。

#### serial_transport

职责：

- 打开 / 关闭串口
- 后台读线程或轮询循环
- 错误回调
- 统一 stop / join 行为

为什么要抽：

- IMU、DVL、Volt32 都在重复“打开串口 + 读线程 + 退出”框架
- 这个层只处理字节或文本，不处理业务解析

#### record_writer

职责：

- 统一 CSV / 文本事件文件创建
- 统一 header 写入、滚动、flush、跨天切分
- 统一 raw / parsed / events 三类文件命名

为什么要抽：

- 目前每个脚本都在各自维护 writer，字段与轮转策略不统一
- 日志统一设计无法落地到三个传感器工具链

#### timestamped_record

职责：

- 统一 `mono_ns`、`est_ns`、`sensor_id`、`record_kind`
- 形成最小结构化记录包络
- 供 raw、parsed、event 三类 writer 共用

为什么要抽：

- 当前 timebase 语义一致，但记录封装不一致
- 后续要接 incident bundle 和后处理工具时，缺少统一外壳

#### sensor_launcher_config

职责：

- 统一脚本输入参数和默认值
- 统一设备路径、波特率、输出目录、是否写 raw、是否写 parsed、滚动大小等配置

为什么要抽：

- 当前同一类参数在多个脚本里重复定义
- 现场启动脚本和 tmux 管理器都难以收敛

#### parser boundary

职责：

- 明确 parser 只接收“原始字节 / 原始行”并返回结构化数据或错误
- transport 不做 parser 语义推断
- record writer 不关心 parser 细节

为什么要抽：

- 现在 DVL、Volt32 的 transport 与 parser 边界不干净
- 不收 parser 边界，后续只会继续把 logger、command、transport 糊在一起

## 6. 目标目录结构建议

本轮不要求立刻整体搬家，但建议以后按以下结构收敛：

```text
apps/
  acquire/
    imu_capture.py
    dvl_capture.py
    volt_capture.py
    sensor_capture_launcher.py
  tools/
    multisensor_postproc.py
    dvl_safety_probe.py
    imu_baud_switch.py
    imu_xy_zero.py

uwnav/
  io/
    timebase.py
    data_paths.py
    serial_transport.py
    record_writer.py
    timestamped_record.py
    sensor_launcher_config.py
  drivers/
    imu/
      wit/
        device_model.py
        filters.py
        parser_adapter.py
    dvl/
      hover_h1000/
        command.py
        parser.py
        session.py
    volt32/
      parser.py
      aggregator.py
  sensors/
    imu_capture_runtime.py
    dvl_capture_runtime.py
    volt_capture_runtime.py
```

说明：

- `apps/acquire/*.py` 保留为薄入口，只负责参数解析和装配。
- `uwnav/io/` 放通用能力，不再把通用串口线程埋在 vendor 目录。
- `uwnav/drivers/*` 只保留设备专属协议、命令、parser。
- `uwnav/sensors/*_capture_runtime.py` 负责把 transport、parser、writer 装起来。

## 7. 模块职责划分建议

### 7.1 入口脚本

入口脚本只做：

1. 解析命令行
2. 读取 `sensor_launcher_config`
3. 调用对应 runtime
4. 打印启动摘要

入口脚本不再做：

1. 自己维护线程
2. 自己拼 CSV header
3. 自己实现 rolling policy
4. 自己处理复杂 parser 逻辑

### 7.2 Capture runtime

每个传感器一个 runtime 组装层，职责是：

- 创建 transport
- 创建 parser
- 创建 raw / parsed / event writer
- 执行时间戳打点
- 负责 clean shutdown

这样做的原因：

- 运行期装配逻辑仍然是传感器特定的
- 但 transport、writer、timebase 可以统一

### 7.3 Parser

parser 只做：

- 原始输入合法性检查
- 结构化字段提取
- parse error 分类

parser 不做：

- 打开串口
- 写文件
- 创建目录
- 业务级重试策略

### 7.4 Writer

writer 只做：

- 写盘
- 文件滚动
- flush
- 命名与目录组织

writer 不做：

- parse 逻辑
- 串口控制
- 数据转换推断

## 8. 兼容性迁移策略

为避免现场脚本立刻失效，建议按兼容模式迁移：

1. 保留现有脚本文件名。
2. 先让现有脚本内部改为调用新模块。
3. 等现场工作流稳定后，再视情况补新的 `*_capture.py` 名称。
4. 旧路径在一个版本周期内保留 thin wrapper。

## 9. 与统一拉起方案的关系

三传感器工具链不应默认并入车载 authority 主启动链。

建议分成两种模式：

### 9.1 authority runtime mode

只拉起：

- `uwnav_navd`
- `nav_viewd`
- `pwm_control_program`
- `gcs_server`

适用于：

- 正式运行
- 控制与导航联调
- 客户演示主链

### 9.2 sensor capture mode

在 authority runtime 之外，按需拉起：

- IMU capture tool
- DVL capture tool
- Volt32 capture tool
- multisensor postproc

适用于：

- 采样建模
- 设备调试
- 池试记录
- 故障复盘补采样

这样设计的原因：

- 三传感器工具链的目标是“观测和记录”
- 不是替代 `uwnav_navd` 变成新的 authority 链

## 10. 本轮不建议立即改动的点

1. 不建议立即重写 IMU vendor 驱动内部实现。
2. 不建议立即把 DVL `protocol.py` 大改成全新协议栈。
3. 不建议立即把所有 CSV 一次性换成统一二进制格式。
4. 不建议立即删除现有入口脚本。
5. 不建议在没有 runbook 配套前改变现场默认使用方式。

## 11. 最小验收标准

后续进入实现阶段时，建议按以下标准验收：

1. IMU / DVL / Volt32 三条工具链仍可独立启动。
2. 新旧脚本入口均能生成与当前等价的数据集。
3. 公共模块覆盖串口、写盘、时间戳、目录和配置五类重复逻辑。
4. Volt32 不再依赖 IMU vendor 目录中的通用串口线程。
5. DVL transport、parser、writer 边界清晰，不再由单个 `io.py` 承担全部职责。
6. 本轮实现不得影响 `uwnav_navd` 的在线 authority 主链。
