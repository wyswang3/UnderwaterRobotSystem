#pragma once
#include <cstdint>
#include <type_traits>

namespace shared::msg {

constexpr std::uint32_t kControlIntentWireVersion = 1;

enum IntentFlags : std::uint32_t {
    kHasEStopCmd      = 1u << 0,
    kHasArmCmd        = 1u << 1,
    kHasModeRequest   = 1u << 2,
    kHasTeleopDof     = 1u << 3,
    kHasRef           = 1u << 4,
    kHasRefDelta      = 1u << 5,
    kHasExitRequest   = 1u << 6,   // NEW
    kHasMotorTest     = 1u << 7,   // NEW

};


enum class ControlMode : std::uint8_t {
    kNone   = 0,
    kManual = 1,
    kAuto   = 2,
    kHold   = 3,
};

enum class IntentSource : std::uint8_t {
    kUnknown = 0,
    kGcs     = 1,
    kLocal   = 2,
    kAuto    = 3,
    kTest    = 4,
};

struct DofCommand final {
    double surge = 0.0;
    double sway  = 0.0;
    double heave = 0.0;
    double roll  = 0.0;
    double pitch = 0.0;
    double yaw   = 0.0;
};

struct MotorTestCmd final {
    std::uint8_t enable     = 0;   // 1=请求开始/维持测试，0=无测试
    std::uint8_t motor_id   = 0;   // 1..8
    std::uint8_t mode       = 0;   // 0=neutral+delta, 1=absolute_pwm (可选)
    std::uint8_t reserved0  = 0;

    float value = 0.0f;            // mode=0: [-1..+1] 推力/归一化; mode=1: PWM 绝对值
    std::uint16_t duration_ms = 500; // 自动超时（建议上限 1000ms）
    std::uint16_t reserved1   = 0;

    std::uint32_t cmd_id = 0;      // 可选：用于去重/日志（由 source 递增）
};


struct ControlIntent final
{
    // ---- wire versioning ----
    std::uint32_t version  = kControlIntentWireVersion;
    std::uint32_t flags    = 0;

    // ---- sequencing / timing ----
    std::uint64_t cmd_seq  = 0;   // monotonic sequence from source
    std::uint64_t stamp_ns = 0;   // source timestamp (mono_ns recommended)
    std::uint32_t ttl_ms   = 0;   // 0 => "use receiver default" or "no ttl" (policy-defined)

    // ---- source meta ----
    std::uint8_t  source_id   = static_cast<std::uint8_t>(IntentSource::kUnknown);
    std::uint8_t  source_prio = 0;    // optional 0..255
    std::uint16_t pad_src     = 0;    // keep alignment stable

    // ---- wire-safe bools: 0/1 ----
    std::uint8_t  request_exit = 0;

    std::uint8_t  estop       = 0;
    std::uint8_t  clear_estop = 0;

    std::uint8_t  arm         = 0;
    std::uint8_t  disarm      = 0;

    // padding to keep alignment stable (optional)
    std::uint8_t  pad0 = 0;
    std::uint8_t  pad1 = 0;
    std::uint8_t  pad2 = 0;

    ControlMode mode_request = ControlMode::kNone;

    // align to 8 for the doubles below (optional)
    std::uint8_t  pad3[7] = {};

    DofCommand teleop_dof_cmd{};
    MotorTestCmd motor_test{};


    std::uint32_t reserved0 = 0;
    std::uint32_t reserved1 = 0;

    void clear_payload() noexcept {
        request_exit = 0;

        estop = 0;
        clear_estop = 0;

        arm = 0;
        disarm = 0;

        mode_request = ControlMode::kNone;
        teleop_dof_cmd = DofCommand{};

        flags = 0;
    }

    void clear_all() noexcept {
        version  = kControlIntentWireVersion;
        flags    = 0;
        cmd_seq  = 0;
        stamp_ns = 0;
        ttl_ms   = 0;

        source_id   = static_cast<std::uint8_t>(IntentSource::kUnknown);
        source_prio = 0;
        pad_src     = 0;

        clear_payload();
    }
};

static_assert(std::is_standard_layout<ControlIntent>::value,
              "ControlIntent must be standard layout for shm/wire usage.");
static_assert(std::is_trivially_copyable<ControlIntent>::value,
              "ControlIntent must be trivially copyable for shm/wire usage.");

} // namespace shared::msg
