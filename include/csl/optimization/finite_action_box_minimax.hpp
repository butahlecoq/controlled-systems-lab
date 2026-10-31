#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_box.hpp>

namespace csl::optimization {

struct FiniteActionBoxMinimaxLimits {
    std::size_t max_plans;
    std::size_t max_points_per_stage;
    std::size_t max_replay_histories;
    std::size_t max_box_corners;
};

struct BoxPlanScore {
    std::vector<std::size_t> action_indices;
    double terminal_box_maximum;
};

struct FiniteActionBoxMinimaxResult {
    ProblemId problem;
    RequestId request;
    std::vector<BoxPlanScore> plan_scores;
    std::vector<std::size_t> selected_action_indices;
    double selected_box_score;
    double selected_replay_value;
    Vector replayed_worst_terminal_state;
    std::vector<std::size_t> replayed_worst_disturbance_indices;
    std::vector<Vector> replayed_worst_disturbance_values;
    std::vector<Vector> replayed_worst_path;
    sets::SetData replayed_terminal_catalogue;
    reachability::FinitePlanBoxTrace selected_box_trace;
    Assurance assurance{Assurance::numerical};
};

using FiniteActionBoxMinimaxOutcome = std::variant<FiniteActionBoxMinimaxResult,
    Unsupported, OperationStopped>;

// Selects one fixed open-loop plan by minimizing the maximum convex objective
// on its terminal outer box, then replays that plan over the original finite
// disturbance catalogues. The box score is numerical enclosure evidence, not
// a validated optimality bound or a complete-family claim.
// For horizon H, state/control/external dimensions n/m/q, A actions per stage,
// P=A^H plans, C=2^n terminal corners, and R initial-disturbance histories
// for the selected plan, work is O(P[Hn(n+m+q)+C C_obj]+RHn(n+m+q)); C_obj
// is the objective evaluation cost per corner. Memory is O(PH+Hn+Cn+KHn+
// sum_k |D_k|q) for saved scores, corner materialization, exact replay stages,
// and disturbance catalogues, where K is the per-stage point limit. The witness search retains
// one path of length H, so R bounds work rather than stored histories. Caller
// limits bound P, C, replay histories R, and exact points per replay stage.
// Bounded V/singleton catalogues and
// universal safe sets are supported; other set forms are not.
FiniteActionBoxMinimaxOutcome finite_action_box_minimax(
    const FiniteActionMinimaxRequest& request, FiniteActionBoxMinimaxLimits limits,
    const ExecutionContext& context = {});

} // namespace csl::optimization
