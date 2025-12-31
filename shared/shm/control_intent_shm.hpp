#pragma once
#include <atomic>
#include <cstdint>
#include <type_traits>

#include "shared/msg/control_intent.hpp"

namespace shared::shm {

// 'I''N''T''1'
constexpr std::uint32_t kIntentShmMagic =
    (static_cast<std::uint32_t>('I') << 24) |
    (static_cast<std::uint32_t>('N') << 16) |
    (static_cast<std::uint32_t>('T') << 8)  |
    (static_cast<std::uint32_t>('1'));

// SHM 布局版本：只要 header/payload 的布局改变就 bump
constexpr std::uint32_t kIntentShmLayoutVersion = 1;

struct IntentShmHeader final {
    // seqlock: odd=writing, even=stable
    std::atomic<std::uint64_t> seqlock{0};

    // timestamps
    std::uint64_t mono_ns = 0;
    std::uint64_t wall_ns = 0;

    // contract
    std::uint32_t magic       = kIntentShmMagic;
    std::uint32_t layout_ver  = kIntentShmLayoutVersion;

    // payload tagging (防止 silent mismatch)
    std::uint32_t payload_ver   = shared::msg::kControlIntentWireVersion;
    std::uint32_t payload_size  = static_cast<std::uint32_t>(sizeof(shared::msg::ControlIntent));
    std::uint32_t payload_align = static_cast<std::uint32_t>(alignof(shared::msg::ControlIntent));

    std::uint32_t reserved = 0;
};

struct IntentShmLayout final {
    IntentShmHeader hdr;
    shared::msg::ControlIntent intent;
};

static_assert(std::is_standard_layout_v<IntentShmLayout>,
              "IntentShmLayout must be standard layout.");
static_assert(std::is_trivially_copyable_v<IntentShmLayout>,
              "IntentShmLayout must be trivially copyable.");

} // namespace shared::shm
