# 水下机器人项目代码质量评估报告 / Project Quality Audit Report

本报告由内部代码分析工具自动生成，旨在：
- 用**可量化指标**说明当前工程的代码规模、复杂度和潜在风险；
- 帮助非专业读者直观理解：这个工程“有多大、多复杂、风险在哪”；
- 为后续重构、测试和工程管理提供决策参考。

## 0. 概览 / Executive Summary

- 项目根目录 (Project root)：`/home/wys/orangepi`
- 扫描文件数 (Files scanned)：**303**
- 代码总行数 (Code LOC)：**32240**，约折合 **322.4 页** 技术书（按每页 ~100 行估算）
- 总行数 (Total LOC)：**51984**（其中空行 8748 行）
- 注释行数 (Comment LOC)：**10996**，注释比例 (Comment ratio)：**25.4%** —— 注释比例还可以，可在复杂模块继续增强。
- 分支关键字计数 (Branch tokens, 反映 if/循环等复杂度大致数量)：**5561**
- 复杂度 / 风险综合水平 (Overall risk level)：**高 / High** (平均风险评分 ~869.7，最高 ~8435.0)
- 规模评价 (Project size)：代码规模较大，适合按照子系统（驱动 / 控制 / 通信等）分级管理。
- Git 热点分析 (Git hotspots)：当前未启用 git 热点分析，可在运行工具时增加 `--git-days` 参数来观察“最近修改最频繁”的文件。

简单来说：如果你不是写代码的人，可以把这个工程理解为——

- 大约有 **322.4 页** 的“代码说明书”；
- 其中一部分文件结构比较复杂，是未来维护和出问题的重点区域；
- 报告后面列出的 Top 表格，就是“最值得优先关注”的那一批文件。

## 1. 语言分布 / Language Breakdown

这一部分用于回答：**“这个工程主要是用什么语言写的，各占多少量？”**

| Lang | Files | Code LOC | Comment LOC | Total LOC | Code % |
| --- | --- | --- | --- | --- | --- |
| cpp | 187 | 21313 | 8082 | 35599 | 66.1% |
| python | 107 | 10166 | 2914 | 15481 | 31.5% |
| cmake | 9 | 761 | 0 | 904 | 2.4% |
## 2. 按顶层目录的代码量 / LOC by Top-level Directory

这一部分回答：**“控制 / 通信 / 导航 / 公共库等大模块，各自大概有多少代码？”**

| Top Dir | Code LOC | Code % |
| --- | --- | --- |
| UnderwaterRobotSystem | 28648 | 88.9% |
| UnderWaterRobotGCS | 2231 | 6.9% |
| tools | 1361 | 4.2% |
## 2b. 目录风险画像 / Directory Risk Profile

这一部分从“目录”的角度综合看工程结构：
- 哪些目录代码量最大，是主要战场；
- 哪些目录风险集中，适合重点重构；
- 哪些目录近期改动频繁，维护压力最大。

| Dir | Files | Code LOC | Comment LOC | Code % | AvgRisk | MaxRisk | TODO | Changes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem | 257 | 28648 | 10081 | 88.9% | 950.2 | 8435.0 | 42 | 0 |
| UnderWaterRobotGCS | 35 | 2231 | 733 | 6.9% | 273.9 | 4683.0 | 0 | 0 |
| tools | 11 | 1361 | 182 | 4.2% | 885.9 | 3863.0 | 33 | 0 |

### 高风险目录（按风险密度排序） / High-risk Directories by Risk Density

| Dir | Code LOC | Risk/LOC | RiskHits | Changes |
| --- | --- | --- | --- | --- |
| UnderwaterRobotSystem | 28648 | 8.52 | 1839 | 0 |
| tools | 1361 | 7.16 | 179 | 0 |
| UnderWaterRobotGCS | 2231 | 4.30 | 87 | 0 |
从上表可以看到：
- 代码量最大的目录承载了主要业务，是未来维护和功能扩展的重点；
- 部分目录虽然代码不多，但 Risk/LOC 较高，说明“单位代码复杂度较高”，适合单独梳理结构；
- Changes 数值高的目录在最近一段时间改动频繁，代表交付压力和问题集中度较高，建议优先补充测试和文档。

## 2c. 二级子目录风险画像 / Subdirectory Risk Profile (Depth=2)

在上一节按“系统级目录”看整体之后，这一节进一步向下看一层，例如 `nav_core/src`、`pwm_control_program/src` 等子目录，用于回答：**“大目录内部，哪一块代码最重 / 最容易出问题？”**

| Subdir (depth=2) | Code LOC | Code % | Risk/LOC | RiskHits | Changes |
| --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV | 16033 | 49.7% | 9.23 | 1024 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation | 10321 | 32.0% | 8.10 | 544 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem | 1824 | 5.7% | 6.14 | 225 | 0 |
| tools/quality | 1178 | 3.7% | 6.05 | 179 | 0 |
| UnderWaterRobotGCS/src | 2231 | 6.9% | 4.30 | 87 | 0 |
| UnderwaterRobotSystem/shared | 465 | 1.4% | 3.11 | 46 | 0 |
解读建议：
- `Code LOC` 大、`Risk/LOC` 也高的子目录，是“体量 + 复杂度都高”的区域，适合单独拉出来做一次专题重构；
- `Changes` 高说明近期改动频繁，可以结合 Git 记录，确认是否存在需求变动频繁或设计不稳定的问题；
- 对于关键子目录（例如控制回路、导航算法、通信协议等），可以在评审会议中单独展示这一节的表格，作为后续工作量的定量依据。

## 3. 高风险文件（综合评分） / Top Risk Files (Composite Score)

这里列出的是**结构复杂 + 行数较多 + 分支较多**的文件，通常是“最难改、最容易出问题”的地方。

| File | RiskScore | Code LOC | MaxFuncLen | MaxNest | BranchTok | CommentRatio |
| --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | 8435 | 361 | 486 | 5 | 73 | 0.24 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | 5242 | 385 | 255 | 5 | 104 | 0.07 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | 4788 | 330 | 238 | 7 | 76 | 0.13 |
| UnderWaterRobotGCS/src/urogcs/app/tui/tui_loop.py | 4683 | 200 | 261 | 7 | 36 | 0.25 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/io.py | 4636 | 564 | 200 | 7 | 99 | 0.25 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/graph_smoother_2d.cpp | 4478 | 296 | 250 | 4 | 34 | 0.24 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/control_guard.cpp | 4328 | 268 | 236 | 5 | 40 | 0.18 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | 4108 | 356 | 192 | 4 | 89 | 0.06 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_arbiter.cpp | 4066 | 215 | 213 | 4 | 62 | 0.15 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_config.cpp | 3980 | 207 | 219 | 6 | 31 | 0.17 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/app_context.cpp | 3910 | 254 | 216 | 3 | 37 | 0.07 |
| tools/quality/audit.py | 3863 | 204 | 229 | 4 | 8 | 0.15 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/audit.py | 3863 | 204 | 229 | 4 | 8 | 0.15 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp | 3644 | 174 | 210 | 3 | 25 | 0.16 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/nav_health_monitor.cpp | 3501 | 148 | 191 | 5 | 36 | 0.38 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon.cpp | 3378 | 365 | 163 | 6 | 41 | 0.14 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/intentd.cpp | 3360 | 198 | 190 | 5 | 14 | 0.08 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/teleop_local.cpp | 3257 | 313 | 136 | 6 | 83 | 0.10 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_view_dump.cpp | 3248 | 383 | 135 | 5 | 80 | 0.09 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/drivers/dvl_driver.cpp | 3150 | 462 | 128 | 4 | 76 | 0.15 |
## 4. 超长函数（重构候选） / Long Functions (Refactor Candidates)

这一部分用来回答：**“哪些函数太长 / 嵌套太深，需要拆分？”**

经验上，超过 100 行、嵌套层数很多的函数，在调试和扩展时成本很高，适合优先拆分为更小的子函数。

| File | Function | Lines | Len | Nest |
| --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | ControlLoop::run | 73-558 | 486 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | while | 201-551 | 351 | 4 |
| UnderWaterRobotGCS/src/urogcs/app/tui/tui_loop.py | on_log | 59-319 | 261 | 7 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | GcsSession::handle_parsed_ | 97-351 | 255 | 5 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/graph_smoother_2d.cpp | GraphSmoother2D::solve | 207-456 | 250 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | main | 207-444 | 238 | 7 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/control_guard.cpp | ControlGuard::step | 161-396 | 236 | 5 |
| tools/quality/audit.py | main | 42-270 | 229 | 4 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/audit.py | main | 42-270 | 229 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_config.cpp | load_nav_daemon_config_from_yaml | 70-288 | 219 | 6 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/app_context.cpp | build_app_context | 110-325 | 216 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_arbiter.cpp | IntentArbiter::decide | 94-306 | 213 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp | main | 46-255 | 210 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | switch | 147-347 | 201 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/io.py | stop_listening | 699-898 | 200 | 6 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | IntentKeyboardSource::handle_event_ | 198-389 | 192 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/nav_health_monitor.cpp | NavHealthMonitor::evaluate | 100-290 | 191 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/intentd.cpp | main | 78-267 | 190 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | switch | 206-388 | 183 | 3 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon.cpp | run_main_loop | 269-431 | 163 | 6 |
## 5. 头文件依赖健康度（C/C++） / Include Dependency Health (C/C++)

这一部分关注：**“模块之间的耦合关系是否清晰，有没有互相环状依赖？”**

- 检测到的 C/C++ 模块数 (Modules detected)：**16** 个
- 发现的环状依赖 (Cycles detected)：**0** 处

### 5.2 高频被引用头文件 / Top Included Headers

| Header | Include Count |
| --- | --- |
| unistd.h | 19 |
| fcntl.h | 17 |
| nav_core/core/types.hpp | 15 |
| sys/stat.h | 13 |
| sys/mman.h | 12 |
| shared/msg/control_intent.hpp | 12 |
| shared/msg/nav_state.hpp | 10 |
| shared/msg/key_event.hpp | 10 |
| shared/msg/nav_state_view.hpp | 9 |
| control_core/control_mode.hpp | 9 |
| yaml-cpp/yaml.h | 8 |
| proto_gcs/gcs_protocol.hpp | 8 |
| control_core/control_intent.hpp | 8 |
| gateway/bytes.hpp | 7 |
| control_core/control_loop.hpp | 7 |
| control_core/control_types.hpp | 7 |
| platform/timebase.hpp | 6 |
| utils/config_loader.hpp | 6 |
| utils/detail/config_log.hpp | 6 |
| time.h | 5 |
## 6. 风险扫描 / Risk Scan

通过扫描 TODO/FIXME/HACK、危险 C 函数、可疑 C++/Python 写法等，给出一些“可能需要额外注意”的位置。

- TODO / FIXME / HACK / XXX 总数：**75**
- 危险 C 函数（如 strcpy/memcpy 等）命中次数：**58**
- 危险 C++ 模式命中次数：**98**
- 危险 Python 模式命中次数：**88**
- 控制相关关键字（estop/failsafe 等）命中次数：**2266**

### 6.1 高风险命中文件 / Top Risk-hit Files

| File | Score | TODO | C-func | C++pat | Pypat | CtrlKW |
| --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/io.py | 96 | 0 | 0 | 0 | 16 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/libpwm_host.c | 89 | 0 | 11 | 0 | 0 | 107 |
| tools/quality/report_md.py | 71 | 14 | 0 | 0 | 0 | 4 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/report_md.py | 71 | 14 | 0 | 0 | 0 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/PwmFrameBuilder.cpp | 67 | 0 | 3 | 7 | 0 | 4 |
| tools/quality/risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | 57 | 0 | 7 | 0 | 0 | 36 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/DVL_logger.py | 54 | 0 | 0 | 0 | 9 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/protocol.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/sensors/imu.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/UdpSender.cpp | 48 | 0 | 0 | 8 | 0 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/keys/key_event_subscriber_shm.cpp | 43 | 0 | 3 | 3 | 0 | 2 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/imu_logger.py | 42 | 0 | 0 | 0 | 7 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/tools/volt32_data_verifier.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/Volt32_logger.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/include/gateway/codec/packet_view.hpp | 33 | 0 | 4 | 0 | 0 | 10 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/include/gateway/codec/gcs_codec.hpp | 33 | 0 | 4 | 0 | 0 | 31 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/tools/imu_data_verifier.py | 30 | 0 | 0 | 0 | 5 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/include/nav_core/drivers/dvl_driver.hpp | 29 | 1 | 0 | 4 | 0 | 0 |
## 7. Git 热点文件（可选） / Git Hotspots (Optional)

- 当前未启用 (Disabled)：disabled

## 8. 建议行动（按优先级） / Suggested Actions (Prioritized)

从工程管理和质量提升的角度，推荐按以下顺序推进：

1) **聚焦 Top Risk Files**：
   - 拆分超长函数，降低嵌套层次；
   - 将“控制逻辑 / 安全相关逻辑”与“日志 / 调试代码”分离。
2) **处理依赖环和高耦合模块**：
   - 打破 include 环状依赖；
   - 将共用类型下沉到稳定的 `shared/` 或 `interfaces/` 层。
3) **清理风险关键字与危险函数**：
   - 系统性梳理 TODO/FIXME，区分“短期必须处理”和“长期规划”；
   - 避免使用不安全的 C 函数（如裸 `strcpy`），统一封装安全 API。
4) **加强安全路径测试（特别是 ROV 相关）**：
   - 为 `ControlGuard` / 急停 (estop) / Failsafe 等模块增加单元测试；
   - 在真实或仿真环境中验证“异常输入 / 网络中断 / 传感器异常”场景。
5) **向非专业干系人汇报**：
   - 使用本报告中的“代码规模”“风险等级”和几张 Top 表格，简单解释工程当前完成度和后续工作量的大致方向。

_本报告由自动化工具生成，无需手工编辑。如需再次评估，可在项目根目录重新运行审计脚本。_
