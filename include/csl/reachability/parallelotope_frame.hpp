#pragma once

#include <csl/core/values.hpp>

#include <cstddef>
#include <span>
#include <string_view>

namespace csl::reachability {

// A parallelotope membership is x = frame * factor with one certified factor
// interval per frame column. Frames must be orthonormal so a factor witness
// is exactly frame^T * state.
//
// Every rule encloses the same bounded H intersection. A cover costs one
// support LP solve per frame column and side, so 2 * dimension solves per
// candidate frame. axis reuses the existing profile. fixed_rotation_45
// rotates each consecutive coordinate pair by 45 degrees; an odd trailing
// coordinate keeps the identity row, so the rotation only helps in the paired
// subspace. support_selected covers both candidates and keeps the frame with
// the smaller factor-width product — the enclosure volume for orthonormal
// frames — so it spends 4 * dimension solves per enclosure and its choice
// depends on dimension through the paired rotation structure. Candidate
// frames must have full rank, which the downstream membership validation
// enforces; ties retain the axis candidate, so the rule can decline a
// rotation when the axis frame is best.
enum class ParallelotopeFrameRule { axis, fixed_rotation_45, support_selected };

struct ParallelotopeFrame {
    Matrix matrix;
    ParallelotopeFrameRule rule{ParallelotopeFrameRule::axis};
    double angle_degrees{};
};

// The ordered candidate list used by support_selected. Candidate zero is the
// axis frame, so select_parallelotope_frame ties retain it.
[[nodiscard]] std::vector<ParallelotopeFrame> parallelotope_frame_candidates(
    ParallelotopeFrameRule rule, std::size_t dimension);

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
