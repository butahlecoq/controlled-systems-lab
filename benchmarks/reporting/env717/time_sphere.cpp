#include <csl/reachability/finite_feedback.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Json = nlohmann::json;
using State = std::array<std::int64_t, 2>;
namespace feedback = csl::reachability::finite_feedback;

constexpr std::int64_t scale = 1'000'000;
constexpr std::int64_t target_radius = scale;
constexpr std::int64_t target_radius_squared = target_radius * target_radius;
constexpr int inner_steps = 10;
constexpr int max_horizon = 12;
constexpr std::array<int, 3> controls{-1, 0, 1};
constexpr State initial{2 * scale, -scale};

bool inside_target(const State& state) {
    return state[0] * state[0] + state[1] * state[1] <= target_radius_squared;
}

State source_step(State state, int control) {
    for(int inner = 0; inner < inner_steps; ++inner) {
        if(inside_target(state)) break;
        if(state[1] % 100 != 0)
            throw std::runtime_error("source Euler lattice is not integral");
        state[0] += state[1] / 100;
        state[1] += static_cast<std::int64_t>(control) * 10'000;
    }
    return state;
}

struct Graph {
    std::vector<std::vector<State>> layers;
    std::vector<std::vector<std::vector<std::size_t>>> next;
    std::vector<std::map<State, std::size_t>> index;
};

Graph graph() {
    Graph result;
    result.layers.resize(max_horizon + 1);
    result.next.resize(max_horizon);
    result.index.resize(max_horizon + 1);
    result.layers[0] = {initial};
    result.index[0].emplace(initial, 0);
    for(int stage = 0; stage < max_horizon; ++stage) {
        std::set<State> next_states;
        for(const auto& state : result.layers[static_cast<std::size_t>(stage)])
            for(const int action : controls)
                next_states.insert(source_step(state, action));
        auto& layer = result.layers[static_cast<std::size_t>(stage + 1)];
        layer.assign(next_states.begin(), next_states.end());
        for(std::size_t i = 0; i < layer.size(); ++i)
            result.index[static_cast<std::size_t>(stage + 1)].emplace(layer[i], i);
        auto& rows = result.next[static_cast<std::size_t>(stage)];
        rows.resize(result.layers[static_cast<std::size_t>(stage)].size());
        for(std::size_t i = 0; i < rows.size(); ++i) {
            for(const int action : controls) {
                const auto destination = source_step(
                    result.layers[static_cast<std::size_t>(stage)][i], action);
                rows[i].push_back(result.index[static_cast<std::size_t>(stage + 1)].at(destination));
            }
        }
    }
    return result;
}

std::size_t padded_size(const Graph& graph_data, int horizon) {
    std::size_t count = 0;
    for(int stage = 0; stage <= horizon; ++stage)
        count = std::max(count, graph_data.layers[static_cast<std::size_t>(stage)].size());
    return count;
}

feedback::Game make_game(const Graph& graph_data, int horizon) {
    const auto count = padded_size(graph_data, horizon);
    std::vector<bool> terminal_safe(count, false), terminal_target(count, false);
    const auto& terminal = graph_data.layers[static_cast<std::size_t>(horizon)];
    for(std::size_t i = 0; i < terminal.size(); ++i) {
        terminal_safe[i] = true;
        terminal_target[i] = inside_target(terminal[i]);
    }
    feedback::Game game{count, {}, std::move(terminal_safe), std::move(terminal_target)};
    for(int stage_index = 0; stage_index < horizon; ++stage_index) {
        feedback::Stage stage{std::vector<bool>(count, false), controls.size(), 1, {}};
        const auto& states = graph_data.layers[static_cast<std::size_t>(stage_index)];
        const auto& transitions = graph_data.next[static_cast<std::size_t>(stage_index)];
        for(std::size_t i = 0; i < states.size(); ++i) stage.safe_states[i] = true;
        stage.next_state.resize(count);
        for(std::size_t i = 0; i < count; ++i) {
            stage.next_state[i].resize(controls.size());
            for(std::size_t action = 0; action < controls.size(); ++action) {
                const auto destination = i < states.size() ? transitions[i][action] : 0;
                stage.next_state[i][action] = {{destination}};
            }
        }
        game.stages.push_back(std::move(stage));
    }
    return game;
}

Json state_json(const State& state) {
    return {static_cast<double>(state[0]) / scale,
            static_cast<double>(state[1]) / scale};
}

Json states_json(const std::vector<State>& states) {
    Json result = Json::array();
    for(const auto& state : states) result.push_back(state_json(state));
    return result;
}

std::int64_t elapsed_source_substeps(State state, int action) {
    std::int64_t elapsed = 0;
    for(int inner = 0; inner < inner_steps; ++inner) {
        if(inside_target(state)) break;
        if(state[1] % 100 != 0)
            throw std::runtime_error("source Euler lattice is not integral");
        state[0] += state[1] / 100;
        state[1] += static_cast<std::int64_t>(action) * 10'000;
        ++elapsed;
    }
    return elapsed;
}

Json report(const Graph& graph_data) {
    Json sweep = Json::array();
    feedback::Policy selected;
    int selected_horizon = 0;
    std::int64_t total_solver_ns = 0;
    for(int horizon = 1; horizon <= max_horizon; ++horizon) {
        auto game = make_game(graph_data, horizon);
        const auto started = std::chrono::steady_clock::now();
        const auto outcome = feedback::solve(game);
        const auto stopped = std::chrono::steady_clock::now();
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            stopped - started).count();
        if(elapsed <= 0) throw std::runtime_error("finite-feedback timing was not positive");
        total_solver_ns += elapsed;
        const auto* policy = std::get_if<feedback::Policy>(&outcome);
        if(!policy) throw std::runtime_error("finite-feedback rejected the authored reachability graph");
        const bool winning = policy->winning[0][0];
        sweep.push_back({{"horizon_steps", horizon},
            {"horizon_seconds", horizon * 0.1}, {"initial_winning", winning},
            {"solver_wall_ns", elapsed}});
        if(winning) {
            selected = *policy;
            selected_horizon = horizon;
            break;
        }
    }
    if(selected_horizon == 0)
        throw std::runtime_error("initial point is not captured by the maximum finite horizon");

    Json selected_layers = Json::array(), winning_layers = Json::array();
    Json admissible_actions = Json::array(), transition_tables = Json::array();
    for(int stage = 0; stage <= selected_horizon; ++stage) {
        selected_layers.push_back(states_json(graph_data.layers[static_cast<std::size_t>(stage)]));
        Json winners = Json::array();
        const auto& states = graph_data.layers[static_cast<std::size_t>(stage)];
        for(std::size_t i = 0; i < states.size(); ++i)
            if(selected.winning[static_cast<std::size_t>(stage)][i])
                winners.push_back(state_json(states[i]));
        winning_layers.push_back(std::move(winners));
        if(stage < selected_horizon) {
            Json actions = Json::array(), transitions = Json::array();
            const auto& state_rows = selected.admissible_actions[static_cast<std::size_t>(stage)];
            const auto& next_rows = graph_data.next[static_cast<std::size_t>(stage)];
            for(std::size_t i = 0; i < states.size(); ++i) {
                Json action_row = Json::array(), transition_row = Json::array();
                for(const auto action : state_rows[i])
                    action_row.push_back(controls[action.value]);
                for(const auto destination : next_rows[i])
                    transition_row.push_back(destination);
                actions.push_back(std::move(action_row));
                transitions.push_back(std::move(transition_row));
            }
            admissible_actions.push_back(std::move(actions));
            transition_tables.push_back(std::move(transitions));
        }
    }

    Json trajectory = Json::array(), trajectory_controls = Json::array();
    State current = initial;
    std::int64_t total_inner_steps = 0;
    trajectory.push_back(state_json(current));
    for(int stage = 0; stage < selected_horizon && !inside_target(current); ++stage) {
        const auto index = graph_data.index[static_cast<std::size_t>(stage)].at(current);
        const auto& feasible = selected.admissible_actions[static_cast<std::size_t>(stage)][index];
        if(feasible.empty()) throw std::runtime_error("winning state has no admissible control");
        const int action = controls[feasible.front().value];
        total_inner_steps += elapsed_source_substeps(current, action);
        current = source_step(current, action);
        trajectory_controls.push_back(action);
        trajectory.push_back(state_json(current));
    }
    if(!inside_target(current)) throw std::runtime_error("selected finite-feedback trajectory missed the target");

    Json layer_counts = Json::array();
    for(int stage = 0; stage <= max_horizon; ++stage)
        layer_counts.push_back(graph_data.layers[static_cast<std::size_t>(stage)].size());
    Json controls_json = Json::array();
    for(const int action : controls) controls_json.push_back(action);
    Json result{{"schema", "csl.env717-time-sphere/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "fd7709a6f8e4196665d36b4ac5d348173599c250"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"position_x1", "velocity_x2"}},
        {"source_model", {{"initial_state", {2.0, -1.0}}, {"outer_dt_seconds", 0.1},
            {"inner_euler_steps", inner_steps}, {"inner_dt_seconds", 0.01},
            {"target", {{"shape", "disk"}, {"center", {0.0, 0.0}}, {"radius", 1.0}}},
            {"dynamics", "x1'=x2+v; x2'=u"},
            {"step_reward", "elapsed inner-Euler time until x enters the unit disk"}}},
        {"adaptation", {{"adversarial_action", 0.0},
            {"adversarial_action_reason", "nominal reachability slice freezes source v at zero"},
            {"control_catalogue", controls_json}, {"maximum_horizon_steps", max_horizon},
            {"maximum_horizon_seconds", max_horizon * 0.1},
            {"information_pattern", "causal finite-state control selected from the current state"},
            {"claim", "finite-catalogue feedback reachability only; not the continuous two-player RL optimum"}}},
        {"solver", "csl.reachability.finite_feedback.solve"},
        {"lattice_scale", scale}, {"target_radius_lattice", target_radius},
        {"maximum_horizon_steps", max_horizon}, {"forward_layer_state_counts", layer_counts},
        {"horizon_sweep", sweep}, {"selected_horizon_steps", selected_horizon},
        {"selected_horizon_seconds", selected_horizon * 0.1},
        {"target_inner_steps", total_inner_steps}, {"target_time_seconds", total_inner_steps * 0.01},
        {"forward_layers", selected_layers}, {"backward_winning_layers", winning_layers},
        {"admissible_actions", admissible_actions}, {"transition_indices", transition_tables},
        {"trajectory", trajectory}, {"trajectory_controls", trajectory_controls},
        {"initial_winning", selected.winning[0][0]},
        {"timing", {{"warmup_calls", 0}, {"measured_solver_calls", sweep.size()},
            {"per_horizon_wall_ns", [&] { Json values=Json::array(); for(const auto& row:sweep) values.push_back(row["solver_wall_ns"]); return values; }()},
            {"total_solver_wall_ns", total_solver_ns},
            {"scope", "finite-feedback solves over candidate horizons; graph construction and serialization excluded"},
            {"comparison_claim", false}, {"worker_threads_requested", 1},
            {"worker_threads_actual", 1}, {"native_threads_requested", 1},
            {"native_threads_actual", 1}, {"workspace_reuse", "none"},
            {"cache_state", "in-memory graph; no prior solver calls"}}},
        {"driver_sha256", CSL_ENV717_TIME_SPHERE_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_TIME_SPHERE_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_TIME_SPHERE_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_TIME_SPHERE_COMPILER_ID},
            {"compiler_version", CSL_ENV717_TIME_SPHERE_COMPILER_VERSION},
            {"build_type", CSL_ENV717_TIME_SPHERE_BUILD_TYPE},
            {"architecture", CSL_ENV717_TIME_SPHERE_ARCHITECTURE}}}};
    return result;
}
}

int main() {
    try {
        const auto result = report(graph());
        std::cout << result.dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "TimeOptimalSphereGame report failed: " << error.what() << '\n';
        return 1;
    }
}
