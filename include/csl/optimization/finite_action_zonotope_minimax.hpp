#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

namespace csl::optimization {

struct FiniteActionZonotopeMinimaxLimits {
    std::size_t max_plans;
    std::size_t max_points_per_stage;
    std::size_t max_replay_histories;
    std::size_t max_generators_per_stage;
    std::size_t max_factor_corners;
};

struct ZonotopeCandidateScore {
    double terminal_factor_corner_maximum;
    std::size_t terminal_generators;
    std::size_t factor_corners_evaluated;
    reachability::FinitePlanZonotopeTrace trace;
};

struct ZonotopePlanScored {
    std::vector<std::size_t> action_indices;
    ZonotopeCandidateScore score;
};

struct ZonotopePlanUnscored {
    std::vector<std::size_t> action_indices;
    Unsupported outcome;
};

using FiniteActionZonotopePlanAttempt = std::variant<ZonotopePlanScored, ZonotopePlanUnscored>;

enum class CandidateSearchCoverage { complete, incomplete };

struct FiniteActionZonotopeReplay {
    double worst_value;
    Vector worst_terminal_state;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
    sets::SetData terminal_catalogue;
};

struct ZonotopePlanSelected {
    std::size_t candidate_attempt_index;
    FiniteActionZonotopeReplay replay;
};
struct ZonotopePlanReplayRefused {
    std::size_t candidate_attempt_index;
    Unsupported outcome;
};
struct ZonotopePlanReplayStopped {
    std::size_t candidate_attempt_index;
    OperationStopped outcome;
};
struct ZonotopeNoScoredCandidate {};

using FiniteActionZonotopeSelectionOutcome = std::variant<ZonotopePlanSelected,
    ZonotopePlanReplayRefused, ZonotopePlanReplayStopped, ZonotopeNoScoredCandidate>;

struct FiniteActionZonotopeMinimaxResult {
    ProblemId problem;
    RequestId request;
    std::vector<FiniteActionZonotopePlanAttempt> plan_attempts;
    CandidateSearchCoverage candidate_search;
    FiniteActionZonotopeSelectionOutcome selection;
    Assurance assurance{Assurance::numerical};
};

using FiniteActionZonotopeMinimaxOutcome = std::variant<FiniteActionZonotopeMinimaxResult,
    Unsupported, OperationStopped>;

// Ranks fixed open-loop plans by numerical maxima over all terminal zonotope
// factor corners, then exactly replays only the selected plan over the finite
// catalogues. Candidate scores are not validated objective bounds or a claim
// that the selector found a globally minimax plan.
FiniteActionZonotopeMinimaxOutcome finite_action_zonotope_minimax(
    const FiniteActionMinimaxRequest& request, FiniteActionZonotopeMinimaxLimits limits,
    const ExecutionContext& context = {});

} // namespace csl::optimization
