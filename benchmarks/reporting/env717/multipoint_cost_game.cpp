#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/finite_causal_minimax.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;
namespace causal = finite_causal_minimax;

constexpr std::size_t state_n = 2;
constexpr std::size_t horizon = 4;
constexpr std::size_t inner_n = 50;
constexpr double inner_dt = 0.02;
constexpr std::array<double, 3> actions{-1.0, 0.0, 1.0};
constexpr double tie_tolerance = 1e-10;
using State = std::array<double, state_n>; // position, velocity
using Matrix2 = std::array<double, 4>;
struct StageMap { Matrix2 A; State B; State E; };
using Key = std::tuple<std::uint64_t, std::uint64_t>;

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

Key key(const State& state) {
    return {std::bit_cast<std::uint64_t>(state[0]),
            std::bit_cast<std::uint64_t>(state[1])};
}

State source_transition(State state, double stage_time, double u, double disturbance) {
    double time = stage_time;
    for(std::size_t i = 0; i < inner_n; ++i) {
        const double old_time = time;
        const double old_position = state[0];
        const double old_velocity = state[1];
        time += inner_dt;
        state[0] = old_position + old_velocity * inner_dt;
        state[1] = old_velocity +
            (3.0 * u + (old_time - 2.0) * (old_time - 2.0) * disturbance) * inner_dt;
    }
    return state;
}

StageMap source_linear_map(double stage_time) {
    Matrix2 A{1.0, 0.0, 0.0, 1.0};
    State B{}, E{};
    double time = stage_time;
    for(std::size_t i = 0; i < inner_n; ++i) {
        const Matrix2 step{1.0, inner_dt, 0.0, 1.0};
        const State old_B = B, old_E = E;
        B = {old_B[0] + inner_dt * old_B[1],
             old_B[1] + 3.0 * inner_dt};
        E = {old_E[0] + inner_dt * old_E[1],
             old_E[1] + (time - 2.0) * (time - 2.0) * inner_dt};
        A = {step[0] * A[0] + step[1] * A[2],
             step[0] * A[1] + step[1] * A[3],
             A[2], A[3]};
        time += inner_dt;
    }
    return {A, B, E};
}

sets::SetData vertices(std::string id, Matrix rows) {
    const auto dimension = rows.cols;
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(rows))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

struct GameData {
    std::vector<StageMap> maps;
    causal::Game feedback;
    std::vector<std::vector<State>> layers;
};

GameData make_feedback_game() {
    GameData data;
    data.maps.reserve(horizon);
    data.layers.resize(horizon + 1);
    data.layers[0].push_back({0.0, 1.0});
    std::vector<causal::Stage> stages;
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        const auto map = source_linear_map(static_cast<double>(stage));
        data.maps.push_back(map);
        std::map<Key, std::size_t> next_ids;
        causal::Stage layer{data.layers[stage].size(), actions.size(), actions.size(), {}, {}};
        layer.safe_states.assign(layer.state_count, true);
        layer.next_state.resize(layer.state_count);
        for(std::size_t state_id = 0; state_id < layer.state_count; ++state_id) {
            layer.next_state[state_id].resize(actions.size());
            for(std::size_t u_id = 0; u_id < actions.size(); ++u_id) {
                auto& destinations = layer.next_state[state_id][u_id];
                destinations.reserve(actions.size());
                for(const double disturbance : actions) {
                    const auto next = source_transition(data.layers[stage][state_id],
                        static_cast<double>(stage), actions[u_id], disturbance);
                    const auto [found, inserted] = next_ids.emplace(key(next), next_ids.size());
                    if(inserted) data.layers[stage + 1].push_back(next);
                    destinations.push_back(causal::StateId{found->second});
                }
            }
        }
        stages.push_back(std::move(layer));
    }
    causal::Terminal terminal{data.layers.back().size(), {}, {}};
    terminal.safe_states.assign(terminal.state_count, true);
    for(const auto& state : data.layers.back())
        terminal.cost.push_back(state[0] * state[0] + state[1] * state[1]);
    data.feedback = {std::move(stages), std::move(terminal), causal::StateId{0}};
    return data;
}

FiniteActionMinimaxRequest make_open_loop_request(const std::vector<StageMap>& maps) {
    std::vector<LinearStage> dynamics;
    std::vector<double> times{0.0};
    for(std::size_t i = 0; i < maps.size(); ++i) {
        const auto& map = maps[i];
        dynamics.push_back({Matrix{state_n, state_n,
                {map.A[0], map.A[1], map.A[2], map.A[3]}},
            Matrix{state_n, 1, {map.B[0], map.B[1]}},
            Matrix{state_n, 1, {map.E[0], map.E[1]}}, Vector(state_n, 0.0)});
        times.push_back(static_cast<double>(i + 1));
    }
    const SystemModel authored{{{state_n, 1, 1}, TimeDomain::discrete,
        std::move(dynamics)}, {}};
    const auto system = take(model::snapshot(authored, times));
    std::vector<Vector> controls;
    std::vector<double> disturbance_rows;
    for(const double action : actions) controls.push_back({action});
    for(const double disturbance : actions) disturbance_rows.push_back(disturbance);
    std::vector<sets::SetData> disturbances;
    for(std::size_t i = 0; i < horizon; ++i)
        disturbances.push_back(vertices("multipoint-disturbances-" + std::to_string(i),
            Matrix{actions.size(), 1, disturbance_rows}));
    std::vector<sets::SetData> admissible;
    for(std::size_t i = 0; i <= horizon; ++i)
        admissible.push_back(take(sets::make_universal(
            {{"multipoint-unconstrained-" + std::to_string(i)}, state_n, {}})));
    const auto objective = std::get<Objective>(snapshot(
        QuadraticTerminal{Matrix{state_n, state_n, {2.0, 0.0, 0.0, 2.0}},
                          Vector(state_n, 0.0), 0.0}));
    return {{"env717-multipoint-terminal-v1"}, {"env717-multipoint-cost-game"}, system,
        vertices("multipoint-initial", Matrix{1, state_n, {0.0, 1.0}}),
        {1, std::move(controls)}, std::move(disturbances), std::move(admissible), objective};
}

FiniteMinimaxOptimal solve_open(const FiniteActionMinimaxRequest& request) {
    auto outcome = finite_action_minimax(request, {81, 81, tie_tolerance});
    const auto* optimum = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!optimum || optimum->plans.size() != 81 || optimum->minimizing_plan_indices.empty())
        throw std::runtime_error("open-loop finite-action minimax did not enumerate all plans");
    return *optimum;
}

causal::Result solve_feedback(const causal::Game& game) {
    auto outcome = causal::solve(game, {tie_tolerance, tie_tolerance});
    const auto* result = std::get_if<causal::Result>(&outcome);
    if(!result || !result->initial().feasible || result->values_by_stage.size() != horizon + 1)
        throw std::runtime_error("finite causal minimax returned no complete initial value");
    return *result;
}

Json state_json(const State& state) { return Json::array({state[0], state[1]}); }

Json feedback_record(const causal::Result& result, const GameData& game) {
    Json values = Json::array();
    for(std::size_t stage = 0; stage < result.values_by_stage.size(); ++stage) {
        Json layer = Json::array();
        for(std::size_t id = 0; id < result.values_by_stage[stage].size(); ++id) {
            const auto& value = result.values_by_stage[stage][id];
            Json actions_json = Json::array();
            for(const auto action : value.optimal_actions) actions_json.push_back(action.value);
            layer.push_back({{"state_id", id}, {"state", state_json(game.layers[stage][id])},
                {"feasible", value.feasible}, {"value", value.value},
                {"optimal_action_indices", std::move(actions_json)}});
        }
        values.push_back(std::move(layer));
    }
    return values;
}

Json open_record(const FiniteMinimaxOptimal& result) {
    Json plans = Json::array();
    for(std::size_t i = 0; i < result.plans.size(); ++i) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&result.plans[i]);
        if(!plan || plan->action_indices.size() != horizon || plan->evaluated_vertices != 81)
            throw std::runtime_error("open-loop plan evidence is incomplete");
        plans.push_back({{"plan_index", i}, {"control_indices", plan->action_indices},
            {"worst_terminal_cost", plan->worst_value},
            {"maximizing_terminal_state", plan->maximizer}});
    }
    return {{"value", result.value}, {"minimizing_plan_indices", result.minimizing_plan_indices},
        {"plans", std::move(plans)}};
}

Json record(const GameData& game, const FiniteMinimaxOptimal& open,
            const causal::Result& feedback, const std::vector<std::int64_t>& open_ns,
            const std::vector<std::int64_t>& feedback_ns) {
    Json maps = Json::array(), u = Json::array();
    for(const auto& map : game.maps)
        maps.push_back({{"A", {{map.A[0], map.A[1]}, {map.A[2], map.A[3]}}},
            {"B", map.B}, {"E", map.E}});
    for(const auto action : actions) u.push_back(action);
    return {{"schema", "csl.env717-multipoint-terminal-pilot/1"},
        {"environment", "MultiPointCostGame"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "baf126c2074c865f3a758abbaade73686a1dc4bc"},
        {"source_license", "no license declared in repository metadata"},
        {"source_state_order", {"time", "position", "velocity"}},
        {"source_initial_state", {0.0, 0.0, 1.0}}, {"source_terminal_time", 4.0},
        {"source_outer_step", 0.1}, {"source_inner_euler_steps", 5},
        {"source_dynamics", "time'=1; position'=velocity; velocity'=3u+(time-2)^2 v_disturbance"},
        {"source_rewards", {{"t=1", "(position-1)^2"},
            {"t=3", "(position+1)^2"}, {"terminal", "position^2+velocity^2"}}},
        {"adaptation", {{"horizon_steps", horizon}, {"decision_period_seconds", 1.0},
            {"inner_euler_steps_per_decision", inner_n}, {"control_catalogue", u},
            {"disturbance_catalogue", u},
            {"information_pattern", "open-loop fixed control plan versus exact-state causal feedback; disturbance follows each control"},
            {"objective", "minimize the worst terminal squared position-plus-velocity cost"},
            {"excluded_source_terms", "intermediate checkpoint rewards at t=1 and t=3 are not included in this terminal-only variant"},
            {"source_integration", "four one-second held-action blocks, each composed from 50 source explicit-Euler updates at dt=0.02"}}},
        {"stage_maps", maps},
        {"open_loop", open_record(open)},
        {"feedback", {{"value", feedback.initial().value},
            {"optimal_initial_action_indices", [&] { Json a = Json::array(); for(auto x : feedback.initial().optimal_actions) a.push_back(x.value); return a; }()},
            {"values_by_stage", feedback_record(feedback, game)}}},
        {"timing", {{"warmup_calls_per_method", 1}, {"measured_calls_per_method", 7},
            {"open_loop_wall_ns", open_ns}, {"feedback_wall_ns", feedback_ns},
            {"scope", "algorithm solve only; source map/state graph construction and verification excluded"},
            {"order", "seven measured rounds alternate open-loop/feedback and feedback/open-loop"},
            {"performance_claim", false}, {"worker_threads_requested", 1},
            {"native_threads_requested", 1}, {"workspace_reuse", "none"}}},
        {"driver_sha256", CSL_ENV717_MULTIPOINT_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_MULTIPOINT_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_MULTIPOINT_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_MULTIPOINT_COMPILER_ID},
            {"compiler_version", CSL_ENV717_MULTIPOINT_COMPILER_VERSION},
            {"build_type", CSL_ENV717_MULTIPOINT_BUILD_TYPE},
            {"architecture", CSL_ENV717_MULTIPOINT_ARCHITECTURE}}}};
}

} // namespace

int main() {
    try {
        auto game = make_feedback_game();
        const auto request = make_open_loop_request(game.maps);
        (void)solve_open(request);
        (void)solve_feedback(game.feedback);
        std::vector<std::int64_t> open_ns, feedback_ns;
        open_ns.reserve(7);
        feedback_ns.reserve(7);
        FiniteMinimaxOptimal open;
        causal::Result feedback;
        for(std::size_t round = 0; round < 7; ++round) {
            auto run_open = [&] {
                const auto start = std::chrono::steady_clock::now();
                open = solve_open(request);
                const auto stop = std::chrono::steady_clock::now();
                open_ns.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count());
            };
            auto run_feedback = [&] {
                const auto start = std::chrono::steady_clock::now();
                feedback = solve_feedback(game.feedback);
                const auto stop = std::chrono::steady_clock::now();
                feedback_ns.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count());
            };
            if(round % 2 == 0) { run_open(); run_feedback(); }
            else { run_feedback(); run_open(); }
        }
        std::cout << record(game, open, feedback, open_ns, feedback_ns).dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "ENV-717 MultiPointCostGame pilot failed: " << error.what() << '\n';
        return 1;
    }
}
