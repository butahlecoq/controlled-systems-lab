#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <limits>
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

sets::SetData points(std::string id, Matrix values) {
    const auto dimension = values.cols;
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(values))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

FiniteActionMinimaxRequest request(std::array<double, 3> terminal_direction) {
    constexpr std::size_t horizon = 3;
    const SystemModel authored{{{3, 1, 1}, TimeDomain::discrete,
        LinearStage{{3, 3, {1.0, 0.0, 0.0,
                            0.0, 0.99505392003313353, 0.099838375271514387,
                            0.0, -0.099838375271514387, 0.99505392003313353}},
                    {3, 1, {0.0, 0.0049460799668663343, 0.099838375271514443}},
                    {3, 1, {0.0, 0.099838375271514443, -0.0049460799668663343}},
                    {0.1, 0.0, 0.0}}}, {}};
    std::vector<double> times{0.0, 0.1, 0.2, 0.3};
    const auto system = take(model::snapshot(authored, times));
    std::vector<sets::SetData> disturbances(horizon,
        points("max-coordinate-v", Matrix{2, 1, {-1.0, 1.0}}));
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"max-coordinate-unconstrained-" + std::to_string(stage)}, 3, {}})));
    const auto objective = std::get<Objective>(snapshot(
        LinearTerminal{{terminal_direction[0], terminal_direction[1], terminal_direction[2]}, 0.0}));
    return {{"env717-max-coordinate-short-horizon-v1"}, {"env717-max-coordinate"},
        system, points("max-coordinate-initial", Matrix{1, 3, {0.0, 0.2, 0.0}}),
        {1, {{-1.0}, {1.0}}}, std::move(disturbances), std::move(safe), objective};
}

Json run_component(std::array<double, 3> direction) {
    constexpr double tol = 1e-12;
    const auto input = request(direction);
    const auto outcome = finite_action_minimax(input, {8, 8, tol});
    const auto* optimum = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!optimum || optimum->plans.size() != 8)
        throw std::runtime_error("finite-action minimax did not enumerate the 8 control plans");
    Json plans = Json::array();
    for(const auto& record : optimum->plans) {
        const auto* feasible = std::get_if<FinitePlanFeasible>(&record);
        if(!feasible) throw std::runtime_error("unconstrained plan was rejected");
        Json controls = Json::array();
        for(const auto index : feasible->action_indices)
            controls.push_back(index == 0 ? -1.0 : 1.0);
        plans.push_back({{"controls", std::move(controls)},
            {"worst_signed_coordinate", feasible->worst_value},
            {"maximizer", feasible->maximizer}});
    }
    return {{"direction", direction}, {"value", optimum->value},
        {"plans", std::move(plans)}};
}

Json result() {
    const auto started = std::chrono::steady_clock::now();
    Json components = Json::array({run_component({0.0, 1.0, 0.0}),
        run_component({0.0, -1.0, 0.0}), run_component({0.0, 0.0, 1.0}),
        run_component({0.0, 0.0, -1.0})});
    std::vector<double> robust_values(8, -std::numeric_limits<double>::infinity());
    for(std::size_t plan = 0; plan < robust_values.size(); ++plan)
        for(const auto& component : components)
            robust_values[plan] = std::max(robust_values[plan],
                component.at("plans").at(plan).at("worst_signed_coordinate").get<double>());
    const auto optimum = *std::min_element(robust_values.begin(), robust_values.end());
    Json minimizing = Json::array();
    for(std::size_t i = 0; i < robust_values.size(); ++i)
        if(robust_values[i] <= optimum + 1e-12) minimizing.push_back(i);
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - started).count();
    return {{"schema", "csl.env717-max-coordinate-pilot/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "d509a1457023b14516d2789bd3033dbaa4110017"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"time", "y", "z"}},
        {"source_model", {{"initial_state", {0.0, 0.2, 0.0}}, {"dt_seconds", 0.1},
            {"horizon_seconds", 4.0}, {"inner_euler_steps", 100},
            {"control_u_bounds", {-1.0, 1.0}}, {"disturbance_v_bounds", {-1.0, 1.0}},
            {"dynamics", "time'=1; y'=z+v; z'=-y+u"},
            {"reward", "max(|y|,|z|) at termination"}}},
        {"adaptation", {{"horizon_steps", 3}, {"horizon_seconds", 0.3},
            {"control_catalogue", {-1.0, 1.0}}, {"disturbance_catalogue", {-1.0, 1.0}},
            {"information_pattern", "fixed open-loop control plan versus full adversarial sequence"},
            {"backward_geometry_information_pattern", "causal state-feedback control on the finite reachable graph; separate from the fixed-plan minimax solve"},
            {"backward_geometry_target", "terminal max(|y|,|z|) no greater than the fixed-plan open-loop minimax value"},
            {"objective", "minimum over fixed plans of maximum over disturbances of max(|y|,|z|)"},
            {"objective_mapping", "four signed linear terminal objectives; combine per-plan worst values"},
            {"source_step", "same simultaneous explicit-Euler update repeated for 100 substeps; the 0.1 s discrete matrix is the exact repeated-step map"}}},
        {"algorithm", "csl.finite-action-minimax.numerical; four signed components combined per fixed plan"},
        {"component_results", std::move(components)},
        {"plan_count", robust_values.size()}, {"objective_value", optimum},
        {"minimizing_plan_indices", std::move(minimizing)},
        {"environment", {{"compiler_id", CSL_ENV717_MAX_COMPILER_ID},
            {"compiler_version", CSL_ENV717_MAX_COMPILER_VERSION},
            {"build_type", CSL_ENV717_MAX_BUILD_TYPE},
            {"architecture", CSL_ENV717_MAX_ARCHITECTURE}, {"requested_workers", 1},
            {"solver_parallelism", "single-threaded"}}},
        {"timing", {{"scope", "single interval from first request construction through four minimax calls, plan extraction, and objective combination; JSON assembly and serialization excluded"},
            {"warmup_calls", 0}, {"measured_calls", 1}, {"elapsed_ns", elapsed},
            {"limiter_profile", "not collected; no comparative speed claim"}}},
        {"driver_sha256", CSL_ENV717_MAX_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_MAX_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_MAX_SOURCE_COMMIT}};
}
}

int main() {
    try { std::cout << result().dump(2) << '\n'; return 0; }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
