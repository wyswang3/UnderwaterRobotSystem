#pragma once
#ifndef SHARED_SHM_NAV_STATE_VIEW_SHM_HPP
#define SHARED_SHM_NAV_STATE_VIEW_SHM_HPP

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <type_traits>

#include "shared/msg/nav_state_view.hpp"

namespace shared::shm {

// -----------------------------------------------------------------------------
// SHM contract for NavStateView
//
// Layout philosophy (matches your ControlIntent SHM style):
//  - Seqlock header (atomic seq) + timestamps + magic/version tagging
//  - Payload is POD / trivially-copyable and copied via memcpy
//  - Header carries payload ABI metadata for hard rejection on mismatch
// -----------------------------------------------------------------------------

// 'N''V''W''1'  (NavView v1)
constexpr std::uint32_t kNavViewMagic =
    (static_cast<std::uint32_t>('N') << 24) |
    (static_cast<std::uint32_t>('V') << 16) |
    (static_cast<std::uint32_t>('W') << 8)  |
    (static_cast<std::uint32_t>('1'));

// SHM header/layout version (independent from payload wire version).
constexpr std::uint32_t kNavViewLayoutVersion = 1;

using Payload = shared::msg::NavStateView;

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
    std::uint32_t magic       = kNavViewMagic;
    std::uint32_t layout_ver  = kNavViewLayoutVersion;

    // payload ABI tagging (hard mismatch => reject)
    std::uint32_t payload_ver   = shared::msg::kNavStateViewWireVersion;
    std::uint32_t payload_size  = static_cast<std::uint32_t>(sizeof(Payload));
    std::uint32_t payload_align = static_cast<std::uint32_t>(alignof(Payload));

    // reserved for future extension (keep header size stable-ish)
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
static_assert(std::is_standard_layout_v<ShmHeader>,
              "ShmHeader must be standard layout for shm usage.");
static_assert(std::is_trivially_copyable_v<ShmHeader>,
              "ShmHeader must be trivially copyable for shm usage.");

static_assert(std::is_standard_layout_v<ShmLayout>,
              "ShmLayout must be standard layout for shm usage.");
static_assert(std::is_trivially_copyable_v<ShmLayout>,
              "ShmLayout must be trivially copyable for shm usage.");

} // namespace shared::shm

#endif // SHARED_SHM_NAV_STATE_VIEW_SHM_HPP
