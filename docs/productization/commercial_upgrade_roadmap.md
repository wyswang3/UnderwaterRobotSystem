# Commercial Upgrade Roadmap

## 文档状态

- 状态：Working draft
- 说明：面向后续商业化收口的升级路线参考，整理“从当前工程态走向可交付产品”所需的关键能力、建议顺序与验收口径。

## 1. 目标定义

当前项目已经具备：

1. 控制、导航、执行主链的基本工程基线。
2. `control_only` / `bench` 两类 bring-up 路径。
3. TUI 主遥控入口、GUI 只读观察入口、incident bundle / replay / compare 工具链。

但若要进一步压缩成“可操作、可销售、可维护”的商业化交付包，还需要把目标从“工程联调平台”提升为：

1. 新用户按文档能完成最小安装、启动、连接、停机。
2. 操作员能分辨当前到底是 dummy backend 还是真实 STM32 输出。
3. 常见故障能在 5 到 10 分钟内定位到网络、导航、控制、STM32 或电源侧。
4. 版本升级不会轻易打破 shared 契约、启动顺序和操作语义。
5. 交付物可以在最小培训下被重复部署、重复验证和重复复盘。

## 2. 当前商业化阻塞点

### 2.1 operator path 仍偏工程人员口径

当前虽然已有最短命令卡，但仍然存在：

1. helper / 原始命令 / 手工启动三套入口并存。
2. dummy backend 与 real STM32 output 容易被误解。
3. 部分判断仍依赖阅读 child logs、源码注释或历史经验。

### 2.2 现场故障仍缺更直接的结构化判据

当前 operator 能看到：

1. `status --json`
2. GUI/TUI 低频状态
3. PWM / telemetry / nav / bundle 日志

但离真正的商业交付还缺：

1. 更明确的“链路断点”表达。
2. GCS 指令是否进入 `gcs_server`、是否进入 `pwm_control_program`、是否进入 STM32 的统一判据。
3. 可直接交给非开发者使用的故障树。

### 2.3 交付基线仍不够“单文件化”

未来若要把项目压缩成一个可操作性交付入口，需要进一步收敛：

1. 默认 profile
2. 默认启动顺序
3. 默认日志出口
4. 默认网络参数和配置覆盖方式
5. 默认验证清单

否则交付给客户时，仍会被解释为“需要工程师陪同才能操作”的系统。

## 3. 后续升级主题

### 3.1 Theme A: 单一操作入口与一页式交付口径

目标：

1. 把当前多份命令卡进一步收敛成一个对外可交付的入口文件。
2. 把默认路径、升级路径、风险边界写成固定模板。

建议实现内容：

1. 固定一个主入口脚本或主入口文档，统一：
   - 默认 `control_only`
   - 真实 PWM 放权条件
   - TUI / GUI 分工
   - bring-up / stop / bundle 顺序
2. 把“dummy backend”和“real STM32 output”做成 operator 必看字段：
   - CLI 启动时打印
   - status JSON 固定字段
   - GUI/TUI 至少有低频提示
3. 固定一页式交付内容：
   - 快速启动
   - 快速停机
   - 快速判障
   - 快速导出 bundle

验收标准：

1. 新人无需读源码即可完成最小联调。
2. 不会再出现“以为已经打到 STM32，实际仍是 dummy”的误判。

### 3.2 Theme B: command / comm / stm32 observability 收口

目标：

1. 把“命令到了哪里”做成可直接回答的问题。

建议实现内容：

1. 完成 `comm_events.csv` 最小落地。
2. 增加 `gcs_server` 到 `pwm_control_program` 的命令链低频关联字段。
3. 在 `pwm_control_program` 或 `orangepi_send` 输出中固定：
   - target STM32 IP/port
   - backend mode
   - heartbeat tx/ack
   - 最近一次发送失败原因
4. 明确“有 PWM 日志”与“STM32 已收包”之间的语义差别。

验收标准：

1. 一次联调失败后，能明确判断问题停在：
   - GCS 未发出
   - `gcs_server` 未注入
   - `pwm_control_program` 未接收
   - `orangepi_send` 未发送
   - STM32 未 ACK

### 3.3 Theme C: 交付配置基线与 profile 产品化

目标：

1. 把 profile 从工程测试概念收敛成交付配置能力。

建议实现内容：

1. 固定最小交付 profile：
   - `control_only`
   - `imu_only`
   - `imu_dvl`
2. 给每个 profile 固定：
   - 必要硬件
   - 必要配置
   - 允许缺失项
   - 默认操作入口
   - 默认验证动作
3. 收敛配置覆盖机制：
   - 网络地址
   - 串口绑定
   - 日志目录
   - 是否 real PWM
4. 为未来单文件化交付准备 profile manifest。

验收标准：

1. 客户知道自己购买的是哪个能力等级。
2. 不同能力等级的 bring-up、故障解释和验收动作不再混淆。

### 3.4 Theme D: GUI / operator experience 收口

目标：

1. 让 GUI 从“开发者观察面”走向“操作员观察面”。

建议实现内容：

1. 固定首页必须直接显示：
   - 连接状态
   - 当前 profile
   - 当前 active capability
   - PWM backend mode
   - 设备在线状态
   - fault summary
2. 为常见故障给出下一步动作提示。
3. 把当前术语做有限度翻译：
   - `control_only`
   - `attitude_feedback`
   - `relative_nav`
   - `dummy`
   - `stm32`
4. 保持 GUI 只读边界，不让它越权成为 authority。

验收标准：

1. 操作员不用打开终端也能理解大多数低频状态。
2. GUI 不会误导用户认为系统已具备超出当前能力等级的功能。

### 3.5 Theme E: 真实样本、复盘与版本化交付闭环

目标：

1. 让每次客户现场问题都能沉淀成可复盘、可回放、可对比的资产。

建议实现内容：

1. 固定 bundle 导出目录结构和必需项。
2. 固定现场结束动作：
   - stop
   - bundle
   - archive
   - replay compare
3. 给真实硬件样本建立最小标签体系：
   - profile
   - hardware set
   - failure class
   - software version
4. 形成“交付版本 -> 样本 -> runbook -> known issues”的对应关系。

验收标准：

1. 客户现场问题可以回放和横向比较。
2. 升级版本后能快速确认是否引入行为回退。

## 4. 推荐实施顺序

当前建议按下面顺序推进：

1. 先完成 Theme A。
2. 再完成 Theme B。
3. 然后完成 Theme C。
4. 再推进 Theme D。
5. 最后把 Theme E 做成版本化例行流程。

原因：

1. 如果主入口和真实输出口径都没收紧，后续再做 GUI 或包装，只会把误解放大。
2. 如果 command / comm / stm32 observability 不清晰，客户现场问题会长期依赖开发者远程排查。
3. 如果 profile 语义不冻结，就无法把交付物压缩成稳定产品。

## 5. 每个阶段尽量避免的事情

当前不建议把商业化升级理解成：

1. 先重写 UI。
2. 先引入 ROS2 authority。
3. 先大改导航融合算法。
4. 先做完整任务层和自动控制平台。
5. 先搞多语言大重构。

这些动作都可能有价值，但不应先于：

1. operator lane 固定
2. real PWM 语义固定
3. comm / stm32 链路可观察
4. profile 与交付配置冻结

## 6. 面向未来“单文件交付入口”的建议结构

未来若真要把整个项目浓缩成一个可操作性文件，建议这个文件至少包含以下结构：

1. `当前能力等级`
2. `当前允许做什么`
3. `当前禁止做什么`
4. `启动步骤`
5. `停机步骤`
6. `如何确认当前是 dummy 还是 real stm32`
7. `常见故障树`
8. `bundle 导出步骤`
9. `升级版本前检查`
10. `现场记录区`

建议把这个“单文件入口”视为最终对外包装层，而不是替代代码仓和接口契约本体。

## 7. 后续可直接展开的候选任务

按当前代码基线，后续最适合直接开工的小任务包括：

1. 在 `gcs_server` 落地 `comm_events.csv`。
2. 在 GUI overview 增加 `pwm backend mode` 低频显示。
3. 在 supervisor status / bundle summary 里增加更明确的 command-chain verdict。
4. 整理 profile manifest 与默认配置覆盖规则。
5. 输出一份面对客户的“单页操作卡”模板。

## 8. 使用方式

这份文档当前不是“已完成事项列表”，而是后续升级参考。

每次准备进入下一轮产品化工作时，建议按以下方式使用：

1. 先选一个主题。
2. 只做该主题里最小闭环的一小段。
3. 同步更新 runbook / 文档索引 / 验收口径。
4. 不把多个主题混成一次大改。
