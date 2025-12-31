# 水下机器人项目代码质量评估报告 / Project Quality Audit Report

本报告由内部代码分析工具自动生成，旨在：
- 用**可量化指标**说明当前工程的代码规模、复杂度和潜在风险；
- 帮助非专业读者直观理解：这个工程“有多大、多复杂、风险在哪”；
- 为后续重构、测试和工程管理提供决策参考。

## 0. 概览 / Executive Summary

- 项目根目录 (Project root)：`/home/wys/orangepi`
- 扫描文件数 (Files scanned)：**270**
- 代码总行数 (Code LOC)：**27158**，约折合 **543.2 页** 技术书（按每页 ~50 行估算）
- 注释行数 (Comment LOC)：**7387**，注释比例 (Comment ratio)：**21.4%** —— 注释比例还可以，可在复杂模块继续增强。
- 分支关键字计数 (Branch tokens, 反映 if/循环等复杂度大致数量)：**4863**
- 复杂度 / 风险综合水平 (Overall risk level)：**高 / High** (平均风险评分 ~838.8，最高 ~5789.0)
- 规模评价 (Project size)：代码规模较大，适合按照子系统（驱动 / 控制 / 通信等）分级管理。
- Git 热点分析 (Git hotspots)：当前未启用 git 热点分析，可在运行工具时增加 `--git-days` 参数来观察“最近修改最频繁”的文件。

简单来说：如果你不是写代码的人，可以把这个工程理解为——

- 大约有 **543.2 页** 的“代码说明书”；
- 其中一部分文件结构比较复杂，是未来维护和出问题的重点区域；
- 报告后面列出的 Top 表格，就是“最值得优先关注”的那一批文件。

## 1. 语言分布 / Language Breakdown

这一部分用于回答：**“这个工程主要是用什么语言写的，各占多少量？”**

| Lang | Files | Code LOC | Comment LOC | Total LOC | Code % |
| --- | --- | --- | --- | --- | --- |
| cpp | 163 | 18122 | 5216 | 28411 | 66.7% |
| python | 98 | 8311 | 2171 | 12382 | 30.6% |
| cmake | 9 | 725 | 0 | 857 | 2.7% |
## 2. 按顶层目录的代码量 / LOC by Top-level Directory

这一部分回答：**“控制 / 通信 / 导航 / 公共库等大模块，各自大概有多少代码？”**

| Top Dir | Code LOC | Code % |
| --- | --- | --- |
| UnderwaterRobotSystem | 24202 | 89.1% |
| UnderWaterRobotGCS | 1753 | 6.5% |
| tools | 1203 | 4.4% |
## 3. 高风险文件（综合评分） / Top Risk Files (Composite Score)

这里列出的是**结构复杂 + 行数较多 + 分支较多**的文件，通常是“最难改、最容易出问题”的地方。

| File | RiskScore | Code LOC | MaxFuncLen | MaxNest | BranchTok | CommentRatio |
| --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_daemon.cpp | 5789 | 377 | 324 | 5 | 44 | 0.13 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | 5768 | 253 | 325 | 5 | 55 | 0.12 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp | 4964 | 409 | 261 | 6 | 50 | 0.12 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | 4788 | 330 | 238 | 7 | 76 | 0.13 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | 4593 | 363 | 218 | 5 | 95 | 0.07 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_arbiter.cpp | 4066 | 215 | 213 | 4 | 62 | 0.15 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | 3984 | 330 | 186 | 4 | 88 | 0.07 |
| tools/quality/audit.py | 3863 | 204 | 229 | 4 | 8 | 0.15 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/dvl_driver.cpp | 3805 | 471 | 162 | 6 | 83 | 0.21 |
| UnderWaterRobotGCS/src/urogcs/app/tui_main.py | 3437 | 249 | 164 | 7 | 56 | 0.13 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/app_context.cpp | 3422 | 224 | 186 | 3 | 36 | 0.08 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/intentd.cpp | 3360 | 198 | 190 | 5 | 14 | 0.08 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/teleop_local.cpp | 3257 | 313 | 136 | 6 | 83 | 0.10 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_view_dump.cpp | 3248 | 383 | 135 | 5 | 80 | 0.09 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_client.cpp | 3170 | 339 | 137 | 4 | 52 | 0.04 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/controllers/manual_controller.cpp | 3014 | 59 | 189 | 2 | 5 | 0.70 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/imu_driver_wit.cpp | 2828 | 384 | 116 | 5 | 63 | 0.20 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/utils/config_loader_pwm_client.cpp | 2787 | 170 | 135 | 5 | 49 | 0.11 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/utils/config_loader_alloc.cpp | 2775 | 145 | 146 | 5 | 30 | 0.01 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/thruster_allocation.cpp | 2738 | 310 | 116 | 4 | 66 | 0.12 |
## 4. 超长函数（重构候选） / Long Functions (Refactor Candidates)

这一部分用来回答：**“哪些函数太长 / 嵌套太深，需要拆分？”**

经验上，超过 100 行、嵌套层数很多的函数，在调试和扩展时成本很高，适合优先拆分为更小的子函数。

| File | Function | Lines | Len | Nest |
| --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | ControlLoop::run | 26-350 | 325 | 5 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_daemon.cpp | main | 197-520 | 324 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp | main | 290-550 | 261 | 6 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | main | 207-444 | 238 | 7 |
| tools/quality/audit.py | main | 42-270 | 229 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | GcsSession::handle_parsed_ | 97-314 | 218 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_arbiter.cpp | IntentArbiter::decide | 94-306 | 213 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/intentd.cpp | main | 78-267 | 190 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | while | 154-343 | 190 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/controllers/manual_controller.cpp | ManualController::compute | 27-215 | 189 | 2 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | IntentKeyboardSource::handle_event_ | 186-371 | 186 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/app_context.cpp | build_app_context | 110-295 | 186 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | switch | 196-370 | 175 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | switch | 147-313 | 167 | 4 |
| UnderWaterRobotGCS/src/urogcs/app/tui_main.py | on_log | 201-364 | 164 | 7 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/dvl_driver.cpp | DvlDriver::parseLine | 446-607 | 162 | 6 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | while | 289-438 | 150 | 6 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/utils/config_loader_alloc.cpp | load_thruster_allocation_config | 21-166 | 146 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_client.cpp | handshake | 163-299 | 137 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/main.cpp | main | 85-221 | 137 | 5 |
## 5. 头文件依赖健康度（C/C++） / Include Dependency Health (C/C++)

这一部分关注：**“模块之间的耦合关系是否清晰，有没有互相环状依赖？”**

- 检测到的 C/C++ 模块数 (Modules detected)：**16** 个
- 发现的环状依赖 (Cycles detected)：**0** 处

### 5.2 高频被引用头文件 / Top Included Headers

| Header | Include Count |
| --- | --- |
| unistd.h | 18 |
| fcntl.h | 16 |
| sys/stat.h | 14 |
| sys/mman.h | 12 |
| shared/msg/control_intent.hpp | 10 |
| nav_core/types.hpp | 9 |
| proto_gcs/gcs_protocol.hpp | 9 |
| shared/msg/nav_state.hpp | 8 |
| shared/msg/key_event.hpp | 8 |
| shared/msg/nav_state_view.hpp | 8 |
| control_core/control_mode.hpp | 8 |
| control_core/control_intent.hpp | 8 |
| gateway/bytes.hpp | 7 |
| control_core/control_loop.hpp | 7 |
| control_core/control_types.hpp | 7 |
| gateway/udp/udp_endpoint.hpp | 6 |
| platform/timebase.hpp | 6 |
| yaml-cpp/yaml.h | 6 |
| gateway/codec/gcs_codec.hpp | 5 |
| shared/shm/control_intent_shm.hpp | 5 |
## 6. 风险扫描 / Risk Scan

通过扫描 TODO/FIXME/HACK、危险 C 函数、可疑 C++/Python 写法等，给出一些“可能需要额外注意”的位置。

- TODO / FIXME / HACK / XXX 总数：**64**
- 危险 C 函数（如 strcpy/memcpy 等）命中次数：**58**
- 危险 C++ 模式命中次数：**93**
- 危险 Python 模式命中次数：**66**
- 控制相关关键字（estop/failsafe 等）命中次数：**2006**

### 6.1 高风险命中文件 / Top Risk-hit Files

| File | Score | TODO | C-func | C++pat | Pypat | CtrlKW |
| --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/libpwm_host.c | 89 | 0 | 11 | 0 | 0 | 107 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/PwmFrameBuilder.cpp | 67 | 0 | 3 | 7 | 0 | 4 |
| tools/quality/report_md.py | 61 | 12 | 0 | 0 | 0 | 4 |
| tools/quality/risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/io.py | 60 | 0 | 0 | 0 | 10 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | 49 | 0 | 6 | 0 | 0 | 37 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/protocol.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/UdpSender.cpp | 48 | 0 | 0 | 8 | 0 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/report_md.py | 46 | 9 | 0 | 0 | 0 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/keys/key_event_subscriber_shm.cpp | 43 | 0 | 3 | 3 | 0 | 2 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/tools/volt32_data_verifier.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/Volt32_logger.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/sensors/imu.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_client.cpp | 33 | 0 | 4 | 0 | 0 | 90 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/include/gateway/codec/packet_view.hpp | 33 | 0 | 4 | 0 | 0 | 10 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/include/gateway/codec/gcs_codec.hpp | 33 | 0 | 4 | 0 | 0 | 31 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/tools/imu_data_verifier.py | 30 | 0 | 0 | 0 | 5 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/tests/test_codec.cpp | 25 | 0 | 3 | 0 | 0 | 15 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/include/control_core/control_loop.hpp | 25 | 0 | 0 | 4 | 0 | 34 |
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
