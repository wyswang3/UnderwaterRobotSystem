#pragma once
#ifndef SHARED_MSG_KEY_EVENT_HPP
#define SHARED_MSG_KEY_EVENT_HPP

#include <cstdint>
#include <type_traits>

namespace shared::msg {

// wire version for KeyEvent payload ABI
constexpr std::uint32_t kKeyEventWireVersion = 1;

enum class KeyAction : std::uint8_t {
    kPress   = 1,   // typical terminal: only press/repeat
    kRelease = 2,   // optional future
    kRepeat  = 3,   // optional future
};

enum KeyMods : std::uint16_t {
    kModNone  = 0,
    kModShift = 1u << 0,
    kModCtrl  = 1u << 1,
    kModAlt   = 1u << 2,
};

// Minimal keyboard event (do NOT encode control semantics here)
struct KeyEvent final {
    std::uint32_t version = kKeyEventWireVersion;

    std::uint32_t seq = 0;            // publisher-side increment
    std::uint64_t stamp_mono_ns = 0;  // monotonic timestamp

    std::int32_t  key = 0;            // usually ASCII (e.g., 'W', 27 for ESC)
    KeyAction     action = KeyAction::kPress;

    std::uint16_t mods = kModNone;
    std::uint16_t reserved0 = 0;

    std::uint32_t reserved1 = 0;
};

static_assert(std::is_standard_layout_v<KeyEvent>, "KeyEvent must be standard layout.");
static_assert(std::is_trivially_copyable_v<KeyEvent>, "KeyEvent must be trivially copyable.");

} // namespace shared::msg

#endif // SHARED_MSG_KEY_EVENT_HPP
