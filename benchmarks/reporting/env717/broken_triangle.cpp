#include <csl/optimization/finite_causal_minimax.hpp>
#include <csl/reachability/finite_feedback.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace {
using Json = nlohmann::json;
namespace causal = csl::optimization::finite_causal_minimax;
namespace feedback = csl::reachability::finite_feedback;

constexpr std::size_t horizon = 4;
constexpr double dt = 0.4;
constexpr double controls[]{-0.25, 0.25};
constexpr double disturbances[]{-1.0, 1.0};
constexpr double tie_tolerance = 1e-12;
using TickState = std::array<int, 2>;
using State = std::array<double, 2>;
using Polygon = std::array<State, 5>;
constexpr TickState initial_ticks{-15, -20}; // (-0.75, -1) on a 0.05 grid
constexpr Polygon target{{{{0.0, 4.5}}, {{0.5, -1.0}}, {{3.5, -4.0}},
                           {{-3.5, -4.0}}, {{-0.5, -1.0}}}};

template<class T> T take(std::variant<T, csl::Diagnostic> outcome) {
    if(const auto* error = std::get_if<csl::Diagnostic>(&outcome))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(outcome));
}

State coordinates(const TickState& state) {
    return {static_cast<double>(state[0]) / 20.0,
            static_cast<double>(state[1]) / 20.0};
}

TickState transition(TickState state, std::size_t u, std::size_t v) {
    state[0] += static_cast<int>(std::lround(20.0 * dt * (controls[u] + disturbances[v])));
    state[1] += static_cast<int>(std::lround(20.0 * dt * disturbances[v]));
    return state;
}

double source_signed_distance(const State& z) {
    double best = 0.0;
    double best_sign = 0.0;
    bool first = true;
    for(std::size_t i = 0; i < target.size(); ++i) {
        const auto& x = target[i];
        const auto& y = target[(i + 1) % target.size()];
        const double dx = y[0] - x[0], dy = y[1] - x[1];
        const double length_squared = dx * dx + dy * dy;
        const double rx = z[0] - x[0], ry = z[1] - x[1];
        const double r = (rx * dx + ry * dy) / length_squared;
        double distance = 0.0;
        if(r < 0.0) distance = std::hypot(rx, ry);
        else if(r > 1.0) distance = std::hypot(z[0] - y[0], z[1] - y[1]);
        else distance = std::sqrt(std::max(0.0, rx * rx + ry * ry - r * r * length_squared));
        if(first || distance < best) {
            best = distance;
            best_sign = ry * dx - rx * dy;
            first = false;
        }
    }
    return best * (best_sign < 0.0 ? -1.0 : 1.0);
}

struct Graph {
    std::vector<std::vector<TickState>> layers;
    std::vector<std::vector<std::vector<std::vector<std::size_t>>>> next;
    std::vector<std::size_t> offsets;
};

Graph make_graph() {
    Graph graph;
    graph.layers.resize(horizon + 1);
    graph.next.resize(horizon);
    graph.layers[0].push_back(initial_ticks);
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        std::map<TickState, std::size_t> ids;
        auto& transitions = graph.next[stage];
        transitions.resize(graph.layers[stage].size());
        for(std::size_t state = 0; state < graph.layers[stage].size(); ++state) {
            transitions[state].resize(2);
            for(std::size_t u = 0; u < 2; ++u) {
                auto& destinations = transitions[state][u];
                for(std::size_t v = 0; v < 2; ++v) {
                    const auto candidate = transition(graph.layers[stage][state], u, v);
                    auto found = ids.find(candidate);
                    if(found == ids.end()) {
                        const auto id = graph.layers[stage + 1].size();
                        graph.layers[stage + 1].push_back(candidate);
                        found = ids.emplace(candidate, id).first;
                    }
                    destinations.push_back(found->second);
                }
            }
        }
    }
    graph.offsets.resize(horizon + 1);
    for(std::size_t stage = 1; stage <= horizon; ++stage)
        graph.offsets[stage] = graph.offsets[stage - 1] + graph.layers[stage - 1].size();
    return graph;
}

bool in_target(const TickState& state) {
    // The source sigma is negative in the polygon, positive outside, and zero on its boundary.
    return source_signed_distance(coordinates(state)) <= tie_tolerance;
}

feedback::Policy solve_reachability(const Graph& graph) {
    feedback::Game game;
    game.state_count = graph.offsets.back() + graph.layers.back().size();
    game.terminal_safe.assign(game.state_count, false);
    game.terminal_target.assign(game.state_count, false);
    for(std::size_t id = 0; id < graph.layers.back().size(); ++id) {
        const auto global = graph.offsets.back() + id;
        game.terminal_safe[global] = true;
        game.terminal_target[global] = in_target(graph.layers.back()[id]);
    }
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        feedback::Stage row;
        row.safe_states.assign(game.state_count, false);
        row.action_count = 2;
        row.disturbance_count = 2;
        row.next_state.resize(game.state_count, std::vector<std::vector<feedback::StateIndex>>(2,
            std::vector<feedback::StateIndex>(2, feedback::StateIndex{0})));
        for(std::size_t state = 0; state < graph.layers[stage].size(); ++state) {
            const auto global = graph.offsets[stage] + state;
            row.safe_states[global] = true;
            for(std::size_t u = 0; u < 2; ++u) {
                for(std::size_t v = 0; v < 2; ++v) {
                    const auto next = graph.next[stage][state][u][v];
                    row.next_state[global][u][v] = feedback::StateIndex{
                        graph.offsets[stage + 1] + next};
                }
            }
        }
        game.stages.push_back(std::move(row));
    }
    game.state_count = game.terminal_target.size();
    const auto result = feedback::solve(game);
    const auto* policy = std::get_if<feedback::Policy>(&result);
    if(!policy || policy->winning.size() != horizon + 1)
        throw std::runtime_error("finite feedback reachability did not return all layers");
    return *policy;
}

causal::Result solve_minimax(const Graph& graph) {
    causal::Game game;
    game.initial_state = causal::StateId{0};
    game.terminal.state_count = graph.layers.back().size();
    game.terminal.safe_states.assign(graph.layers.back().size(), true);
    for(const auto& state : graph.layers.back())
        game.terminal.cost.push_back(source_signed_distance(coordinates(state)));
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        causal::Stage row{graph.layers[stage].size(), 2, 2, {}, {}};
        row.safe_states.assign(row.state_count, true);
        row.next_state.resize(row.state_count);
        for(std::size_t state = 0; state < row.state_count; ++state) {
            row.next_state[state].resize(2);
            for(std::size_t u = 0; u < 2; ++u) {
                for(const auto v : graph.next[stage][state][u])
                    row.next_state[state][u].push_back(causal::StateId{v});
            }
        }
        game.stages.push_back(std::move(row));
    }
    auto outcome = causal::solve(game, {tie_tolerance, tie_tolerance});
    auto* result = std::get_if<causal::Result>(&outcome);
    if(!result || !result->initial().feasible || result->values_by_stage.size() != horizon + 1)
        throw std::runtime_error("finite causal minimax did not return a complete state-value graph");
    return std::move(*result);
}

struct OpenPlan { std::vector<std::size_t> actions; double worst; std::vector<std::size_t> worst_v; std::vector<std::size_t> path; };

void enumerate_open(const Graph& graph, std::size_t stage, std::size_t state,
                    std::vector<std::size_t>& us, std::vector<std::size_t>& vs,
                    double& worst, std::vector<std::size_t>& worst_vs) {
    if(stage == horizon) {
        const double cost = source_signed_distance(coordinates(graph.layers[stage][state]));
        if(cost > worst + tie_tolerance) { worst = cost; worst_vs = vs; }
        return;
    }
    for(std::size_t v = 0; v < 2; ++v) {
        vs[stage] = v;
        const auto next = graph.next[stage][state][us[stage]][v];
        enumerate_open(graph, stage + 1, next, us, vs, worst, worst_vs);
    }
}

std::vector<OpenPlan> open_plans(const Graph& graph) {
    std::vector<OpenPlan> plans;
    for(std::size_t code = 0; code < 16; ++code) {
        std::vector<std::size_t> us(horizon), vs(horizon), worst_vs;
        std::size_t digits = code;
        for(std::size_t stage = 0; stage < horizon; ++stage) { us[stage] = digits % 2; digits /= 2; }
        double worst = -std::numeric_limits<double>::infinity();
        enumerate_open(graph, 0, 0, us, vs, worst, worst_vs);
        std::vector<std::size_t> path{0};
        std::size_t state = 0;
        for(std::size_t stage = 0; stage < horizon; ++stage) {
            state = graph.next[stage][state][us[stage]][worst_vs[stage]];
            path.push_back(state);
        }
        plans.push_back({std::move(us), worst, std::move(worst_vs), std::move(path)});
    }
    return plans;
}

Json state_json(const TickState& state) {
    const auto xy = coordinates(state);
    return Json::array({xy[0], xy[1]});
}

Json main_record(const Graph& graph, const feedback::Policy& policy,
                 const causal::Result& values, const std::vector<OpenPlan>& plans,
                 std::int64_t elapsed_ns) {
    const auto best = std::min_element(plans.begin(), plans.end(), [](const auto& a, const auto& b) {
        return a.worst < b.worst;
    });
    Json layers = Json::array();
    for(std::size_t stage = 0; stage < graph.layers.size(); ++stage) {
        Json states = Json::array();
        for(std::size_t id = 0; id < graph.layers[stage].size(); ++id) {
            const auto value = values.values_by_stage[stage][id];
            Json actions = Json::array();
            for(const auto action : value.optimal_actions) actions.push_back(action.value);
            states.push_back({{"id", id}, {"xy", state_json(graph.layers[stage][id])},
                {"target", in_target(graph.layers[stage][id])},
                {"feedback_winning", policy.winning[stage][graph.offsets[stage] + id]},
                {"causal_feasible", value.feasible}, {"causal_value", value.value},
                {"optimal_actions", std::move(actions)}});
        }
        layers.push_back(std::move(states));
    }
    Json saved_plans = Json::array();
    for(std::size_t i = 0; i < plans.size(); ++i) {
        Json us = Json::array(), vs = Json::array(), path = Json::array();
        for(const auto id : plans[i].actions) us.push_back(id);
        for(const auto id : plans[i].worst_v) vs.push_back(id);
        for(const auto id : plans[i].path) path.push_back(state_json(graph.layers[path.size()][id]));
        saved_plans.push_back({{"plan_id", i}, {"u_indices", std::move(us)},
            {"worst_v_indices", std::move(vs)}, {"worst_cost", plans[i].worst},
            {"worst_path", std::move(path)}});
    }
    Json causal_path = Json::array(), causal_actions = Json::array(), causal_disturbances = Json::array();
    std::size_t state = 0;
    causal_path.push_back(state_json(graph.layers[0][state]));
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        const auto& value = values.values_by_stage[stage][state];
        if(value.optimal_actions.empty()) throw std::runtime_error("minimax state has no optimal action");
        const auto u = value.optimal_actions.front().value;
        std::size_t v_worst = 0;
        double v_value = -std::numeric_limits<double>::infinity();
        for(std::size_t v = 0; v < 2; ++v) {
            const auto next = graph.next[stage][state][u][v];
            const double candidate = values.values_by_stage[stage + 1][next].value;
            if(candidate > v_value + tie_tolerance) { v_value = candidate; v_worst = v; }
        }
        causal_actions.push_back(u); causal_disturbances.push_back(v_worst);
        state = graph.next[stage][state][u][v_worst];
        causal_path.push_back(state_json(graph.layers[stage + 1][state]));
    }
    Json raw_layers = Json::array();
    for(const auto& layer : graph.layers) {
        Json rows = Json::array(); for(const auto& point : layer) rows.push_back(state_json(point));
        raw_layers.push_back(std::move(rows));
    }
    Json target_rows = Json::array(); for(const auto& point : target) target_rows.push_back(point);
    Json open_us = Json::array(), open_vs = Json::array(), open_path = Json::array();
    for(const auto id : best->actions) open_us.push_back(id);
    for(const auto id : best->worst_v) open_vs.push_back(id);
    for(std::size_t stage = 0; stage < best->path.size(); ++stage)
        open_path.push_back(state_json(graph.layers[stage][best->path[stage]]));
    return {{"schema", "csl.env717-broken-triangle-pilot/1"},
        {"source_repository", "https://github.com/imm-rl-lab/optimal_control"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"game_file_blob", "91771d55f6f868bb31d871cb0ad8a5d2af521c2a"},
        {"rl_notebook_blob", "2ba6b9d73040caf2c98017ecc7bcee3d41c1be8a"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"time", "x", "y"}}, {"initial_state", {0.0, -0.75, -1.0}},
        {"terminal_polygon", target_rows}, {"source_dt", dt}, {"source_terminal_time", 1.6},
        {"source_u_actions", {-0.25, 0.25}}, {"source_v_actions", {-1.0, 1.0}},
        {"source_dynamics", "(t,x,y)'=(1,u+v,v)"},
        {"source_terminal_reward", "signed distance to terminal polygon M"},
        {"adaptation", {{"horizon", horizon}, {"dt", dt},
            {"open_loop_plan_count", plans.size()}, {"disturbance_sequences_per_plan", 16},
            {"control_information", "fixed open-loop plan versus observed-state causal feedback"},
            {"cost", "source signed distance to polygon M; the disturbance maximizes terminal cost"},
            {"reachability", "finite forward state catalog and exact finite-feedback predecessor game; no continuous boundary claim"}}},
        {"layers", std::move(layers)}, {"state_catalogues", std::move(raw_layers)},
        {"open_loop_plans", std::move(saved_plans)},
        {"open_loop_value", best->worst}, {"open_loop_u_indices", std::move(open_us)},
        {"open_loop_worst_v_indices", std::move(open_vs)}, {"open_loop_worst_path", std::move(open_path)},
        {"causal_value", values.initial().value}, {"causal_u_indices", std::move(causal_actions)},
        {"causal_worst_v_indices", std::move(causal_disturbances)}, {"causal_worst_path", std::move(causal_path)},
        {"feedback_winning_initial", policy.winning.front().front()},
        {"winning_counts_by_stage", [&policy]() { Json a=Json::array(); for(const auto& w:policy.winning) a.push_back(std::count(w.begin(),w.end(),true)); return a; }()},
        {"state_counts_by_stage", [&graph]() { Json a=Json::array(); for(const auto& row:graph.layers) a.push_back(row.size()); return a; }()},
        {"timing", {{"warmup_calls", 1}, {"measured_calls", 1}, {"measured_wall_ns", {elapsed_ns}},
            {"scope", "one finite_causal_minimax solve; state graph construction, reachability, open-loop enumeration and serialization excluded"},
            {"comparison_claim", false}}},
        {"source_commit", CSL_ENV717_BROKEN_SOURCE_COMMIT},
        {"driver_sha256", CSL_ENV717_BROKEN_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_BROKEN_ALGORITHM_SHA256},
        {"compiler", CSL_ENV717_BROKEN_COMPILER_ID},
        {"compiler_version", CSL_ENV717_BROKEN_COMPILER_VERSION},
        {"build_type", CSL_ENV717_BROKEN_BUILD_TYPE},
        {"architecture", CSL_ENV717_BROKEN_ARCHITECTURE}};
}
}

int main() {
    try {
        const auto graph = make_graph();
        const auto policy = solve_reachability(graph);
        const auto plans = open_plans(graph);
        (void)solve_minimax(graph); // one excluded warmup
        const auto start = std::chrono::steady_clock::now();
        const auto minimax = solve_minimax(graph);
        const auto stop = std::chrono::steady_clock::now();
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
        const auto result = main_record(graph, policy, minimax, plans, elapsed);
        std::cout << result.dump() << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "BrokenTriangleGame pilot failed: " << error.what() << '\n';
        return 1;
    }
}
