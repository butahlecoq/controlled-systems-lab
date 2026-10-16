#pragma once

#include <csl/problem/contracts.hpp>
#include <csl/reachability/fixed_plan_disturbance.hpp>
#include <csl/optimization/worst_case_vertex.hpp>

namespace csl::optimization {

// Stage-invariant ordered action catalogue; indices distinguish duplicate rows.
struct FiniteActionMinimaxRequest {
    ProblemId problem;
    RequestId request;
    model::LinearSystem system;
    sets::SetData initial;
    FiniteDomain actions;
    std::vector<sets::SetData> disturbances;
    std::vector<sets::SetData> admissible_states;
    Objective objective;
};
struct FiniteActionMinimaxLimits {
    std::size_t max_plans;
    std::size_t max_points_per_stage;
    // Computed values within this absolute distance of the minimum are retained.
    double near_optimal_tolerance;
};
struct FinitePlanFeasible {
    std::vector<std::size_t> action_indices;
    double worst_value;
    Vector maximizer;
    std::size_t evaluated_vertices;
    // Complete generated terminal V description for independent cost replay.
    sets::SetData terminal;
};
struct FinitePlanRejected {
    std::vector<std::size_t> action_indices;
    std::size_t stage;
    Vector violating_successor;
};
using FinitePlanRecord = std::variant<FinitePlanFeasible, FinitePlanRejected>;
struct FiniteMinimaxOptimal {
    ProblemId problem;
    RequestId request;
    double value;
    std::vector<FinitePlanRecord> plans;
    // Indices into plans, ordered by catalogue enumeration.
    std::vector<std::size_t> minimizing_plan_indices;
    Assurance assurance;
};
struct FiniteMinimaxInfeasible {
    ProblemId problem;
    RequestId request;
    std::vector<FinitePlanRejected> rejected_plans;
    Assurance assurance;
};
struct FiniteMinimaxEmptyCatalogue {};
// An empty initial/disturbance set leaves no adversarial trajectory to score.
struct FiniteMinimaxNoScenarios {};
using FiniteActionMinimaxOutcome = std::variant<FiniteMinimaxOptimal,
    FiniteMinimaxInfeasible, FiniteMinimaxEmptyCatalogue, FiniteMinimaxNoScenarios,
    Unsupported, OperationStopped>;

// Exhausts every fixed action sequence and every generated terminal V row.
// Only numerical assurance is available; records are replay witnesses, not
// validated rounding certificates or an independently proved H/V conversion.
FiniteActionMinimaxOutcome finite_action_minimax(
    const FiniteActionMinimaxRequest& request,
    FiniteActionMinimaxLimits limits,
    const ExecutionContext& context = {});

} // namespace csl::optimization
