#pragma once
#ifndef UWSYS_SHARED_MSG_NAV_STATE_HPP
#define UWSYS_SHARED_MSG_NAV_STATE_HPP

/**
 * @file   nav_state.hpp
 * @brief  导航状态在「导航进程 ↔ 控制进程」之间的共享消息定义（跨项目通用）
 *
 * 设计目标：
 *   - 仅依赖标准头文件，可在任意 C++17 项目中直接 include；
 *   - POD / 平凡布局，便于通过共享内存 / ZeroMQ / UDP 直接按字节发送；
 *   - 字段语义清晰，既能满足 PID，也能满足后续 MPC / 轨迹控制需求；
 *   - 导航项目（Underwater-robot-navigation）和控制项目
 *     （OrangePi_STM32_for_ROV）统一使用此定义，避免结构漂移。
 *
 * 时间基准约定：
 *   - t_ns 使用「单调时钟」的纳秒计数（std::chrono::steady_clock）；
 *   - t_ns 表示“当前导航状态真正对应的估计时间”，不是发布线程的当前时间；
 *   - age_ms 表示该状态在当前发布时刻已经老化了多少毫秒；
 *   - 控制程序若还要叠加 gateway / 本地消费延迟，应在后续 hop 上继续累加 age_ms，
 *     而不是重新解释 t_ns。
 */

#include <cstdint>
#include <type_traits>

namespace shared::msg {

/**
 * @brief 导航整体健康状况（粗粒度）
 */
enum class NavHealth : std::uint8_t {
    UNINITIALIZED = 0,   ///< 尚未完成初始化 / 尚无有效状态
    OK            = 1,   ///< 工作正常（IMU + DVL + 深度等基本可用）
    DEGRADED      = 2,   ///< 降级模式（例如 DVL 丢失，仅惯导）
    INVALID       = 3    ///< 状态不可用，控制侧建议进入 failsafe
};

/**
 * @brief 导航发布状态机（控制侧消费的主语义）
 *
 * 说明：
 *   - NavHealth 负责表达“质量等级”；
 *   - NavRunState 负责表达“当前处于什么生命周期阶段”；
 *   - 控制侧必须优先看 NavRunState/valid/stale/fault_code，而不是只看数值字段。
 */
enum class NavRunState : std::uint8_t {
    kUninitialized = 0,  ///< 尚未拿到足够输入，不能解释数值字段
    kAligning      = 1,  ///< 传感器已上线，但对准 / bias 建立未完成
    kOk            = 2,  ///< 可正常用于控制
    kDegraded      = 3,  ///< 可用于受限控制，但部分传感器缺失
    kInvalid       = 4   ///< 输出明确不可用于闭环
};

/**
 * @brief 导航失效原因码（硬故障/不可用原因）
 *
 * 约定：
 *   - valid=1 的正常 / 降级状态应尽量使用 kNone；
 *   - fault_code 非零时，控制侧应视为“需要明确处理”的异常，而不是模糊地当作 false。
 */
enum class NavFaultCode : std::uint16_t {
    kNone                  = 0,
    kEstimatorUninitialized= 1,
    kAlignmentPending      = 2,
    kImuNoData             = 3,
    kImuStale              = 4,
    kDepthStale            = 5,
    kEstimatorNumericInvalid = 6,
    kNavOutputStale        = 7,
    kNavViewStale          = 8,
    kNoData                = 9,
    kImuDeviceNotFound     = 10,
    kImuDeviceMismatch     = 11,
    kImuDisconnected       = 12,
    kDvlDeviceNotFound     = 13,
    kDvlDeviceMismatch     = 14,
    kDvlDisconnected       = 15,
};

/**
 * @brief 当前可参与导航输出的传感器 bitmask。
 *
 * sensor_mask 只表达“当前这帧状态所依赖/确认新鲜的传感器”：
 *   - bit 置位：该传感器数据在本帧语义下是 fresh / usable；
 *   - bit 清零：该传感器缺失、过期、未接入，或当前不可信。
 */
enum NavSensorBits : std::uint16_t {
    NAV_SENSOR_NONE  = 0,
    NAV_SENSOR_IMU   = 1u << 0,
    NAV_SENSOR_DVL   = 1u << 1,
    NAV_SENSOR_DEPTH = 1u << 2,
    NAV_SENSOR_USBL  = 1u << 3,
};

/**
 * @brief 传感器 / 估计器状态的 bitmask（细粒度）
 *
 * 可按需组合：
 *   - IMU / DVL / 深度 / USBL 单独是否可用；
 *   - ESKF 当前是否正常收敛等。
 */
enum NavStatusFlags : std::uint16_t {
    NAV_FLAG_NONE        = 0,

    NAV_FLAG_IMU_OK      = 1u << 0,   ///< IMU 数据正常
    NAV_FLAG_DVL_OK      = 1u << 1,   ///< DVL 速度有效
    NAV_FLAG_DEPTH_OK    = 1u << 2,   ///< 深度传感器正常
    NAV_FLAG_USBL_OK     = 1u << 3,   ///< USBL / 外部定位正常

    NAV_FLAG_ESKF_OK     = 1u << 4,   ///< ESKF / 状态估计算法正常
    NAV_FLAG_ALIGN_DONE  = 1u << 5,   ///< 完成初始对准 / 零偏估计

    NAV_FLAG_IMU_DEVICE_ONLINE   = 1u << 6,   ///< IMU 设备当前已绑定且驱动在线
    NAV_FLAG_DVL_DEVICE_ONLINE   = 1u << 7,   ///< DVL 设备当前已绑定且驱动在线
    NAV_FLAG_IMU_BIND_MISMATCH   = 1u << 8,   ///< 找到了设备，但身份不匹配
    NAV_FLAG_DVL_BIND_MISMATCH   = 1u << 9,   ///< 找到了设备，但身份不匹配
    NAV_FLAG_IMU_RECONNECTING    = 1u << 10,  ///< IMU 处于 probing/backoff/reconnect 中
    NAV_FLAG_DVL_RECONNECTING    = 1u << 11,  ///< DVL 处于 probing/backoff/reconnect 中
    NAV_FLAG_RESERVED12  = 1u << 12,
    NAV_FLAG_RESERVED13  = 1u << 13,
    NAV_FLAG_RESERVED14  = 1u << 14,
    NAV_FLAG_RESERVED15  = 1u << 15
};

// （可选但推荐）bitmask 辅助函数：避免散落的强转
constexpr inline std::uint16_t nav_flag_u16(NavStatusFlags f) noexcept {
    return static_cast<std::uint16_t>(f);
}
constexpr inline bool nav_flag_has(std::uint16_t flags, NavStatusFlags f) noexcept {
    return (flags & nav_flag_u16(f)) != 0;
}
constexpr inline void nav_flag_set(std::uint16_t& flags, NavStatusFlags f) noexcept {
    flags = static_cast<std::uint16_t>(flags | nav_flag_u16(f));
}
constexpr inline void nav_flag_clear(std::uint16_t& flags, NavStatusFlags f) noexcept {
    flags = static_cast<std::uint16_t>(flags & static_cast<std::uint16_t>(~nav_flag_u16(f)));
}

constexpr inline std::uint16_t nav_sensor_u16(NavSensorBits b) noexcept {
    return static_cast<std::uint16_t>(b);
}
constexpr inline bool nav_sensor_has(std::uint16_t mask, NavSensorBits b) noexcept {
    return (mask & nav_sensor_u16(b)) != 0;
}
constexpr inline void nav_sensor_set(std::uint16_t& mask, NavSensorBits b) noexcept {
    mask = static_cast<std::uint16_t>(mask | nav_sensor_u16(b));
}
constexpr inline void nav_sensor_clear(std::uint16_t& mask, NavSensorBits b) noexcept {
    mask = static_cast<std::uint16_t>(mask & static_cast<std::uint16_t>(~nav_sensor_u16(b)));
}

/**
 * @brief 导航状态主结构（跨进程共享的“语言”）
 */
struct NavState
{
    std::uint64_t t_ns{0};      ///< 当前状态真正对应的估计时间（steady ns）

    // ---- 1. 导航层基础输出 (NED/ENU) ----
    double pos[3]{0.0, 0.0, 0.0};           ///< 位置: [x, y, z]
    double vel[3]{0.0, 0.0, 0.0};           ///< 速度: [vx, vy, vz]
    double rpy[3]{0.0, 0.0, 0.0};           ///< 姿态: roll, pitch, yaw (rad)

    double depth{0.0};            ///< 深度 [m]，下为正

    // ---- 2. 高频动力学量（body 坐标系）----
    double omega_b[3]{0.0, 0.0, 0.0};       ///< 机体系角速度 [wx, wy, wz], rad/s
    double acc_b[3]{0.0, 0.0, 0.0};         ///< 机体系线加速度 [ax, ay, az], m/s^2

    // ---- 3. 显式状态语义（控制侧必须优先消费）----
    std::uint32_t age_ms{0xFFFFFFFFu}; ///< 当前状态在本 hop 发布时已经老化的时间
    std::uint8_t  valid{0};            ///< 1=可用于闭环；0=严禁当作可信导航
    std::uint8_t  stale{1};            ///< 1=时间上已经过期；0=时间仍新鲜
    std::uint8_t  degraded{0};         ///< 1=可控但降级；0=非降级
    NavRunState   nav_state{NavRunState::kUninitialized};
    NavHealth     health{NavHealth::UNINITIALIZED};
    std::uint8_t  reserved0{0};        ///< 未来可扩展为 mode/profile 编号
    NavFaultCode  fault_code{NavFaultCode::kNone};
    std::uint16_t sensor_mask{NAV_SENSOR_NONE}; ///< 当前这帧确认 fresh 的传感器集合
    std::uint16_t status_flags{NAV_FLAG_NONE};  ///< bitmask（NavStatusFlags 的组合）
    std::uint16_t reserved1{0};
};

// ABI/传输约束：编译期钉死
static_assert(sizeof(NavState) % 4 == 0,
              "NavState size should be 4-byte aligned for efficient transport");
static_assert(std::is_trivially_copyable_v<NavState>,
              "NavState must be trivially copyable for shm/byte transport.");
static_assert(std::is_trivially_copyable_v<NavHealth>,
              "NavHealth must be trivially copyable.");
static_assert(std::is_trivially_copyable_v<NavRunState>,
              "NavRunState must be trivially copyable.");
static_assert(std::is_trivially_copyable_v<NavFaultCode>,
              "NavFaultCode must be trivially copyable.");

} // namespace shared::msg

#endif // UWSYS_SHARED_MSG_NAV_STATE_HPP
