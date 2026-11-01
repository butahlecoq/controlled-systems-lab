#include "finite_action_replay.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <limits>
#include <optional>

namespace csl::optimization::detail {
namespace {
Unsupported unsupported(std::string field, std::string message) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
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

struct Witness {
    double value{-std::numeric_limits<double>::infinity()};
    Vector terminal;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
};

using WitnessOutcome = std::variant<Witness, Unsupported, OperationStopped>;

WitnessOutcome replay_all(const reachability::FixedPlanRequest& request, const Objective& objective,
    std::size_t history_limit, std::string_view prefix, const ExecutionContext& context) {
    auto initial_result = catalogue(request.initial, std::string(prefix) + ".replay.initial");
    if(const auto* error = std::get_if<Unsupported>(&initial_result)) return *error;
    const auto& initial = std::get<std::vector<Vector>>(initial_result);
    std::vector<std::vector<Vector>> disturbances;
    disturbances.reserve(request.disturbances.size());
    std::size_t total = initial.size();
    if(total > history_limit)
        return unsupported(std::string(prefix) + ".replay.capacity", "Initial replay count exceeds caller limit.");
    for(const auto& set : request.disturbances) {
        auto rows = catalogue(set, std::string(prefix) + ".replay.disturbance");
        if(const auto* error = std::get_if<Unsupported>(&rows)) return *error;
        const auto count = std::get<std::vector<Vector>>(rows).size();
        if(count == 0 || total > history_limit / count)
            return unsupported(std::string(prefix) + ".replay.capacity", "Replay history count exceeds caller limit.");
        total *= count;
        disturbances.push_back(std::get<std::vector<Vector>>(std::move(rows)));
    }
    if(initial.empty()) return unsupported(std::string(prefix) + ".replay.empty", "Replay has no initial states.");
    Witness best;
    std::vector<std::size_t> indices;
    std::vector<Vector> chosen_disturbances;
    std::vector<Vector> path;
    std::optional<Unsupported> failure;
    std::optional<OperationStopped> stopped;
    std::function<void(std::size_t,Vector)> visit = [&](std::size_t stage, Vector state) {
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
        return unsupported(std::string(prefix) + ".replay.empty", "Replay produced no finite terminal score.");
    return best;
}
}

FiniteActionReplayOutcome replay_finite_action_plan(const reachability::FixedPlanRequest& request,
    const Objective& objective, std::size_t point_limit, std::size_t history_limit,
    std::string_view prefix, const ExecutionContext& context) {
    const auto exact = reachability::fixed_plan_disturbance(request, point_limit, context);
    if(const auto* error = std::get_if<Unsupported>(&exact)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&exact)) return *stop;
    if(const auto* violation = std::get_if<reachability::FixedPlanViolation>(&exact))
        return unsupported(std::string(prefix) + ".replay", "Selected plan violates a declared state constraint at stage " +
            std::to_string(violation->stage) + ".");
    if(std::holds_alternative<reachability::FixedPlanEmpty>(exact))
        return unsupported(std::string(prefix) + ".replay", "Selected plan has no disturbance trajectories.");
    const auto terminal = std::get<reachability::FixedPlanReachable>(exact).stages.back();
    const auto exact_score = worst_case_vertex(terminal, objective, point_limit, context);
    if(const auto* error = std::get_if<Unsupported>(&exact_score)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&exact_score)) return *stop;
    if(std::holds_alternative<WorstCaseEmpty>(exact_score))
        return unsupported(std::string(prefix) + ".replay", "Selected terminal catalogue is empty.");
    auto witness = replay_all(request, objective, history_limit, prefix, context);
    if(const auto* error = std::get_if<Unsupported>(&witness)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&witness)) return *stop;
    const auto& replayed = std::get<Witness>(witness);
    const auto realized = std::get<WorstCaseValue>(exact_score);
    const auto scale = std::max({1.0, std::abs(realized.value), std::abs(replayed.value)});
    const auto tolerance = context.numerical.absolute_tolerance + context.numerical.relative_tolerance * scale;
    if(std::abs(realized.value - replayed.value) > tolerance)
        return OperationStopped{StopReason::numerical_failure,
            "Full-history witness does not match terminal catalogue scoring."};
    return FiniteActionReplay{replayed.value, replayed.terminal, replayed.disturbance_indices,
        replayed.disturbances, replayed.path, terminal};
}
} // namespace csl::optimization::detail
