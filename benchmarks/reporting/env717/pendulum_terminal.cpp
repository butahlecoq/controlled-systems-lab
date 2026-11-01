#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <array>
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
    if (const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 4;
    constexpr double step = 0.05;
    const SystemModel authored{{{2, 1, 1}, TimeDomain::discrete,
        LinearStage{{2, 2, {1.0375, 0.05, 0.75, 1.0}},
            {2, 1, {0.015, 0.3}}, {2, 1, {0.0, 0.0}}, {0.0, 0.0}}}, {}};
    const auto system = take(model::snapshot(authored,
        Vector{0.0, step, 2.0 * step, 3.0 * step, 4.0 * step}));
    const auto initial = take(sets::make_singleton({{"pendulum-linearized-initial"}, 2,
        {"theta_rad", "theta_dot_rad_s"}}, take(numeric::snapshot_vector(Vector{0.25, 0.0}))));
    const auto zero_disturbance = take(sets::make_singleton({{"pendulum-zero-disturbance"}, 1,
        {"w"}}, take(numeric::snapshot_vector(Vector{0.0}))));
    std::vector<sets::SetData> disturbances(horizon, zero_disturbance);
    std::vector<sets::SetData> admissible_states;
    admissible_states.reserve(horizon + 1);
    for (std::size_t stage = 0; stage <= horizon; ++stage)
        admissible_states.push_back(take(sets::make_universal({
            {"pendulum-unbounded-state-" + std::to_string(stage)}, 2,
            {"theta_rad", "theta_dot_rad_s"}})));
    const auto objective = std::get<Objective>(snapshot(
        QuadraticTerminal{{2, 2, {2.0, 0.0, 0.0, 0.2}}, {0.0, 0.0}, 0.0}));
    return {{"env717-pendulum-terminal-linearized-v1"}, {"finite-open-loop-pilot"},
        system, initial, {1, {{-1.0}, {0.0}, {1.0}}}, std::move(disturbances),
        std::move(admissible_states), objective};
}

Json record() {
    constexpr std::size_t horizon = 4;
    constexpr std::array<double, 3> actions{-1.0, 0.0, 1.0};
    const auto result = finite_action_minimax(request(), {81, 1, 0.0});
    const auto* optimal = std::get_if<FiniteMinimaxOptimal>(&result);
    if (!optimal) throw std::runtime_error("finite-action solver did not return an optimum");
    if (optimal->plans.size() != 81 || optimal->minimizing_plan_indices.empty())
        throw std::runtime_error("unexpected finite action plan inventory");

    Json plans = Json::array();
    for (std::size_t plan_index = 0; plan_index < optimal->plans.size(); ++plan_index) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&optimal->plans[plan_index]);
        if (!plan || plan->action_indices.size() != horizon)
            throw std::runtime_error("unbounded-state pilot returned an infeasible plan");
        Json indices = Json::array();
        Json controls = Json::array();
        Json predicted = Json::array({Json::array({0.25, 0.0})});
        double theta = 0.25;
        double theta_dot = 0.0;
        for (const auto index : plan->action_indices) {
            if (index >= actions.size()) throw std::runtime_error("invalid action catalogue index");
            const auto action = actions[index];
            indices.push_back(index);
            controls.push_back(action);
            const double next_theta_dot = 0.75 * theta + theta_dot + 0.3 * action;
            theta = 1.0375 * theta + 0.05 * theta_dot + 0.015 * action;
            theta_dot = next_theta_dot;
            predicted.push_back(Json::array({theta, theta_dot}));
        }
        plans.push_back({{"plan_index", plan_index}, {"action_indices", std::move(indices)},
            {"actions", std::move(controls)}, {"predicted_states", std::move(predicted)},
            {"linearized_terminal_objective", plan->worst_value}});
    }
    Json winners = Json::array();
    for (const auto index : optimal->minimizing_plan_indices) winners.push_back(index);
    return {{"schema", "csl.env717-pendulum-terminal-pilot/1"},
        {"environment", "PendulumTerminal"},
        {"source_url", "https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/PendulumTerminal/PendulumTerminal.py"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "4c3ef514524fa98fab53b2de18dfa9127316263f"},
        {"source_license", "no license declared in repository metadata"},
        {"source_model", {{"state", "[time, theta_rad, theta_dot_rad_s]"},
            {"sample_time_seconds", 0.05}, {"default_terminal_time_seconds", 5.0},
            {"gravity_m_s2", 10.0}, {"mass_kg", 1.0}, {"length_m", 1.0},
            {"action_bounds", Json::array({-1.0, 1.0})},
            {"torque_mapping", "u=2*clip(action,-1,1)"},
            {"step", "theta_dot+=(-15*sin(theta+pi)+3*u)*dt; theta+=theta_dot*dt"},
            {"step_cost", "angle_normalize(theta)^2 + 0.1*theta_dot^2 + 0.001*u^2"}}},
        {"pilot_adaptation", {{"initial_state", Json::array({0.0, 0.25, 0.0})},
            {"horizon_steps", horizon}, {"horizon_seconds", 0.2},
            {"action_catalogue", actions},
            {"linearization_point", Json::array({0.0, 0.0})},
            {"linearized_A", Json::array({Json::array({1.0375, 0.05}), Json::array({0.75, 1.0})})},
            {"linearized_B", Json::array({0.015, 0.3})},
            {"objective", "minimize theta_T^2 + 0.1*theta_dot_T^2 on the local affine model"},
            {"disturbance", "singleton zero; this is nominal open-loop planning"},
            {"state_constraints", "unbounded"},
            {"objective_deviation", "the source running cost is replayed for evaluation; the planner minimizes a terminal surrogate"}}},
        {"algorithm", "csl.finite-action-minimax.numerical"},
        {"assurance", "exhaustive over 3^4 fixed plans for the local affine surrogate"},
        {"plan_count", optimal->plans.size()}, {"linearized_objective_value", optimal->value},
        {"linearized_minimizing_plan_indices", std::move(winners)}, {"plans", std::move(plans)},
        {"driver_sha256", CSL_ENV717_PENDULUM_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_PENDULUM_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_PENDULUM_SOURCE_COMMIT},
        {"compiler", {{"id", CSL_ENV717_PENDULUM_COMPILER_ID},
            {"version", CSL_ENV717_PENDULUM_COMPILER_VERSION},
            {"build_type", CSL_ENV717_PENDULUM_BUILD_TYPE},
            {"architecture", CSL_ENV717_PENDULUM_ARCHITECTURE}}}};
}
}

int main() {
    try {
        std::cout << record().dump(2) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "ENV-717 PendulumTerminal pilot failed: " << error.what() << '\n';
        return 2;
    }
}
