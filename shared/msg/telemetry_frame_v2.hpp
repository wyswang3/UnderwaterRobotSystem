#pragma once
#ifndef UWSYS_SHARED_MSG_TELEMETRY_FRAME_V2_HPP
#define UWSYS_SHARED_MSG_TELEMETRY_FRAME_V2_HPP

#include <cstdint>
#include <cstring>
#include <type_traits>

namespace shared::msg {

constexpr std::uint32_t kTelemetryFrameV2WireVersion = 1;
constexpr std::size_t   kTelemetryControllerNameMax  = 32;
constexpr std::size_t   kTelemetryEventHistory       = 16;

enum class TelemetrySource : std::uint8_t {
    kUnknown     = 0,
    kControlCore = 1,
    kGateway     = 2,
};

enum class RuntimeControlMode : std::uint8_t {
    kUnknown  = 0,
    kNone     = 1,
    kManual   = 2,
    kAuto     = 3,
    kFailsafe = 4,
};

enum class ControlSource : std::uint8_t {
    kUnknown = 0,
    kGcs     = 1,
    kLocal   = 2,
    kAuto    = 3,
    kScript  = 4,
    kTest    = 5,
};

enum class ControllerStatus : std::uint8_t {
    kUnknown  = 0,
    kIdle     = 1,
    kRunning  = 2,
    kDegraded = 3,
    kFault    = 4,
};

enum class SessionState : std::uint8_t {
    kUnknown      = 0,
    kDisconnected = 1,
    kConnected    = 2,
    kSessionReady = 3,
};

enum class RuntimeNavState : std::uint8_t {
    kUnknown  = 0,
    kInvalid  = 1,
    kDegraded = 2,
    kOk       = 3,
};

enum class LinkState : std::uint8_t {
    kUnknown  = 0,
    kDown     = 1,
    kAlive    = 2,
    kDegraded = 3,
};

enum class HealthState : std::uint8_t {
    kUnknown  = 0,
    kOk       = 1,
    kDegraded = 2,
    kFault    = 3,
};

enum class CommandResultCode : std::uint8_t {
    kNone     = 0,
    kAccepted = 1,
    kRejected = 2,
    kExecuted = 3,
    kExpired  = 4,
    kFailed   = 5,
};

enum class FaultCode : std::uint16_t {
    kNone                     = 0,
    kCommFault                = 1,
    kSessionFault             = 2,
    kIntentStale              = 3,
    kNavUntrusted             = 4,
    kPwmLinkDown              = 5,
    kStm32LinkDown            = 6,
    kIllegalStateTransition   = 7,
    kArmPreconditionFailed    = 8,
    kMotorTestViolation       = 9,
    kConfigError              = 10,
    kControllerUnavailable    = 11,
    kControllerComputeFailed  = 12,
    kPwmStepFailed            = 13,
};

enum class EventCode : std::uint16_t {
    kNone               = 0,
    kIntentAccepted     = 1,
    kIntentExecuted     = 2,
    kIntentExpired      = 3,
    kIntentFailed       = 4,
    kModeChanged        = 5,
    kFailsafeEntered    = 6,
    kEstopLatched       = 7,
    kEstopCleared       = 8,
    kArmChanged         = 9,
    kMotorTestStarted   = 10,
    kMotorTestStopped   = 11,
    kMotorTestRejected  = 12,
    kNavDegraded        = 13,
    kLinkStateChanged   = 14,
    kSessionStateChanged= 15,
};

struct MotorTestState final {
    std::uint8_t  active      = 0;
    std::uint8_t  motor_id    = 0;
    std::uint8_t  mode        = 0;
    std::uint8_t  reserved0   = 0;

    float         value       = 0.0f;
    std::uint32_t remaining_ms = 0;
    std::uint32_t cmd_id      = 0;
};

struct ControlIntentState final {
    std::uint64_t intent_id   = 0;
    std::uint64_t session_id  = 0;
    std::uint64_t cmd_seq     = 0;
    std::uint64_t stamp_ns    = 0;

    std::uint32_t ttl_ms      = 0;
    std::uint8_t  source      = static_cast<std::uint8_t>(ControlSource::kUnknown);
    std::uint8_t  requested_mode = static_cast<std::uint8_t>(RuntimeControlMode::kUnknown);
    std::uint8_t  arm_cmd     = 0;
    std::uint8_t  estop_cmd   = 0;

    std::uint8_t  valid       = 0;
    std::uint8_t  reserved0[3]{};

    float         dof_cmd[6]  = {0.f, 0.f, 0.f, 0.f, 0.f, 0.f};
    MotorTestState motor_test{};
};

struct ControlState final {
    std::uint8_t  active_mode      = static_cast<std::uint8_t>(RuntimeControlMode::kUnknown);
    std::uint8_t  armed            = 0;
    std::uint8_t  estop_latched    = 0;
    std::uint8_t  failsafe_active  = 0;

    std::uint8_t  control_source   = static_cast<std::uint8_t>(ControlSource::kUnknown);
    std::uint8_t  intent_fresh     = 0;
    std::uint8_t  controller_status = static_cast<std::uint8_t>(ControllerStatus::kUnknown);
    std::uint8_t  motor_test_active = 0;

    std::uint64_t active_intent_id = 0;

    char          controller_name[kTelemetryControllerNameMax]{};
    char          desired_controller[kTelemetryControllerNameMax]{};

    float         dof_cmd_applied[6] = {0.f, 0.f, 0.f, 0.f, 0.f, 0.f};
    float         thruster_cmd[8]    = {0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f};
    float         pwm_duty[8]        = {0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f};

    std::uint32_t consecutive_failures = 0;
    std::uint32_t auto_fail_limit      = 0;
};

struct SystemState final {
    std::uint8_t  session_state   = static_cast<std::uint8_t>(SessionState::kUnknown);
    std::uint8_t  nav_state       = static_cast<std::uint8_t>(RuntimeNavState::kUnknown);
    std::uint8_t  stm32_link_state= static_cast<std::uint8_t>(LinkState::kUnknown);
    std::uint8_t  pwm_link_state  = static_cast<std::uint8_t>(LinkState::kUnknown);

    std::uint8_t  health_state    = static_cast<std::uint8_t>(HealthState::kUnknown);
    std::uint8_t  degraded        = 0;
    std::uint8_t  fault_state     = 0;
    std::uint8_t  reserved0       = 0;

    std::uint16_t last_fault_code = static_cast<std::uint16_t>(FaultCode::kNone);
    std::uint16_t reserved1       = 0;

    std::uint32_t heartbeat_age_ms = 0;
    std::uint32_t nav_age_ms       = 0;

    std::uint8_t  nav_valid       = 0;
    std::uint8_t  nav_health      = 0;
    std::uint8_t  nav_stale       = 0;
    std::uint8_t  nav_degraded    = 0;

    std::uint64_t session_id      = 0;
    float         stm32_last_rtt_ms = -1.0f;

    std::uint64_t pwm_tx_frames   = 0;
    std::uint64_t stm32_hb_tx     = 0;
    std::uint64_t stm32_hb_ack    = 0;
};

struct CommandResult final {
    std::uint64_t intent_id    = 0;
    std::uint64_t cmd_seq      = 0;
    std::uint64_t stamp_ns     = 0;

    std::uint16_t event_code   = static_cast<std::uint16_t>(EventCode::kNone);
    std::uint16_t fault_code   = static_cast<std::uint16_t>(FaultCode::kNone);

    std::uint8_t  status       = static_cast<std::uint8_t>(CommandResultCode::kNone);
    std::uint8_t  source       = static_cast<std::uint8_t>(ControlSource::kUnknown);
    std::uint8_t  reserved0[6]{};
};

struct EventRecord final {
    std::uint64_t seq          = 0;
    std::uint64_t stamp_ns     = 0;

    std::uint16_t event_code   = static_cast<std::uint16_t>(EventCode::kNone);
    std::uint16_t fault_code   = static_cast<std::uint16_t>(FaultCode::kNone);

    std::int32_t  arg0         = 0;
    std::int32_t  arg1         = 0;
};

struct TelemetryFrameV2 final {
    std::uint32_t version      = kTelemetryFrameV2WireVersion;
    std::uint32_t payload_size = static_cast<std::uint32_t>(sizeof(TelemetryFrameV2));

    std::uint64_t seq          = 0;
    std::uint64_t stamp_ns     = 0;

    std::uint8_t  valid        = 0;
    std::uint8_t  source       = static_cast<std::uint8_t>(TelemetrySource::kControlCore);
    std::uint16_t reserved0    = 0;

    ControlIntentState intent{};
    ControlState       control{};
    SystemState        system{};

    float              attitude_rpy[3] = {0.f, 0.f, 0.f};
    float              position[3]     = {0.f, 0.f, 0.f};
    float              velocity[3]     = {0.f, 0.f, 0.f};
    float              depth_m         = 0.0f;

    CommandResult      last_command_result{};
    EventRecord        last_event{};

    std::uint32_t      event_count     = 0;
    std::uint32_t      event_head      = 0;
    EventRecord        events[kTelemetryEventHistory]{};
};

inline void telemetry_write_cstr(char* dst,
                                 std::size_t dst_cap,
                                 const char* src) noexcept
{
    if (!dst || dst_cap == 0) return;
    std::memset(dst, 0, dst_cap);
    if (!src) return;

    std::size_t n = 0;
    while (src[n] != '\0' && n + 1 < dst_cap) {
        dst[n] = src[n];
        ++n;
    }
}

static_assert(std::is_standard_layout_v<MotorTestState>,
              "MotorTestState must be standard layout.");
static_assert(std::is_trivially_copyable_v<MotorTestState>,
              "MotorTestState must be trivially copyable.");
static_assert(std::is_standard_layout_v<ControlIntentState>,
              "ControlIntentState must be standard layout.");
static_assert(std::is_trivially_copyable_v<ControlIntentState>,
              "ControlIntentState must be trivially copyable.");
static_assert(std::is_standard_layout_v<ControlState>,
              "ControlState must be standard layout.");
static_assert(std::is_trivially_copyable_v<ControlState>,
              "ControlState must be trivially copyable.");
static_assert(std::is_standard_layout_v<SystemState>,
              "SystemState must be standard layout.");
static_assert(std::is_trivially_copyable_v<SystemState>,
              "SystemState must be trivially copyable.");
static_assert(std::is_standard_layout_v<CommandResult>,
              "CommandResult must be standard layout.");
static_assert(std::is_trivially_copyable_v<CommandResult>,
              "CommandResult must be trivially copyable.");
static_assert(std::is_standard_layout_v<EventRecord>,
              "EventRecord must be standard layout.");
static_assert(std::is_trivially_copyable_v<EventRecord>,
              "EventRecord must be trivially copyable.");
static_assert(std::is_standard_layout_v<TelemetryFrameV2>,
              "TelemetryFrameV2 must be standard layout.");
static_assert(std::is_trivially_copyable_v<TelemetryFrameV2>,
              "TelemetryFrameV2 must be trivially copyable.");

} // namespace shared::msg

#endif // UWSYS_SHARED_MSG_TELEMETRY_FRAME_V2_HPP
