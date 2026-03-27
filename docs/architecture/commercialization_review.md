# Commercialization Review

## 文档状态

- 状态：Authoritative
- 说明：基于 2026-03-27 当前真实代码、handoff、runbook 和阶段成果，对 UnderwaterRobotSystem 面向商业化落地的成熟度、短板和升级路线做审查。

## 1. 本轮目标与范围

本轮目标不是重复做一轮技术细节审查，而是站在“成熟可用商业化项目”的角度，回答四个问题：

1. 当前项目离“稳定可交付”还有多远。
2. 哪些模块已经具备产品化基础。
3. 哪些短板会直接影响现场交付、客户体验和后续扩展。
4. 下一轮 Codex 最值得优先推进什么，哪些工作应继续后置。

本轮审查依据主要来自当前真实代码与文档：

- `tools/supervisor/phase0_supervisor.py`
- `tools/supervisor/device_identification.py`
- `tools/supervisor/device_profiles.py`
- `tools/supervisor/incident_bundle.py`
- `docs/runbook/local_debug_and_field_startup_guide.md`
- `docs/runbook/incident_bundle_guide.md`
- `docs/runbook/gcs_ui_operator_guide.md`
- `docs/architecture/logging_full_chain_audit.md`
- `docs/interfaces/logging_contract.md`
- `docs/handoff/CODEX_HANDOFF.md`
- `docs/handoff/CODEX_NEXT_ACTIONS.md`
- `UnderWaterRobotGCS` 当前 GUI / TUI / preflight / launcher 代码

本轮不做：

- 核心 C++ authority 主链重构
- 导航融合或控制算法扩展
- USBL 与复杂 profile 扩面
- ROS2 写回或新的 authority 路径

## 2. 当前项目成熟度评估

### 2.1 总体判断

当前项目已经不是“原型堆功能”的状态，而是一个：

- 核心主链语义已经基本稳定
- 外围 bring-up / diagnostics / replay / UI 已有明显产品化基础
- 但距离“现场可稳定部署、客户可直接使用”的商业化项目，仍有一到两个收口阶段

更准确地说，当前形态更接近：

- `bench-safe` 的工程集成平台
- 带有 operator diagnostics 和首页 GUI preview 的客户预览版本

而不是：

- 已完成交付路径冻结的商业化产品
- 已完成多平台安装与现场 SOP 固化的客户版本

### 2.2 六个维度的当前成熟度

| 维度 | 当前成熟度 | 审查判断 |
| --- | --- | --- |
| 运行与部署能力 | 中高 | `phase0_supervisor` 已具备 `preflight/start/status/stop/device-scan/startup-profiles/bundle`、固定 run dir、状态文件、fault summary、事件时间线；但安装/打包/服务化和真实 bench 通过样本仍不足。 |
| 上位机与客户体验 | 中 | TUI 已是稳定 teleop 基线，GUI 已有六张总览卡片、连接/断开和 ROS2 只读 preview；但仍缺日志导出、恢复动作按钮、远程编排和 Windows 现场级验证。 |
| 日志与排障体系 | 中 | supervisor run files、incident bundle、replay/compare、`nav_events.csv`、`control_events.csv` 已形成最小闭环；但 `comm_events.csv` 缺口仍在，跨进程命令链和部分 C++ 边界事件还不完整。 |
| 设备与配置管理 | 中低 | device-scan、startup profile、preflight gate 已落地，DVL/Volt32/IMU 已有一轮真实样本校准；但静态身份样本仍不足，配置入口仍偏工程文件路径级，不是交付级配置治理。 |
| 核心控制与导航能力 | 中高（运行基线） / 高风险（继续改动） | 当前 `NavState -> NavStateView -> ControlGuard -> Telemetry` 主链已足以支撑外围产品化收口；但核心 C++ 主链仍属于高风险区，不适合并行展开算法重构。 |
| 文档、测试与交付体系 | 中 | handoff、runbook、文档分层和定向 Python 单测已经成体系；但仍存在 authoritative 文档漂移、跨仓集成验收不足、打包/依赖/版本治理不完整。 |

### 2.3 当前离商业化目标还有多远

如果把目标定义为“可被内部稳定部署、可被客户或现场工程师按标准步骤启动、观察、停机、导出故障样本”，当前已经完成了约一半以上的基础建设。

如果把目标定义为“可直接面向客户交付、支持多平台安装、具备稳定现场恢复路径和更强 operator 体验”，当前仍明显不足，主要差距不在算法框架，而在：

1. 真实设备验证闭环还没跑完。
2. 运维/交付路径还没冻结成单一标准入口。
3. 客户侧体验还停留在 TUI 主路径 + GUI preview。
4. 文档与提示口径还存在小范围漂移。

## 3. 已具备产品化基础的模块

### 3.1 运行与部署外围层

以下能力已经具备明显的产品化基础：

1. `phase0_supervisor.py` 已形成统一入口。
   - 已支持 `preflight`、`start`、`status`、`stop`、`device-scan`、`startup-profiles`、`bundle`。
2. run dir 结构已经固定。
   - `run_manifest.json`
   - `process_status.json`
   - `last_fault_summary.txt`
   - `supervisor_events.csv`
3. failure-path 也能稳定产出最小真源。
   - 这对商业化尤其重要，因为现场最先需要的是“失败时也能解释”，而不是只在成功路径有日志。
4. incident bundle Phase 1 已落地。
   - 已能把 supervisor、child logs、低频事件入口和高频日志入口按固定目录导出。

这意味着“启动、停机、取证、交接”这条外围运维线已经开始像产品，而不再只是开发者脚本集合。

### 3.2 上位机基础体验

以下能力已经可以视为产品化基础，而不是纯开发者临时界面：

1. TUI 已经是当前完整 teleop 基线。
2. GUI 已经不是空壳。
   - 当前真实代码中，GUI 已有六张首页卡片：`Connection`、`Devices`、`Navigation`、`Control`、`Command`、`Fault Summary`。
3. GUI 已支持：
   - connect / disconnect
   - UDP 主路径
   - ROS2 只读 preview 数据源
4. GCS 已有 preflight 与 Linux/Windows launcher 脚本。
5. GUI 的状态卡片和 fault summary 已经复用现有 telemetry / advisory 语义，而不是另起一套 UI 自定义状态机。

这说明 GCS 已具备“可演示、可观察、可解释”的产品雏形。

### 3.3 日志与排障骨架

以下排障体系已经不是从零开始：

1. supervisor 运行真源已经固定。
2. replay / compare / merge timeline 已有最小闭环。
3. `nav_events.csv` 与 `control_events.csv` 已落地首批低频结构化事件。
4. logging contract 已经明确四层划分：
   - 启动 / 运维日志
   - 事件日志
   - 状态快照日志
   - 高频数据日志
5. incident bundle 已能服务 failure-path 和后续 replay 前准备。

对商业化来说，这意味着“故障闭环”的骨架已经具备，不再是只能靠口头复盘。

### 3.4 设备与 profile 机制

以下设备管理能力已经具备商业化基础价值：

1. device-scan 已能输出静态身份、动态探测、候选分数、歧义和推荐绑定。
2. startup profiles 已固定为：
   - `no_sensor`
   - `volt_only`
   - `imu_only`
   - `imu_dvl`
   - `imu_dvl_usbl`（预留）
   - `full_stack`（预留）
3. `startup_profile_gate` 已把“当前是否允许进入 bench authority 链”前移到 preflight。
4. 当前识别逻辑已经从“尽量猜”收紧为“宁可 unknown，也不误绑”。

这套机制已经能在商业化路径里承担“设备风险前移”和“错误设备拒绝放行”的职责。

### 3.5 文档与 handoff 体系

从商业化视角看，当前文档体系的最大优点是：交接和基线已经开始固定化。

1. `AGENTS.md + handoff + next actions + nightly progress` 已经形成稳定入口。
2. runbook 已覆盖：
   - 本地调试
   - field startup 前检查
   - incident bundle
   - GCS UI 操作
   - replay / reconnect
3. 文档目录结构和状态标识已经清晰。

这套体系对后续“多人接续推进、避免重复试错”非常关键。

## 4. 当前最大短板与风险分级

### 4.1 高风险

#### 风险 A：真实设备闭环还没完成，仍是当前最大商业化阻塞项

当前最大的风险不是框架，而是实机闭环仍未完成：

1. IMU / DVL / Volt32 的静态身份样本仍不足。
2. `imu_only` / `imu_dvl` 真实 bench `start -> status -> stop -> bundle` 还没完成。
3. Volt32 live `CHn:` 规则仍是 partial。

商业化影响：

- 设备一旦换口、重枚举或上板环境变化，当前系统虽然会拒绝误绑，但还不能保证“稳定识别 + 稳定放行 + 稳定 runbook”。

#### 风险 B：交付路径还没有冻结成“客户可直接执行”的安装 / 启动标准入口

当前虽然已经有 launcher 和 preflight，但交付层仍明显偏工程环境：

1. `UnderWaterRobotGCS/pyproject.toml` 当前为空。
2. 没有冻结的安装包、依赖锁定或明确的产品级打包方式。
3. Windows 路径仍是 preview / 最小诊断路径，不是现场 validated path。
4. supervisor 目前更像 Phase 0 bring-up 工具，而不是产品化 service manager。

商业化影响：

- 内部团队可以用，但外部交付仍会高度依赖熟悉代码仓结构的人。

#### 风险 C：命令链与通信链的结构化日志仍不完整

当前日志体系的主要缺口仍然是：

1. `gcs_server` 的 `comm_events.csv` 还没落地。
2. packet seq -> session_id -> intent cmd_seq -> control result 的关联链还没冻结。
3. `pwm_control_program` 的 controller / allocator / PWM 边界事件还没有全部并入同一条结构化链路。

商业化影响：

- 现场最关键的一类问题不是“有没有 telemetry”，而是“命令到底有没有被接收、拒绝、执行、覆盖或失败”。这一段当前还不够强。

#### 风险 D：核心 C++ 主链仍然是高风险区，不能把商业化整改和核心重构绑在一起

这一点本身不是 bug，但如果执行策略失控，会立刻把项目重新拖回高风险状态。

商业化影响：

- 一旦在 supervisor / GCS / 日志 / profile 还没收口时并行展开核心改造，现场可用性反而会下降。

### 4.2 中风险

#### 风险 E：authoritative 文档与真实实现出现小范围漂移

本轮审查已看到几处具体漂移：

1. `project_memory.md` 仍写着 GUI 为空文件，但当前 GUI 已有首页总览实现。
2. `preflight_check.py` 打印的 ROV 启动顺序与 runbook / supervisor 真实顺序不一致。
3. `documentation_index.md` 当前权威 runbook 列表还没有完全对齐新的本地调试 / field startup 基线。

商业化影响：

- 这类问题单个看不大，但会直接增加 operator 和交付同事的误判成本。

#### 风险 F：配置治理与配置校验还停留在工程文件级

当前已有文件存在性检查和路径校验，但仍缺少交付级能力：

1. 跨仓配置的兼容矩阵还不够强。
2. 配置入口仍以 repo 内路径和 CLI 参数为主。
3. 缺少更明确的版本/环境/依赖组合说明。

商业化影响：

- 只要环境偏离当前开发机，bring-up 成本会明显上升。

#### 风险 G：GUI 已有产品雏形，但还没形成客户闭环

GUI 当前的短板非常明确：

1. 只有首页，没有更完整的 operator workflow。
2. 还不支持日志导出。
3. 还没有恢复建议执行按钮或 bundle 入口。
4. 还没有替代 TUI 的 teleop 主路径。

商业化影响：

- GUI 可以作为客户预览和只读观测入口，但还不能承担完整操作台角色。

### 4.3 低风险

#### 风险 H：USBL 和复杂 profile 延后是合理的，不是当前短板

当前 USBL、`imu_dvl_usbl`、`full_stack` 都仍应视为后置项。

原因不是缺 ambition，而是：

1. 真实样本不足。
2. 当前主风险还在 IMU / DVL / Volt32 与基础 operator path。
3. 现在扩复杂 profile 只会扩大变量面。

#### 风险 I：ROS2 preview 目前只读是合理边界

ROS2 preview 当前不承担 authority，这是当前阶段的正确边界，不应被当成商业化缺陷优先修。

## 5. 后续优化优先级

### 5.1 第一优先级：把真实 bench 与设备识别闭环做实

优先级最高的仍然是：

1. 补静态身份快照。
2. 做 `imu_only` 真实 bench safe smoke。
3. 做 `imu_dvl` 真实 bench safe smoke。
4. 产出稳定 bundle 样本。

原因：

- 这是当前所有商业化工作的真实入口约束；设备侧不收口，后面的 GUI、打包、日志体验提升都缺乏可靠支点。

### 5.2 第二优先级：收口单一 operator path

下一优先级应放在“让非开发者能按同一套步骤工作”上：

1. 对齐 runbook、preflight、launcher、状态提示里的启动顺序与术语。
2. 固定“设备检查 -> device-scan -> startup-profiles -> preflight -> start -> status -> stop -> bundle”这条单一路径。
3. 收口 authoritative 文档漂移。

原因：

- 商业化现场最怕的不是某个底层组件不够优雅，而是入口太多、口径不一致。

### 5.3 第三优先级：补交付级安装与配置基线

建议在不动核心主链的前提下，把以下事情做成固定基线：

1. Linux 依赖与启动路径冻结。
2. GCS 最小 package / requirements / 版本说明补齐。
3. Windows 明确继续定位为 preview / observation path，不提前承诺 teleop 交付。
4. 配置检查从“文件存在”继续提高到“组合是否合理”。

### 5.4 第四优先级：补通信链与命令链的结构化日志

如果要继续推进日志产品化，最值得补的不是更多 stdout，而是：

1. `comm_events.csv`
2. command lifecycle 关联字段
3. controller / allocator / PWM 边界的最小低频事件

这一步对商业化的价值高于继续扩更多高频日志。

### 5.5 第五优先级：GUI 做“操作员可用性”而不是“大平台化”

GUI 下一步最值得补的是：

1. 故障提示一致性
2. bundle / log export 入口
3. 恢复建议可读性
4. 与现有 TUI / supervisor 的状态口径对齐

而不是先扩多页面、大量控件或远程编排。

## 6. 分阶段商业化升级路线图

### P1：非导航侧交付路径收口

P1 的目标不是增加新功能，而是让当前系统形成“bench-safe 可复用交付路径”。

建议目标：

1. 完成真实 `imu_only` / `imu_dvl` safe smoke。
2. 把静态身份规则收口到能支撑 bench 放行。
3. 收口 operator path 和文档提示漂移。
4. 固定 Linux 最小安装、启动、停机、bundle 流程。
5. 明确 Windows 仍是 preview，单独写出边界。

P1 完成后的项目形态应是：

- 内部工程团队可稳定 bring-up
- 操作员可按 runbook 独立完成基本流程
- failure-path 样本可稳定交接

P1 明确不做：

- USBL 扩面
- 复杂 profile
- 导航融合重构
- GUI 平台化重做

### P2：客户可用性与排障闭环增强

P2 目标是把当前“工程可用”提升到“客户可读、客户可排障”。

建议目标：

1. 落地 `comm_events.csv`。
2. 补控制侧剩余关键边界低频事件。
3. GUI 增加日志导出 / bundle 入口 / 恢复建议强化。
4. 完成 Linux 交付基线的依赖与版本说明。
5. 建立跨仓最小 acceptance smoke。

P2 完成后的项目形态应是：

- 常见现场问题可通过固定 bundle + runbook 排查
- 客户能看懂主要状态和建议动作
- 交付团队不必每次解释仓库结构和手工启动顺序

### P3：谨慎进入核心链路增强

只有在 P1 / P2 稳定后，才建议进入核心链路增强。

P3 的推进原则应固定为：

1. 只改一个核心模块。
2. 只落一个小点。
3. 优先补日志、状态暴露、错误原因，不先改算法行为。
4. 每次都带最小 build / test / smoke。
5. 每次都同步更新 runbook / handoff / contract 影响说明。

P3 更适合做：

- `gcs_server` 命令链可观察性增强
- `pwm_control_program` 关键边界低频事件增强
- `uwnav_navd` 的 health / bind / timing 暴露增强

P3 仍不建议直接展开：

- ESKF 大改
- trajectory / autonomy 扩面
- ROS2 authority 化
- 三传感器大重构

## 7. 下一步最值得做的工作

### 7.1 如果只从非导航侧先做商业化收口，下一步最合适做什么

最合适的下一步不是继续搭新框架，而是把 supervisor / GCS / runbook / bundle 收口成一条稳定 operator lane：

1. 修正启动顺序和提示口径漂移。
2. 固定唯一推荐操作顺序。
3. 固定 Linux 依赖与启动入口。
4. 让操作员能够稳定完成：
   - `preflight`
   - `start`
   - `status`
   - `stop`
   - `bundle`

如果真实设备此时已经就位，则应把这条 operator lane 直接建立在：

1. 静态身份快照补采
2. `imu_only` bench
3. `imu_dvl` bench

之上，而不是继续空转做更多抽象设计。

### 7.2 下一轮最值得直接执行的工作顺序

建议按以下顺序执行：

1. 若设备就绪：
   - 先补静态身份样本
   - 再做 `imu_only`
   - 再做 `imu_dvl`
   - 每轮都导出 bundle
2. 若设备暂未就绪：
   - 先收口 GCS preflight / runbook / documentation index 的口径漂移
   - 再补 Linux / Windows 启动与依赖说明
   - 再准备后续 `comm_events.csv` 的最小设计审查

### 7.3 如果后续进入核心链路增强，应如何保持谨慎推进

必须同时满足以下条件：

1. 先完成 P1 的 bench-safe/operator path 收口。
2. 一次只动一个核心模块。
3. 优先做日志、状态、错误原因暴露，不先做算法行为调整。
4. 明确说明为什么必须改这个点。
5. 明确说明为什么本轮只改这个点。
6. 改后立即做最小 build / test / smoke。
7. 不把核心改动和 USBL / GUI / ROS2 / profile 扩面混在同一轮。

## 8. 暂不建议展开的工作

当前不建议优先展开：

1. USBL、`imu_dvl_usbl`、`full_stack`
2. 导航融合大改、ESKF 大调参、三传感器重构
3. 导航模式分级大实现
4. ROS2 写回、ROS2 authority 化
5. GUI 平台化重做、多页面大改、远程编排
6. 轨迹跟踪、任务层或更复杂自动化功能

这些内容不是永远不做，而是必须后置到“设备闭环、operator path、日志闭环、交付基线”稳定之后。

## 9. 结论

当前 UnderwaterRobotSystem 已经具备明显的产品化基础，尤其是在 supervisor、runbook、incident bundle、device gate、TUI 基线和 GUI 总览 preview 上，已经不再是简单的开发者脚本集合。

但从商业化落地视角看，当前还不能宣称“可稳定交付”。最关键的剩余工作不是继续改导航主链，而是把真实 bench、设备识别、operator path、安装/配置基线和通信链排障能力做扎实。

因此，下一轮最合理的策略仍然是：

1. 继续优先做外围收口。
2. 先完成 `imu_only` / `imu_dvl` 的真实 bench 闭环。
3. 再补交付与排障路径。
4. 最后才谨慎进入核心链路增强。
