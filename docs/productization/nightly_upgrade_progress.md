# Nightly Upgrade Progress

## 日期

2026-03-21

## 当前目标

本轮目标严格收敛为第一阶段 GUI 落地，不扩展成完整商业化平台。

本轮只做：

1. 在 `UnderWaterRobotGCS` 中落一个真正可运行的 `PySide6 + Qt` GUI 骨架。
2. 完成首页级“总览仪表盘”。
3. 让首页只复用现有 `GcsService + TelemetrySnapshot + ui_viewmodels`。
4. 在 Linux 下完成启动和最小验证。
5. 梳理 Windows 当前运行差异，但不进入打包阶段。

## 已完成项

- 新增 `urogcs.app.gui_main` 作为 GUI 真入口。
- 新增 `src/urogcs/app/gui/` 目录，包含：
  - `gui_env.py`
  - `overview_presenter.py`
  - `main_window.py`
- 新增 Qt 主窗口与总览首页。
- 首页已能展示：
  - 连接状态
  - 设备状态
  - 导航状态
  - 控制状态
  - 命令状态
  - 故障摘要
- GUI 首页状态严格建立在：
  - `GcsServiceState`
  - `TelemetrySnapshot`
  - `build_dashboard_viewmodel()`
  之上，没有重写协议或状态机。
- 新增 `tests/test_gui_overview_presenter.py` 覆盖首页状态映射。
- 新增 Linux GUI 启动脚本 `scripts/run_gui.sh`。
- 把 `scripts/run_gui.ps1` 从“重定向到 TUI”升级为“GUI preview 入口”。
- `preflight_check.py` 文案已同步为 GUI/TUI 双入口。
- 更新 UI plan、operator guide、Windows audit 与 nightly 文档。

## 修改的仓库 / 文件

### GCS / UI 仓

仓库：`/home/wys/orangepi/UnderWaterRobotGCS`

本轮新增 / 更新的关键文件：

- `src/urogcs/app/gui_main.py`
- `src/urogcs/app/gui/__init__.py`
- `src/urogcs/app/gui/gui_env.py`
- `src/urogcs/app/gui/overview_presenter.py`
- `src/urogcs/app/gui/main_window.py`
- `src/urogcs/tools/preflight_check.py`
- `scripts/run_gui.sh`
- `scripts/run_gui.ps1`
- `tests/test_gui_overview_presenter.py`

说明：

- GCS 仓在本轮开始前已带有上一轮 TUI / preflight / customer usability 改动未提交。
- 本轮继续在该脏工作区上追加 GUI 第一阶段改动，没有回滚前序变更。

### 控制仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`

- 本轮无代码改动。
- 本轮只继续复用其 `gcs_server` / `nav_viewd` / `pwm_control_program` 作为联调上下游参考。

### 导航仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`

- 本轮无代码改动。
- 本轮只继续复用既有导航设备绑定、诊断和契约语义。

### 文档仓

仓库：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`

本轮更新：

- `docs/productization/ui_upgrade_plan.md`
- `docs/runbook/gcs_ui_operator_guide.md`
- `docs/productization/ui_windows_support_audit.md`
- `docs/productization/nightly_upgrade_progress.md`

说明：

- 文档仓在本轮开始前已经带有上一轮 P0 / customer usability 文档改动。
- 本轮只继续追加 GUI 第一阶段相关文档，不回滚前序改动。

## 编译结果

### GCS / UI 仓

- `python3 -m py_compile`：通过
  - `src/urogcs/app/gui/gui_env.py`
  - `src/urogcs/app/gui/overview_presenter.py`
  - `src/urogcs/app/gui/main_window.py`
  - `src/urogcs/app/gui_main.py`
  - `src/urogcs/tools/preflight_check.py`
  - `tests/test_gui_overview_presenter.py`

### 启动脚本 / 检查脚本

- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m urogcs.app.gui_main --no-auto-connect --quit-after-ms 200`：通过，退出码 `0`
- `QT_QPA_PLATFORM=offscreen bash scripts/run_gui.sh --no-auto-connect --quit-after-ms 200`：通过，退出码 `0`
- `pwsh` 语法解析 `scripts/run_gui.ps1`：通过

### 控制仓 / 导航仓

- 本轮没有代码改动，因此未新增编译动作。

## 测试结果

- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m unittest tests.test_gui_overview_presenter`：通过
- `cd /home/wys/orangepi/UnderWaterRobotGCS && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`：通过
- GCS 当前共运行 `10` 个 Python 单测，结果 `OK`

## 更新的文档

本轮更新后的参考文档包括：

- `docs/productization/ui_upgrade_plan.md`
- `docs/runbook/gcs_ui_operator_guide.md`
- `docs/productization/ui_windows_support_audit.md`
- `docs/productization/nightly_upgrade_progress.md`

## 本地 Git 收口情况

### GCS / UI 仓

- 路径：`/home/wys/orangepi/UnderWaterRobotGCS`
- 分支：`feature/gcs-p0-status-telemetry-alignment`
- HEAD commit：`3e2cb0437a24ecf233b15ac74d2af9f2df1cd33e`
- commit message：`Refresh GCS readme for developers`
- 工作区：不干净

当前仍在工作区中的主要类型：

- 上一轮 TUI / preflight / usability 改动
- 本轮 GUI 骨架与首页改动
- 本轮单测和 launcher 改动

说明：

- 已清理由本轮验证产生的 `__pycache__` / `.pyc` 缓存，不把缓存文件纳入收口。

### 控制仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/OrangePi_STM32_for_ROV`
- 分支：`feature/control-p0-status-telemetry-baseline`
- HEAD commit：`c23d83d52fa972a0a509714f6d64229de99ec6a1`
- commit message：`Refresh control stack readmes and operator guide`
- 工作区：干净

### 导航仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/Underwater-robot-navigation`
- 分支：`feature/nav-p0-contract-baseline`
- HEAD commit：`2329255905570fcd6d89fc71cca6d9511df46f6d`
- commit message：`Refresh navigation readmes for developers`
- 工作区：干净

### 文档仓

- 路径：`/home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem`
- 分支：`feature/docs-p0-baseline-alignment`
- HEAD commit：`054ea736399f9bb93e4fa62c5ae9f12e0018dc7f`
- commit message：`Refresh system and offline nav readmes`
- 工作区：不干净

说明：

- 文档仓仍同时包含上一轮 baseline 文档改动和本轮 GUI 第一阶段文档改动。

## 当前阻塞点

- 还没有真实 Windows 主机上的 GUI 运行样本。
- `pyproject.toml` 仍为空，依赖和安装流程还未产品化。
- GUI 当前只有首页，没有多页面导航，也没有启动编排和配置编排。

## 剩余风险

- 不能把当前 GUI 首页描述成完整商业化上位机。
- Windows 路径当前只能称为 preview，不宜承诺 parity。
- GCS 仓与文档仓都带有前序未提交改动，后续提交时必须把“上一轮”和“本轮 GUI”边界拆清。

## 下一步建议

1. 进入第二阶段时，先补“最近命令 / 最近失败 / 更清晰 fault detail”区域。
2. 再补启动向导和更明确的连接流程，但先不要进入 SSH 编排。
3. 在 GUI 首页稳定后，再规划导航设备扫描和串口配置页。
4. 在真实 Windows 主机验证完成前，不进入 Windows 打包和安装器阶段。
