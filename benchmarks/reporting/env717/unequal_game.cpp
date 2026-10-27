#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

sets::SetData vertices(std::string id, Matrix points) {
    return take(sets::make_v({{std::move(id)}, 1, {}},
        {take(numeric::snapshot(std::move(points))),
         take(numeric::snapshot(Matrix{0, 1, {}}))}));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 3;
    constexpr double dt = 0.05;
    const SystemModel authored{{{1, 1, 1}, TimeDomain::discrete,
        LinearStage{{1, 1, {1.0}}, {1, 1, {dt}}, {1, 1, {dt}}, {0.0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{1.0}));
    std::vector<sets::SetData> disturbances;
    disturbances.reserve(horizon);
    for(std::size_t stage = 0; stage < horizon; ++stage)
        disturbances.push_back(vertices("unequal-disturbance-catalogue-" +
            std::to_string(stage), Matrix{3, 1, {-1.0, 0.0, 1.0}}));
    std::vector<sets::SetData> admissible;
    admissible.reserve(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        admissible.push_back(take(sets::make_universal(
            {{"unequal-unconstrained-" + std::to_string(stage)}, 1, {}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        {1, 1, {2.0}}, {0.0}, 0.0}));
    return {{"env717-unequal-game-short-horizon-v1"}, {"env717-unequal-game"},
        system, vertices("unequal-initial-state", Matrix{1, 1, {1.0}}),
        {1, {{-2.0}, {0.0}, {2.0}}}, std::move(disturbances),
        std::move(admissible), objective};
}

Json result_record() {
    constexpr std::array<double, 3> controls{-2.0, 0.0, 2.0};
    constexpr double tolerance = 1e-12;
    const auto input = request();
    std::vector<std::int64_t> measured_ns;
    FiniteActionMinimaxOutcome outcome;
    for(std::size_t repetition = 0; repetition <= 7; ++repetition) {
        const auto started = std::chrono::steady_clock::now();
        outcome = finite_action_minimax(input, {27, 27, tolerance});
        const auto stopped = std::chrono::steady_clock::now();
        if(repetition > 0)
            measured_ns.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(
                stopped - started).count());
    }
    const auto* result = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!result) throw std::runtime_error("finite-action minimax did not return an optimum");
    if(result->plans.size() != 27 || result->minimizing_plan_indices.empty())
        throw std::runtime_error("unexpected exhaustive action catalogue");

    Json plans = Json::array();
    for(std::size_t index = 0; index < result->plans.size(); ++index) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&result->plans[index]);
        if(!plan) throw std::runtime_error("unconstrained game rejected a control plan");
        Json values = Json::array();
        for(const auto action_index : plan->action_indices) {
            if(action_index >= controls.size()) throw std::runtime_error("invalid control index");
            values.push_back(controls[action_index]);
        }
        plans.push_back({{"plan_index", index}, {"controls", std::move(values)},
            {"worst_terminal_squared_state", plan->worst_value},
            {"maximizing_terminal_state", plan->maximizer}});
    }
    Json minimizing = Json::array();
    for(const auto index : result->minimizing_plan_indices) minimizing.push_back(index);
    auto ordered_ns = measured_ns;
    std::sort(ordered_ns.begin(), ordered_ns.end());
    return {{"schema", "csl.env717-unequal-game-pilot/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "a05c7caafa8c36b44f75a8c3e3355677419af6c4"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"position"}},
        {"source_model", {{"initial_state", {0.0, 1.0}}, {"dt_seconds", 0.05},
            {"source_horizon_seconds", 2.0}, {"u_bounds", {-2.0, 2.0}},
            {"v_bounds", {-1.0, 1.0}}, {"reward", "squared terminal position"},
            {"transition", "t_next=t+dt; x_next=x+dt*(u+v)"}}},
        {"adaptation", {{"horizon_steps", 3}, {"terminal_time_seconds", 0.15},
            {"u_catalogue", {-2.0, 0.0, 2.0}}, {"v_catalogue", {-1.0, 0.0, 1.0}},
            {"information_pattern", "open-loop control sequence; adversary chooses a full disturbance sequence"},
            {"objective", "minimize maximum squared terminal position over all disturbance vertices"},
            {"stage_map", "x_next=x+0.05*u+0.05*v"},
            {"safe_state", "unbounded one-dimensional state"}}},
        {"algorithm", "csl.finite-action-minimax.numerical"},
        {"assurance", "numerical; exhaustive over all 27 fixed control plans and 27 disturbance sequences per plan"},
        {"environment", {{"compiler_id", CSL_ENV717_UNEQUAL_COMPILER_ID},
            {"compiler_version", CSL_ENV717_UNEQUAL_COMPILER_VERSION},
            {"build_type", CSL_ENV717_UNEQUAL_BUILD_TYPE},
            {"architecture", CSL_ENV717_UNEQUAL_ARCHITECTURE}, {"requested_workers", 1},
            {"solver_parallelism", "single-threaded"}}},
        {"objective_value", result->value}, {"minimizing_plan_indices", std::move(minimizing)},
        {"plan_count", result->plans.size()}, {"plans", std::move(plans)},
        {"near_optimal_tolerance", tolerance},
        {"timing", {{"scope", "finite_action_minimax call; request setup and JSON output excluded"},
            {"warmup_calls", 1}, {"measured_calls", measured_ns.size()},
            {"measured_wall_ns", measured_ns}, {"median_wall_ns", ordered_ns[3]},
            {"min_wall_ns", ordered_ns.front()}, {"max_wall_ns", ordered_ns.back()},
            {"limiter_profile", "not collected; no comparative speed claim"}}},
        {"driver_sha256", CSL_ENV717_UNEQUAL_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_UNEQUAL_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_UNEQUAL_SOURCE_COMMIT}};
}
}

int main() {
    try {
        std::cout << result_record().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "unequal game pilot failed: " << error.what() << '\n';
        return 1;
    }
}
