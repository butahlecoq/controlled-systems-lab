#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>

#include <limits>

namespace csl::optimization {

struct FiniteActionParallelotopeMinimaxLimits {
    std::size_t max_plans;
    std::size_t max_points_per_stage;
    std::size_t max_replay_histories;
    std::size_t max_candidate_attempts{std::numeric_limits<std::size_t>::max()};
};

struct ParallelotopeCandidateScore {
    double terminal_frame_box_corner_maximum;
    // Number of full-dimensional evaluations by the numerical objective.
    // The large diagonal route evaluates its reconstructed corner once.
    std::size_t corners_evaluated;
    reachability::FinitePlanParallelotopeTrace trace;
};
struct ParallelotopePlanScored {
    std::vector<std::size_t> action_indices;
    ParallelotopeCandidateScore score;
};
struct ParallelotopePlanUnscored {
    std::vector<std::size_t> action_indices;
    Unsupported outcome;
};
struct ParallelotopePlanStopped {
    std::vector<std::size_t> action_indices;
    OperationStopped outcome;
};
using FiniteActionParallelotopePlanAttempt =
    std::variant<ParallelotopePlanScored, ParallelotopePlanUnscored, ParallelotopePlanStopped>;

struct FiniteActionParallelotopeReplay {
    double worst_value;
    Vector worst_terminal_state;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
    sets::SetData terminal_catalogue;
};
struct ParallelotopePlanSelected {
    std::size_t candidate_attempt_index;
    FiniteActionParallelotopeReplay replay;
};
struct ParallelotopePlanReplayRefused {
    std::size_t candidate_attempt_index;
    Unsupported outcome;
};
struct ParallelotopePlanReplayStopped {
    std::size_t candidate_attempt_index;
    OperationStopped outcome;
};
struct ParallelotopeCandidateSearchStopped {
    std::size_t candidate_attempt_index;
    OperationStopped outcome;
};
struct ParallelotopeNoScoredCandidate {};
using FiniteActionParallelotopeSelectionOutcome =
    std::variant<ParallelotopePlanSelected, ParallelotopePlanReplayRefused,
                 ParallelotopePlanReplayStopped, ParallelotopeCandidateSearchStopped,
                 ParallelotopeNoScoredCandidate>;

struct FiniteActionParallelotopeMinimaxResult {
    ProblemId problem;
    RequestId request;
    std::vector<FiniteActionParallelotopePlanAttempt> plan_attempts;
    CandidateSearchCoverage candidate_search;
    FiniteActionParallelotopeSelectionOutcome selection;
    Assurance assurance{Assurance::numerical};
};
using FiniteActionParallelotopeMinimaxOutcome =
    std::variant<FiniteActionParallelotopeMinimaxResult, Unsupported, OperationStopped>;

// Ranks fixed open-loop plans by terminal parallelotope scores, then replays
// the selected plan over finite catalogs. Up to eight states use exhaustive
// corner evaluation. Larger adjacent-pair frames require a convex diagonal
// quadratic. They choose maximizing endpoints with exact block comparisons
// and evaluate one reconstructed corner. Scores are numerical estimates.
FiniteActionParallelotopeMinimaxOutcome
finite_action_parallelotope_minimax(const FiniteActionMinimaxRequest &request,
                                    FiniteActionParallelotopeMinimaxLimits limits,
                                    const ExecutionContext &context = {});

} // namespace csl::optimization
