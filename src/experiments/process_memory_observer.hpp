#pragma once

#include <cstdint>
#include <optional>

namespace csl::experiments::detail {

// Returns the process resident-set size at the instant of observation. This is
// a snapshot, not a peak, allocation total, or memory limit.
std::optional<std::uint64_t> process_resident_bytes() noexcept;

} // namespace csl::experiments::detail
