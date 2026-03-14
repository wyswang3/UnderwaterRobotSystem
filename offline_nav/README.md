# offline_nav

`offline_nav` 是当前项目的离线导航分析与批处理工具目录。

它主要面向两类人：

- 做数据复盘、对比、画图和诊断的工程开发者
- 想学习“在线导航之后，离线还能怎么检查和比较结果”的代码学习者

它不是实时控制组件，也不是在线导航守护进程。

## 1. 这个目录现在负责什么

当前 `offline_nav` 主要用来做：

- 原始 IMU / DVL CSV 的离线检查
- IMU / DVL 预处理
- dead-reckon / ESKF 等离线导航管线
- 轨迹图、诊断图和统计结果导出

## 2. 目录结构

- `configs/`
  - 数据集、导航参数和常用命令说明
- `src/offnav/`
  - 主 Python 包
- `apps/`
  - 一些诊断和工具脚本
- `scripts/`
  - 图像和辅助生成脚本
- `data/`
  - 样例或实验数据

## 3. 当前建议的使用方式

先安装：

```bash
cd /home/wys/orangepi/UnderwaterRobotSystem/UnderwaterRobotSystem/offline_nav
pip install -e .
```

注意：

- 当前 `pyproject.toml` 里存在一些入口脚本声明
- 但源码重构后，最稳妥的方式仍然是直接用 `python -m offnav.xxx`

也就是说，阅读和开发时更推荐：

```bash
python -m offnav.cli_raw
python -m offnav.cli_proc
python -m offnav.cli_nav
python -m offnav.cli_dvl
```

## 4. 当前几个主要 CLI

- `offnav.cli_raw`
  - 看原始数据，做基础检查
- `offnav.cli_proc`
  - 做 IMU / DVL 预处理与诊断
- `offnav.cli_nav`
  - 跑离线导航管线
- `offnav.cli_dvl`
  - 专门做 DVL 数据拆分与检查

## 5. 推荐阅读顺序

1. 本 README
2. `configs/快捷命令行.md`
3. `src/offnav/cli_proc.py`
4. `src/offnav/cli_nav.py`
5. `src/offnav/preprocess/`
6. `src/offnav/algo/`
7. `src/offnav/viz/`

## 6. 和在线导航仓的关系

`offline_nav` 和 `nav_core` 的关系是：

- `nav_core` 负责在线产生权威状态和实时日志
- `offline_nav` 负责对原始/处理后数据做离线重算、可视化和诊断

前者面向运行时，后者面向复盘和分析。

## 7. 当前边界与注意事项

这个目录里保留了不少实验性代码、样例数据和历史产物，因此请注意：

- 不要默认所有入口都已经完全收口
- 优先相信当前存在的 `src/offnav/*.py`
- 优先用模块方式调用，而不是盲目依赖旧命令别名

如果你是第一次接触这个目录，先把它当成“离线分析实验台”，不要把它当成已经产品化的离线平台。
