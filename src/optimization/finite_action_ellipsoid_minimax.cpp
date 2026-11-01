#include <csl/optimization/finite_action_ellipsoid_minimax.hpp>

#include "finite_action_plans.hpp"
#include "finite_action_replay.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string explanation) {
  return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
}

bool exceeds_point_limit(const sets::SetData& set, std::size_t limit) {
  const auto representation = set.representation();
  if (std::holds_alternative<sets::SingletonRepresentation>(representation)) return limit < 1;
  if (const auto* vertices = std::get_if<sets::VRepresentation>(&representation))
    return vertices->vertices.rows() > limit;
  return false;
}

std::variant<double, Unsupported, OperationStopped> support_score(
    const reachability::FinitePlanEllipsoidTrace::Stage& terminal,
    const Objective& objective, const ExecutionContext& context) {
  if (context.cancellation.stop_requested())
    return OperationStopped{StopReason::cancelled, "Ellipsoid candidate scoring cancelled."};
  if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
    return OperationStopped{StopReason::deadline_expired, "Ellipsoid candidate scoring deadline expired."};
  if (terminal.center.size() != objective.dimension() ||
      terminal.radii.size() != terminal.center.size())
    return unsupported("finite_ellipsoid_minimax.terminal", "Terminal ellipsoid and objective dimensions differ.");

  const auto coefficients = objective.coefficients();
  const auto base = evaluate(objective, terminal.center);
  if (const auto* error = std::get_if<Diagnostic>(&base))
    return unsupported(error->field, error->explanation);
  if (const auto* stopped = std::get_if<OperationStopped>(&base)) return *stopped;
  double score = std::get<double>(base);

  if (const auto* linear = std::get_if<LinearCoefficients>(&coefficients)) {
    double squared = 0.0;
    for (std::size_t i = 0; i < terminal.center.size(); ++i) {
      const double term = linear->coefficients[i] * terminal.radii[i];
      squared += term * term;
    }
    score += std::sqrt(squared);
  } else if (const auto* quadratic = std::get_if<QuadraticCoefficients>(&coefficients)) {
    const auto checks = objective.quadratic_checks();
    if (!checks)
      return unsupported("finite_ellipsoid_minimax.objective", "Quadratic convexity checks are unavailable.");
    const double psd_tolerance = checks->positive_semidefiniteness.absolute_tolerance +
        checks->positive_semidefiniteness.relative_tolerance * checks->eigenvalue_scale;
    if (checks->minimum_eigenvalue < -psd_tolerance)
      return unsupported("finite_ellipsoid_minimax.objective", "A numerically positive-semidefinite quadratic is required.");
    const double psd_shift = std::max(0.0, -checks->minimum_eigenvalue);
    double gradient_norm_squared = 0.0;
    double diagonal_trace = 0.0;
    for (std::size_t i = 0; i < terminal.center.size(); ++i) {
      double gradient = quadratic->linear[i];
      for (std::size_t j = 0; j < terminal.center.size(); ++j) {
        const double symmetric = 0.5 * (quadratic->Q(i, j) + quadratic->Q(j, i));
        gradient += symmetric * terminal.center[j];
      }
      const double weighted = terminal.radii[i] * gradient;
      gradient_norm_squared += weighted * weighted;
      diagonal_trace += (quadratic->Q(i, i) + psd_shift) *
                        terminal.radii[i] * terminal.radii[i];
    }
    score += std::sqrt(gradient_norm_squared) + 0.5 * diagonal_trace;
  } else {
    const auto& residual = std::get<ResidualCoefficients>(coefficients);
    double frobenius_squared = 0.0;
    for (std::size_t row = 0; row < residual.map.rows(); ++row)
      for (std::size_t column = 0; column < residual.map.cols(); ++column) {
        const double term = residual.map(row, column) * terminal.radii[column];
        frobenius_squared += term * term;
      }
    score += std::sqrt(frobenius_squared);
  }
  if (!std::isfinite(score))
    return unsupported("finite_ellipsoid_minimax.score", "Terminal ellipsoid support estimate is nonfinite.");
  return score;
}
} // namespace

FiniteActionEllipsoidMinimaxOutcome finite_action_ellipsoid_minimax(
    const FiniteActionMinimaxRequest& request,
    FiniteActionEllipsoidMinimaxLimits limits,
    const ExecutionContext& context) {
  const auto horizon = request.system.horizon();
  if (request.problem.value.empty() || request.request.value.empty())
    return unsupported("finite_ellipsoid_minimax.identity", "Problem and request identities must be nonempty.");
  if (request.actions.catalogue.empty() && horizon != 0)
    return unsupported("finite_ellipsoid_minimax.actions", "A nonempty finite action catalogue is required.");
  std::size_t plan_count = 1;
  for (std::size_t stage = 0; stage < horizon; ++stage) {
    if (!request.actions.catalogue.empty() &&
        plan_count > limits.max_plans / request.actions.catalogue.size())
      return unsupported("finite_ellipsoid_minimax.plans", "Action plan count exceeds caller limit.");
    plan_count *= request.actions.catalogue.size();
  }
  if (plan_count > limits.max_plans)
    return unsupported("finite_ellipsoid_minimax.plans", "Action plan count exceeds caller limit.");
  if (request.objective.dimension() != request.system.dimensions().state ||
      request.actions.dimension != request.system.dimensions().control ||
      request.disturbances.size() != horizon ||
      request.admissible_states.size() != horizon + 1)
    return unsupported("finite_ellipsoid_minimax.dimensions", "Objective, catalogue or stage dimensions differ from the model.");

  std::vector<FiniteActionEllipsoidPlanAttempt> attempts;
  const auto capacity = limits.max_candidate_attempts < plan_count
      ? limits.max_candidate_attempts + 1 : plan_count;
  attempts.reserve(capacity);
  std::size_t selected_index = 0;
  double minimum = std::numeric_limits<double>::infinity();
  bool has_scored = false;
  const auto stop_search = [&](const std::vector<std::size_t>& choices,
                               std::size_t index, OperationStopped stopped)
      -> FiniteActionEllipsoidMinimaxOutcome {
    attempts.emplace_back(EllipsoidPlanStopped{choices, stopped});
    return FiniteActionEllipsoidMinimaxResult{
        request.problem, request.request, std::move(attempts),
        CandidateSearchCoverage::incomplete,
        EllipsoidCandidateSearchStopped{index, std::move(stopped)}, Assurance::numerical};
  };
  for (std::size_t plan = 0; plan < plan_count; ++plan) {
    const auto choices = detail::action_plan_indices(
        plan, request.actions.catalogue.size(), horizon);
    if (plan >= limits.max_candidate_attempts)
      return stop_search(choices, plan,
          {StopReason::resource_limit, "Ellipsoid candidate-attempt limit was reached."});
    if (context.cancellation.stop_requested())
      return stop_search(choices, plan,
          {StopReason::cancelled, "Ellipsoid candidate search cancelled."});
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
      return stop_search(choices, plan,
          {StopReason::deadline_expired, "Ellipsoid candidate-search deadline expired."});

    if (exceeds_point_limit(request.initial, limits.max_points_per_stage) ||
        std::any_of(request.disturbances.begin(), request.disturbances.end(),
            [&](const auto& set) { return exceeds_point_limit(set, limits.max_points_per_stage); })) {
      attempts.emplace_back(EllipsoidPlanUnscored{choices,
          unsupported("finite_ellipsoid_minimax.point_budget", "Initial or disturbance vertex count exceeds caller limit.")});
      continue;
    }
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for (const auto choice : choices) controls.push_back(request.actions.catalogue[choice]);
    reachability::FixedPlanRequest fixed{
        request.system, request.initial, std::move(controls), request.disturbances,
        request.admissible_states,
        {request.request.value + "/ellipsoid-candidate-" + std::to_string(plan)}};
    const auto propagation = reachability::finite_plan_ellipsoid(fixed, context);
    if (const auto* failure = std::get_if<Unsupported>(&propagation)) {
      attempts.emplace_back(EllipsoidPlanUnscored{choices, *failure});
      continue;
    }
    if (const auto* stopped = std::get_if<OperationStopped>(&propagation))
      return stop_search(choices, plan, *stopped);
    auto trace = std::get<reachability::FinitePlanEllipsoidTrace>(propagation);
    auto scored = support_score(trace.stages.back(), request.objective, context);
    if (const auto* failure = std::get_if<Unsupported>(&scored)) {
      attempts.emplace_back(EllipsoidPlanUnscored{choices, *failure});
      continue;
    }
    if (const auto* stopped = std::get_if<OperationStopped>(&scored))
      return stop_search(choices, plan, *stopped);
    const double value = std::get<double>(scored);
    attempts.emplace_back(EllipsoidPlanScored{choices, {value, std::move(trace)}});
    if (value < minimum) {
      minimum = value;
      selected_index = plan;
      has_scored = true;
    }
  }

  const bool complete = attempts.size() == plan_count;
  const auto coverage = complete ? CandidateSearchCoverage::complete
                                 : CandidateSearchCoverage::incomplete;
  if (!has_scored)
    return FiniteActionEllipsoidMinimaxResult{
        request.problem, request.request, std::move(attempts), coverage,
        EllipsoidNoScoredCandidate{}, Assurance::numerical};

  const auto& selected = std::get<EllipsoidPlanScored>(attempts[selected_index]);
  std::vector<Vector> controls;
  controls.reserve(horizon);
  for (const auto choice : selected.action_indices)
    controls.push_back(request.actions.catalogue[choice]);
  reachability::FixedPlanRequest replay_request{
      request.system, request.initial, std::move(controls), request.disturbances,
      request.admissible_states,
      {request.request.value + "/ellipsoid-selected-replay"}};
  const auto replay = detail::replay_finite_action_plan(
      replay_request, request.objective, limits.max_points_per_stage,
      limits.max_replay_histories, "finite_ellipsoid_minimax", context);
  if (const auto* failure = std::get_if<Unsupported>(&replay))
    return FiniteActionEllipsoidMinimaxResult{
        request.problem, request.request, std::move(attempts), coverage,
        EllipsoidPlanReplayRefused{selected_index, *failure}, Assurance::numerical};
  if (const auto* stopped = std::get_if<OperationStopped>(&replay))
    return FiniteActionEllipsoidMinimaxResult{
        request.problem, request.request, std::move(attempts), coverage,
        EllipsoidPlanReplayStopped{selected_index, *stopped}, Assurance::numerical};
  const auto& realized = std::get<detail::FiniteActionReplay>(replay);
  FiniteActionEllipsoidReplay replay_result{
      realized.value, realized.terminal_state, realized.disturbance_indices,
      realized.disturbances, realized.path, realized.terminal_catalogue};
  return FiniteActionEllipsoidMinimaxResult{
      request.problem, request.request, std::move(attempts), coverage,
      EllipsoidPlanSelected{selected_index, std::move(replay_result)},
      Assurance::numerical};
}
} // namespace csl::optimization
