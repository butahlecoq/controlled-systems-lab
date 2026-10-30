#pragma once

#include <csl/problem/resolved_problem.hpp>
#include <csl/synthesis/finite_action_histories.hpp>
#include <csl/sets/data.hpp>

namespace csl::synthesis {

struct FiniteMixedBranchCoordinates {
    JointCoordinates source;
    JointCoordinates continuous_subproblem;
    std::vector<Vector> discrete_controls;
};

struct FiniteMixedBranchProblem {
    FiniteActionHistory history;
    Problem problem;
    FiniteMixedBranchCoordinates coordinates;
};

using FiniteMixedBranchOutcome = std::variant<FiniteMixedBranchProblem, Diagnostics>;
using FiniteMixedBranchRelationOutcome = std::variant<sets::SetData, Diagnostics>;

// Fixes one complete catalogue-index history in a nominal discrete-time
// mixed-control problem and returns the equivalent continuous subproblem.
// The mapping records how a later joint relation returns to source coordinates.
FiniteMixedBranchOutcome prepare_finite_mixed_branch(
    const problem::ResolvedProblem&, const FiniteActionHistory&);

// Embeds an H-represented continuous branch relation into the source problem's
// canonical joint coordinates and fixes every discrete control coordinate.
FiniteMixedBranchRelationOutcome lift_finite_mixed_branch_relation(
    const FiniteMixedBranchProblem&, const sets::SetData&);

} // namespace csl::synthesis
