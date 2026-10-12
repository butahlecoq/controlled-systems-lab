#pragma once

#include <csl/optimization/lp_backend.hpp>
#include <csl/sets/data.hpp>

namespace csl::geometry::polyhedral {

using SetResult = std::variant<sets::SetData, Diagnostics>;

// Intersect two H descriptions while keeping inequalities and affine
// equalities in their separate authored conventions. Conversion to V is a
// separate operation and can therefore enumerate vertices created by cuts.
SetResult intersect_h(const sets::SetData& left, const sets::SetData& right,
                     SetId output_id);

enum class HalfspaceReductionStatus { complete, incomplete };
struct HalfspaceReduction {
    sets::SetData set;
    HalfspaceReductionStatus status;
    std::vector<std::size_t> retained_inequalities;
    std::vector<std::size_t> removed_inequalities;
    std::size_t lp_calls;
};
using HalfspaceReductionResult = std::variant<HalfspaceReduction, Diagnostics>;

// A row is removed only when the selected workspace returns a completed,
// correctly bound supported lower bound for min(-a_i*x), establishing
// max(a_i*x-b_i) <= 0 over the remaining rows. Unsupported evidence is kept.
HalfspaceReductionResult remove_redundant_halfspaces(
    const sets::SetData& input, SetId output_id, LPWorkspace& lp,
    const ExecutionContext& context);

} // namespace csl::geometry::polyhedral
