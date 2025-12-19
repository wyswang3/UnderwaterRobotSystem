# Project Quality Audit Report
- Root: `D:\UnderwaterRobotSystem`
- Files scanned: **184**
- Code LOC: **18490** (comments 5691, blanks 4790)
- Branch tokens (rough): **2970**

## 1. Language Breakdown
| Lang | Files | Code LOC | Comment lines | Total lines |
| --- | --- | --- | --- | --- |
| cpp | 114 | 12372 | 3940 | 19767 |
| python | 61 | 5538 | 1751 | 8518 |
| cmake | 9 | 580 | 0 | 686 |

## 2. LOC by Top-level Directory
| Top Dir | Code LOC |
| --- | --- |
| OrangePi_STM32_for_ROV | 10109 |
| Underwater-robot-navigation | 7340 |
| tools | 886 |
| shared | 75 |
| UnderwaterRobotSystem | 75 |
| (root) | 5 |

## 3. Top Risk Files (Composite Score)
| File | Risk | LOC | MaxFuncLen | MaxNest | BranchTok | CommentRatio |
| --- | --- | --- | --- | --- | --- | --- |
| Underwater-robot-navigation\nav_core\src\nav_daemon.cpp | 5789 | 377 | 324 | 5 | 44 | 0.1333 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\control_core\control_loop.cpp | 4717 | 335 | 250 | 5 | 54 | 0.154 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\utils\config_loader.cpp | 4123 | 559 | 172 | 5 | 98 | 0.0683 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\control_core\app_main.cpp | 4016 | 304 | 192 | 4 | 59 | 0.0225 |
| OrangePi_STM32_for_ROV\comm_gcs\src\session\gcs_session.cpp | 3824 | 265 | 177 | 5 | 88 | 0.0569 |
| Underwater-robot-navigation\nav_core\src\dvl_driver.cpp | 3805 | 471 | 162 | 6 | 83 | 0.2071 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\controllers\manual_controller.cpp | 3014 | 59 | 189 | 2 | 5 | 0.705 |
| Underwater-robot-navigation\nav_core\src\imu_driver_wit.cpp | 2828 | 384 | 116 | 5 | 63 | 0.2017 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\control_core\thruster_allocation.cpp | 2738 | 310 | 116 | 4 | 66 | 0.1243 |
| OrangePi_STM32_for_ROV\comm_gcs\apps\gcs_client.cpp | 2700 | 308 | 112 | 4 | 44 | 0.0284 |
| tools\project_size_report.py | 2614 | 183 | 121 | 7 | 42 | 0.183 |
| Underwater-robot-navigation\tools\project_size_report.py | 2614 | 183 | 121 | 7 | 42 | 0.183 |
| OrangePi_STM32_for_ROV\orangepi_send\src\main.cpp | 2581 | 174 | 137 | 5 | 19 | 0.0984 |
| Underwater-robot-navigation\nav_core\src\imu_rt_filter.cpp | 2566 | 187 | 133 | 5 | 23 | 0.3345 |
| OrangePi_STM32_for_ROV\comm_gcs\apps\gcs_server.cpp | 2553 | 136 | 143 | 3 | 19 | 0.0748 |
| Underwater-robot-navigation\apps\tools\tmux_telemetry_manager.py | 2541 | 229 | 120 | 4 | 44 | 0.1455 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\io\input\gcs_input_adapter.cpp | 2509 | 320 | 107 | 3 | 58 | 0.0751 |
| OrangePi_STM32_for_ROV\orangepi_send\src\pwm_control.c | 2349 | 388 | 71 | 4 | 92 | 0.2286 |
| Underwater-robot-navigation\uwnav\drivers\dvl\hover_h1000\io.py | 2213 | 340 | 71 | 7 | 66 | 0.1371 |
| OrangePi_STM32_for_ROV\orangepi_send\src\libpwm_host.c | 2194 | 372 | 66 | 4 | 84 | 0.1409 |

## 4. Long Functions (Need Refactor Candidates)
| File | Function | Lines | Len | Nest |
| --- | --- | --- | --- | --- |
| Underwater-robot-navigation\nav_core\src\nav_daemon.cpp | main | 197-520 | 324 | 5 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\control_core\control_loop.cpp | ControlLoop::run | 244-493 | 250 | 5 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\control_core\app_main.cpp | app_main | 175-366 | 192 | 3 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\controllers\manual_controller.cpp | ManualController::compute | 27-215 | 189 | 2 |
| OrangePi_STM32_for_ROV\comm_gcs\src\session\gcs_session.cpp | GcsSession::handle_parsed_ | 58-234 | 177 | 5 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\utils\config_loader.cpp | load_thruster_allocation_config | 341-512 | 172 | 5 |
| Underwater-robot-navigation\nav_core\src\dvl_driver.cpp | DvlDriver::parseLine | 446-607 | 162 | 6 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\control_core\control_loop.cpp | while | 328-487 | 160 | 4 |
| OrangePi_STM32_for_ROV\comm_gcs\apps\gcs_server.cpp | main | 39-181 | 143 | 3 |
| OrangePi_STM32_for_ROV\orangepi_send\src\main.cpp | main | 85-221 | 137 | 5 |
| Underwater-robot-navigation\nav_core\src\imu_rt_filter.cpp | RealTimeImuFilterCpp::process | 186-318 | 133 | 5 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\utils\config_loader.cpp | load_trajectory_config | 551-680 | 130 | 4 |
| OrangePi_STM32_for_ROV\comm_gcs\src\session\gcs_session.cpp | switch | 106-233 | 128 | 3 |
| tools\project_size_report.py | add_file | 59-179 | 121 | 7 |
| Underwater-robot-navigation\tools\project_size_report.py | add_file | 59-179 | 121 | 7 |
| Underwater-robot-navigation\apps\tools\tmux_telemetry_manager.py | main | 179-298 | 120 | 2 |
| Underwater-robot-navigation\apps\tools\tmux_telemetry_manager.py | graceful_stop_all | 68-178 | 111 | 4 |
| tools\quality\audit.py | main | 20-127 | 108 | 3 |
| Underwater-robot-navigation\apps\acquire\DVL_logger.py | __init__ | 47-144 | 98 | 5 |
| Underwater-robot-navigation\apps\tools\dvl_data_verifier.py | _on_parsed_with_timebase | 190-283 | 94 | 3 |

## 5. Include Dependency Health (C/C++)
- Modules detected: 17
- Cycles detected: 0

### Top Included Headers
| Header | Count |
| --- | --- |
| control_core/control_mode.hpp | 10 |
| unistd.h | 9 |
| control_core/control_intent.hpp | 9 |
| nav_core/types.hpp | 9 |
| proto_gcs/gcs_protocol.hpp | 8 |
| control_core/control_types.hpp | 8 |
| comm_gcs/bytes.hpp | 7 |
| fcntl.h | 6 |
| shared/msg/nav_state.hpp | 6 |
| comm_gcs/udp_endpoint.hpp | 5 |
| comm_gcs/codec/gcs_codec.hpp | 5 |
| arpa/inet.h | 5 |
| sys/socket.h | 5 |
| platform/pwm_client.hpp | 5 |
| platform/timebase.hpp | 5 |
| netinet/in.h | 4 |
| stdint.h | 4 |
| libpwm_host.h | 4 |
| controllers/controller_base.hpp | 4 |
| control_core/thruster_allocation.hpp | 4 |

## 6. Risk Scan
- TODO/FIXME/HACK/XXX: **32**
- Dangerous C funcs hits: **53**
- Dangerous C++ patterns hits: **61**
- Dangerous Python patterns hits: **54**
- Control keywords hits: **1561**

### Top Risk-hit Files
| File | Score | TODO | C-func | C++pat | Pypat | CtrlKW |
| --- | --- | --- | --- | --- | --- | --- |
| OrangePi_STM32_for_ROV\orangepi_send\src\libpwm_host.c | 89 | 0 | 11 | 0 | 0 | 107 |
| OrangePi_STM32_for_ROV\pwm_control_program\src\io\input\gcs_input_adapter.cpp | 81 | 0 | 10 | 0 | 0 | 114 |
| OrangePi_STM32_for_ROV\orangepi_send\src\PwmFrameBuilder.cpp | 67 | 0 | 3 | 7 | 0 | 4 |
| tools\quality\risk_scan.py | 60 | 12 | 0 | 0 | 0 | 0 |
| Underwater-robot-navigation\uwnav\drivers\dvl\hover_h1000\io.py | 60 | 0 | 0 | 0 | 10 | 0 |
| OrangePi_STM32_for_ROV\orangepi_send\src\UdpSender.cpp | 48 | 0 | 0 | 8 | 0 | 0 |
| Underwater-robot-navigation\uwnav\drivers\dvl\hover_h1000\protocol.py | 48 | 0 | 0 | 0 | 8 | 0 |
| tools\quality\report_md.py | 46 | 9 | 0 | 0 | 0 | 3 |
| OrangePi_STM32_for_ROV\comm_gcs\src\session\gcs_session.cpp | 41 | 0 | 5 | 0 | 0 | 37 |
| OrangePi_STM32_for_ROV\comm_gcs\tests\test_session.cpp | 41 | 0 | 5 | 0 | 0 | 44 |
| Underwater-robot-navigation\apps\acquire\Volt32_logger.py | 36 | 0 | 0 | 0 | 6 | 0 |
| Underwater-robot-navigation\apps\tools\volt32_data_verifier.py | 36 | 0 | 0 | 0 | 6 | 0 |
| Underwater-robot-navigation\uwnav\sensors\imu.py | 36 | 0 | 0 | 0 | 6 | 0 |
| OrangePi_STM32_for_ROV\comm_gcs\include\comm_gcs\codec\gcs_codec.hpp | 33 | 0 | 4 | 0 | 0 | 30 |
| OrangePi_STM32_for_ROV\comm_gcs\include\comm_gcs\codec\packet_view.hpp | 33 | 0 | 4 | 0 | 0 | 11 |
| Underwater-robot-navigation\apps\tools\imu_data_verifier.py | 30 | 0 | 0 | 0 | 5 | 0 |
| OrangePi_STM32_for_ROV\comm_gcs\apps\gcs_client.cpp | 25 | 0 | 3 | 0 | 0 | 97 |
| OrangePi_STM32_for_ROV\comm_gcs\tests\test_codec.cpp | 25 | 0 | 3 | 0 | 0 | 17 |
| OrangePi_STM32_for_ROV\pwm_control_program\include\controllers\controller_manager.hpp | 25 | 0 | 0 | 4 | 0 | 2 |
| OrangePi_STM32_for_ROV\pwm_control_program\include\control_core\control_loop.hpp | 25 | 0 | 0 | 4 | 0 | 13 |

## 7. Git Hotspots (Optional)
- Disabled: not a git repository

## 8. Suggested Actions (Prioritized)
1) Review **Top Risk Files**: split long functions, reduce nesting, isolate responsibilities.
2) Break **include cycles** and reduce cross-module includes; move shared types to a stable `shared/` or `interfaces/` layer.
3) Resolve **risk hits**: TODO/FIXME triage, audit memcpy/strcpy-like calls, ban naked `except:`.
4) Add tests around **ControlGuard / failsafe / TTL / estop** paths; these are safety-critical for ROV.
