#pragma once
#ifndef SHARED_MSG_NAV_STATE_VIEW_HPP
#define SHARED_MSG_NAV_STATE_VIEW_HPP

#include <cstdint>
#include <type_traits>

#include "shared/msg/nav_state.hpp"

namespace shared::msg {

// -----------------------------------------------------------------------------
// Versioning
// -----------------------------------------------------------------------------
constexpr std::uint32_t kNavStateViewWireVersion = 2;

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

// -----------------------------------------------------------------------------
// NavStateView (stable control-facing view)
// -----------------------------------------------------------------------------
struct NavStateView final
{
    // ---- wire / ABI header ----
    std::uint32_t version   = kNavStateViewWireVersion;
    std::uint32_t flags     = 0;

    // timestamps
    std::uint64_t stamp_ns  = 0;            // navigation estimate timestamp (steady clock)
    std::uint64_t mono_ns   = 0;            // gateway publish time for this hop
    std::uint32_t age_ms    = 0xFFFFFFFFu;  // accumulated age up to this hop
    std::uint8_t  valid     = 0;            // 1=control-usable, 0=must reject
    std::uint8_t  stale     = 1;            // 1=age already exceeded budget on this hop
    std::uint8_t  degraded  = 0;            // 1=usable but degraded
    NavRunState   nav_state = NavRunState::kUninitialized;
    NavHealth     health    = NavHealth::UNINITIALIZED;
    std::uint8_t  reserved0 = 0;
    NavFaultCode  fault_code = NavFaultCode::kNone;
    std::uint16_t sensor_mask = NAV_SENSOR_NONE;
    std::uint16_t status_flags = NAV_FLAG_NONE;
    std::uint16_t reserved1 = 0;

    // ---- kinematics (nav frame unless otherwise stated) ----
    double pos[3]   = {0.0, 0.0, 0.0};  // position (e.g. NED / ENU, system-defined)
    double vel[3]   = {0.0, 0.0, 0.0};  // linear velocity
    double rpy[3]   = {0.0, 0.0, 0.0};  // roll/pitch/yaw (rad)

    double depth_m  = 0.0;

    // ---- body-frame quantities ----
    double omega_b[3] = {0.0, 0.0, 0.0}; // body angular rate (rad/s)
    double acc_b[3]   = {0.0, 0.0, 0.0}; // body linear acceleration (m/s^2)

    // ---- reserved for forward compatibility ----
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
