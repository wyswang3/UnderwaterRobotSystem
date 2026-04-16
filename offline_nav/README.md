# offline_nav

`offline_nav` 是当前项目的 offline analysis / batch navigation / plotting 工具目录。

它的定位不是实时运行时，而是：

- 做原始数据复盘
- 做预处理、重算、可视化和诊断
- 帮助理解在线导航之后还能怎样离线检查结果

## 当前进度 / Current Status

当前这个目录仍然更像 engineering workbench，而不是完整产品化平台：

- 已经具备 raw / preprocess / nav / dvl 等离线 CLI
- 适合做 CSV 数据检查、轨迹图、统计图和参数试验
- 仍保留部分实验代码、样例数据和历史脚本

所以当前更准确的理解是：

- useful
- developer-facing
- still experimental in parts

## 这个目录负责什么

主要负责：

- 原始 IMU / DVL CSV 检查
- IMU / DVL 预处理
- dead-reckon / ESKF 等离线导航流程
- 轨迹图、诊断图和统计结果导出

不负责：

- 在线导航 authority
- 控制链
- GCS

## 目录结构

- `configs/`
  - 数据集、参数和快捷命令
- `src/offnav/`
  - 主 Python 包
- `apps/`
  - 诊断与小工具脚本
- `scripts/`
  - 图像和辅助生成脚本
- `data/`
  - 样例或实验数据

## 当前推荐使用方式

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav
pip install -e .
```

开发和阅读时，更推荐直接用 module entry：

```bash
python -m offnav.cli_raw
python -m offnav.cli_proc
python -m offnav.cli_nav
python -m offnav.cli_dvl
```

## 推荐阅读顺序

1. 本 README
2. `configs/快捷命令行.md`
3. `src/offnav/cli_proc.py`
4. `src/offnav/cli_nav.py`
5. `src/offnav/preprocess/`
6. `src/offnav/algo/`
7. `src/offnav/viz/`

## 和在线导航仓的关系

- `nav_core` 负责在线产生权威状态和实时日志
- `offline_nav` 负责对原始或处理中数据做离线重算、可视化和诊断

前者面向 runtime，后者面向 analysis。
