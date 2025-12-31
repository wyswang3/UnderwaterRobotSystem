#pragma once
#ifndef SHARED_SHM_KEY_EVENT_RING_SHM_HPP
#define SHARED_SHM_KEY_EVENT_RING_SHM_HPP

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <type_traits>

#include "shared/msg/key_event.hpp"

namespace shared::shm {

// -----------------------------------------------------------------------------
// SHM contract: KeyEvent ring buffer (single-writer friendly)
//
// Design goals:
//  - Publisher owns creation (shm_open O_CREAT|O_RDWR + ftruncate + mmap).
//  - Subscriber opens existing (O_RDONLY) and mmaps read-only.
//  - ABI safety: magic + layout_ver + payload_ver + size + align + capacity.
//  - Seqlock: odd => writer in progress, even => stable snapshot.
//  - Ring semantics: overwrite-on-write (non-blocking).
//    Subscriber tracks its own read_idx and may miss events if lagging.
//
// Notes:
//  - Capacity is stored in header; the mapped shm size must match
//    sizeof(Header) + capacity*sizeof(KeyEvent).
//  - This header intentionally does NOT expose OS-specific shm APIs.
// -----------------------------------------------------------------------------

// 'K''E''Y''1'
constexpr std::uint32_t kKeyEventRingMagic =
    (static_cast<std::uint32_t>('K') << 24) |
    (static_cast<std::uint32_t>('E') << 16) |
    (static_cast<std::uint32_t>('Y') << 8)  |
    (static_cast<std::uint32_t>('1'));

constexpr std::uint32_t kKeyEventRingLayoutVersion = 1;

using Payload = shared::msg::KeyEvent;

// If you later version KeyEvent payload, bump this in shared/msg/key_event.hpp.
constexpr std::uint32_t kKeyEventPayloadVersion = shared::msg::kKeyEventWireVersion;

// -----------------------------------------------------------------------------
// Header
// -----------------------------------------------------------------------------
struct KeyEventRingShmHeader final {
    // Seqlock: odd => writing, even => stable
    std::atomic<std::uint64_t> seqlock{0};

    // Timestamps updated by publisher on every publish batch
    std::uint64_t mono_ns = 0;  // CLOCK_MONOTONIC / steady_clock
    std::uint64_t wall_ns = 0;  // system_clock

    // Contract tagging
    std::uint32_t magic      = kKeyEventRingMagic;
    std::uint32_t layout_ver = kKeyEventRingLayoutVersion;

    // Payload ABI tagging (hard reject on mismatch)
    std::uint32_t payload_ver   = kKeyEventPayloadVersion;
    std::uint32_t payload_size  = static_cast<std::uint32_t>(sizeof(Payload));
    std::uint32_t payload_align = static_cast<std::uint32_t>(alignof(Payload));

    // Ring metadata
    std::uint32_t capacity = 0;     // number of Payload slots in ring
    std::uint32_t reserved0 = 0;    // keep alignment / future use

    // Monotonic write index (ever-increasing). Slot = write_idx % capacity.
    std::uint64_t write_idx = 0;

    // Diagnostics: publisher may increment when it detects internal drops.
    // (Ring itself overwrites; subscriber detects loss by idx jump.)
    std::uint64_t drop_count = 0;

    // Reserved for future extension
    std::uint64_t reserved1 = 0;
};

// -----------------------------------------------------------------------------
// Layout (header + variable-length ring storage)
// -----------------------------------------------------------------------------
struct KeyEventRingShmLayout final {
    KeyEventRingShmHeader hdr;
    Payload               ring[1]; // placeholder for variable-length mapping
};

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------
inline constexpr std::size_t key_event_ring_bytes(std::uint32_t capacity) noexcept
{
    return sizeof(KeyEventRingShmHeader) + static_cast<std::size_t>(capacity) * sizeof(Payload);
}

inline Payload* key_event_ring_ptr(KeyEventRingShmHeader* hdr) noexcept
{
    // Ring storage begins immediately after header.
    auto* base = reinterpret_cast<std::uint8_t*>(hdr);
    return reinterpret_cast<Payload*>(base + sizeof(KeyEventRingShmHeader));
}

inline const Payload* key_event_ring_ptr(const KeyEventRingShmHeader* hdr) noexcept
{
    auto* base = reinterpret_cast<const std::uint8_t*>(hdr);
    return reinterpret_cast<const Payload*>(base + sizeof(KeyEventRingShmHeader));
}

// -----------------------------------------------------------------------------
// ABI guarantees
// -----------------------------------------------------------------------------
static_assert(std::is_standard_layout_v<Payload>,
              "KeyEvent payload must be standard layout for shm/wire usage.");
static_assert(std::is_trivially_copyable_v<Payload>,
              "KeyEvent payload must be trivially copyable for shm/wire usage.");

static_assert(std::is_standard_layout_v<KeyEventRingShmHeader>,
              "KeyEventRingShmHeader must be standard layout.");
static_assert(std::is_trivially_copyable_v<KeyEventRingShmHeader>,
              "KeyEventRingShmHeader must be trivially copyable.");

} // namespace shared::shm

#endif // SHARED_SHM_KEY_EVENT_RING_SHM_HPP
