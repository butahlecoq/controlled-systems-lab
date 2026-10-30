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
#include <numbers>
#include <set>
#include <stdexcept>
#include <vector>

namespace {
using Json = nlohmann::json;
namespace causal = csl::optimization::finite_causal_minimax;
namespace feedback = csl::reachability::finite_feedback;

constexpr std::int64_t scale = 1'000'000;
constexpr int horizon = 4;
constexpr int inner_steps = 10;
constexpr double outer_dt = 0.1;
constexpr double target_radius = 7.8;
constexpr std::array<double, 3> turn_rates{-1.0, 0.0, 1.0};
constexpr std::array<double, 4> evader_headings{
    0.0, std::numbers::pi / 2.0, std::numbers::pi, 3.0 * std::numbers::pi / 2.0};

struct State {
    std::int64_t pursuer_x{};
    std::int64_t pursuer_y{};
    std::int64_t heading{};
    std::int64_t evader_x{};
    std::int64_t evader_y{};
    auto operator<=>(const State&) const = default;
};
using DoubleState = std::array<double, 5>;
using Destinations = std::array<std::array<std::size_t, 4>, 3>;
struct TransitionRow { Destinations destination{}; };
struct Graph {
    std::vector<std::vector<State>> layers;
    std::vector<std::vector<TransitionRow>> next;
    std::vector<std::map<State, std::size_t>> index;
};

DoubleState derivative(const DoubleState& state, double turn_rate, double evader_heading) {
    return {3.0 * std::cos(state[2]), 3.0 * std::sin(state[2]), turn_rate,
        std::cos(evader_heading), std::sin(evader_heading)};
}

State advance_source(const State& input, double turn_rate, double evader_heading) {
    DoubleState state{static_cast<double>(input.pursuer_x) / scale,
        static_cast<double>(input.pursuer_y) / scale,
        static_cast<double>(input.heading) / scale,
        static_cast<double>(input.evader_x) / scale,
        static_cast<double>(input.evader_y) / scale};
    const double step_size = outer_dt / static_cast<double>(inner_steps);
    for(int step = 0; step < inner_steps; ++step) {
        const auto k1 = derivative(state, turn_rate, evader_heading);
        auto stage = state;
        for(std::size_t i = 0; i < stage.size(); ++i) stage[i] += step_size * k1[i] / 2.0;
        const auto k2 = derivative(stage, turn_rate, evader_heading);
        stage = state;
        for(std::size_t i = 0; i < stage.size(); ++i) stage[i] += step_size * k2[i] / 2.0;
        const auto k3 = derivative(stage, turn_rate, evader_heading);
        stage = state;
        for(std::size_t i = 0; i < stage.size(); ++i) stage[i] += step_size * k3[i];
        const auto k4 = derivative(stage, turn_rate, evader_heading);
        for(std::size_t i = 0; i < state.size(); ++i)
            state[i] += step_size * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) / 6.0;
    }
    return {std::llround(state[0] * scale), std::llround(state[1] * scale),
        std::llround(state[2] * scale), std::llround(state[3] * scale),
        std::llround(state[4] * scale)};
}

Graph build_graph() {
    Graph graph;
    graph.layers.resize(static_cast<std::size_t>(horizon + 1));
    graph.next.resize(static_cast<std::size_t>(horizon));
    graph.index.resize(static_cast<std::size_t>(horizon + 1));
    graph.layers[0].push_back({0, 0, 0, 2'500'000, 7'500'000});
    graph.index[0].emplace(graph.layers[0][0], 0);
    for(int stage = 0; stage < horizon; ++stage) {
        std::set<State> candidates;
        for(const auto& state : graph.layers[static_cast<std::size_t>(stage)])
            for(const double control : turn_rates)
                for(const double disturbance : evader_headings)
                    candidates.insert(advance_source(state, control, disturbance));
        auto& next_layer = graph.layers[static_cast<std::size_t>(stage + 1)];
        next_layer.assign(candidates.begin(), candidates.end());
        auto& next_index = graph.index[static_cast<std::size_t>(stage + 1)];
        for(std::size_t i = 0; i < next_layer.size(); ++i) next_index.emplace(next_layer[i], i);
        auto& rows = graph.next[static_cast<std::size_t>(stage)];
        rows.resize(graph.layers[static_cast<std::size_t>(stage)].size());
        for(std::size_t state_id = 0; state_id < rows.size(); ++state_id)
            for(std::size_t control_id = 0; control_id < turn_rates.size(); ++control_id)
                for(std::size_t disturbance_id = 0; disturbance_id < evader_headings.size(); ++disturbance_id) {
                    const auto next_state = advance_source(graph.layers[static_cast<std::size_t>(stage)][state_id],
                        turn_rates[control_id], evader_headings[disturbance_id]);
                    rows[state_id].destination[control_id][disturbance_id] = next_index.at(next_state);
                }
    }
    return graph;
}

double separation(const State& state) {
    const double dx = static_cast<double>(state.pursuer_x - state.evader_x) / scale;
    const double dy = static_cast<double>(state.pursuer_y - state.evader_y) / scale;
    return std::hypot(dx, dy);
}

feedback::Game feedback_game(const Graph& graph, int selected_horizon) {
    std::size_t state_count = 0;
    for(int stage = 0; stage <= selected_horizon; ++stage)
        state_count = std::max(state_count, graph.layers[static_cast<std::size_t>(stage)].size());
    std::vector<bool> terminal_safe(state_count, false), terminal_target(state_count, false);
    const auto& terminal = graph.layers[static_cast<std::size_t>(selected_horizon)];
    for(std::size_t i = 0; i < terminal.size(); ++i) {
        terminal_safe[i] = true;
        terminal_target[i] = separation(terminal[i]) <= target_radius;
    }
    feedback::Game game{state_count, {}, std::move(terminal_safe), std::move(terminal_target)};
    for(int stage_id = 0; stage_id < selected_horizon; ++stage_id) {
        const auto& states = graph.layers[static_cast<std::size_t>(stage_id)];
        const auto& transitions = graph.next[static_cast<std::size_t>(stage_id)];
        feedback::Stage stage{std::vector<bool>(state_count, false), turn_rates.size(),
            evader_headings.size(), {}};
        stage.next_state.resize(state_count);
        for(std::size_t state_id = 0; state_id < state_count; ++state_id) {
            stage.next_state[state_id].resize(turn_rates.size());
            for(std::size_t control_id = 0; control_id < turn_rates.size(); ++control_id) {
                stage.next_state[state_id][control_id].resize(evader_headings.size());
                for(std::size_t disturbance_id = 0; disturbance_id < evader_headings.size(); ++disturbance_id) {
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
    for(const auto& state : terminal) game.terminal.cost.push_back(separation(state));
    for(int stage_id = 0; stage_id < horizon; ++stage_id) {
        const auto& states = graph.layers[static_cast<std::size_t>(stage_id)];
        causal::Stage stage{states.size(), turn_rates.size(), evader_headings.size(), {}, {}};
        stage.safe_states.assign(states.size(), true);
        stage.next_state.resize(states.size());
        for(std::size_t state_id = 0; state_id < states.size(); ++state_id) {
            stage.next_state[state_id].resize(turn_rates.size());
            for(std::size_t control_id = 0; control_id < turn_rates.size(); ++control_id)
                for(std::size_t disturbance_id = 0; disturbance_id < evader_headings.size(); ++disturbance_id)
                    stage.next_state[state_id][control_id].push_back(causal::StateId{
                        graph.next[static_cast<std::size_t>(stage_id)][state_id]
                            .destination[control_id][disturbance_id]});
        }
        game.stages.push_back(std::move(stage));
    }
    return game;
}

Json state_json(const State& state) {
    return Json{{"ticks", {state.pursuer_x, state.pursuer_y, state.heading, state.evader_x, state.evader_y}},
        {"state", {static_cast<double>(state.pursuer_x) / scale,
            static_cast<double>(state.pursuer_y) / scale, static_cast<double>(state.heading) / scale,
            static_cast<double>(state.evader_x) / scale, static_cast<double>(state.evader_y) / scale}}};
}

Json layers_json(const Graph& graph, const feedback::Policy& policy) {
    Json layers = Json::array();
    for(int stage = 0; stage <= horizon; ++stage) {
        Json forward = Json::array(), winning = Json::array();
        const auto& states = graph.layers[static_cast<std::size_t>(stage)];
        for(std::size_t index = 0; index < states.size(); ++index) {
            auto item = state_json(states[index]);
            forward.push_back(item);
            if(policy.winning[static_cast<std::size_t>(stage)][index]) winning.push_back(std::move(item));
        }
        layers.push_back({{"stage", stage}, {"time_seconds", stage * outer_dt},
            {"forward_states", std::move(forward)}, {"backward_winning_intersection", std::move(winning)}});
    }
    return layers;
}

Json minimax_trajectory(const Graph& graph, const causal::Result& result) {
    Json path = Json::array();
    std::size_t state_id = result.initial_state.value;
    for(int stage = 0; stage <= horizon; ++stage) {
        const auto& state = graph.layers[static_cast<std::size_t>(stage)].at(state_id);
        const auto& value = result.values_by_stage[static_cast<std::size_t>(stage)].at(state_id);
        Json row{{"stage", stage}, {"time_seconds", stage * outer_dt},
            {"state_ticks", {state.pursuer_x, state.pursuer_y, state.heading, state.evader_x, state.evader_y}},
            {"state", {static_cast<double>(state.pursuer_x) / scale,
                static_cast<double>(state.pursuer_y) / scale, static_cast<double>(state.heading) / scale,
                static_cast<double>(state.evader_x) / scale, static_cast<double>(state.evader_y) / scale}},
            {"minimax_value", value.value}};
        if(stage < horizon) {
            const auto control_id = value.optimal_actions.front().value;
            std::size_t disturbance_id = 0;
            double worst = -1.0;
            for(std::size_t candidate = 0; candidate < evader_headings.size(); ++candidate) {
                const auto next = graph.next[static_cast<std::size_t>(stage)][state_id]
                    .destination[control_id][candidate];
                const auto next_value = result.values_by_stage[static_cast<std::size_t>(stage + 1)][next].value;
                if(next_value > worst) { worst = next_value; disturbance_id = candidate; }
            }
            row["turn_rate"] = turn_rates[control_id];
            row["evader_heading"] = evader_headings[disturbance_id];
            state_id = graph.next[static_cast<std::size_t>(stage)][state_id]
                .destination[control_id][disturbance_id];
        }
        path.push_back(std::move(row));
    }
    return path;
}

Json run() {
    const auto graph = build_graph();
    std::vector<bool> initial_wins;
    int first_capture = -1;
    for(int steps = 1; steps <= horizon; ++steps) {
        const auto outcome = feedback::solve(feedback_game(graph, steps));
        const auto* policy = std::get_if<feedback::Policy>(&outcome);
        if(!policy) throw std::runtime_error("finite-feedback solver rejected the reachable game graph");
        const bool wins = policy->winning.front().at(0);
        initial_wins.push_back(wins);
        if(wins && first_capture < 0) first_capture = steps;
    }
    if(first_capture != horizon) throw std::runtime_error("expected first robust capture at the four-step pilot horizon");
    const auto reachability_outcome = feedback::solve(feedback_game(graph, horizon));
    const auto* reachability = std::get_if<feedback::Policy>(&reachability_outcome);
    if(!reachability) throw std::runtime_error("finite-feedback solve failed at the selected horizon");
    const auto minimax_outcome = causal::solve(causal_game(graph), {1e-12, 1e-12});
    const auto* minimax = std::get_if<causal::Result>(&minimax_outcome);
    if(!minimax) throw std::runtime_error("finite causal minimax solve failed on the source-derived game");
    const auto value = minimax->initial().value;
    Json counts = Json::array(), capture = Json::array();
    for(const auto& layer : graph.layers) counts.push_back(layer.size());
    for(int step = 1; step <= horizon; ++step)
        capture.push_back({{"steps", step}, {"seconds", step * outer_dt},
            {"initial_state_winning", initial_wins[static_cast<std::size_t>(step - 1)]}});
    const auto path = minimax_trajectory(graph, *minimax);
    if(std::abs(path.back()["minimax_value"].get<double>() - value) > 1e-12)
        throw std::runtime_error("selected worst-response trajectory does not attain the initial minimax value");
    Json action_u = Json::array(), action_v = Json::array();
    for(const auto action : turn_rates) action_u.push_back(action);
    for(const auto action : evader_headings) action_v.push_back(action);
    return Json{{"schema", "csl.env717-homicidal-chauffeur/1"},
        {"source", {{"repository", "https://github.com/imm-rl-lab/differential_game_gym"},
            {"repository_commit", "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8"},
            {"file", "Environments/HomicidalChauffeur/HomicidalChauffeur.py"},
            {"file_blob", "f770a5c81c363ba628c987ee70f84af483c81b10"},
            {"license", "Apache-2.0; repository LICENSE blob 261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"}}},
        {"scenario_sha256", CSL_ENV717_HOMICIDAL_SCENARIO_SHA256},
        {"build", {{"source_commit", CSL_ENV717_HOMICIDAL_SOURCE_COMMIT},
            {"driver_sha256", CSL_ENV717_HOMICIDAL_DRIVER_SHA256},
            {"algorithm_source_sha256", CSL_ENV717_HOMICIDAL_ALGORITHM_SHA256},
            {"compiler_id", CSL_ENV717_HOMICIDAL_COMPILER_ID},
            {"compiler_version", CSL_ENV717_HOMICIDAL_COMPILER_VERSION},
            {"build_type", CSL_ENV717_HOMICIDAL_BUILD_TYPE},
            {"architecture", CSL_ENV717_HOMICIDAL_ARCHITECTURE},
            {"requested_workers", 1}, {"native_solver_threads", 1}}},
        {"source_state_order", {"time", "pursuer_x", "pursuer_y", "pursuer_heading", "evader_x", "evader_y"}},
        {"projection_labels", {{"pursuer", {"pursuer x position", "pursuer y position"}},
            {"evader", {"evader x position", "evader y position"}}}},
        {"adaptation", {{"initial_state", {0.0, 0.0, 0.0, 0.0, 2.5, 7.5}},
            {"horizon_steps", horizon}, {"horizon_seconds", horizon * outer_dt},
            {"turn_rate_catalogue", action_u}, {"evader_heading_catalogue_radians", action_v},
            {"state_quantization_scale", scale}, {"target_radius", target_radius},
            {"objective_orientation", "analysis adaptation: pursuer turn rate minimizes terminal Euclidean separation and evader heading maximizes it; source returns positive separation but does not specify per-agent payoff signs"},
            {"information_pattern", "finite causal response: pursuer chooses from the current state, then evader observes that turn rate and responds before the next state is observed"},
            {"interpretation", "source-derived finite game; not a reproduction of the continuous-action RL result"}}},
        {"graph_state_counts", counts}, {"first_robust_capture_steps", first_capture},
        {"capture_horizon_sweep", capture}, {"finite_causal_minimax_terminal_separation", value},
        {"figure_layers", layers_json(graph, *reachability)}, {"minimax_trajectory", path}};
}
}

int main() {
    try { std::cout << run().dump(2) << '\n'; }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
    return 0;
}
