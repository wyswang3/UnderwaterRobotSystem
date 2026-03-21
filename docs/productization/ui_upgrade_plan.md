# UI Upgrade Plan

## 当前目标

当前阶段继续坚持“客户可用性优先”，但本轮范围严格收敛到第一阶段 GUI 落地：

1. 在 `UnderWaterRobotGCS` 中落一个真正可运行的 `PySide6 + Qt` GUI 入口。
2. 只完成一个首页级“总览仪表盘”。
3. GUI 只复用现有 `GcsService + TelemetrySnapshot + ui_viewmodels`，不重写协议和状态机。
4. 先在 Linux 跑通，并明确 Windows 当前仍只是 preview 路径。

## 本轮已落地

### 阶段 G0：GUI 骨架与总览首页

已完成：

- 新增 `urogcs.app.gui_main` 作为真正的 GUI 启动入口。
- 新增 Qt 主窗口与总览首页，首页至少展示：
  - 连接状态
  - 设备状态
  - 导航状态
  - 控制状态
  - 命令状态
  - 故障摘要
- 新增 `overview_presenter.py`，把首页卡片文案统一建立在：
  - `GcsServiceState`
  - `TelemetrySnapshot`
  - `build_dashboard_viewmodel()`
  之上。
- 新增 `scripts/run_gui.sh`，并把 `run_gui.ps1` 从“仅重定向到 TUI”升级为“GUI preview 启动入口”。
- `preflight_check.py` 文案已同步更新，明确 GUI 也是当前可用入口之一。

### 本轮刻意不做

- 不做 SSH 编排。
- 不做串口配置写回。
- 不做日志导出。
- 不做故障恢复中心。
- 不做复杂视觉美化。
- 不做多页面铺开。
- 不让 GUI 接管安全裁决、控制裁决或导航判断。

## 当前技术策略

### 权威状态来源

首页状态只能来自现有主线：

- `urogcs.core.service.GcsService`
- `urogcs.telemetry.model.TelemetrySnapshot`
- `urogcs.telemetry.ui_viewmodels.build_dashboard_viewmodel()`

GUI 允许补充的仅是“展示层解释”和“本地启动/连接入口”，不允许：

- 重写 wire protocol
- 重写 session 状态机
- 自行发明新的安全判定规则

### 主链边界

继续保持：

- 控制、导航、状态传播、执行链：C/C++ 主线
- GCS、日志、工具、安装检查：Python
- ROS 2：只允许继续作为外围 UI/诊断/工具候选，不进入核心执行主线

## 当前阶段验收标准

### 阶段 G0 验收标准

- `gui_main.py` 能在 Linux 环境启动。
- 首页能稳定显示六类状态卡片。
- 首页状态来源可追溯到现有 telemetry / viewmodel。
- 启动失败或未连接时，界面仍能给出可解释占位状态。
- 至少有一条单测覆盖首页状态映射。

当前结论：以上标准已满足，但仅限第一阶段 preview 级别。

## 下一阶段推荐顺序

1. 阶段 G1：补“最近命令 / 最近失败 / 更清晰 fault detail”区域。
2. 阶段 G2：补启动向导与一键连接入口，但仍不进入 SSH 编排。
3. 阶段 G3：补导航设备扫描与串口候选展示，建立 UI 到 `nav_daemon.yaml` 的受控配置面板。
4. 阶段 G4：在前面几步稳定后，再考虑更成熟的 GUI 外观、日志导出和 Windows 交付。

## 当前不建议做的事

1. 直接把 GCS 扩成完整商业化平台再回头补状态语义。
2. 在 GUI 中自行复制一份 TUI 的状态机逻辑。
3. 让 GUI 直接操纵控制/导航核心线程。
4. 在 Windows 原生验证之前宣称已完成 Windows parity。
