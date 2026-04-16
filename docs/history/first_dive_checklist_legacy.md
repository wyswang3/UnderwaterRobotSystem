# First Dive Experiment Checklist

## 1. System Overview

This experiment runs on:
- Main controller SBC: Orange Pi 3B
- PWM output board (8 channels): STM32F4
- IMU sensor (RS485, Modbus RTU): WT901C-485
- Doppler velocity sensor (10 Hz reference): DVL Hover H1000
- Motion pipeline: **Read → Timestamp → Record → Backup → Offline Process**

**Important rule:** During the first dive, we perform **data acquisition only**, without online navigation or filter tuning.

---

## 2. Sensors to Be Recorded

| Sensor | Frequency | Fields to record | Purpose |
|---|---:|---|---|
| WT901C-485 (IMU) | 100 Hz | Acceleration (g), angular velocity (rad/s), quaternion, temperature, magnetic angles | State observation & rotation matrix calculation |
| DVL Hover H1000 | 10 Hz | Valid minimal speed (m/s), altitude/distance, validity flag | Underwater velocity baseline for cross-calibration |
| PWM Output | 100 Hz | 8-channel duty cycle (float 0-1.0), AB group toggle state | Thruster allocation & future neural net training |
| Depth sensor (optional parallel note) | 10-50 Hz | Depth (meters), validity | Future Kalman filter accuracy improvement |

---

## 3. 现场操作流程（分步执行）

### 3.1 入水前（Boot & Connection）
1. 确认 Orange Pi 3B 上电正常
2. 连接 485-USB Adapter 并确认串口设备（`ttyUSB`）显示
3. 运行 IMU + DVL 读取脚本，确认无报错
4. 校准笔记准备好（纸笔现场记录，**不写入程序**）

### 3.2 运行 Python 采集（2 小时）
5. 启动 脚本（控制 loop 100 Hz）
6. 采集过程中不得关闭脚本
7. 观察 10 分钟内前 10 步 IMU 加速度平均值，**作为漂移备案参考**
8. 观察前 10 个 DVL 读数是否 valid，记录“首 valid 时刻”
9. 若出现速度或位移跳变：
   - 标记时间段为 `abnormal segment`
   - 不删除数据，只备注“不可信 / 待后检”
10. 若出现串口或UDP中断：
   - 立即调用 `emergencyStop()` 归零 PWM 下发
   - 记录系统错误码与错误信息
11. 运行至 2 小时结束，手动停止采集脚本

### 3.3 运行 C++ 导航 Runtime（30 分钟）
12. 启动 30 min `nav_daemon` 运行（仅读取 IMU + DVL，不做滤波与导航决策）
13. 关闭 Runtime，准备离线数据导出与对比

---

## 4. 现场移动平台中观察与记录（Equipment Notes）

| 现场现象 | 记录内容 | 现场动作 |
|---|---|---|
| IMU 读数不稳定 | 前 10 步线加速度平均值（g） | 只记录，不调参 |
| DVL 有效速度出现前的杂数据 | 首次 valid 速度时刻 | 等待 1-2 秒稳定，不强制删除 |
| 机器人姿态过快变化 | 记录角速度最大值（rad/s） | 执行紧急停机备用逻辑 |
| 485 或 UDP 连接 reset | 记录通信断开时刻 | 立即 emergencyStop 保护 |
| 外部干扰（泵/池壁/电源等） | 干扰类型与时间段 | 备注，不删除 |

---

## 5. Safety Protections (Newcomer Must Understand)

### 5.1 AB Group Channel Protection Mechanism
- 8 通道推进器会按 **A/B 组交替下发 PWM**
- 作用：防止电源 / MCU / 485 负载瞬时冲击引发系统 reset
- 交替频率：**100 Hz 控制 loop 兼容**
- 现场新人不需修改 duty，只需理解“**为什么交替**”并记录 toggle 状态

### 5.2 Rollback Threshold Note (Offline Use)
Python 端已有回退模块，但现场新人负责观察并记录这些时刻，而不是在线更改参数：

- 速度**突增** threshold: `|Δv| > 0.8 m/s within 0.2 s`
- 位置**跳变** threshold: `|Δp| > 0.5 m within 0.1 s`
- 现场动作：记录时间段，实验后 Python 端再进行回退数据处理 & 模型调参

---

## 6. 采集后处理目的（新人必须知晓我们之后要做什么）

数据采集完成后，我们将在 Python 端（离线）完成：

1. Timestamp alignment & interpolation (IMU 100Hz ⇄ DVL 10Hz)
2. Noise filtering (Median / Hampel / Low-pass)
3. Body frame → Inertial frame rotation matrix calculation
4. Kalman Q/R matrix tuning
5. Build cross-validation plots (velocity/acc/attitude)
6. Prepare training dataset (PWM → thrust dynamics NN)
7. Final MPC/KF parameters migration to C++

---

## 7. Deliverables Confirmation Before Leaving Test Pool

- 完整_raw_日志不可编辑或删除
- 立即备份 logs 目录到 data 归档目录，以日期命名
- 命名规范参考：
  - `imu_raw_data_YYYYMMDD.csv`
  - `dvl_speed_min_tb_YYYYMMDD.csv`
  - `pwm_duty_8ch_YYYYMMDD.csv`
  - `depth_data_YYYYMMDD.csv` (如启用)

---

## 8. Final Summary

- 本次实验**仅读取和记录数据，不参与导航解算**
- 100Hz 控制 loop 已兼容入水并行采集
- 需现场观察速度/位姿跳变并记录异常段
- 采集 2h Python raw logs + 30 min C++ runtime logs 用于互校
- 所有滤波、回退、坐标变换与卡尔曼参数调参，均放在**离线 Python 端完成**
