#pragma once

#include <csl/core/values.hpp>

#include <cstddef>
#include <span>
#include <string_view>

namespace csl::reachability {

// A parallelotope is x = center + frame * factor with one independent factor
// interval per frame column. The axis frame preserves the existing profile.
enum class ParallelotopeFrameRule { axis, fixed_rotation_45 };

struct ParallelotopeFrame {
    Matrix matrix;
    ParallelotopeFrameRule rule{ParallelotopeFrameRule::axis};
    double angle_degrees{};
};

[[nodiscard]] std::string_view parallelotope_frame_rule_name(ParallelotopeFrameRule rule) noexcept;
// Identity basis. Kept explicit so the axis profile and saved captures are
// unchanged by the nonaxis option.
[[nodiscard]] Matrix identity_parallelotope_frame(std::size_t dimension);
// Independent 45-degree rotation in each consecutive coordinate pair. An odd
// trailing coordinate keeps the identity row.
[[nodiscard]] Matrix fixed_rotation_45_frame(std::size_t dimension);
[[nodiscard]] ParallelotopeFrame parallelotope_frame(ParallelotopeFrameRule rule,
                                                     std::size_t dimension);
// Deterministic candidate choice from measured support excess. The smallest
// entry wins; a numerical tie (including equal values) keeps candidate zero,
// which callers reserve for the axis frame.
[[nodiscard]] std::size_t select_parallelotope_frame(std::span<const double> excess) noexcept;

} // namespace csl::reachability
