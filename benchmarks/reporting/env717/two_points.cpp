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

sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(points))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 3;
    const SystemModel authored{{{4, 1, 1}, TimeDomain::discrete,
        LinearStage{{4, 4, {1.0, 0.01, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 1.0, 0.1,
                            0.0, 0.0, 0.0, 1.0}},
                    {4, 1, {0.09, 1.0, 0.0, 0.0}},
                    {4, 1, {0.0, 0.0, 0.0045, 0.1}},
                    {0.0, 0.0, 0.0, 0.0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{0.0, 0.1, 0.2, 0.3}));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("point2-acceleration-catalogue", 1, Matrix{3, 1, {-1.0, 0.0, 1.0}}));
    std::vector<sets::SetData> safe;
    safe.reserve(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"two-points-unconstrained-" + std::to_string(stage)}, 4, {}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        {4, 4, {2.0, 0.0, -2.0, 0.0,
                0.0, 0.0, 0.0, 0.0,
                -2.0, 0.0, 2.0, 0.0,
                0.0, 0.0, 0.0, 0.0}},
        {0.0, 0.0, 0.0, 0.0}, 0.0}));
    return {{"env717-two-points-short-horizon-v1"}, {"env717-two-points"},
        system, vertices("two-points-initial", 4, Matrix{1, 4, {4.5, 0.0, 0.0, 0.0}}),
        {1, {{-2.5}, {0.0}, {2.5}}}, std::move(disturbances), std::move(safe), objective};
}

Json result_record() {
    constexpr std::array<double, 3> controls{-2.5, 0.0, 2.5};
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
            {"worst_terminal_squared_gap", plan->worst_value},
            {"maximizing_terminal_state", plan->maximizer}});
    }
    Json minimizing = Json::array();
    for(const auto index : result->minimizing_plan_indices) minimizing.push_back(index);
    auto ordered_ns = measured_ns;
    std::sort(ordered_ns.begin(), ordered_ns.end());
    return {{"schema", "csl.env717-two-points-pilot/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "4e71bed8ceffa1990645fb85e54d6b5b1eeb688d"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"position_1", "velocity_1", "position_2", "velocity_2"}},
        {"source_model", {{"initial_state", {4.5, 0.0, 0.0, 0.0}},
            {"alpha", 1.0}, {"m1", 0.01}, {"m2", 1.0},
            {"dt_seconds", 0.1}, {"inner_euler_steps", 10},
            {"source_horizon_seconds", 10.0}, {"u_bounds", {-2.5, 2.5}},
            {"v_bounds", {-1.0, 1.0}},
            {"reward", "negative absolute terminal position gap"}}},
        {"adaptation", {{"horizon_steps", 3}, {"terminal_time_seconds", 0.3},
            {"u_catalogue", {-2.5, 0.0, 2.5}}, {"v_catalogue", {-1.0, 0.0, 1.0}},
            {"information_pattern", "open-loop control sequence; adversary chooses a full disturbance sequence"},
            {"objective", "minimize maximum terminal squared position gap; monotone-equivalent to source absolute-gap reward"},
            {"safe_state", "unbounded four-dimensional state"},
            {"discrete_stage_map", "p1+=0.01*v1+0.09*u; v1+=u; p2+=0.1*v2+0.0045*v; v2+=0.1*v"}}},
        {"algorithm", "csl.finite-action-minimax.numerical"},
        {"assurance", "numerical; exhaustive over all 27 fixed control plans and 27 disturbance sequences per plan"},
        {"environment", {{"compiler_id", CSL_ENV717_COMPILER_ID},
            {"compiler_version", CSL_ENV717_COMPILER_VERSION},
            {"build_type", CSL_ENV717_BUILD_TYPE},
            {"architecture", CSL_ENV717_ARCHITECTURE}, {"requested_workers", 1},
            {"solver_parallelism", "single-threaded"}}},
        {"objective_value", result->value}, {"worst_terminal_gap", std::sqrt(result->value)},
        {"minimizing_plan_indices", std::move(minimizing)}, {"plan_count", result->plans.size()},
        {"plans", std::move(plans)}, {"near_optimal_tolerance", tolerance},
        {"timing", {{"scope", "finite_action_minimax call; request setup and JSON output excluded"},
            {"warmup_calls", 1}, {"measured_calls", measured_ns.size()},
            {"measured_wall_ns", measured_ns}, {"median_wall_ns", ordered_ns[3]},
            {"min_wall_ns", ordered_ns.front()}, {"max_wall_ns", ordered_ns.back()},
            {"limiter_profile", "not collected; no comparative speed claim"}}},
        {"driver_sha256", CSL_ENV717_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_SOURCE_COMMIT}};
}
}

int main() {
    try {
        std::cout << result_record().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "two-points pilot failed: " << error.what() << '\n';
        return 2;
    }
}
