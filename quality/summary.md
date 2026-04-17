# 项目代码审查报告 / Code Audit Report

## 1. 审查结论 / Audit Conclusion

| 项目项 | 结论 |
| --- | --- |
| 项目根目录 | `/home/wys/orangepi` |
| 扫描文件数 | 521 |
| 代码行数 (Code LOC) | 74956 |
| 总行数 (Total LOC) | 108040 |
| 注释行数 / 注释比例 | 16035 / 17.6% (注释比例尚可。) |
| 分支关键字计数 | 11530 |
| 风险等级 | 高 / High (avg=926.9, max=14465.0) |
| 量级判断 | 多仓中大型系统工程 / Multi-repo mid-large system |
| 推荐审查粒度 | subsystem -> runtime chain -> module -> file |
- 结论说明：代码量已达到系统工程量级，且工作量明显分散在多个主要子系统中。该类项目不能按普通单仓应用估算工作量。
- 推荐方法：应先按控制、导航、GCS、shared、tooling 分层，再审 authority boundary、运行时链路和关键契约，最后才进入文件级复杂度。
- 代码量换算：约 **749.6 页** 技术书（按每页 100 行估算）。

## 2. 审查范围与方法 / Scope And Method

| 项目项 | 说明 |
| --- | --- |
| 扫描扩展名 | `.c .cpp .cc .cxx .h .hpp .hh .py .cmake CMakeLists.txt` |
| 默认排除目录 | `.git`、`build`、`third_party`、`generated`、`logs`、`data` 等 |
| 统计维度 | LOC、复杂度风险分数、include 依赖、风险模式命中、git 热点 |
| Git 分析模式 | `multi-repo`，窗口 `30` 天 |
| Git 覆盖仓数 | 4 |
- 说明：本报告属于静态审查报告，适合回答“体量多大、结构如何、风险在哪、应先看哪里”，不替代运行时验证、硬件联调和系统集成测试。

## 3. 量级判断 / Scale Assessment

| 项目项 | 说明 |
| --- | --- |
| 量级判断 | 多仓中大型系统工程 / Multi-repo mid-large system |
| 审查粒度 | subsystem -> runtime chain -> module -> file |
| 量级解释 | 代码量已达到系统工程量级，且工作量明显分散在多个主要子系统中。该类项目不能按普通单仓应用估算工作量。 |
| 审查方法 | 应先按控制、导航、GCS、shared、tooling 分层，再审 authority boundary、运行时链路和关键契约，最后才进入文件级复杂度。 |
| 系统特征 | C/C++ runtime + Python tooling / CMake-based native build / 4 git repositories detected |

### 3.1 主要一级子系统 / Major Top-level Subsystems

| 目录 | Code LOC |
| --- | --- |
| UnderwaterRobotSystem | 68284 |

### 3.2 主要二级子系统 / Major Subsystems (Depth=2)

| 目录 | Code LOC |
| --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV | 24239 |
| UnderwaterRobotSystem/Underwater-robot-navigation | 22188 |
| UnderwaterRobotSystem/UnderwaterRobotSystem | 21038 |

- 判断原则：量级不只由代码行数决定，还取决于子系统数量、语言混合度、接口契约、运行时链路、bring-up / replay / diagnostics 等工程收口成本。

## 4. 结构概览 / Structural Overview

### 4.1 语言分布 / Language Breakdown

| Lang | Files | Code LOC | Comment LOC | Total LOC | Code % |
| --- | --- | --- | --- | --- | --- |
| python | 243 | 37618 | 6778 | 52696 | 50.2% |
| cpp | 268 | 36258 | 9257 | 54069 | 48.4% |
| cmake | 10 | 1080 | 0 | 1275 | 1.4% |

### 4.2 一级目录代码量 / LOC by Top-level Directory

| Top Dir | Code LOC | Code % |
| --- | --- | --- |
| UnderwaterRobotSystem | 68284 | 91.1% |
| UnderWaterRobotGCS | 4941 | 6.6% |
| tools | 1502 | 2.0% |
| 2026-01-26 | 229 | 0.3% |

### 4.3 二级目录结构 / Subsystems (Depth=2)

| Subdir | Files | Code LOC | Code % | Risk/LOC |
| --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV | 187 | 24239 | 32.3% | 8.14 |
| UnderwaterRobotSystem/Underwater-robot-navigation | 154 | 22188 | 29.6% | 7.57 |
| UnderwaterRobotSystem/UnderwaterRobotSystem | 102 | 21038 | 28.1% | 4.01 |
| UnderWaterRobotGCS/src | 40 | 4284 | 5.7% | 3.57 |
| tools/quality | 10 | 1214 | 1.6% | 6.43 |
| UnderwaterRobotSystem/shared | 12 | 814 | 1.1% | 2.94 |
| UnderWaterRobotGCS/tests | 12 | 657 | 0.9% | 4.54 |
| tools | 1 | 288 | 0.4% | 15.02 |
| 2026-01-26 | 2 | 229 | 0.3% | 1.91 |
## 5. 风险与热点 / Risk And Hotspots

### 5.1 目录风险画像 / Directory Risk Profile

| Dir | Files | Code LOC | Code % | AvgRisk | MaxRisk | RiskHits | Changes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem | 456 | 68284 | 91.1% | 991.4 | 14465.0 | 2307 | 373 |
| UnderWaterRobotGCS | 52 | 4941 | 6.6% | 351.4 | 5529.0 | 121 | 103 |
| tools | 11 | 1502 | 2.0% | 1102.5 | 4325.0 | 129 | 0 |
| 2026-01-26 | 2 | 229 | 0.3% | 218.5 | 283.0 | 0 | 0 |

### 5.2 高风险目录（按风险密度） / High-risk Directories By Risk Density

| Dir | Code LOC | Risk/LOC | RiskHits | Changes |
| --- | --- | --- | --- | --- |
| tools | 1502 | 8.07 | 129 | 0 |
| UnderwaterRobotSystem | 68284 | 6.62 | 2307 | 373 |
| UnderWaterRobotGCS | 4941 | 3.70 | 121 | 103 |
| 2026-01-26 | 229 | 1.91 | 0 | 0 |

### 5.3 高风险文件 / Top Risk Files

| File | RiskScore | Code LOC | MaxFuncLen | MaxNest | BranchTok | CommentRatio |
| --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | 14465 | 832 | 839 | 5 | 106 | 0.12 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav/src/offnav/viz/plots.py | 14168 | 646 | 830 | 9 | 89 | 0.23 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/control_guard.cpp | 7341 | 536 | 387 | 5 | 100 | 0.06 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/eskf_update_dvl.cpp | 6270 | 419 | 349 | 4 | 32 | 0.03 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_config.cpp | 6059 | 359 | 340 | 5 | 50 | 0.13 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/app_context.cpp | 6004 | 511 | 307 | 3 | 71 | 0.04 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | 5936 | 576 | 296 | 5 | 90 | 0.07 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | 5743 | 408 | 281 | 5 | 115 | 0.06 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav/apps/tools/dvl_diag_demo.py | 5740 | 255 | 323 | 2 | 70 | 0.22 |
| UnderWaterRobotGCS/src/urogcs/app/tui/tui_loop.py | 5529 | 257 | 312 | 7 | 39 | 0.20 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/io.py | 5138 | 676 | 210 | 10 | 114 | 0.21 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/nav_health_monitor.cpp | 5115 | 407 | 252 | 4 | 96 | 0.08 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/supervisor/phase0_supervisor.py | 5040 | 1904 | 0 | 0 | 367 | 0.00 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/graph_smoother_2d.cpp | 4478 | 296 | 250 | 4 | 34 | 0.24 |
| tools/project_size_report.py | 4325 | 288 | 211 | 7 | 74 | 0.11 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/preprocess/imu_rt_preprocessor.cpp | 4306 | 306 | 232 | 4 | 45 | 0.18 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_keyboard_source.cpp | 4108 | 356 | 192 | 4 | 89 | 0.06 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_arbiter.cpp | 4066 | 215 | 213 | 4 | 62 | 0.15 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp | 4063 | 197 | 230 | 5 | 27 | 0.14 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/preprocess/dvl_rt_preprocessor.cpp | 4011 | 188 | 233 | 4 | 21 | 0.25 |

### 5.4 超长函数 / Long Functions

| File | Function | Lines | Len | Nest |
| --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | ControlLoop::run | 226-1064 | 839 | 5 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav/src/offnav/viz/plots.py | _update | 230-1059 | 830 | 9 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/loop/control_loop_run.cpp | while | 533-1056 | 524 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/control_guard.cpp | ControlGuard::step | 257-643 | 387 | 5 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/eskf_update_dvl.cpp | EskfFilter::update_dvl_xy | 27-375 | 349 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_config.cpp | load_nav_daemon_config_from_yaml | 135-474 | 340 | 5 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav/apps/tools/dvl_diag_demo.py | _to_bool | 83-405 | 323 | 2 |
| UnderWaterRobotGCS/src/urogcs/app/tui/tui_loop.py | on_log | 65-376 | 312 | 7 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/pwm_control_program/src/control_core/app_context.cpp | build_app_context | 308-614 | 307 | 3 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/nav_viewd.cpp | main | 395-690 | 296 | 5 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | GcsSession::handle_parsed_ | 97-377 | 281 | 5 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/nav_health_monitor.cpp | NavHealthMonitor::evaluate | 214-465 | 252 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/estimator/graph_smoother_2d.cpp | GraphSmoother2D::solve | 207-456 | 250 | 3 |
| tools/quality/audit.py | main | 42-274 | 233 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/preprocess/dvl_rt_preprocessor.cpp | DvlRtPreprocessor::process | 68-300 | 233 | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/preprocess/imu_rt_preprocessor.cpp | ImuRtPreprocessor::process | 208-439 | 232 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/apps/gcs_server.cpp | main | 49-278 | 230 | 5 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/audit.py | main | 42-270 | 229 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | switch | 147-373 | 227 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/intent/intent_arbiter.cpp | IntentArbiter::decide | 94-306 | 213 | 4 |

### 5.5 风险模式命中 / Risk Pattern Hits

| File | Score | TODO | C-func | C++pat | Pypat | CtrlKW |
| --- | --- | --- | --- | --- | --- | --- |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/libpwm_host.c | 89 | 0 | 11 | 0 | 0 | 107 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/io.py | 78 | 0 | 0 | 0 | 13 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/report_md.py | 71 | 14 | 0 | 0 | 0 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/PwmFrameBuilder.cpp | 67 | 0 | 3 | 7 | 0 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/session/gcs_session.cpp | 65 | 0 | 8 | 0 | 0 | 37 |
| tools/quality/risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/quality/risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/DVL_logger.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/drivers/dvl/hover_h1000/protocol.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/uwnav/sensors/imu.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav/src/offnav/eskf/monitor.py | 48 | 0 | 0 | 0 | 8 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/orangepi_send/src/UdpSender.cpp | 48 | 0 | 0 | 8 | 0 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/supervisor/tests/test_phase0_supervisor.py | 43 | 0 | 0 | 0 | 7 | 4 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/src/IPC/keys/key_event_subscriber_shm.cpp | 43 | 0 | 3 | 3 | 0 | 2 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/tools/volt32_data_verifier.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/imu_logger.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/Underwater-robot-navigation/apps/acquire/Volt32_logger.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav/src/offnav/eskf/filter.py | 36 | 0 | 0 | 0 | 6 | 0 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/include/gateway/codec/packet_view.hpp | 33 | 0 | 4 | 0 | 0 | 10 |
| UnderwaterRobotSystem/OrangePi_STM32_for_ROV/gateway/include/gateway/codec/gcs_codec.hpp | 33 | 0 | 4 | 0 | 0 | 31 |

### 5.6 Include 依赖健康度 / Include Dependency Health

| 项目项 | 数值 |
| --- | --- |
| Modules detected | 16 |
| Cycles detected | 0 |
### 5.7 Git 热点 / Git Hotspots

| File | Changes |
| --- | --- |
| UnderwaterRobotSystem/UnderwaterRobotSystem/docs/documentation_index.md | 8 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/docs/handoff/CODEX_HANDOFF.md | 8 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/docs/handoff/CODEX_NEXT_ACTIONS.md | 8 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/docs/runbook/gcs_ui_operator_guide.md | 8 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/docs/productization/nightly_upgrade_progress.md | 8 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/app/nav_daemon_runner.cpp | 7 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/docs/handoff/CODEX_PROGRESS_LOG.md | 7 |
| UnderWaterRobotGCS/src/urogcs/app/gui/main_window.py | 6 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/src/nav_core/drivers/imu_driver_wit.cpp | 6 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/CMakeLists.txt | 6 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/supervisor/phase0_supervisor.py | 6 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/docs/device_test_and_debug.md | 5 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/README.md | 5 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/tools/supervisor/run_local_teleop_smoke.sh | 5 |
| UnderwaterRobotSystem/UnderwaterRobotSystem/.gitignore | 5 |
| UnderWaterRobotGCS/src/urogcs/app/gui/gui_env.py | 4 |
| UnderWaterRobotGCS/src/urogcs/tools/preflight_check.py | 4 |
| UnderWaterRobotGCS/src/urogcs/app/gui/overview_presenter.py | 4 |
| UnderWaterRobotGCS/tests/test_gui_overview_presenter.py | 4 |
| UnderwaterRobotSystem/Underwater-robot-navigation/nav_core/include/nav_core/app/nav_daemon_logging.hpp | 4 |

#### Git 分析说明 / Git Analysis Notes

| 项目项 | 说明 |
| --- | --- |
| Mode | multi-repo |
| Window(days) | 30 |
| Repo count | 4 |

#### Git 仓覆盖范围 / Repositories Covered

| Repo Root | Changed Paths Counted |
| --- | --- |
| /home/wys/orangepi/UnderWaterRobotGCS | 103 |
| /home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV | 128 |
| /home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation | 228 |
| /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem | 262 |
## 6. 建议的审查顺序 / Recommended Audit Order

1. 先确认主要子系统和职责边界。
2. 再沿运行时链路审查 authority、契约和状态传播。
3. 随后进入模块级风险和热点目录。
4. 最后处理高风险文件、长函数和局部重构建议。

## 7. 结论限制 / Limitations

- 本报告基于静态扫描，不代表运行时行为已验证。
- 风险分数用于排序，不应被解读为严格的缺陷概率。
- Git 热点表示近期修改频率，不等同于缺陷密度或设计正确性。
- 若存在多仓聚合根，最终量级判断应结合子系统级报告一起解读。
