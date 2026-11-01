#include <csl/optimization/finite_action_parallelotope_minimax.hpp>

#include "finite_action_plans.hpp"
#include "finite_action_replay.hpp"

#include <chrono>
#include <cmath>
#include <limits>
#include <string>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string message) {
  return {
      {{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

bool exceeds_vertex_limit(const sets::SetData &set, std::size_t limit) {
  const auto representation = set.representation();
  if (std::holds_alternative<sets::SingletonRepresentation>(representation))
    return limit < 1;
  if (const auto *vertices =
          std::get_if<sets::VRepresentation>(&representation))
    return vertices->vertices.rows() > limit;
  return false;
}

struct CornerScore {
  double maximum;
  std::size_t evaluated;
};
using CornerScoreOutcome =
    std::variant<CornerScore, Unsupported, OperationStopped>;

CornerScoreOutcome
score_corners(const reachability::ParallelotopeStage &terminal,
              const Matrix &frame, const Objective &objective,
              const ExecutionContext &context) {
  constexpr std::size_t dimension = 4;
  if (terminal.lower.size() != dimension ||
      terminal.upper.size() != dimension || frame.rows != dimension ||
      frame.cols != dimension || frame.values.size() != dimension * dimension)
    return unsupported(
        "finite_parallelotope_minimax.terminal",
        "Terminal frame box or frame dimensions are inconsistent.");
  double maximum = -std::numeric_limits<double>::infinity();
  constexpr std::size_t count = std::size_t{1} << dimension;
  for (std::size_t mask = 0; mask < count; ++mask) {
    if (context.cancellation.stop_requested())
      return OperationStopped{StopReason::cancelled,
                              "Parallelotope candidate scoring cancelled."};
    if (context.deadline &&
        std::chrono::steady_clock::now() >= *context.deadline)
      return OperationStopped{
          StopReason::deadline_expired,
          "Parallelotope candidate scoring deadline expired."};
    Vector point(dimension);
    for (std::size_t row = 0; row < dimension; ++row) {
      double coordinate = 0.0;
      for (std::size_t column = 0; column < dimension; ++column) {
        const auto y = (mask & (std::size_t{1} << column))
                           ? terminal.upper[column]
                           : terminal.lower[column];
        coordinate += frame.values[row * dimension + column] * y;
      }
      if (!std::isfinite(coordinate))
        return unsupported("finite_parallelotope_minimax.score",
                           "Frame corner transform is nonfinite.");
      point[row] = coordinate;
    }
    const auto value = evaluate(objective, point);
    if (const auto *error = std::get_if<Diagnostic>(&value))
      return unsupported(error->field, error->explanation);
    if (const auto *stop = std::get_if<OperationStopped>(&value))
      return *stop;
    maximum = std::max(maximum, std::get<double>(value));
  }
  if (!std::isfinite(maximum))
    return unsupported("finite_parallelotope_minimax.score",
                       "Terminal frame-box corners produced no finite score.");
  return CornerScore{maximum, count};
}
} // namespace

FiniteActionParallelotopeMinimaxOutcome finite_action_parallelotope_minimax(
    const FiniteActionMinimaxRequest &request,
    FiniteActionParallelotopeMinimaxLimits limits,
    const ExecutionContext &context) {
  const auto horizon = request.system.horizon();
  if (request.problem.value.empty() || request.request.value.empty())
    return unsupported("finite_parallelotope_minimax.identity",
                       "Problem and request identities must be nonempty.");
  if (request.actions.catalogue.empty() && horizon != 0)
    return unsupported("finite_parallelotope_minimax.actions",
                       "A nonempty finite action catalogue is required.");
  std::size_t plan_count = 1;
  for (std::size_t stage = 0; stage < horizon; ++stage) {
    if (!request.actions.catalogue.empty() &&
        plan_count > limits.max_plans / request.actions.catalogue.size())
      return unsupported("finite_parallelotope_minimax.plans",
                         "Action plan count exceeds caller limit.");
    plan_count *= request.actions.catalogue.size();
  }
  if (plan_count > limits.max_plans)
    return unsupported("finite_parallelotope_minimax.plans",
                       "Action plan count exceeds caller limit.");
  if (request.objective.dimension() != request.system.dimensions().state ||
      request.actions.dimension != request.system.dimensions().control ||
      request.disturbances.size() != horizon ||
      request.admissible_states.size() != horizon + 1)
    return unsupported(
        "finite_parallelotope_minimax.dimensions",
        "Objective, catalogue or stage dimensions differ from the model.");

  std::vector<FiniteActionParallelotopePlanAttempt> attempts;
  const auto capacity = limits.max_candidate_attempts < plan_count
                            ? limits.max_candidate_attempts + 1
                            : plan_count;
  attempts.reserve(capacity);
  bool complete = true;
  std::size_t selected_index = 0;
  double minimum = std::numeric_limits<double>::infinity();
  bool has_scored = false;
  const auto stop_search =
      [&](const std::vector<std::size_t> &choices, std::size_t index,
          OperationStopped stopped) -> FiniteActionParallelotopeMinimaxOutcome {
    attempts.emplace_back(ParallelotopePlanStopped{choices, stopped});
    return FiniteActionParallelotopeMinimaxResult{
        request.problem,
        request.request,
        std::move(attempts),
        CandidateSearchCoverage::incomplete,
        ParallelotopeCandidateSearchStopped{index, std::move(stopped)},
        Assurance::numerical};
  };
  for (std::size_t index = 0; index < plan_count; ++index) {
    const auto choices = detail::action_plan_indices(
        index, request.actions.catalogue.size(), horizon);
    if (index >= limits.max_candidate_attempts)
      return stop_search(
          choices, index,
          {StopReason::resource_limit,
           "Parallelotope candidate-attempt limit reached before this plan."});
    if (context.cancellation.stop_requested())
      return stop_search(
          choices, index,
          {StopReason::cancelled,
           "Parallelotope finite minimax cancelled before this plan."});
    if (context.deadline &&
        std::chrono::steady_clock::now() >= *context.deadline)
      return stop_search(
          choices, index,
          {StopReason::deadline_expired,
           "Parallelotope finite minimax deadline expired before this plan."});
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for (const auto choice : choices)
      controls.push_back(request.actions.catalogue[choice]);
    bool point_limit_exceeded =
        exceeds_vertex_limit(request.initial, limits.max_points_per_stage);
    for (const auto &disturbance : request.disturbances)
      point_limit_exceeded =
          point_limit_exceeded ||
          exceeds_vertex_limit(disturbance, limits.max_points_per_stage);
    if (point_limit_exceeded) {
      attempts.emplace_back(ParallelotopePlanUnscored{
          choices,
          unsupported(
              "finite_parallelotope_minimax.points.limit",
              "Initial or disturbance vertex count exceeds caller limit.")});
      complete = false;
      continue;
    }
    reachability::FixedPlanRequest plan{request.system,
                                        request.initial,
                                        std::move(controls),
                                        request.disturbances,
                                        request.admissible_states,
                                        {request.request.value +
                                         "/parallelotope-plan/" +
                                         std::to_string(index)}};
    auto propagated = reachability::finite_plan_parallelotope(plan, context);
    if (const auto *stop = std::get_if<OperationStopped>(&propagated))
      return stop_search(choices, index, *stop);
    if (const auto *error = std::get_if<Unsupported>(&propagated)) {
      attempts.emplace_back(ParallelotopePlanUnscored{choices, *error});
      complete = false;
      continue;
    }
    auto trace = std::get<reachability::FinitePlanParallelotopeTrace>(
        std::move(propagated));
    auto scored = score_corners(trace.stages.back(), trace.frame,
                                request.objective, context);
    if (const auto *stop = std::get_if<OperationStopped>(&scored))
      return stop_search(choices, index, *stop);
    if (const auto *error = std::get_if<Unsupported>(&scored)) {
      attempts.emplace_back(ParallelotopePlanUnscored{choices, *error});
      complete = false;
      continue;
    }
    const auto score = std::get<CornerScore>(scored);
    attempts.emplace_back(ParallelotopePlanScored{
        choices, {score.maximum, score.evaluated, std::move(trace)}});
    if (score.maximum < minimum) {
      minimum = score.maximum;
      selected_index = index;
      has_scored = true;
    }
  }
  const auto coverage = complete ? CandidateSearchCoverage::complete
                                 : CandidateSearchCoverage::incomplete;
  if (!has_scored)
    return FiniteActionParallelotopeMinimaxResult{
        request.problem,
        request.request,
        std::move(attempts),
        coverage,
        ParallelotopeNoScoredCandidate{},
        Assurance::numerical};
  const auto &selected =
      std::get<ParallelotopePlanScored>(attempts[selected_index]);
  std::vector<Vector> controls;
  controls.reserve(horizon);
  for (const auto choice : selected.action_indices)
    controls.push_back(request.actions.catalogue[choice]);
  reachability::FixedPlanRequest replay_request{
      request.system,
      request.initial,
      std::move(controls),
      request.disturbances,
      request.admissible_states,
      {request.request.value + "/parallelotope-selected-replay"}};
  const auto replay = detail::replay_finite_action_plan(
      replay_request, request.objective, limits.max_points_per_stage,
      limits.max_replay_histories, "finite_parallelotope_minimax", context);
  if (const auto *error = std::get_if<Unsupported>(&replay))
    return FiniteActionParallelotopeMinimaxResult{
        request.problem,
        request.request,
        std::move(attempts),
        coverage,
        ParallelotopePlanReplayRefused{selected_index, *error},
        Assurance::numerical};
  if (const auto *stop = std::get_if<OperationStopped>(&replay))
    return FiniteActionParallelotopeMinimaxResult{
        request.problem,
        request.request,
        std::move(attempts),
        coverage,
        ParallelotopePlanReplayStopped{selected_index, *stop},
        Assurance::numerical};
  const auto &realized = std::get<detail::FiniteActionReplay>(replay);
  FiniteActionParallelotopeReplay replay_result{realized.value,
                                                realized.terminal_state,
                                                realized.disturbance_indices,
                                                realized.disturbances,
                                                realized.path,
                                                realized.terminal_catalogue};
  return FiniteActionParallelotopeMinimaxResult{
      request.problem,
      request.request,
      std::move(attempts),
      coverage,
      ParallelotopePlanSelected{selected_index, std::move(replay_result)},
      Assurance::numerical};
}
} // namespace csl::optimization
