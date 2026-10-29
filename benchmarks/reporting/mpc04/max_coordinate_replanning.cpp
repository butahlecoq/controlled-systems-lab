#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
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
using Clock = std::chrono::steady_clock;

constexpr std::size_t episode_steps = 4;
constexpr std::size_t fixed_lookahead = 2;
constexpr double dt = 0.1;
constexpr std::array<double, 2> actions{-1.0, 1.0};
constexpr std::array<double, 2> disturbances{-1.0, 1.0};
using State = std::array<double, 3>;

struct SelectedPlan {
    std::vector<double> controls;
    double squared_objective{};
    std::uint64_t elapsed_ns{};
};

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

sets::SetData vertices(std::string id, Matrix rows) {
    const auto dimension = rows.cols;
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(rows))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

sets::SetData point(std::string id, const State& state) {
    return vertices(std::move(id), Matrix{1, state.size(),
        {state[0], state[1], state[2]}});
}

FiniteActionMinimaxRequest request(const State& initial, std::size_t horizon,
                                   bool robust, const std::array<double, 3>& direction,
                                   std::size_t component) {
    const SystemModel authored{{{3, 1, 1}, TimeDomain::discrete,
        LinearStage{{3, 3, {1.0, 0.0, 0.0,
                            0.0, 0.99505392003313353, 0.099838375271514387,
                            0.0, -0.099838375271514387, 0.99505392003313353}},
                    {3, 1, {0.0, 0.0049460799668663343, 0.099838375271514443}},
                    {3, 1, {0.0, 0.099838375271514443, -0.0049460799668663343}},
                    {0.1, 0.0, 0.0}}}, {}};
    std::vector<double> times;
    times.reserve(horizon + 1);
    for(std::size_t i = 0; i <= horizon; ++i)
        times.push_back(initial[0] + dt * static_cast<double>(i));
    auto system = take(model::snapshot(authored, std::move(times)));

    std::vector<Vector> action_points;
    for(const double action : actions) action_points.push_back({action});
    std::vector<sets::SetData> disturbance_sets;
    disturbance_sets.reserve(horizon);
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(robust) {
            disturbance_sets.push_back(vertices("mpc04-disturbance-" +
                std::to_string(component) + "-" + std::to_string(stage),
                Matrix{2, 1, {disturbances[0], disturbances[1]}}));
        } else {
            disturbance_sets.push_back(vertices("mpc04-nominal-disturbance-" +
                std::to_string(component) + "-" + std::to_string(stage),
                Matrix{1, 1, {0.0}}));
        }
    }
    std::vector<sets::SetData> safe;
    safe.reserve(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"mpc04-unconstrained-" + std::to_string(stage)}, 3, {}})));
    const auto terminal = std::get<Objective>(snapshot(LinearTerminal{
        {direction[0], direction[1], direction[2]}, 0.0}));
    return {{"mpc04-max-coordinate-replanning"}, {"mpc04-finite-mpc"},
        std::move(system), point("mpc04-initial", initial),
        {1, std::move(action_points)}, std::move(disturbance_sets),
        std::move(safe), terminal};
}

SelectedPlan choose_plan(const State& state, std::size_t horizon, bool robust) {
    constexpr double tie_tolerance = 1e-12;
    constexpr std::array<std::array<double, 3>, 4> directions{{
        {0.0, 1.0, 0.0}, {0.0, -1.0, 0.0},
        {0.0, 0.0, 1.0}, {0.0, 0.0, -1.0}}};
    const auto start = Clock::now();
    std::vector<std::vector<double>> plan_controls;
    std::vector<double> combined;
    std::size_t plan_count = 0;
    for(std::size_t component = 0; component < directions.size(); ++component) {
        auto input = request(state, horizon, robust, directions[component], component);
        const auto limits = FiniteActionMinimaxLimits{
            std::size_t{1} << horizon, 256, tie_tolerance};
        auto outcome = finite_action_minimax(input, limits);
        const auto* optimum = std::get_if<FiniteMinimaxOptimal>(&outcome);
        if(!optimum) throw std::runtime_error("finite_action_minimax did not return a plan optimum");
        if(component == 0) {
            plan_count = optimum->plans.size();
            plan_controls.reserve(plan_count);
            combined.assign(plan_count, -std::numeric_limits<double>::infinity());
            for(const auto& record : optimum->plans) {
                const auto* feasible = std::get_if<FinitePlanFeasible>(&record);
                if(!feasible) throw std::runtime_error("unconstrained plan was rejected");
                std::vector<double> controls;
                for(const auto index : feasible->action_indices) {
                    if(index >= actions.size()) throw std::runtime_error("action index is outside catalogue");
                    controls.push_back(actions[index]);
                }
                plan_controls.push_back(std::move(controls));
            }
        } else if(optimum->plans.size() != plan_count) {
            throw std::runtime_error("signed-coordinate solves returned different plan counts");
        }
        for(std::size_t i = 0; i < optimum->plans.size(); ++i) {
            const auto* feasible = std::get_if<FinitePlanFeasible>(&optimum->plans[i]);
            if(!feasible) throw std::runtime_error("unconstrained plan was rejected");
            combined[i] = std::max(combined[i], feasible->worst_value);
        }
    }
    if(plan_controls.empty()) throw std::runtime_error("empty finite action catalogue");
    std::size_t best = 0;
    for(std::size_t i = 1; i < combined.size(); ++i) {
        if(combined[i] < combined[best] - tie_tolerance) best = i;
    }
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - start).count();
    const double nonnegative = std::max(0.0, combined[best]);
    return {std::move(plan_controls[best]), nonnegative * nonnegative,
            static_cast<std::uint64_t>(elapsed)};
}

State advance(State state, double action, double disturbance) {
    // The pinned source holds both player actions over 100 explicit Euler steps.
    constexpr double h = dt / 100.0;
    for(int i = 0; i < 100; ++i) {
        const double y = state[1];
        const double z = state[2];
        state[1] = y + h * (z + disturbance);
        state[2] = z + h * (-y + action);
    }
    state[0] += dt;
    return state;
}

double source_objective(const State& state) {
    return std::max(std::abs(state[1]), std::abs(state[2]));
}

Json episode(std::string policy, std::string horizon_name,
             const std::array<double, episode_steps>& history) {
    State state{0.0, 0.2, 0.0};
    Json states = Json::array({state});
    Json decisions = Json::array();
    std::size_t fallbacks = 0;
    for(std::size_t step = 0; step < episode_steps; ++step) {
        const auto horizon = horizon_name == "shrinking_to_episode_terminal"
            ? episode_steps - step : fixed_lookahead;
        SelectedPlan plan;
        std::string status = "solved";
        std::string solver_detail;
        try {
            plan = choose_plan(state, horizon, policy == "finite_minimax");
        } catch(const std::exception& error) {
            plan.controls = {0.0};
            plan.squared_objective = std::numeric_limits<double>::quiet_NaN();
            status = "solver_failure_fallback";
            solver_detail = error.what();
            ++fallbacks;
        }
        double action = plan.controls.empty() ? 0.0 : plan.controls.front();
        if(plan.elapsed_ns > 50'000'000) {
            action = 0.0;
            status = "deadline_fallback";
            solver_detail = "native solve returned after the per-decision deadline; cancellation is unavailable";
            ++fallbacks;
        }
        Json remaining = plan.controls;
        if(status != "solved") remaining = Json::array();
        decisions.push_back({{"step", step}, {"observed_state", state},
            {"action", action}, {"status", status}, {"requested_horizon", horizon},
            {"effective_horizon", horizon},
            {"planned_squared_objective", std::isfinite(plan.squared_objective)
                ? Json(plan.squared_objective) : Json(nullptr)},
            {"solve_ns", plan.elapsed_ns}, {"remaining_plan", std::move(remaining)},
            {"solver_detail", solver_detail}, {"fallback", status != "solved"}});
        state = advance(state, action, history[step]);
        states.push_back(state);
    }
    return {{"policy", std::move(policy)}, {"horizon", std::move(horizon_name)},
        {"disturbances", history}, {"states", std::move(states)},
        {"decisions", std::move(decisions)}, {"terminal_state", state},
        {"terminal_original_objective", source_objective(state)},
        {"fallback_count", fallbacks}, {"violations", 0}, {"completed", true}};
}

Json run() {
    Json episodes = Json::array();
    for(const std::string policy : {"nominal_zero_disturbance", "finite_minimax"}) {
        for(const std::string horizon : {"shrinking_to_episode_terminal",
                                         "moving_fixed_2_stage_lookahead"}) {
            for(const double v0 : disturbances) for(const double v1 : disturbances)
                for(const double v2 : disturbances) for(const double v3 : disturbances)
                    episodes.push_back(episode(policy, horizon, {v0, v1, v2, v3}));
        }
    }
    return {{"episodes", std::move(episodes)}};
}
}

int main() {
    try { std::cout << run().dump() << '\n'; return 0; }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
