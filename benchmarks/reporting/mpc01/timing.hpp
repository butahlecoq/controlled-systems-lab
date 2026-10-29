#pragma once

#include <chrono>
#include <cstdint>

namespace csl::mpc01::timing {

using Clock = std::chrono::steady_clock;

inline std::uint64_t elapsed_ns(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

} // namespace csl::mpc01::timing
