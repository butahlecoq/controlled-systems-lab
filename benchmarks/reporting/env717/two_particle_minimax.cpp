#include <csl/optimization/finite_causal_minimax.hpp>
#include <csl/reachability/finite_feedback.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <compare>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Json = nlohmann::json;
namespace causal = csl::optimization::finite_causal_minimax;
namespace feedback = csl::reachability::finite_feedback;

constexpr std::int64_t scale = 1'000'000;
constexpr int horizon = 4;
constexpr int inner_steps = 20;
constexpr double outer_dt = 0.2;
constexpr std::array<int, 3> action_codes{-1, 0, 1};
constexpr double target_radius = 1.0;

struct State {
    std::int64_t x1{};
    std::int64_t v1{};
    std::int64_t x2{};
    std::int64_t v2{};
    auto operator<=>(const State&) const = default;
};
using DoubleState = std::array<double, 4>;
using Destinations = std::array<std::array<std::size_t, action_codes.size()>, action_codes.size()>;
struct TransitionRow { Destinations destination{}; };
struct Graph {
    std::vector<std::vector<State>> layers;
    std::vector<std::vector<TransitionRow>> next;
    std::vector<std::map<State, std::size_t>> index;
};

DoubleState derivative(const DoubleState& state, int control_code, int disturbance_code) {
    const double control = static_cast<double>(control_code) * 3.0;
    const double disturbance = static_cast<double>(disturbance_code) * 3.0;
    return {state[1], -10.0 * state[1] + 10.0 * control, state[3], disturbance};
}

State advance_source(const State& input, int control_code, int disturbance_code) {
    DoubleState state{static_cast<double>(input.x1) / scale,
        static_cast<double>(input.v1) / scale,
        static_cast<double>(input.x2) / scale,
        static_cast<double>(input.v2) / scale};
    const double h = outer_dt / static_cast<double>(inner_steps);
    for(int step = 0; step < inner_steps; ++step) {
        const auto k1 = derivative(state, control_code, disturbance_code);
        auto stage = state;
        for(std::size_t i = 0; i < stage.size(); ++i) stage[i] += h * k1[i] / 2.0;
        const auto k2 = derivative(stage, control_code, disturbance_code);
        stage = state;
        for(std::size_t i = 0; i < stage.size(); ++i) stage[i] += h * k2[i] / 2.0;
        const auto k3 = derivative(stage, control_code, disturbance_code);
        stage = state;
        for(std::size_t i = 0; i < stage.size(); ++i) stage[i] += h * k3[i];
        const auto k4 = derivative(stage, control_code, disturbance_code);
        for(std::size_t i = 0; i < state.size(); ++i)
            state[i] += h * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) / 6.0;
    }
    return {std::llround(state[0] * scale), std::llround(state[1] * scale),
        std::llround(state[2] * scale), std::llround(state[3] * scale)};
}

Graph build_graph() {
    Graph graph;
    graph.layers.resize(static_cast<std::size_t>(horizon + 1));
    graph.next.resize(static_cast<std::size_t>(horizon));
    graph.index.resize(static_cast<std::size_t>(horizon + 1));
    graph.layers[0].push_back({2 * scale, 0, 0, 0});
    graph.index[0].emplace(graph.layers[0][0], 0);
    for(int stage = 0; stage < horizon; ++stage) {
        std::set<State> candidates;
        for(const auto& state : graph.layers[static_cast<std::size_t>(stage)])
            for(const int control : action_codes)
                for(const int disturbance : action_codes)
                    candidates.insert(advance_source(state, control, disturbance));
        auto& next_layer = graph.layers[static_cast<std::size_t>(stage + 1)];
        next_layer.assign(candidates.begin(), candidates.end());
        auto& next_index = graph.index[static_cast<std::size_t>(stage + 1)];
        for(std::size_t i = 0; i < next_layer.size(); ++i) next_index.emplace(next_layer[i], i);
        auto& rows = graph.next[static_cast<std::size_t>(stage)];
        rows.resize(graph.layers[static_cast<std::size_t>(stage)].size());
        for(std::size_t state_id = 0; state_id < rows.size(); ++state_id) {
            for(std::size_t control_id = 0; control_id < action_codes.size(); ++control_id) {
                for(std::size_t disturbance_id = 0; disturbance_id < action_codes.size(); ++disturbance_id) {
                    const auto state = advance_source(graph.layers[static_cast<std::size_t>(stage)][state_id],
                        action_codes[control_id], action_codes[disturbance_id]);
                    rows[state_id].destination[control_id][disturbance_id] = next_index.at(state);
                }
            }
        }
    }
    return graph;
}

bool in_target(const State& state) {
    return std::abs(state.x1 - state.x2) <= static_cast<std::int64_t>(target_radius * scale);
}

feedback::Game feedback_game(const Graph& graph, int selected_horizon) {
    std::size_t state_count = 0;
    for(int stage = 0; stage <= selected_horizon; ++stage)
        state_count = std::max(state_count, graph.layers[static_cast<std::size_t>(stage)].size());
    std::vector<bool> terminal_safe(state_count, false), terminal_target(state_count, false);
    const auto& terminal = graph.layers[static_cast<std::size_t>(selected_horizon)];
    for(std::size_t i = 0; i < terminal.size(); ++i) {
        terminal_safe[i] = true;
        terminal_target[i] = in_target(terminal[i]);
    }
    feedback::Game game{state_count, {}, std::move(terminal_safe), std::move(terminal_target)};
    for(int stage_id = 0; stage_id < selected_horizon; ++stage_id) {
        const auto& states = graph.layers[static_cast<std::size_t>(stage_id)];
        const auto& transitions = graph.next[static_cast<std::size_t>(stage_id)];
        feedback::Stage stage{std::vector<bool>(state_count, false), action_codes.size(),
            action_codes.size(), {}};
        stage.next_state.resize(state_count);
        for(std::size_t state_id = 0; state_id < state_count; ++state_id) {
            stage.next_state[state_id].resize(action_codes.size());
            for(std::size_t control_id = 0; control_id < action_codes.size(); ++control_id) {
                stage.next_state[state_id][control_id].resize(action_codes.size());
                for(std::size_t disturbance_id = 0; disturbance_id < action_codes.size(); ++disturbance_id) {
                    const auto next_id = state_id < states.size()
                        ? transitions[state_id].destination[control_id][disturbance_id] : 0;
                    stage.next_state[state_id][control_id][disturbance_id] = feedback::StateIndex{next_id};
                }
            }
        }
        std::fill_n(stage.safe_states.begin(), states.size(), true);
        game.stages.push_back(std::move(stage));
    }
    return game;
}

causal::Game causal_game(const Graph& graph) {
    causal::Game game;
    game.initial_state = causal::StateId{0};
    const auto& terminal = graph.layers.back();
    game.terminal.state_count = terminal.size();
    game.terminal.safe_states.assign(terminal.size(), true);
    game.terminal.cost.reserve(terminal.size());
    for(const auto& state : terminal)
        game.terminal.cost.push_back(static_cast<double>(std::abs(state.x1 - state.x2)) / scale);
    for(int stage_id = 0; stage_id < horizon; ++stage_id) {
        const auto& states = graph.layers[static_cast<std::size_t>(stage_id)];
        causal::Stage stage{states.size(), action_codes.size(), action_codes.size(), {}, {}};
        stage.safe_states.assign(states.size(), true);
        stage.next_state.resize(states.size());
        for(std::size_t state_id = 0; state_id < states.size(); ++state_id) {
            stage.next_state[state_id].resize(action_codes.size());
            for(std::size_t control_id = 0; control_id < action_codes.size(); ++control_id)
                for(std::size_t disturbance_id = 0; disturbance_id < action_codes.size(); ++disturbance_id)
                    stage.next_state[state_id][control_id].push_back(causal::StateId{
                        graph.next[static_cast<std::size_t>(stage_id)][state_id]
                            .destination[control_id][disturbance_id]});
        }
        game.stages.push_back(std::move(stage));
    }
    return game;
}

void selected_trajectory(const Graph& graph, const causal::Result& result, Json& path) {
    path = Json::array();
    std::size_t state_id = result.initial_state.value;
    for(int stage = 0; stage <= horizon; ++stage) {
        const auto& state = graph.layers[static_cast<std::size_t>(stage)].at(state_id);
        const auto& value = result.values_by_stage[static_cast<std::size_t>(stage)].at(state_id);
        Json row{{"stage", stage}, {"time_seconds", stage * outer_dt},
            {"state_ticks", {state.x1, state.v1, state.x2, state.v2}},
            {"state", {static_cast<double>(state.x1) / scale, static_cast<double>(state.v1) / scale,
                static_cast<double>(state.x2) / scale, static_cast<double>(state.v2) / scale}},
            {"minimax_value", value.value}};
        if(stage < horizon) {
            const auto control_id = value.optimal_actions.front().value;
            std::size_t disturbance_id = 0;
            double worst = -1.0;
            for(std::size_t candidate = 0; candidate < action_codes.size(); ++candidate) {
                const auto next = graph.next[static_cast<std::size_t>(stage)][state_id]
                    .destination[control_id][candidate];
                const auto next_value = result.values_by_stage[static_cast<std::size_t>(stage + 1)][next].value;
                if(next_value > worst) { worst = next_value; disturbance_id = candidate; }
            }
            row["control"] = action_codes[control_id] * 3;
            row["disturbance"] = action_codes[disturbance_id] * 3;
            state_id = graph.next[static_cast<std::size_t>(stage)][state_id]
                .destination[control_id][disturbance_id];
        }
        path.push_back(std::move(row));
    }
}

Json layers_json(const Graph& graph, const feedback::Policy& policy) {
    Json layers = Json::array();
    for(int stage = 0; stage <= horizon; ++stage) {
        Json states = Json::array(), winning = Json::array();
        const auto& layer = graph.layers[static_cast<std::size_t>(stage)];
        for(std::size_t index = 0; index < layer.size(); ++index) {
            const auto& state = layer[index];
            Json item{{"ticks", {state.x1, state.v1, state.x2, state.v2}},
                {"state", {static_cast<double>(state.x1) / scale, static_cast<double>(state.v1) / scale,
                    static_cast<double>(state.x2) / scale, static_cast<double>(state.v2) / scale}}};
            states.push_back(item);
            if(policy.winning[static_cast<std::size_t>(stage)][index]) winning.push_back(std::move(item));
        }
        layers.push_back({{"stage", stage}, {"time_seconds", stage * outer_dt},
            {"forward_states", std::move(states)}, {"backward_winning_intersection", std::move(winning)}});
    }
    return layers;
}

Json run() {
    const auto graph = build_graph();
    std::vector<bool> initial_wins;
    int first_capture = -1;
    for(int steps = 1; steps <= horizon; ++steps) {
        const auto game = feedback_game(graph, steps);
        const auto outcome = feedback::solve(game);
        const auto* policy = std::get_if<feedback::Policy>(&outcome);
        if(!policy) throw std::runtime_error("finite feedback solver rejected the finite reachable graph");
        const bool wins = policy->winning.front().at(0);
        initial_wins.push_back(wins);
        if(wins && first_capture < 0) first_capture = steps;
    }
    if(first_capture != horizon) throw std::runtime_error("expected the first robust capture at the four-step pilot horizon");
    const auto reachability_outcome = feedback::solve(feedback_game(graph, horizon));
    const auto* reachability = std::get_if<feedback::Policy>(&reachability_outcome);
    if(!reachability) throw std::runtime_error("finite feedback solve failed at the selected horizon");
    const auto minimax_outcome = causal::solve(causal_game(graph), {1e-12, 1e-12});
    const auto* minimax = std::get_if<causal::Result>(&minimax_outcome);
    if(!minimax) throw std::runtime_error("finite causal minimax solve failed on the source-derived game");
    const auto value = minimax->initial().value;
    if(std::abs(value - 0.859899) > 1e-6)
        throw std::runtime_error("finite minimax value differs from the source-step reference");
    Json path;
    selected_trajectory(graph, *minimax, path);
    if(std::abs(path.back()["minimax_value"].get<double>() - value) > 1e-12)
        throw std::runtime_error("selected minimax trajectory does not attain the initial value");
    Json action_values = Json::array(), state_counts = Json::array();
    for(const auto code : action_codes) action_values.push_back(code * 3);
    for(const auto& layer : graph.layers) state_counts.push_back(layer.size());
    Json capture_by_horizon = Json::array();
    for(int steps = 1; steps <= horizon; ++steps)
        capture_by_horizon.push_back({{"steps", steps}, {"seconds", steps * outer_dt},
            {"initial_state_winning", initial_wins[static_cast<std::size_t>(steps - 1)]}});
    return Json{{"schema", "csl.env717-two-particle-minimax/1"},
        {"source", {{"repository", "https://github.com/imm-rl-lab/differential_game_gym"},
            {"repository_commit", "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8"},
            {"file", "Environments/TwoParticleGame/TwoParticleGame.py"},
            {"file_blob", "7e7d326f8ff81f7dacc05ac72848eeaac6a03021"},
            {"license", "Apache-2.0; repository LICENSE blob 261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"}}},
        {"source_model", {{"state_order", {"time", "x1", "v1", "x2", "v2"}},
            {"initial_state", {0.0, 2.0, 0.0, 0.0, 0.0}},
            {"upstream_default_initial_state", {0.0, 0.0, 0.0, 0.0, 0.0}},
            {"alpha", 1.0}, {"m1", 0.1}, {"m2", 1.0}, {"dt_seconds", outer_dt},
            {"terminal_time_seconds", 2.0}, {"inner_rk4_steps", inner_steps},
            {"dynamics", "x1'=v1; v1'=-10*v1+10*u; x2'=v2; v2'=v"},
            {"control_bounds", {-3.0, 3.0}}, {"disturbance_bounds", {-3.0, 3.0}},
            {"terminal_reward", "-abs(x1-x2)"}}},
        {"adaptation", {{"initial_state_override", "x1 is set to 2.0; the upstream default is all zeros"},
            {"horizon_steps", horizon}, {"horizon_seconds", horizon * outer_dt},
            {"action_catalogue", action_values}, {"disturbance_catalogue", action_values},
            {"quantization_scale", scale}, {"quantization", "round each outer RK4 state to the nearest 1e-6 lattice point"},
            {"objective_orientation", "u minimizes the terminal absolute position gap (maximizes the source reward); v maximizes the gap"},
            {"information_pattern", "finite causal game: u chooses from the observed current state; then v observes u and responds before the next state is observed"},
            {"information_pattern_change", "the upstream Markov game supplies both actions at one step; sequential response gives v a stronger within-stage information pattern"},
            {"scope", "source-derived finite catalogue and quantized state graph; not a continuous-action RL reproduction"}}},
        {"solvers", {{"reachability", "csl.reachability.finite_feedback.solve"},
            {"minimax", "csl.optimization.finite_causal_minimax.solve"}}},
        {"target", {{"set", "abs(x1-x2) <= 1.0 at the selected terminal stage"}, {"radius", target_radius}}},
        {"numerical_assurance", "numerical; finite double-precision RK4 transitions rounded to the declared 1e-6 state lattice"},
        {"graph_state_counts", state_counts}, {"first_robust_capture_steps", first_capture},
        {"capture_horizon_sweep", capture_by_horizon}, {"finite_causal_minimax_terminal_gap", value},
        {"minimax_trajectory", path}, {"figure_layers", layers_json(graph, *reachability)},
        {"driver_sha256", CSL_ENV717_TWO_PARTICLE_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_TWO_PARTICLE_ALGORITHM_SHA256},
        {"scenario_sha256", CSL_ENV717_TWO_PARTICLE_SCENARIO_SHA256},
        {"source_commit", CSL_ENV717_TWO_PARTICLE_SOURCE_COMMIT},
        {"build", {{"compiler", CSL_ENV717_TWO_PARTICLE_COMPILER_ID},
            {"compiler_version", CSL_ENV717_TWO_PARTICLE_COMPILER_VERSION},
            {"build_type", CSL_ENV717_TWO_PARTICLE_BUILD_TYPE},
            {"architecture", CSL_ENV717_TWO_PARTICLE_ARCHITECTURE}}}};
}
}

int main() {
    try {
        std::cout << run().dump(2) << '\n';
    } catch(const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
