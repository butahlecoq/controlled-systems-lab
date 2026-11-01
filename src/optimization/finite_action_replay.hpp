#pragma once

#include <csl/optimization/worst_case_vertex.hpp>
#include <csl/reachability/fixed_plan_disturbance.hpp>

#include <string_view>

namespace csl::optimization::detail {

struct FiniteActionReplay {
    double value;
    Vector terminal_state;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
    sets::SetData terminal_catalogue;
};

using FiniteActionReplayOutcome = std::variant<FiniteActionReplay, Unsupported, OperationStopped>;

FiniteActionReplayOutcome replay_finite_action_plan(
    const reachability::FixedPlanRequest& request, const Objective& objective,
    std::size_t max_points_per_stage, std::size_t max_histories,
    std::string_view error_prefix, const ExecutionContext& context);

} // namespace csl::optimization::detail
