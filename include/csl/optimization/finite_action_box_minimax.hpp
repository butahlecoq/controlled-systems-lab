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

struct BoxPlanScored {
    std::vector<std::size_t> action_indices;
    double terminal_box_maximum;
    reachability::FinitePlanBoxTrace trace;
};

struct BoxPlanUnscored {
    std::vector<std::size_t> action_indices;
    Unsupported reason;
};
struct BoxPlanStopped {
    std::vector<std::size_t> action_indices;
    OperationStopped reason;
};
using FiniteActionBoxPlanAttempt =
    std::variant<BoxPlanScored, BoxPlanUnscored, BoxPlanStopped>;

struct FiniteActionBoxReplay {
    double worst_value;
    Vector worst_terminal_state;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
    sets::SetData terminal_catalogue;
};
struct BoxPlanSelected {
    std::size_t candidate_attempt_index;
    FiniteActionBoxReplay replay;
};
struct BoxPlanReplayRefused {
    std::size_t candidate_attempt_index;
    Unsupported reason;
};
struct BoxPlanReplayStopped {
    std::size_t candidate_attempt_index;
    OperationStopped reason;
};
struct BoxNoScoredCandidate {};
using FiniteActionBoxSelectionOutcome = std::variant<BoxPlanSelected,
    BoxPlanReplayRefused, BoxPlanReplayStopped, BoxNoScoredCandidate>;

struct FiniteActionBoxMinimaxResult {
    ProblemId problem;
    RequestId request;
    std::vector<FiniteActionBoxPlanAttempt> plan_attempts;
    CandidateSearchCoverage candidate_search;
    FiniteActionBoxSelectionOutcome selection;
    Assurance assurance{Assurance::numerical};
};

using FiniteActionBoxMinimaxOutcome = std::variant<FiniteActionBoxMinimaxResult,
    Unsupported, OperationStopped>;

// Scores every fixed open-loop plan against its terminal outer box and retains
// scored, unsupported, and stopped attempts. It replays the best scored plan
// separately over the original finite disturbance catalogues. Coverage is
// complete only when every declared plan received a score. The box score is
// numerical enclosure evidence, not a validated optimality bound or a
// complete-family claim when coverage is incomplete.
// For horizon H, state/control/external dimensions n/m/q, A actions per stage,
// P=A^H plans, C=2^n terminal corners, and R initial-disturbance histories
// for the selected plan, work is O(P[Hn(n+m+q)+C C_obj]+RHn(n+m+q)); C_obj
// is the objective evaluation cost per corner. Memory is O(PHn+Hn+Cn+KHn+
// sum_k |D_k|q) for saved scores, corner materialization, exact replay stages,
// retained candidate traces, and disturbance catalogues, where K is the
// per-stage point limit. The witness search retains one path of length H, so
// R bounds work rather than stored histories. Caller
// limits bound P, C, replay histories R, and exact points per replay stage.
// Bounded V/singleton catalogues and
// universal safe sets are supported; other set forms are not.
FiniteActionBoxMinimaxOutcome finite_action_box_minimax(
    const FiniteActionMinimaxRequest& request, FiniteActionBoxMinimaxLimits limits,
    const ExecutionContext& context = {});

} // namespace csl::optimization
