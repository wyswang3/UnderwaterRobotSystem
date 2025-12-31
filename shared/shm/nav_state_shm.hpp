#pragma once
#ifndef SHARED_SHM_NAV_STATE_SHM_HPP
#define SHARED_SHM_NAV_STATE_SHM_HPP

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <type_traits>

#include "shared/msg/nav_state.hpp"

namespace shared::shm {

// -----------------------------------------------------------------------------
// SHM contract for shared::msg::NavState
//
// Design (aligned with your ControlIntent SHM style):
//  - Seqlock header (atomic seq): odd => writing, even => stable
//  - Timestamps: mono_ns / wall_ns filled by publisher (nav process)
//  - Contract tagging: magic + layout_ver
//  - Payload ABI tagging: payload_ver + size + align (hard reject on mismatch)
//  - Payload is POD/trivially-copyable and transferred by memcpy
// -----------------------------------------------------------------------------

// 'N''A''V''1'  (NavState SHM v1)
constexpr std::uint32_t kNavStateMagic =
    (static_cast<std::uint32_t>('N') << 24) |
    (static_cast<std::uint32_t>('A') << 16) |
    (static_cast<std::uint32_t>('V') << 8)  |
    (static_cast<std::uint32_t>('1'));

// SHM header/layout version (independent from payload content version).
constexpr std::uint32_t kNavStateLayoutVersion = 1;

using Payload = shared::msg::NavState;

// Optional: payload wire version
// If you later add a version field to shared::msg::NavState, switch this to that.
// For now, pin at 1 and rely on size/align to detect mismatch.
constexpr std::uint32_t kNavStatePayloadVersion = 1;

// -----------------------------------------------------------------------------
// ShmHeader
// -----------------------------------------------------------------------------
struct ShmHeader final {
    // seqlock: odd => writer in progress, even => stable
    std::atomic<std::uint64_t> seq{0};

    // writer timestamps
    std::uint64_t mono_ns = 0;   // steady clock timestamp at publish time
    std::uint64_t wall_ns = 0;   // system clock timestamp at publish time

    // contract tagging
    std::uint32_t magic      = kNavStateMagic;
    std::uint32_t layout_ver = kNavStateLayoutVersion;

    // payload ABI tagging (hard mismatch => reject)
    std::uint32_t payload_ver   = kNavStatePayloadVersion;
    std::uint32_t payload_size  = static_cast<std::uint32_t>(sizeof(Payload));
    std::uint32_t payload_align = static_cast<std::uint32_t>(alignof(Payload));

    // reserved for future extension
    std::uint32_t reserved0 = 0;
};

// -----------------------------------------------------------------------------
// ShmLayout
// -----------------------------------------------------------------------------
struct ShmLayout final {
    ShmHeader hdr;
    Payload   payload;
};

// -----------------------------------------------------------------------------
// ABI guarantees
// -----------------------------------------------------------------------------
static_assert(std::is_standard_layout_v<Payload>,
              "NavState payload must be standard layout for shm/wire usage.");
static_assert(std::is_trivially_copyable_v<Payload>,
              "NavState payload must be trivially copyable for shm/wire usage.");

static_assert(std::is_standard_layout_v<ShmHeader>,
              "NavState shm header must be standard layout for shm usage.");
static_assert(std::is_trivially_copyable_v<ShmHeader>,
              "NavState shm header must be trivially copyable for shm usage.");

static_assert(std::is_standard_layout_v<ShmLayout>,
              "NavState shm layout must be standard layout for shm usage.");
static_assert(std::is_trivially_copyable_v<ShmLayout>,
              "NavState shm layout must be trivially copyable for shm usage.");

} // namespace shared::shm

#endif // SHARED_SHM_NAV_STATE_SHM_HPP
