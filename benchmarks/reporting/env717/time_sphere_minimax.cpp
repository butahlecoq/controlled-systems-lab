#include <csl/optimization/finite_causal_minimax.hpp>
#include <csl/reachability/finite_feedback.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <compare>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using Json = nlohmann::json;
namespace causal = csl::optimization::finite_causal_minimax;
namespace feedback = csl::reachability::finite_feedback;

constexpr std::int64_t scale = 1'000'000;
constexpr std::int64_t radius = scale;
constexpr int outer_horizon = 35;
constexpr int inner_steps = 10;
constexpr std::array<int, 3> controls{-1, 0, 1};
constexpr std::array<int, 3> disturbances{-1, 0, 1};

struct State {
    std::int64_t x1{};
    std::int64_t x2{};
    int captured_at_inner_step{-1};
    auto operator<=>(const State&) const = default;
};
using Position = std::array<std::int64_t, 2>;
using Destinations = std::array<std::array<std::size_t, 3>, 3>;
using Durations = std::array<std::array<int, 3>, 3>;
struct TransitionRow { Destinations destination{}; Durations elapsed{}; };
struct Graph {
    std::vector<std::vector<State>> layers;
    std::vector<std::vector<TransitionRow>> next;
    std::vector<std::map<State, std::size_t>> index;
};
struct Advance { State state; int elapsed{}; std::vector<Position> samples; };

bool in_target(const State& state) {
    return state.x1 * state.x1 + state.x2 * state.x2 <= radius * radius;
}

Advance advance_source(State state, int control, int disturbance, int stage) {
    Advance result{state, 0, {Position{state.x1, state.x2}}};
    if(state.captured_at_inner_step >= 0) return result;
    if(in_target(state)) {
        result.state.captured_at_inner_step = stage * inner_steps;
        return result;
    }
    for(int inner = 0; inner < inner_steps; ++inner) {
        if(in_target(state)) {
            state.captured_at_inner_step = stage * inner_steps + inner;
            result.state = state;
            return result;
        }
        if((state.x2 + disturbance * scale) % 100 != 0 || state.x2 % 100 != 0)
            throw std::runtime_error("source Euler update left the exact integer lattice");
        state.x1 += (state.x2 + disturbance * scale) / 100;
        state.x2 += static_cast<std::int64_t>(control) * (scale / 100);
        ++result.elapsed;
        result.samples.push_back(Position{state.x1, state.x2});
        if(in_target(state)) {
            state.captured_at_inner_step = stage * inner_steps + result.elapsed;
            result.state = state;
            return result;
        }
    }
    result.state = state;
    return result;
}

Graph build_graph() {
    Graph graph;
    graph.layers.resize(static_cast<std::size_t>(outer_horizon + 1));
    graph.next.resize(static_cast<std::size_t>(outer_horizon));
    graph.index.resize(static_cast<std::size_t>(outer_horizon + 1));
    graph.layers[0].push_back({2 * scale, -scale, -1});
    graph.index[0].emplace(graph.layers[0][0], 0);
    for(int stage = 0; stage < outer_horizon; ++stage) {
        std::set<State> candidates;
        for(const auto& state : graph.layers[static_cast<std::size_t>(stage)])
            for(const int control : controls)
                for(const int disturbance : disturbances)
                    candidates.insert(advance_source(state, control, disturbance, stage).state);
        auto& next_layer = graph.layers[static_cast<std::size_t>(stage + 1)];
        next_layer.assign(candidates.begin(), candidates.end());
        auto& next_index = graph.index[static_cast<std::size_t>(stage + 1)];
        for(std::size_t i = 0; i < next_layer.size(); ++i) next_index.emplace(next_layer[i], i);
        auto& rows = graph.next[static_cast<std::size_t>(stage)];
        rows.resize(graph.layers[static_cast<std::size_t>(stage)].size());
        for(std::size_t state_id = 0; state_id < rows.size(); ++state_id) {
            for(std::size_t action_id = 0; action_id < controls.size(); ++action_id) {
                for(std::size_t disturbance_id = 0; disturbance_id < disturbances.size(); ++disturbance_id) {
                    const auto advanced = advance_source(
                        graph.layers[static_cast<std::size_t>(stage)][state_id],
                        controls[action_id], disturbances[disturbance_id], stage);
                    rows[state_id].destination[action_id][disturbance_id] =
                        next_index.at(advanced.state);
                    rows[state_id].elapsed[action_id][disturbance_id] = advanced.elapsed;
                }
            }
        }
    }
    return graph;
}

feedback::Game feedback_game(const Graph& graph, int horizon) {
    std::size_t padded_count = 0;
    for(int stage = 0; stage <= horizon; ++stage)
        padded_count = std::max(padded_count, graph.layers[static_cast<std::size_t>(stage)].size());
    std::vector<bool> terminal_safe(padded_count, false), terminal_target(padded_count, false);
    const auto& terminal = graph.layers[static_cast<std::size_t>(horizon)];
    for(std::size_t i = 0; i < terminal.size(); ++i) {
        terminal_safe[i] = true;
        terminal_target[i] = terminal[i].captured_at_inner_step >= 0;
    }
    feedback::Game game{padded_count, {}, std::move(terminal_safe), std::move(terminal_target)};
    for(int stage_id = 0; stage_id < horizon; ++stage_id) {
        feedback::Stage stage{std::vector<bool>(padded_count, false), controls.size(),
                              disturbances.size(), {}};
        const auto& states = graph.layers[static_cast<std::size_t>(stage_id)];
        const auto& transitions = graph.next[static_cast<std::size_t>(stage_id)];
        stage.next_state.resize(padded_count);
        for(std::size_t state_id = 0; state_id < padded_count; ++state_id) {
            stage.next_state[state_id].resize(controls.size());
            for(std::size_t action_id = 0; action_id < controls.size(); ++action_id) {
                stage.next_state[state_id][action_id].resize(disturbances.size());
                for(std::size_t disturbance_id = 0; disturbance_id < disturbances.size(); ++disturbance_id) {
                    const auto destination = state_id < states.size()
                        ? transitions[state_id].destination[action_id][disturbance_id] : 0;
                    stage.next_state[state_id][action_id][disturbance_id] =
                        feedback::StateIndex{destination};
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
    game.terminal.safe_states.reserve(terminal.size());
    game.terminal.cost.reserve(terminal.size());
    for(const auto& state : terminal) {
        const bool captured = state.captured_at_inner_step >= 0;
        game.terminal.safe_states.push_back(captured);
        game.terminal.cost.push_back(captured ? state.captured_at_inner_step * 0.01 : 0.0);
    }
    for(int stage_id = 0; stage_id < outer_horizon; ++stage_id) {
        const auto& states = graph.layers[static_cast<std::size_t>(stage_id)];
        causal::Stage stage{states.size(), controls.size(), disturbances.size(), {}, {}};
        stage.safe_states.assign(states.size(), true);
        stage.next_state.resize(states.size());
        for(std::size_t state_id = 0; state_id < states.size(); ++state_id) {
            stage.next_state[state_id].resize(controls.size());
            for(std::size_t action_id = 0; action_id < controls.size(); ++action_id) {
                for(std::size_t disturbance_id = 0; disturbance_id < disturbances.size(); ++disturbance_id)
                    stage.next_state[state_id][action_id].push_back(causal::StateId{
                        graph.next[static_cast<std::size_t>(stage_id)][state_id]
                            .destination[action_id][disturbance_id]});
            }
        }
        game.stages.push_back(std::move(stage));
    }
    return game;
}

Json position_json(const Position& position) {
    return {position[0], position[1]};
}
Position position_of(const State& state) { return {state.x1, state.x2}; }
Json state_json(const State& state) {
    return {state.x1, state.x2, state.captured_at_inner_step};
}

Json json_positions(const std::set<Position>& positions) {
    Json result = Json::array();
    for(const auto& position : positions) result.push_back(position_json(position));
    return result;
}

Json figure_layers(const Graph& graph, const feedback::Policy& policy, int horizon) {
    Json result = Json::array();
    for(int stage = 0; stage <= horizon; ++stage) {
        std::set<Position> forward, winning;
        const auto& states = graph.layers[static_cast<std::size_t>(stage)];
        for(std::size_t i = 0; i < states.size(); ++i) {
            const auto position = position_of(states[i]);
            forward.insert(position);
            if(policy.winning[static_cast<std::size_t>(stage)][i]) winning.insert(position);
        }
        result.push_back({{"stage", stage}, {"elapsed_seconds", stage * 0.1},
            {"forward_positions_ticks", json_positions(forward)},
            {"winning_positions_ticks", json_positions(winning)}});
    }
    return result;
}

struct TimedResult { causal::Result result; std::vector<std::int64_t> causal_times_ns; };

TimedResult causal_result(const Graph& graph) {
    const auto game = causal_game(graph);
    const auto started = std::chrono::steady_clock::now();
    auto outcome = causal::solve(game, {0.0, 0.0});
    const auto stopped = std::chrono::steady_clock::now();
    const auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(stopped - started).count();
    if(duration <= 0) throw std::runtime_error("finite causal minimax timing was not positive");
    const auto* result = std::get_if<causal::Result>(&outcome);
    if(!result || !result->initial().feasible)
        throw std::runtime_error("finite causal minimax could not guarantee target capture by the horizon");
    return {*result, {duration}};
}

Json selected_trajectory(const Graph& graph, const causal::Result& solution) {
    std::size_t current = 0;
    Json samples = Json::array({position_json(position_of(graph.layers[0][0]))});
    Json control_sequence = Json::array(), disturbance_sequence = Json::array();
    Json stage_states = Json::array({state_json(graph.layers[0][0])});
    State final_state = graph.layers[0][0];
    for(int stage = 0; stage < outer_horizon; ++stage) {
        const auto& current_state = graph.layers[static_cast<std::size_t>(stage)][current];
        if(current_state.captured_at_inner_step >= 0) {
            final_state = current_state;
            break;
        }
        const auto& value = solution.values_by_stage[static_cast<std::size_t>(stage)][current];
        if(!value.feasible || value.optimal_actions.empty())
            throw std::runtime_error("minimax state has no optimal control action");
        const auto action = value.optimal_actions.front().value;
        std::size_t worst_disturbance = 0;
        double worst_value = -1.0;
        for(std::size_t disturbance = 0; disturbance < disturbances.size(); ++disturbance) {
            const auto destination = graph.next[static_cast<std::size_t>(stage)][current]
                .destination[action][disturbance];
            const auto& next_value = solution.values_by_stage[static_cast<std::size_t>(stage + 1)][destination];
            if(!next_value.feasible) throw std::runtime_error("selected minimax control has an infeasible disturbance successor");
            if(next_value.value > worst_value) {
                worst_value = next_value.value;
                worst_disturbance = disturbance;
            }
        }
        const auto advanced = advance_source(current_state, controls[action],
            disturbances[worst_disturbance], stage);
        for(std::size_t i = 1; i < advanced.samples.size(); ++i)
            samples.push_back(position_json(advanced.samples[i]));
        control_sequence.push_back(controls[action]);
        disturbance_sequence.push_back(disturbances[worst_disturbance]);
        current = graph.next[static_cast<std::size_t>(stage)][current]
            .destination[action][worst_disturbance];
        final_state = graph.layers[static_cast<std::size_t>(stage + 1)][current];
        stage_states.push_back(state_json(final_state));
    }
    if(final_state.captured_at_inner_step < 0)
        throw std::runtime_error("minimax disturbance path failed to capture the target");
    return {{"microstep_positions_ticks", samples}, {"stage_states", stage_states},
        {"control_actions", control_sequence}, {"disturbance_actions", disturbance_sequence},
        {"capture_inner_step", final_state.captured_at_inner_step},
        {"capture_time_seconds", final_state.captured_at_inner_step * 0.01}};
}

Json run() {
    const auto build_started = std::chrono::steady_clock::now();
    const auto graph = build_graph();
    const auto build_stopped = std::chrono::steady_clock::now();
    const auto graph_build_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
        build_stopped - build_started).count();
    if(graph_build_ns <= 0) throw std::runtime_error("graph construction timing was not positive");

    int selected_horizon = 0;
    std::vector<std::int64_t> feedback_solver_ns;
    feedback::Policy selected_policy;
    for(int horizon = 1; horizon <= outer_horizon; ++horizon) {
        const auto game = feedback_game(graph, horizon);
        const auto started = std::chrono::steady_clock::now();
        const auto outcome = feedback::solve(game);
        const auto stopped = std::chrono::steady_clock::now();
        const auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(stopped - started).count();
        if(duration <= 0) throw std::runtime_error("finite-feedback timing was not positive");
        feedback_solver_ns.push_back(duration);
        const auto* policy = std::get_if<feedback::Policy>(&outcome);
        if(!policy) throw std::runtime_error("finite-feedback rejected the source-derived graph");
        if(policy->winning[0][0]) {
            selected_horizon = horizon;
            selected_policy = *policy;
            break;
        }
    }
    if(selected_horizon == 0)
        throw std::runtime_error("the initial state is not robustly captured by the finite horizon");
    if(selected_horizon != outer_horizon)
        throw std::runtime_error("pilot horizon must end at the first guaranteed-capture horizon");

    const auto minimax = causal_result(graph);
    const auto value = minimax.result.initial().value;
    const auto value_ms = static_cast<std::int64_t>(std::llround(value * 100.0));
    if(std::abs(value - value_ms * 0.01) > 1e-12)
        throw std::runtime_error("minimax capture time is not on the source inner-step lattice");

    Json figure_layers_json = figure_layers(graph, selected_policy, selected_horizon);
    Json state_counts = Json::array(), winning_counts = Json::array();
    for(int stage = 0; stage <= selected_horizon; ++stage) {
        state_counts.push_back(graph.layers[static_cast<std::size_t>(stage)].size());
        std::set<Position> wins;
        const auto& states = graph.layers[static_cast<std::size_t>(stage)];
        for(std::size_t i = 0; i < states.size(); ++i)
            if(selected_policy.winning[static_cast<std::size_t>(stage)][i])
                wins.insert(position_of(states[i]));
        winning_counts.push_back(wins.size());
    }

    Json controls_json = Json::array(), disturbances_json = Json::array();
    for(const auto value : controls) controls_json.push_back(value);
    for(const auto value : disturbances) disturbances_json.push_back(value);
    Json result{{"schema", "csl.env717-time-sphere-minimax/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "fd7709a6f8e4196665d36b4ac5d348173599c250"},
        {"source_license", "no license declared in repository metadata"},
        {"source_model", {{"initial_state", {2.0, -1.0}}, {"state_order", {"position_x1", "velocity_x2"}},
            {"dynamics", "x1_next=x1+0.01*(x2+v); x2_next=x2+0.01*u"},
            {"outer_dt_seconds", 0.1}, {"inner_euler_steps", inner_steps}, {"inner_dt_seconds", 0.01},
            {"target", {{"shape", "unit disk"}, {"center", {0.0, 0.0}}, {"radius", 1.0}}},
            {"action_bounds", {{"u", {-1.0, 1.0}}, {"v", {-1.0, 1.0}}}},
            {"reward", "elapsed inner-Euler time until the state enters the unit disk"},
            {"game_orientation", {{"u_player", "minimizes elapsed time"},
                {"v_player", "maximizes elapsed time"}}}}},
        {"source_information_pattern", "both player policies use the current environment state; neither policy receives the opponent's current action"},
        {"adaptation", {{"control_catalogue", controls_json}, {"disturbance_catalogue", disturbances_json},
            {"decision_interval_seconds", 0.1}, {"maximum_outer_steps", outer_horizon},
            {"information_pattern", "sequential response: u selects an action from the current exact state, then v observes u and selects a disturbance; the next state is observed"},
            {"information_pattern_change", "unlike the source state-feedback policies, v's action may depend on u's current action"},
            {"scope", "finite-catalogue, finite-state feedback differential game; not the continuous-action RL result"}}},
        {"solvers", {{"reachability", "csl.reachability.finite_feedback.solve"},
            {"minimax", "csl.optimization.finite_causal_minimax.solve"}}},
        {"lattice_scale", scale}, {"outer_horizon_steps", outer_horizon},
        {"first_guaranteed_capture_horizon_steps", selected_horizon},
        {"first_guaranteed_capture_horizon_seconds", selected_horizon * 0.1},
        {"minimax_capture_time_seconds", value}, {"minimax_capture_inner_steps", value_ms},
        {"forward_state_counts", state_counts}, {"backward_winning_position_counts", winning_counts},
        {"figure_layers", figure_layers_json}, {"worst_case_minimax_trajectory", selected_trajectory(graph, minimax.result)},
        {"timing", {{"claim", "descriptive only; no performance comparison"},
            {"graph_build_wall_ns", graph_build_ns}, {"finite_feedback_solver_calls", feedback_solver_ns.size()},
            {"finite_feedback_wall_ns_by_horizon", feedback_solver_ns},
            {"finite_causal_minimax_solver_calls", minimax.causal_times_ns.size()},
            {"finite_causal_minimax_wall_ns", minimax.causal_times_ns},
            {"timed_work", "finite_feedback horizon sweep and finite_causal_minimax solve; graph building and rendering reported separately"},
            {"all_solver_calls_succeeded", true}, {"worker_threads", 1}, {"native_threads", 1}}},
        {"driver_sha256", CSL_ENV717_TIME_SPHERE_MINIMAX_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_TIME_SPHERE_MINIMAX_ALGORITHM_SHA256},
        {"source_commit", CSL_ENV717_TIME_SPHERE_MINIMAX_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_TIME_SPHERE_MINIMAX_COMPILER_ID},
            {"compiler_version", CSL_ENV717_TIME_SPHERE_MINIMAX_COMPILER_VERSION},
            {"build_type", CSL_ENV717_TIME_SPHERE_MINIMAX_BUILD_TYPE},
            {"architecture", CSL_ENV717_TIME_SPHERE_MINIMAX_ARCHITECTURE}}}};
    return result;
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
