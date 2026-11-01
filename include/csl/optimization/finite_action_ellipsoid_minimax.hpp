#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>

#include <limits>

namespace csl::optimization {

struct FiniteActionEllipsoidMinimaxLimits {
  std::size_t max_plans;
  std::size_t max_points_per_stage;
  std::size_t max_replay_histories;
  std::size_t max_candidate_attempts{std::numeric_limits<std::size_t>::max()};
};

struct EllipsoidCandidateScore {
  // Numerical support upper estimate for the objective over the terminal
  // ellipsoid. It is not validated arithmetic or an optimality certificate.
  double terminal_support_estimate;
  reachability::FinitePlanEllipsoidTrace trace;
};
struct EllipsoidPlanScored {
  std::vector<std::size_t> action_indices;
  EllipsoidCandidateScore score;
};
struct EllipsoidPlanUnscored {
  std::vector<std::size_t> action_indices;
  Unsupported outcome;
};
struct EllipsoidPlanStopped {
  std::vector<std::size_t> action_indices;
  OperationStopped outcome;
};
using FiniteActionEllipsoidPlanAttempt =
    std::variant<EllipsoidPlanScored, EllipsoidPlanUnscored,
                 EllipsoidPlanStopped>;

struct FiniteActionEllipsoidReplay {
  double worst_value;
  Vector worst_terminal_state;
  std::vector<std::size_t> disturbance_indices;
  std::vector<Vector> disturbances;
  std::vector<Vector> path;
  sets::SetData terminal_catalogue;
};
struct EllipsoidPlanSelected {
  std::size_t candidate_attempt_index;
  FiniteActionEllipsoidReplay replay;
};
struct EllipsoidPlanReplayRefused {
  std::size_t candidate_attempt_index;
  Unsupported outcome;
};
struct EllipsoidPlanReplayStopped {
  std::size_t candidate_attempt_index;
  OperationStopped outcome;
};
struct EllipsoidCandidateSearchStopped {
  std::size_t candidate_attempt_index;
  OperationStopped outcome;
};
struct EllipsoidNoScoredCandidate {};
using FiniteActionEllipsoidSelectionOutcome =
    std::variant<EllipsoidPlanSelected, EllipsoidPlanReplayRefused,
                 EllipsoidPlanReplayStopped, EllipsoidCandidateSearchStopped,
                 EllipsoidNoScoredCandidate>;

struct FiniteActionEllipsoidMinimaxResult {
  ProblemId problem;
  RequestId request;
  std::vector<FiniteActionEllipsoidPlanAttempt> plan_attempts;
  CandidateSearchCoverage candidate_search;
  FiniteActionEllipsoidSelectionOutcome selection;
  Assurance assurance{Assurance::numerical};
};
using FiniteActionEllipsoidMinimaxOutcome =
    std::variant<FiniteActionEllipsoidMinimaxResult, Unsupported,
                 OperationStopped>;

// Ranks fixed open-loop plans by a numerical upper estimate over a stagewise
// outer ellipsoid, then independently replays the selected plan across every
// finite disturbance history. This does not prove global minimax optimality.
FiniteActionEllipsoidMinimaxOutcome finite_action_ellipsoid_minimax(
    const FiniteActionMinimaxRequest& request,
    FiniteActionEllipsoidMinimaxLimits limits,
    const ExecutionContext& context = {});

} // namespace csl::optimization
