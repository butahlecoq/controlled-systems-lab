#include <csl/optimization/finite_action_box_minimax.hpp>

#include "finite_action_plans.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
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

std::variant<std::vector<Vector>, Unsupported> catalogue(const sets::SetData& set,
    std::string field) {
    const auto dimension = set.metadata()->set.dimension;
    const auto rep = set.representation();
    if(const auto* singleton = std::get_if<sets::SingletonRepresentation>(&rep)) {
        const auto values = singleton->point.values();
        return std::vector<Vector>{Vector(values.begin(), values.end())};
    }
    const auto* vertices = std::get_if<sets::VRepresentation>(&rep);
    if(!vertices || vertices->rays.rows() != 0 || vertices->vertices.rows() == 0)
        return unsupported(std::move(field), "Replay requires a nonempty bounded V set or singleton.");
    std::vector<Vector> result;
    result.reserve(vertices->vertices.rows());
    for(std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
        Vector point(dimension);
        for(std::size_t col = 0; col < dimension; ++col) point[col] = vertices->vertices(row,col);
        result.push_back(std::move(point));
    }
    return result;
}

struct Replay {
    double value{-std::numeric_limits<double>::infinity()};
    Vector terminal;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
};

using ReplayOutcome = std::variant<Replay, Unsupported, OperationStopped>;

ReplayOutcome replay_all(const reachability::FixedPlanRequest& request, const Objective& objective,
    std::size_t point_limit, const ExecutionContext& context) {
    auto initial_result = catalogue(request.initial, "finite_box_minimax.replay.initial");
    if(const auto* error = std::get_if<Unsupported>(&initial_result)) return *error;
    const auto& initial = std::get<std::vector<Vector>>(initial_result);
    std::vector<std::vector<Vector>> disturbances;
    disturbances.reserve(request.disturbances.size());
    std::size_t total = initial.size();
    for(const auto& set : request.disturbances) {
        auto rows = catalogue(set, "finite_box_minimax.replay.disturbance");
        if(const auto* error = std::get_if<Unsupported>(&rows)) return *error;
        const auto count = std::get<std::vector<Vector>>(rows).size();
        if(count == 0 || total > point_limit / count)
            return unsupported("finite_box_minimax.replay.capacity", "Replay history count exceeds caller limit.");
        total *= count;
        disturbances.push_back(std::get<std::vector<Vector>>(std::move(rows)));
    }
    if(initial.empty()) return unsupported("finite_box_minimax.replay.empty", "Replay has no initial states.");
    Replay best;
    std::vector<std::size_t> indices;
    std::vector<Vector> chosen_disturbances;
    std::vector<Vector> path;
    std::optional<Unsupported> failure;
    std::optional<OperationStopped> stopped;
    std::function<void(std::size_t,const Vector&)> visit = [&](std::size_t stage, const Vector& state) {
        if(failure || stopped) return;
        if(context.cancellation.stop_requested()) {
            stopped = OperationStopped{StopReason::cancelled, "Worst-case witness replay cancelled."};
            return;
        }
        if(context.deadline && std::chrono::steady_clock::now() >= *context.deadline) {
            stopped = OperationStopped{StopReason::deadline_expired, "Worst-case witness replay deadline expired."};
            return;
        }
        if(stage == request.system.horizon()) {
            auto scored = evaluate(objective, state);
            if(const auto* error = std::get_if<Diagnostic>(&scored)) {
                failure = unsupported(error->field, error->explanation);
                return;
            }
            if(const auto* stop = std::get_if<OperationStopped>(&scored)) {
                stopped = *stop;
                return;
            }
            const auto value = std::get<double>(scored);
            if(value > best.value) {
                best.value = value;
                best.terminal = state;
                best.disturbance_indices = indices;
                best.disturbances = chosen_disturbances;
                best.path = path;
            }
            return;
        }
        for(std::size_t index = 0; index < disturbances[stage].size(); ++index) {
            const auto next = request.system.step({stage}, state, request.controls[stage], disturbances[stage][index]);
            if(const auto* error = std::get_if<Diagnostic>(&next)) {
                failure = unsupported(error->field, error->explanation);
                return;
            }
            if(const auto* stop = std::get_if<OperationStopped>(&next)) {
                stopped = *stop;
                return;
            }
            indices.push_back(index);
            chosen_disturbances.push_back(disturbances[stage][index]);
            path.push_back(std::get<Vector>(next));
            visit(stage + 1, path.back());
            path.pop_back();
            chosen_disturbances.pop_back();
            indices.pop_back();
            if(failure || stopped) return;
        }
    };
    for(const auto& state : initial) {
        path = {state};
        visit(0, state);
        if(failure) return *failure;
        if(stopped) return *stopped;
    }
    if(!std::isfinite(best.value))
        return unsupported("finite_box_minimax.replay.empty", "Replay produced no finite terminal score.");
    return best;
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

    std::vector<BoxPlanScore> scores;
    scores.reserve(plan_count);
    std::size_t selected_index = 0;
    double minimum = std::numeric_limits<double>::infinity();
    reachability::FinitePlanBoxTrace selected_trace;
    for(std::size_t plan_index = 0; plan_index < plan_count; ++plan_index) {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled, "Approximate finite minimax cancelled."};
        const auto choices = detail::action_plan_indices(plan_index,
            request.actions.catalogue.size(), horizon);
        std::vector<Vector> controls;
        controls.reserve(horizon);
        for(const auto choice : choices) controls.push_back(request.actions.catalogue[choice]);
        reachability::FixedPlanRequest plan{request.system, request.initial, std::move(controls),
            request.disturbances, request.admissible_states,
            {request.request.value + "/box-plan/" + std::to_string(plan_index)}};
        auto propagated = reachability::finite_plan_box(plan, context);
        if(const auto* error = std::get_if<Unsupported>(&propagated)) return *error;
        if(const auto* stop = std::get_if<OperationStopped>(&propagated)) return *stop;
        auto corners = terminal_box(std::get<reachability::FinitePlanBoxTrace>(propagated).stages.back(),
            limits.max_box_corners);
        if(const auto* error = std::get_if<Unsupported>(&corners)) return *error;
        const auto score = worst_case_vertex(std::get<sets::SetData>(corners), request.objective,
            limits.max_box_corners, context);
        if(const auto* error = std::get_if<Unsupported>(&score)) return *error;
        if(const auto* stop = std::get_if<OperationStopped>(&score)) return *stop;
        if(std::holds_alternative<WorstCaseEmpty>(score))
            return unsupported("finite_box_minimax.empty", "An empty terminal box cannot be scored.");
        const auto value = std::get<WorstCaseValue>(score).value;
        scores.push_back({choices, value});
        if(value < minimum) {
            minimum = value;
            selected_index = plan_index;
            selected_trace = std::get<reachability::FinitePlanBoxTrace>(std::move(propagated));
        }
    }

    const auto selected_choices = scores[selected_index].action_indices;
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for(const auto choice : selected_choices) controls.push_back(request.actions.catalogue[choice]);
    reachability::FixedPlanRequest replay_request{request.system, request.initial,
        std::move(controls), request.disturbances, request.admissible_states,
        {request.request.value + "/box-selected-replay"}};
    const auto replay = reachability::fixed_plan_disturbance(replay_request,
        limits.max_points_per_stage, context);
    if(const auto* error = std::get_if<Unsupported>(&replay)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&replay)) return *stop;
    if(const auto* violation = std::get_if<reachability::FixedPlanViolation>(&replay))
        return unsupported("finite_box_minimax.replay", "Selected plan violates a declared state constraint at stage " +
            std::to_string(violation->stage) + ".");
    if(std::holds_alternative<reachability::FixedPlanEmpty>(replay))
        return unsupported("finite_box_minimax.replay", "Selected plan has no disturbance trajectories.");
    const auto& tube = std::get<reachability::FixedPlanReachable>(replay);
    const auto terminal = tube.stages.back();
    const auto replay_score = worst_case_vertex(terminal, request.objective,
        limits.max_points_per_stage, context);
    if(const auto* error = std::get_if<Unsupported>(&replay_score)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&replay_score)) return *stop;
    if(std::holds_alternative<WorstCaseEmpty>(replay_score))
        return unsupported("finite_box_minimax.replay", "Selected terminal catalogue is empty.");
    const auto& realized = std::get<WorstCaseValue>(replay_score);
    const auto witness = replay_all(replay_request, request.objective,
        limits.max_replay_histories, context);
    if(const auto* error = std::get_if<Unsupported>(&witness)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&witness)) return *stop;
    const auto& replayed = std::get<Replay>(witness);
    const auto scale = std::max({1.0, std::abs(realized.value), std::abs(replayed.value)});
    const auto tolerance = context.numerical.absolute_tolerance + context.numerical.relative_tolerance * scale;
    if(std::abs(realized.value - replayed.value) > tolerance || replayed.terminal != realized.maximizer)
        return OperationStopped{StopReason::numerical_failure, "Full-history witness does not match terminal catalogue scoring."};
    return FiniteActionBoxMinimaxResult{request.problem, request.request, std::move(scores), selected_choices,
        minimum, replayed.value, replayed.terminal, replayed.disturbance_indices,
        replayed.disturbances, replayed.path, terminal, std::move(selected_trace), Assurance::numerical};
}
} // namespace csl::optimization
