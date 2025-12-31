#pragma once
#ifndef SHARED_MSG_NAV_STATE_VIEW_HPP
#define SHARED_MSG_NAV_STATE_VIEW_HPP

#include <cstdint>
#include <type_traits>

namespace shared::msg {

// -----------------------------------------------------------------------------
// Versioning
// -----------------------------------------------------------------------------
constexpr std::uint32_t kNavStateViewWireVersion = 1;

// -----------------------------------------------------------------------------
// Flags / Quality
// -----------------------------------------------------------------------------
enum NavStateViewFlags : std::uint32_t {
    kHasPosition   = 1u << 0,
    kHasVelocity   = 1u << 1,
    kHasRPY        = 1u << 2,
    kHasDepth      = 1u << 3,
    kHasOmegaBody  = 1u << 4,
    kHasAccBody    = 1u << 5,
};

enum class NavHealthView : std::uint8_t {
    kUnknown = 0,
    kOk      = 1,
    kDegraded= 2,
    kBad     = 3,
};

// -----------------------------------------------------------------------------
// NavStateView (stable control-facing view)
// -----------------------------------------------------------------------------
struct NavStateView final
{
    // ---- wire / ABI header ----
    std::uint32_t version   = kNavStateViewWireVersion;
    std::uint32_t flags     = 0;

    // timestamps
    std::uint64_t stamp_ns  = 0;   // navigation timestamp (sensor / fusion time)
    std::uint64_t mono_ns   = 0;   // comm_gcs publish time (steady clock)
    std::uint32_t age_ms    = 0;   // filled by comm_gcs
    std::uint8_t  valid     = 0;   // 0/1, filled by comm_gcs
    std::uint8_t  health    = static_cast<std::uint8_t>(NavHealthView::kUnknown);

    std::uint16_t reserved0 = 0;

    // ---- kinematics (nav frame unless otherwise stated) ----
    double pos[3]   = {0.0, 0.0, 0.0};  // position (e.g. NED / ENU, system-defined)
    double vel[3]   = {0.0, 0.0, 0.0};  // linear velocity
    double rpy[3]   = {0.0, 0.0, 0.0};  // roll/pitch/yaw (rad)

    double depth_m  = 0.0;

    // ---- body-frame quantities ----
    double omega_b[3] = {0.0, 0.0, 0.0}; // body angular rate (rad/s)
    double acc_b[3]   = {0.0, 0.0, 0.0}; // body linear acceleration (m/s^2)

    // ---- reserved for forward compatibility ----
    std::uint32_t reserved1 = 0;
    std::uint32_t reserved2 = 0;
};

// -----------------------------------------------------------------------------
// ABI guarantees
// -----------------------------------------------------------------------------
static_assert(std::is_standard_layout_v<NavStateView>,
              "NavStateView must be standard layout for shm/wire usage.");
static_assert(std::is_trivially_copyable_v<NavStateView>,
              "NavStateView must be trivially copyable for shm/wire usage.");

} // namespace shared::msg

#endif // SHARED_MSG_NAV_STATE_VIEW_HPP
