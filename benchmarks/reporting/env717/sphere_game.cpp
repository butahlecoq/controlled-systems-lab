#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
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

sets::SetData vertices(std::string id, Matrix data) {
    const auto dimension = data.cols;
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(data))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 3;
    const SystemModel authored{{{3, 1, 1}, TimeDomain::discrete,
        LinearStage{{3, 3, {1.0, 0.0, 0.0,
                            0.0, 1.0, 0.0,
                            0.0, 0.0, 1.0}},
                    {3, 1, {0.0, 0.0, 0.1}},
                    {3, 1, {0.0, 0.1, 0.0}},
                    {0.1, 0.0, 0.0}}}, {}};
    const std::vector<double> times{0.0, 0.1, 0.2, 0.3};
    const auto system = take(model::snapshot(authored, times));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("sphere-game-v-catalogue", Matrix{3, 1, {-0.5, 0.0, 0.5}}));
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"sphere-game-unconstrained-" + std::to_string(stage)}, 3, {}})));
    const auto objective = std::get<Objective>(snapshot(
        ResidualNormTerminal{{2, 3, {0.0, 1.0, 0.0, 0.0, 0.0, 1.0}}, {0.0, 0.0}}));
    return {{"env717-sphere-game-short-horizon-v1"}, {"env717-sphere-game"},
        system, vertices("sphere-game-initial", Matrix{1, 3, {0.0, 0.0, 0.5}}),
        {1, {{-0.25}, {0.0}, {0.25}}}, std::move(disturbances), std::move(safe), objective};
}

Json result() {
    const auto input = request();
    const auto started = std::chrono::steady_clock::now();
    const auto outcome = finite_action_minimax(input, {27, 27, 1e-12});
    const auto stopped = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stopped-started).count();
    const auto* optimum = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!optimum || optimum->plans.size() != 27)
        throw std::runtime_error("finite-action minimax did not enumerate all 27 fixed plans");
    Json plans = Json::array();
    for(const auto& record : optimum->plans) {
        const auto* feasible = std::get_if<FinitePlanFeasible>(&record);
        if(!feasible) throw std::runtime_error("unconstrained fixed plan was rejected");
        Json controls = Json::array();
        for(const auto index : feasible->action_indices)
            controls.push_back(index == 0 ? -0.25 : (index == 1 ? 0.0 : 0.25));
        plans.push_back({{"controls", std::move(controls)},
            {"worst_terminal_norm", feasible->worst_value},
            {"maximizing_terminal_state", feasible->maximizer}});
    }
    Json minimizing = Json::array();
    for(const auto index : optimum->minimizing_plan_indices) minimizing.push_back(index);
    return {{"schema", "csl.env717-sphere-game-pilot/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "dd8ff3ce718570f05288dc4d8d343a8784ca2327"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"time", "y", "z"}},
        {"source_model", {{"initial_state", {0.0, 0.0, 0.5}}, {"dt_seconds", 0.1},
            {"horizon_seconds", 8.0}, {"control_u_bounds", {-0.25, 0.25}},
            {"disturbance_v_bounds", {-0.5, 0.5}},
            {"dynamics", "time'=1; y'=v; z'=u"},
            {"reward", "sqrt(y^2+z^2)-4 at termination"}}},
        {"adaptation", {{"horizon_steps", 3}, {"horizon_seconds", 0.3},
            {"control_catalogue", {-0.25, 0.0, 0.25}},
            {"disturbance_catalogue", {-0.5, 0.0, 0.5}},
            {"information_pattern", "fixed open-loop control plan versus full adversarial sequence"},
            {"objective", "minimize maximum terminal Euclidean norm; source reward is norm minus 4"},
            {"backward_geometry_information_pattern", "causal state-feedback control on the finite reachable graph; separate from the fixed-plan minimax solve"},
            {"backward_geometry_target", "terminal Euclidean norm no greater than the fixed-plan open-loop minimax norm"}}},
        {"algorithm", "csl.finite-action-minimax.numerical"},
        {"assurance", "numerical; exhaustive over all 27 fixed plans and 27 disturbance sequences per plan"},
        {"environment", {{"compiler_id", CSL_ENV717_SPHERE_COMPILER_ID},
            {"compiler_version", CSL_ENV717_SPHERE_COMPILER_VERSION},
            {"build_type", CSL_ENV717_SPHERE_BUILD_TYPE},
            {"architecture", CSL_ENV717_SPHERE_ARCHITECTURE}, {"requested_workers", 1},
            {"solver_parallelism", "single-threaded"}}},
        {"plan_count", optimum->plans.size()}, {"objective_value", optimum->value},
        {"source_reward_value", optimum->value - 4.0},
        {"minimizing_plan_indices", std::move(minimizing)}, {"plans", std::move(plans)},
        {"timing", {{"scope", "one finite_action_minimax call; request setup and JSON assembly excluded"},
            {"warmup_calls", 0}, {"measured_calls", 1}, {"elapsed_ns", elapsed},
            {"limiter_profile", "not collected; no comparative speed claim"}}},
        {"driver_sha256", CSL_ENV717_SPHERE_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_SPHERE_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_SPHERE_SOURCE_COMMIT}};
}
}

int main() {
    try { std::cout << result().dump(2) << '\n'; return 0; }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
