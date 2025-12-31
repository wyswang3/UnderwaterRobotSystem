#pragma once
#ifndef SHARED_SHM_KEY_EVENT_SHM_HPP
#define SHARED_SHM_KEY_EVENT_SHM_HPP

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <type_traits>

#include "shared/msg/key_event.hpp"

namespace shared::shm {

// 'K''E''V''1'
constexpr std::uint32_t kKeyEventMagic =
    (static_cast<std::uint32_t>('K') << 24) |
    (static_cast<std::uint32_t>('E') << 16) |
    (static_cast<std::uint32_t>('V') << 8)  |
    (static_cast<std::uint32_t>('1'));

constexpr std::uint32_t kKeyEventLayoutVersion = 1;

using Payload = shared::msg::KeyEvent;

struct ShmHeader final {
    // seqlock: odd => writer in progress, even => stable snapshot
    std::atomic<std::uint64_t> seqlock{0};

    // publisher timestamps (optional; convenient for health)
    std::uint64_t mono_ns = 0;
    std::uint64_t wall_ns = 0;

    std::uint32_t magic      = kKeyEventMagic;
    std::uint32_t layout_ver = kKeyEventLayoutVersion;

    std::uint32_t payload_ver   = shared::msg::kKeyEventWireVersion;
    std::uint32_t payload_size  = static_cast<std::uint32_t>(sizeof(Payload));
    std::uint32_t payload_align = static_cast<std::uint32_t>(alignof(Payload));

    std::uint32_t capacity = 0;   // ring capacity (N)
    std::uint32_t reserved0 = 0;
};

// Ring buffer layout:
// - writer advances write_seq monotonically
// - reader stores last_read_seq locally (no shared tail)
template<std::size_t N>
struct ShmLayoutT final {
    ShmHeader hdr;

    // monotonically increasing sequence counters
    std::atomic<std::uint64_t> write_seq{0};

    // ring payload
    Payload ring[N];
};

static_assert(std::is_standard_layout_v<ShmHeader>);
static_assert(std::is_trivially_copyable_v<ShmHeader>);

} // namespace shared::shm

#endif // SHARED_SHM_KEY_EVENT_SHM_HPP
