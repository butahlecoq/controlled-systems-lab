#include <csl/optimization/finite_action_zonotope_minimax.hpp>

#include "finite_action_plans.hpp"
#include "finite_action_replay.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string message) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

struct CornerScore {
    double maximum;
    std::size_t evaluated;
};

using CornerScoreOutcome = std::variant<CornerScore, Unsupported, OperationStopped>;

CornerScoreOutcome score_corners(const reachability::FinitePlanZonotopeTrace::Stage& terminal,
    const Objective& objective, std::size_t corner_limit, const ExecutionContext& context) {
    const auto dimension = terminal.center.size();
    const auto generators = terminal.generators.cols;
    if(terminal.generators.rows != dimension || terminal.factors.size() != generators)
        return unsupported("finite_zonotope_minimax.terminal", "Terminal zonotope generator data are inconsistent.");
    if(generators >= std::numeric_limits<std::size_t>::digits)
        return unsupported("finite_zonotope_minimax.corners", "Terminal generator count exceeds corner enumeration capacity.");
    const auto count = std::size_t{1} << generators;
    if(count > corner_limit)
        return unsupported("finite_zonotope_minimax.corners", "Terminal factor-corner count exceeds caller limit.");
    double maximum = -std::numeric_limits<double>::infinity();
    for(std::size_t mask = 0; mask < count; ++mask) {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled, "Zonotope candidate scoring cancelled."};
        if(context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return OperationStopped{StopReason::deadline_expired, "Zonotope candidate scoring deadline expired."};
        Vector point = terminal.center;
        for(std::size_t column = 0; column < generators; ++column) {
            const double sign = (mask & (std::size_t{1} << column)) ? 1.0 : -1.0;
            for(std::size_t row = 0; row < dimension; ++row)
                point[row] += sign * terminal.generators.values[row * generators + column];
        }
        const auto value = evaluate(objective, point);
        if(const auto* error = std::get_if<Diagnostic>(&value))
            return unsupported(error->field, error->explanation);
        if(const auto* stop = std::get_if<OperationStopped>(&value)) return *stop;
        maximum = std::max(maximum, std::get<double>(value));
    }
    if(!std::isfinite(maximum))
        return unsupported("finite_zonotope_minimax.score", "Terminal factor corners produced no finite score.");
    return CornerScore{maximum, count};
}
}

FiniteActionZonotopeMinimaxOutcome finite_action_zonotope_minimax(
    const FiniteActionMinimaxRequest& request, FiniteActionZonotopeMinimaxLimits limits,
    const ExecutionContext& context) {
    const auto horizon = request.system.horizon();
    if(request.problem.value.empty() || request.request.value.empty())
        return unsupported("finite_zonotope_minimax.identity", "Problem and request identities must be nonempty.");
    if(request.actions.catalogue.empty() && horizon != 0)
        return unsupported("finite_zonotope_minimax.actions", "A nonempty finite action catalogue is required.");
    std::size_t plan_count = 1;
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(request.actions.catalogue.size() != 0 &&
           plan_count > limits.max_plans / request.actions.catalogue.size())
            return unsupported("finite_zonotope_minimax.plans", "Action plan count exceeds caller limit.");
        plan_count *= request.actions.catalogue.size();
    }
    if(plan_count > limits.max_plans)
        return unsupported("finite_zonotope_minimax.plans", "Action plan count exceeds caller limit.");
    if(request.objective.dimension() != request.system.dimensions().state ||
       request.actions.dimension != request.system.dimensions().control ||
       request.disturbances.size() != horizon || request.admissible_states.size() != horizon + 1)
        return unsupported("finite_zonotope_minimax.dimensions", "Objective, catalogue or stage dimensions differ from the model.");

    std::vector<FiniteActionZonotopePlanAttempt> attempts;
    attempts.reserve(plan_count);
    bool complete = true;
    std::size_t selected_index = 0;
    double minimum = std::numeric_limits<double>::infinity();
    bool has_scored = false;
    for(std::size_t plan_index = 0; plan_index < plan_count; ++plan_index) {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled, "Zonotope finite minimax cancelled."};
        if(context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return OperationStopped{StopReason::deadline_expired, "Zonotope finite minimax deadline expired."};
        const auto choices = detail::action_plan_indices(plan_index,
            request.actions.catalogue.size(), horizon);
        std::vector<Vector> controls;
        controls.reserve(horizon);
        for(const auto choice : choices) controls.push_back(request.actions.catalogue[choice]);
        reachability::FixedPlanRequest plan{request.system, request.initial, std::move(controls),
            request.disturbances, request.admissible_states,
            {request.request.value + "/zonotope-plan/" + std::to_string(plan_index)}};
        auto propagated = reachability::finite_plan_zonotope(plan,
            {limits.max_generators_per_stage}, context);
        if(const auto* stop = std::get_if<OperationStopped>(&propagated)) return *stop;
        if(const auto* error = std::get_if<Unsupported>(&propagated)) {
            attempts.emplace_back(ZonotopePlanUnscored{choices, *error});
            complete = false;
            continue;
        }
        auto trace = std::get<reachability::FinitePlanZonotopeTrace>(std::move(propagated));
        auto scored = score_corners(trace.stages.back(), request.objective,
            limits.max_factor_corners, context);
        if(const auto* stop = std::get_if<OperationStopped>(&scored)) return *stop;
        if(const auto* error = std::get_if<Unsupported>(&scored)) {
            attempts.emplace_back(ZonotopePlanUnscored{choices, *error});
            complete = false;
            continue;
        }
        const auto score = std::get<CornerScore>(scored);
        attempts.emplace_back(ZonotopePlanScored{choices,
            {score.maximum, trace.stages.back().generators.cols, score.evaluated, std::move(trace)}});
        if(score.maximum < minimum) {
            minimum = score.maximum;
            selected_index = plan_index;
            has_scored = true;
        }
    }
    const auto coverage = complete ? CandidateSearchCoverage::complete : CandidateSearchCoverage::incomplete;
    if(!has_scored)
        return FiniteActionZonotopeMinimaxResult{request.problem, request.request,
            std::move(attempts), coverage, ZonotopeNoScoredCandidate{}, Assurance::numerical};

    const auto& selected_attempt = std::get<ZonotopePlanScored>(attempts[selected_index]);
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for(const auto choice : selected_attempt.action_indices) controls.push_back(request.actions.catalogue[choice]);
    reachability::FixedPlanRequest replay_request{request.system, request.initial, std::move(controls),
        request.disturbances, request.admissible_states,
        {request.request.value + "/zonotope-selected-replay"}};
    const auto replay = detail::replay_finite_action_plan(replay_request, request.objective,
        limits.max_points_per_stage, limits.max_replay_histories,
        "finite_zonotope_minimax", context);
    if(const auto* error = std::get_if<Unsupported>(&replay))
        return FiniteActionZonotopeMinimaxResult{request.problem, request.request,
            std::move(attempts), coverage, ZonotopePlanReplayRefused{selected_index, *error}, Assurance::numerical};
    if(const auto* stop = std::get_if<OperationStopped>(&replay))
        return FiniteActionZonotopeMinimaxResult{request.problem, request.request,
            std::move(attempts), coverage, ZonotopePlanReplayStopped{selected_index, *stop}, Assurance::numerical};
    const auto& realized = std::get<detail::FiniteActionReplay>(replay);
    FiniteActionZonotopeReplay replay_result{realized.value, realized.terminal_state,
        realized.disturbance_indices, realized.disturbances, realized.path, realized.terminal_catalogue};
    return FiniteActionZonotopeMinimaxResult{request.problem, request.request,
        std::move(attempts), coverage, ZonotopePlanSelected{selected_index, std::move(replay_result)},
        Assurance::numerical};
}
} // namespace csl::optimization
