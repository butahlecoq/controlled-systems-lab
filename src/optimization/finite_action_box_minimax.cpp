#include <csl/optimization/finite_action_box_minimax.hpp>

#include "finite_action_replay.hpp"
#include "finite_action_plans.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string message) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

std::variant<sets::SetData, Unsupported> terminal_box(const reachability::BoxStage& box,
    std::size_t corner_limit) {
    const auto dimension = box.lower.size();
    if(dimension >= std::numeric_limits<std::size_t>::digits)
        return unsupported("finite_box_minimax.dimension", "Terminal dimension exceeds corner enumeration capacity.");
    const auto count = std::size_t{1} << dimension;
    if(count > corner_limit)
        return unsupported("finite_box_minimax.corners", "Terminal box corner count exceeds caller limit.");
    if(dimension != 0 && count > std::numeric_limits<std::size_t>::max() / dimension)
        return unsupported("finite_box_minimax.capacity", "Terminal corner storage size overflows.");
    Matrix corners{count, dimension, Vector(count * dimension)};
    for(std::size_t mask = 0; mask < count; ++mask)
        for(std::size_t coordinate = 0; coordinate < dimension; ++coordinate)
            corners.values[mask * dimension + coordinate] = (mask & (std::size_t{1} << coordinate))
                ? box.upper[coordinate] : box.lower[coordinate];
    auto vertices = numeric::snapshot(std::move(corners));
    if(const auto* error = std::get_if<Diagnostic>(&vertices))
        return unsupported(error->field, error->explanation);
    Matrix rays{0, dimension, {}};
    auto ray_view = numeric::snapshot(std::move(rays));
    if(const auto* error = std::get_if<Diagnostic>(&ray_view))
        return unsupported(error->field, error->explanation);
    auto set = sets::make_v({{"finite-box-terminal-corners"}, dimension, {}},
        {std::get<numeric::MatrixView>(std::move(vertices)),
         std::get<numeric::MatrixView>(std::move(ray_view))});
    if(const auto* error = std::get_if<Diagnostic>(&set))
        return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(std::move(set));
}

}

FiniteActionBoxMinimaxOutcome finite_action_box_minimax(
    const FiniteActionMinimaxRequest& request, FiniteActionBoxMinimaxLimits limits,
    const ExecutionContext& context) {
    const auto horizon = request.system.horizon();
    if(request.problem.value.empty() || request.request.value.empty())
        return unsupported("finite_box_minimax.identity", "Problem and request identities must be nonempty.");
    if(request.actions.catalogue.empty() && horizon != 0)
        return unsupported("finite_box_minimax.actions", "A nonempty finite action catalogue is required.");
    std::size_t plan_count = 1;
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(request.actions.catalogue.size() != 0 &&
           plan_count > limits.max_plans / request.actions.catalogue.size())
            return unsupported("finite_box_minimax.plans", "Action plan count exceeds caller limit.");
        plan_count *= request.actions.catalogue.size();
    }
    if(plan_count > limits.max_plans)
        return unsupported("finite_box_minimax.plans", "Action plan count exceeds caller limit.");
    if(request.objective.dimension() != request.system.dimensions().state ||
       request.actions.dimension != request.system.dimensions().control ||
       request.disturbances.size() != horizon || request.admissible_states.size() != horizon + 1)
        return unsupported("finite_box_minimax.dimensions", "Objective, catalogue or stage dimensions differ from the model.");

    std::vector<FiniteActionBoxPlanAttempt> attempts;
    attempts.reserve(plan_count);
    std::optional<std::size_t> selected_index;
    double minimum = std::numeric_limits<double>::infinity();
    bool search_stopped = false;
    for(std::size_t plan_index = 0; plan_index < plan_count; ++plan_index) {
        const auto choices = detail::action_plan_indices(plan_index,
            request.actions.catalogue.size(), horizon);
        if(context.cancellation.stop_requested()) {
            attempts.emplace_back(BoxPlanStopped{choices,
                {StopReason::cancelled, "Approximate finite minimax cancelled."}});
            search_stopped = true;
            break;
        }
        std::vector<Vector> controls;
        controls.reserve(horizon);
        for(const auto choice : choices) controls.push_back(request.actions.catalogue[choice]);
        reachability::FixedPlanRequest plan{request.system, request.initial, std::move(controls),
            request.disturbances, request.admissible_states,
            {request.request.value + "/box-plan/" + std::to_string(plan_index)}};
        auto propagated = reachability::finite_plan_box(plan, context);
        if(const auto* error = std::get_if<Unsupported>(&propagated)) {
            attempts.emplace_back(BoxPlanUnscored{choices, *error});
            continue;
        }
        if(const auto* stop = std::get_if<OperationStopped>(&propagated)) {
            attempts.emplace_back(BoxPlanStopped{choices, *stop});
            search_stopped = true;
            break;
        }
        auto trace = std::get<reachability::FinitePlanBoxTrace>(std::move(propagated));
        auto corners = terminal_box(trace.stages.back(), limits.max_box_corners);
        if(const auto* error = std::get_if<Unsupported>(&corners)) {
            attempts.emplace_back(BoxPlanUnscored{choices, *error});
            continue;
        }
        const auto score = worst_case_vertex(std::get<sets::SetData>(corners), request.objective,
            limits.max_box_corners, context);
        if(const auto* error = std::get_if<Unsupported>(&score)) {
            attempts.emplace_back(BoxPlanUnscored{choices, *error});
            continue;
        }
        if(const auto* stop = std::get_if<OperationStopped>(&score)) {
            attempts.emplace_back(BoxPlanStopped{choices, *stop});
            search_stopped = true;
            break;
        }
        if(std::holds_alternative<WorstCaseEmpty>(score)) {
            attempts.emplace_back(BoxPlanUnscored{choices,
                unsupported("finite_box_minimax.empty", "An empty terminal box cannot be scored.")});
            continue;
        }
        const auto value = std::get<WorstCaseValue>(score).value;
        const auto attempt_index = attempts.size();
        attempts.emplace_back(BoxPlanScored{choices, value, std::move(trace)});
        if(value < minimum) {
            minimum = value;
            selected_index = attempt_index;
        }
    }

    const auto coverage = !search_stopped && attempts.size() == plan_count &&
        std::all_of(attempts.begin(), attempts.end(), [](const auto& attempt) {
            return std::holds_alternative<BoxPlanScored>(attempt);
        }) ? CandidateSearchCoverage::complete : CandidateSearchCoverage::incomplete;
    if(!selected_index)
        return FiniteActionBoxMinimaxResult{request.problem, request.request,
            std::move(attempts), CandidateSearchCoverage::incomplete,
            BoxNoScoredCandidate{}, Assurance::numerical};

    const auto selected_choices = std::get<BoxPlanScored>(attempts[*selected_index]).action_indices;
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for(const auto choice : selected_choices) controls.push_back(request.actions.catalogue[choice]);
    reachability::FixedPlanRequest replay_request{request.system, request.initial,
        std::move(controls), request.disturbances, request.admissible_states,
        {request.request.value + "/box-selected-replay"}};
    const auto replay = detail::replay_finite_action_plan(replay_request, request.objective,
        limits.max_points_per_stage, limits.max_replay_histories, "finite_box_minimax", context);
    if(const auto* error = std::get_if<Unsupported>(&replay))
        return FiniteActionBoxMinimaxResult{request.problem, request.request,
            std::move(attempts), coverage, BoxPlanReplayRefused{*selected_index, *error},
            Assurance::numerical};
    if(const auto* stop = std::get_if<OperationStopped>(&replay))
        return FiniteActionBoxMinimaxResult{request.problem, request.request,
            std::move(attempts), coverage, BoxPlanReplayStopped{*selected_index, *stop},
            Assurance::numerical};
    const auto& replayed = std::get<detail::FiniteActionReplay>(replay);
    return FiniteActionBoxMinimaxResult{request.problem, request.request, std::move(attempts),
        coverage, BoxPlanSelected{*selected_index, {replayed.value, replayed.terminal_state,
            replayed.disturbance_indices, replayed.disturbances, replayed.path,
            replayed.terminal_catalogue}}, Assurance::numerical};
}
} // namespace csl::optimization
