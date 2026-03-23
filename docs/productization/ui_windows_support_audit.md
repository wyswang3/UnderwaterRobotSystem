# UI Windows Support Audit

## 文档状态

- 状态：Working draft
- 说明：当前设计方向或阶段性方案已冻结，但尚未全部实施。


## 当前结论

截至 2026-03-21，Windows 路径已经从“只有 TUI 诊断入口”前进到：

- `run_tui.ps1`：最小 TUI / 诊断入口
- `run_gui.ps1`：第一阶段 GUI preview 入口

但当前仍不能宣称 Windows 已达到交付级 parity。

## 当前支持矩阵

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| preflight | 支持 | `preflight_check.py` 可在 PowerShell 路径被调用 |
| TUI 观测/诊断 | 基本支持 | 适合会话、telemetry、状态阅读 |
| GUI 总览首页 | Preview | `gui_main.py` + `run_gui.ps1` 已可启动，但未完成现场验证 |
| 完整键盘 teleop | 不支持 | 仍依赖 POSIX 键盘输入路径 |
| 安装器/打包 | 不支持 | `build_installer.ps1` 仍明确提示未产品化 |

## 当前已知差距

1. 还没有真实 Windows 主机上的稳定运行样本。
2. 没有 Windows 打包、签名、安装器与依赖收口。
3. GUI 目前只是单首页 preview，不是完整交付界面。
4. 当前 `pyproject.toml` 为空，无法把 `PySide6` 依赖收口到安装流程中。
5. 终端/TUI 相关体验在 Windows 上仍不应被视为主路径。

## 当前建议

1. Windows 客户若只需要看状态，优先尝试 `run_gui.ps1`。
2. 如 GUI 路径异常，再退回 `run_tui.ps1` 做最小诊断。
3. 在没有真实 Windows 现场验证前，不要承诺 GUI/TUI 的完整操作 parity。
4. 下一步应先完成真实 Windows 主机上的启动验证，再决定是否进入打包阶段。
