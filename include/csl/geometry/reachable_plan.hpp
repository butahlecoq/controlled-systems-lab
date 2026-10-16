#pragma once

#include <csl/geometry/approximation.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/verification/trajectory.hpp>

namespace csl::geometry::approximation {

// A caller-declared stage set, bound to the complete resolved problem identity.
// The identity encodes initial, external-input and information semantics. The
// ordered map is from set coordinates to original state coordinates. This type
// does not prove that the reference contains all reachable states.
struct StageSetReference {
    ProblemId problem;
    StageIndex stage;
    SetHandle set;
    std::vector<std::size_t> state_coordinates;
    ReferenceId reference_id; // must be the approximation's ideal-output identity
};

struct PlanCheck {
    std::optional<RunOutcome> approximation;
    verification::CheckStatus membership{verification::CheckStatus::not_checked};
    std::optional<verification::TrajectoryReport> trajectory;
    Termination termination{Termination::completed};
    // Present only after independently checking the inner-state membership and
    // the full original witness, including its reported and recomputed cost.
    // Numerical feasibility is not a validated real-model or optimum bound.
    std::optional<double> numerical_achievable_value;
    Diagnostics diagnostics;
};

PlanCheck check_inner_state_plan(const problem::ResolvedProblem&,const StageSetReference&,
    const registry::Registry<registry::ApproximationPort>&,registry::Method,
    const ApproximationRequest&,const Witness&,const ExecutionContext& = {});

} // namespace csl::geometry::approximation
