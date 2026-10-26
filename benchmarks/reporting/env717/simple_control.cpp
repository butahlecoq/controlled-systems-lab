#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
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

sets::SetData singleton(std::string id, double x) {
    return take(sets::make_singleton({{std::move(id)}, 1, {"x"}},
        take(numeric::snapshot_vector(Vector{x}))));
}

sets::SetData no_disturbance() {
    return take(sets::make_v({{"environment-zero-disturbance"}, 1, {"w"}},
        {take(numeric::snapshot(Matrix{1, 1, {0.0}})),
         take(numeric::snapshot(Matrix{0, 1, {}}))}));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 4;
    constexpr double step = 0.05;
    const SystemModel authored{{{1, 1, 1}, TimeDomain::discrete,
        LinearStage{{1, 1, {1.0}}, {1, 1, {step}}, {1, 1, {0.0}}, {0.0}}}, {}};
    const auto system = take(model::snapshot(authored,
        Vector{0.0, step, 2.0 * step, 3.0 * step, 4.0 * step}));
    const auto disturbance = no_disturbance();
    std::vector<sets::SetData> disturbances(horizon, disturbance);
    std::vector<sets::SetData> safe;
    safe.reserve(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"pilot-unconstrained-" + std::to_string(stage)}, 1, {"x"}})));
    const auto objective = std::get<Objective>(snapshot(
        QuadraticTerminal{{1, 1, {2.0}}, {0.0}, 0.0}));
    return {{"immrl-simple-control-short-horizon-v1"}, {"env717-simple-control"},
        system, singleton("pilot-initial", 0.1), {1, {{-1.0}, {0.0}, {1.0}}},
        std::move(disturbances), std::move(safe), objective};
}

Json main_record() {
    constexpr double step = 0.05;
    constexpr double initial = 0.1;
    constexpr std::size_t horizon = 4;
    constexpr std::array<double, 3> actions{-1.0, 0.0, 1.0};
    constexpr double near_optimal_tolerance = 1e-14;
    const auto input = request();
    std::vector<std::int64_t> measured_ns;
    measured_ns.reserve(7);
    FiniteActionMinimaxOutcome result;
    for(std::size_t repetition = 0; repetition <= 7; ++repetition) {
        const auto started = std::chrono::steady_clock::now();
        result = finite_action_minimax(input, {81, 1, near_optimal_tolerance});
        const auto stopped = std::chrono::steady_clock::now();
        if(!std::holds_alternative<FiniteMinimaxOptimal>(result))
            throw std::runtime_error("finite-action minimax did not return an optimum");
        if(repetition > 0)
            measured_ns.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(
                stopped - started).count());
    }
    const auto* optimal = std::get_if<FiniteMinimaxOptimal>(&result);
    if(!optimal) throw std::runtime_error("final finite-action minimax result disappeared");
    if(optimal->plans.size() != 81 || optimal->minimizing_plan_indices.empty())
        throw std::runtime_error("unexpected exhaustive plan catalogue");

    Json plans = Json::array();
    for(std::size_t i = 0; i < optimal->plans.size(); ++i) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&optimal->plans[i]);
        if(!plan) throw std::runtime_error("unconstrained pilot rejected a plan");
        Json controls = Json::array();
        Json trajectory = Json::array();
        double x = initial;
        trajectory.push_back(x);
        for(const auto index : plan->action_indices) {
            if(index >= actions.size()) throw std::runtime_error("invalid action index");
            controls.push_back(actions[index]);
            x += step * actions[index];
            trajectory.push_back(x);
        }
        if(plan->action_indices.size() != horizon)
            throw std::runtime_error("plan horizon mismatch");
        plans.push_back({{"plan_index", i}, {"controls", std::move(controls)},
            {"states", std::move(trajectory)}, {"terminal_squared_error", x * x}});
    }
    Json winners = Json::array();
    for(const auto index : optimal->minimizing_plan_indices) winners.push_back(index);
    auto ordered_ns = measured_ns;
    std::sort(ordered_ns.begin(), ordered_ns.end());
    if(optimal->value != 0.0) throw std::runtime_error("expected zero terminal residual");
    return {{"schema", "csl.env717-simple-control-pilot/1"},
        {"source", "https://github.com/imm-rl-lab/optimal_control/tree/master/Environments/SimpleControlProblem"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blobs", {{"SimpleControlProblem.py", "4eb0bb6fc04aa8e56891e1772287d013d2b32b3d"},
            {"SimpleControlProblem_Discrete.py", "40b9c13cf0d123ae3823a91b36a1b54162e04dad"}}},
        {"source_license", "no license declared in repository metadata"},
        {"source_behavior", {{"state", "[time, x]"}, {"dt_seconds", step},
            {"continuous_action_bounds", Json::array({-1.0, 1.0})},
            {"step_reward", "-0.5 * dt * u^2; terminal reward additionally subtracts x^2"},
            {"cost_method_running_reward", "-dt * u^2 (differs from step())"}}},
        {"adaptation", {{"initial_x", initial}, {"horizon_steps", horizon},
            {"terminal_time_seconds", step * horizon}, {"action_catalogue", actions},
            {"model_time_grid_seconds", Json::array({0.0, step, 2.0 * step, 3.0 * step, 4.0 * step})},
            {"objective", "minimize terminal x^2; source running reward omitted"},
            {"disturbance", "fixed at zero"}, {"safe_state", "unbounded scalar state"}}},
        {"algorithm", "csl.finite-action-minimax.numerical"},
        {"assurance", "numerical; exhaustive over all 3^4 fixed action sequences"},
        {"environment", {{"compiler_id", CSL_ENV717_COMPILER_ID},
            {"compiler_version", CSL_ENV717_COMPILER_VERSION},
            {"build_type", CSL_ENV717_BUILD_TYPE}, {"architecture", CSL_ENV717_ARCHITECTURE},
            {"requested_workers", 1}, {"solver_parallelism", "single-threaded"}}},
        {"near_optimal_tolerance", near_optimal_tolerance},
        {"timing", {{"scope", "finite_action_minimax call; request setup and JSON output excluded"},
            {"warmup_calls", 1}, {"measured_calls", measured_ns.size()},
            {"measured_wall_ns", measured_ns}, {"median_wall_ns", ordered_ns[3]},
            {"min_wall_ns", ordered_ns.front()}, {"max_wall_ns", ordered_ns.back()},
            {"limiter_profile", "not collected; no comparative performance claim"}}},
        {"plan_count", optimal->plans.size()}, {"objective_value", optimal->value},
        {"minimizing_plan_indices", std::move(winners)}, {"plans", std::move(plans)},
        {"driver_sha256", CSL_ENV717_DRIVER_SHA256},
        {"source_commit", CSL_ENV717_SOURCE_COMMIT}};
}
}

int main() {
    try {
        std::cout << main_record().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "environment pilot failed: " << error.what() << '\n';
        return 2;
    }
}
