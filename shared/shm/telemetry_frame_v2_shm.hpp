#pragma once
#ifndef UWSYS_SHARED_SHM_TELEMETRY_FRAME_V2_SHM_HPP
#define UWSYS_SHARED_SHM_TELEMETRY_FRAME_V2_SHM_HPP

#include <atomic>
#include <cstdint>
#include <type_traits>

#include "shared/msg/telemetry_frame_v2.hpp"

namespace shared::shm {

constexpr std::uint32_t kTelemetryFrameV2Magic =
    (static_cast<std::uint32_t>('T') << 24) |
    (static_cast<std::uint32_t>('L') << 16) |
    (static_cast<std::uint32_t>('M') << 8)  |
    (static_cast<std::uint32_t>('2'));

constexpr std::uint32_t kTelemetryFrameV2LayoutVersion = 1;

struct TelemetryFrameV2ShmHeader final {
    std::atomic<std::uint64_t> seqlock{0};

    std::uint64_t mono_ns = 0;
    std::uint64_t wall_ns = 0;

    std::uint32_t magic      = kTelemetryFrameV2Magic;
    std::uint32_t layout_ver = kTelemetryFrameV2LayoutVersion;

    std::uint32_t payload_ver   = shared::msg::kTelemetryFrameV2WireVersion;
    std::uint32_t payload_size  = static_cast<std::uint32_t>(sizeof(shared::msg::TelemetryFrameV2));
    std::uint32_t payload_align = static_cast<std::uint32_t>(alignof(shared::msg::TelemetryFrameV2));

    std::uint32_t reserved0 = 0;
};

struct TelemetryFrameV2ShmLayout final {
    TelemetryFrameV2ShmHeader hdr;
    shared::msg::TelemetryFrameV2 payload;
};

static_assert(std::is_standard_layout_v<TelemetryFrameV2ShmHeader>,
              "TelemetryFrameV2ShmHeader must be standard layout.");
static_assert(std::is_trivially_copyable_v<TelemetryFrameV2ShmHeader>,
              "TelemetryFrameV2ShmHeader must be trivially copyable.");
static_assert(std::is_standard_layout_v<TelemetryFrameV2ShmLayout>,
              "TelemetryFrameV2ShmLayout must be standard layout.");
static_assert(std::is_trivially_copyable_v<TelemetryFrameV2ShmLayout>,
              "TelemetryFrameV2ShmLayout must be trivially copyable.");

} // namespace shared::shm

#endif // UWSYS_SHARED_SHM_TELEMETRY_FRAME_V2_SHM_HPP
