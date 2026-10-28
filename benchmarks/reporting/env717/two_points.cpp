#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_feedback.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <compare>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
namespace feedback = csl::reachability::finite_feedback;
using Json = nlohmann::json;

struct LatticeState {
    std::int64_t p1, v1, p2, v2;
    auto operator<=>(const LatticeState&) const = default;
};

std::int64_t checked_add(std::int64_t left, std::int64_t right) {
    if((right > 0 && left > std::numeric_limits<std::int64_t>::max() - right) ||
       (right < 0 && left < std::numeric_limits<std::int64_t>::min() - right))
        throw std::runtime_error("feedback lattice addition overflow");
    return left + right;
}

std::int64_t checked_mul(std::int64_t left, std::int64_t right) {
    if(left == 0 || right == 0) return 0;
    if((left == -1 && right == std::numeric_limits<std::int64_t>::min()) ||
       (right == -1 && left == std::numeric_limits<std::int64_t>::min()))
        throw std::runtime_error("feedback lattice multiplication overflow");
    if((left > 0 && right > 0 && left > std::numeric_limits<std::int64_t>::max() / right) ||
       (left > 0 && right < 0 && right < std::numeric_limits<std::int64_t>::min() / left) ||
       (left < 0 && right > 0 && left < std::numeric_limits<std::int64_t>::min() / right) ||
       (left < 0 && right < 0 && left < std::numeric_limits<std::int64_t>::max() / right))
        throw std::runtime_error("feedback lattice multiplication overflow");
    return left * right;
}

std::int64_t exact_div(std::int64_t value, std::int64_t divisor) {
    if(value % divisor != 0) throw std::runtime_error("feedback lattice division is not integral");
    return value / divisor;
}

LatticeState advance_lattice(const LatticeState& s, int action, int disturbance) {
    const auto p1_delta = exact_div(s.v1, 100);
    const auto p2_delta = exact_div(s.v2, 10);
    return {checked_add(checked_add(s.p1, p1_delta), checked_mul(450, action)),
            checked_mul(5000, action),
            checked_add(checked_add(s.p2, p2_delta), checked_mul(9, disturbance)),
            checked_add(s.v2, checked_mul(200, disturbance))};
}

std::int64_t gap_numerator(const LatticeState& state) {
    const auto gap = checked_add(state.p1, checked_mul(-1, state.p2));
    return checked_mul(gap, gap);
}

struct FeedbackOutput { Json record; };

FeedbackOutput feedback_result() {
    constexpr std::array<int, 3> codes{-1, 0, 1};
    std::array<std::vector<LatticeState>, 4> layers;
    layers[0] = {{9000, 0, 0, 0}};
    for(std::size_t t = 0; t < 3; ++t) {
        std::vector<LatticeState> next;
        for(const auto& state : layers[t])
            for(const int a : codes) for(const int d : codes)
                next.push_back(advance_lattice(state, a, d));
        std::sort(next.begin(), next.end());
        next.erase(std::unique(next.begin(), next.end()), next.end());
        layers[t + 1] = std::move(next);
    }
    std::size_t padded_count = 0;
    for(const auto& layer : layers) padded_count = std::max(padded_count, layer.size());
    std::array<std::map<LatticeState, std::size_t>, 4> indices;
    for(std::size_t t = 0; t < layers.size(); ++t)
        for(std::size_t i = 0; i < layers[t].size(); ++i) indices[t].emplace(layers[t][i], i);

    std::vector<bool> terminal_safe(padded_count, false);
    std::fill_n(terminal_safe.begin(), layers[3].size(), true);
    feedback::Game game{padded_count, {}, std::move(terminal_safe),
                        std::vector<bool>(padded_count, false)};
    Json transition_json = Json::array();
    double max_euler_discrepancy = 0.0;
    std::vector<std::int64_t> candidates;
    for(const auto& state : layers[3]) candidates.push_back(gap_numerator(state));
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());

    for(std::size_t t = 0; t < 3; ++t) {
        feedback::Stage stage{std::vector<bool>(padded_count, false), 3, 3, {}};
        std::fill_n(stage.safe_states.begin(), layers[t].size(), true);
        stage.next_state.resize(padded_count);
        Json stage_json = Json::array();
        for(std::size_t i = 0; i < padded_count; ++i) {
            stage.next_state[i].resize(3);
            Json state_json = Json::array();
            for(std::size_t ai = 0; ai < 3; ++ai) {
                stage.next_state[i][ai].resize(3);
                Json action_json = Json::array();
                for(std::size_t di = 0; di < 3; ++di) {
                    const auto next_padding = layers[t + 1].size() < padded_count
                        ? layers[t + 1].size() : std::size_t{0};
                    const auto dest = i < layers[t].size()
                        ? indices[t + 1].at(advance_lattice(layers[t][i], codes[ai], codes[di]))
                        : next_padding;
                    if(i < layers[t].size() && dest >= layers[t + 1].size())
                        throw std::runtime_error("real feedback transition targets padding");
                    stage.next_state[i][ai][di] = {dest};
                    action_json.push_back(dest);
                    if(i < layers[t].size()) {
                        const auto& s = layers[t][i];
                        double p1 = static_cast<double>(s.p1) / 2000.0;
                        double v1 = static_cast<double>(s.v1) / 2000.0;
                        double p2 = static_cast<double>(s.p2) / 2000.0;
                        double v2 = static_cast<double>(s.v2) / 2000.0;
                        const double u = 2.5 * codes[ai], disturbance = codes[di];
                        for(int step = 0; step < 10; ++step) {
                            p1 += 0.01 * v1;
                            v1 += 0.01 * (-100.0 * v1 + 100.0 * u);
                            p2 += 0.01 * v2;
                            v2 += 0.01 * disturbance;
                        }
                        const auto& target = layers[t + 1][dest];
                        const std::array<double, 4> float_target{p1, v1, p2, v2};
                        const std::array<double, 4> exact_target{
                            target.p1 / 2000.0, target.v1 / 2000.0,
                            target.p2 / 2000.0, target.v2 / 2000.0};
                        for(std::size_t coordinate = 0; coordinate < 4; ++coordinate)
                            max_euler_discrepancy = std::max(max_euler_discrepancy,
                                std::abs(float_target[coordinate] - exact_target[coordinate]));
                    }
                }
                state_json.push_back(std::move(action_json));
            }
            stage_json.push_back(std::move(state_json));
        }
        transition_json.push_back(std::move(stage_json));
        game.stages.push_back(std::move(stage));
    }

    std::optional<feedback::Policy> selected;
    std::int64_t chosen = 0;
    std::size_t solves = 0;
    for(const auto candidate : candidates) {
        game.terminal_target.assign(padded_count, false);
        for(std::size_t i = 0; i < layers[3].size(); ++i)
            game.terminal_target[i] = gap_numerator(layers[3][i]) <= candidate;
        const auto outcome = feedback::solve(game);
        ++solves;
        const auto* policy = std::get_if<feedback::Policy>(&outcome);
        if(!policy) throw std::runtime_error("finite_feedback rejected generated graph");
        if(policy->winning[0][0]) { selected = *policy; chosen = candidate; break; }
    }
    if(!selected) throw std::runtime_error("no feedback threshold reaches initial state");

    Json layer_json = Json::array();
    for(const auto& layer : layers) {
        Json states = Json::array();
        for(const auto& s : layer) states.push_back({s.p1, s.v1, s.p2, s.v2});
        layer_json.push_back(std::move(states));
    }
    Json winning_json = Json::array(), actions_json = Json::array(), safe_json = Json::array();
    Json terminal_safe_json = Json::array();
    for(const bool safe : game.terminal_safe) terminal_safe_json.push_back(safe);
    for(const auto& stage : game.stages) {
        Json mask = Json::array();
        for(const bool safe : stage.safe_states) mask.push_back(safe);
        safe_json.push_back(std::move(mask));
    }
    for(std::size_t t = 0; t < selected->winning.size(); ++t) {
        Json wins = Json::array();
        for(std::size_t i = 0; i < padded_count; ++i)
            wins.push_back(selected->winning[t][i]);
        winning_json.push_back(std::move(wins));
    }
    for(std::size_t t = 0; t < selected->admissible_actions.size(); ++t) {
        Json actions = Json::array();
        for(std::size_t i = 0; i < padded_count; ++i) {
            Json cell = Json::array();
            for(const auto a : selected->admissible_actions[t][i])
                cell.push_back(static_cast<int>(a.value) - 1);
            actions.push_back(std::move(cell));
        }
        actions_json.push_back(std::move(actions));
    }
    Json result{{"scale", 2000}, {"layer_states", layer_json},
        {"padded_state_count", padded_count}, {"candidate_count", candidates.size()},
        {"solve_count", solves}, {"threshold_numerator", chosen},
        {"threshold_denominator", 4000000}, {"winning", winning_json},
        {"stage_safe_masks", safe_json}, {"terminal_safe_mask", terminal_safe_json},
        {"transition_table", transition_json},
        {"euler_crosscheck_tolerance", 1e-10},
        {"euler_max_abs_discrepancy", max_euler_discrepancy},
        {"admissible_action_codes", actions_json},
        {"action_codes", {-1, 0, 1}}, {"disturbance_codes", {-1, 0, 1}},
        {"information_pattern", "action selected from current exact state before disturbance vertex"},
        {"solver", "csl.reachability.finite_feedback.solve"},
        {"selector", "first admissible action in authored code order; feasible, not cost-optimal"}};
    std::int64_t worst_terminal = -1;
    std::vector<LatticeState> worst_path;
    std::vector<int> worst_actions, worst_disturbances;
    std::function<void(std::size_t, std::size_t, std::vector<LatticeState>,
                       std::vector<int>, std::vector<int>)> visit;
    visit = [&](std::size_t t, std::size_t index, std::vector<LatticeState> path,
                std::vector<int> actions, std::vector<int> disturbances) {
        const auto& current = layers[t][index];
        if(t == 3) {
            const auto value = gap_numerator(current);
            if(value > worst_terminal || (value == worst_terminal && disturbances < worst_disturbances)) {
                worst_terminal = value; worst_path = std::move(path);
                worst_actions = std::move(actions); worst_disturbances = std::move(disturbances);
            }
            return;
        }
        const auto& feasible = selected->admissible_actions[t][index];
        if(feasible.empty()) throw std::runtime_error("winning feedback state has no action");
        const int action = static_cast<int>(feasible.front().value) - 1;
        for(const int disturbance : codes) {
            const auto next = advance_lattice(current, action, disturbance);
            auto next_path = path; next_path.push_back(next);
            auto next_actions = actions; next_actions.push_back(action);
            auto next_disturbances = disturbances; next_disturbances.push_back(disturbance);
            visit(t + 1, indices[t + 1].at(next), std::move(next_path),
                  std::move(next_actions), std::move(next_disturbances));
        }
    };
    visit(0, 0, {layers[0][0]}, {}, {});
    Json trajectory = Json::array(), action_path = Json::array(), disturbance_path = Json::array();
    for(const auto& state : worst_path) trajectory.push_back({state.p1, state.v1, state.p2, state.v2});
    for(const auto action : worst_actions) action_path.push_back(action);
    for(const auto disturbance : worst_disturbances) disturbance_path.push_back(disturbance);
    result["selected_actions"] = std::move(action_path);
    result["worst_case_disturbances"] = std::move(disturbance_path);
    result["worst_terminal_gap_numerator"] = worst_terminal;
    result["worst_case_states"] = std::move(trajectory);
    return {std::move(result)};
}

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(points))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 3;
    const SystemModel authored{{{4, 1, 1}, TimeDomain::discrete,
        LinearStage{{4, 4, {1.0, 0.01, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 1.0, 0.1,
                            0.0, 0.0, 0.0, 1.0}},
                    {4, 1, {0.09, 1.0, 0.0, 0.0}},
                    {4, 1, {0.0, 0.0, 0.0045, 0.1}},
                    {0.0, 0.0, 0.0, 0.0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{0.0, 0.1, 0.2, 0.3}));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("point2-acceleration-catalogue", 1, Matrix{3, 1, {-1.0, 0.0, 1.0}}));
    std::vector<sets::SetData> safe;
    safe.reserve(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"two-points-unconstrained-" + std::to_string(stage)}, 4, {}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        {4, 4, {2.0, 0.0, -2.0, 0.0,
                0.0, 0.0, 0.0, 0.0,
                -2.0, 0.0, 2.0, 0.0,
                0.0, 0.0, 0.0, 0.0}},
        {0.0, 0.0, 0.0, 0.0}, 0.0}));
    return {{"env717-two-points-short-horizon-v1"}, {"env717-two-points"},
        system, vertices("two-points-initial", 4, Matrix{1, 4, {4.5, 0.0, 0.0, 0.0}}),
        {1, {{-2.5}, {0.0}, {2.5}}}, std::move(disturbances), std::move(safe), objective};
}

Json result_record() {
    constexpr std::array<double, 3> controls{-2.5, 0.0, 2.5};
    constexpr double tolerance = 1e-12;
    const auto input = request();
    std::vector<std::int64_t> measured_ns;
    FiniteActionMinimaxOutcome outcome;
    for(std::size_t repetition = 0; repetition <= 7; ++repetition) {
        const auto started = std::chrono::steady_clock::now();
        outcome = finite_action_minimax(input, {27, 27, tolerance});
        const auto stopped = std::chrono::steady_clock::now();
        if(repetition > 0)
            measured_ns.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(
                stopped - started).count());
    }
    const auto* result = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!result) throw std::runtime_error("finite-action minimax did not return an optimum");
    if(result->plans.size() != 27 || result->minimizing_plan_indices.empty())
        throw std::runtime_error("unexpected exhaustive action catalogue");

    Json plans = Json::array();
    for(std::size_t index = 0; index < result->plans.size(); ++index) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&result->plans[index]);
        if(!plan) throw std::runtime_error("unconstrained game rejected a control plan");
        Json values = Json::array();
        for(const auto action_index : plan->action_indices) {
            if(action_index >= controls.size()) throw std::runtime_error("invalid control index");
            values.push_back(controls[action_index]);
        }
        plans.push_back({{"plan_index", index}, {"controls", std::move(values)},
            {"worst_terminal_squared_gap", plan->worst_value},
            {"maximizing_terminal_state", plan->maximizer}});
    }
    Json minimizing = Json::array();
    for(const auto index : result->minimizing_plan_indices) minimizing.push_back(index);
    auto ordered_ns = measured_ns;
    std::sort(ordered_ns.begin(), ordered_ns.end());
    Json record{{"schema", "csl.env717-two-points-feedback/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "4e71bed8ceffa1990645fb85e54d6b5b1eeb688d"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"position_1", "velocity_1", "position_2", "velocity_2"}},
        {"source_model", {{"initial_state", {4.5, 0.0, 0.0, 0.0}},
            {"alpha", 1.0}, {"m1", 0.01}, {"m2", 1.0},
            {"dt_seconds", 0.1}, {"inner_euler_steps", 10},
            {"source_horizon_seconds", 10.0}, {"u_bounds", {-2.5, 2.5}},
            {"v_bounds", {-1.0, 1.0}},
            {"reward", "negative absolute terminal position gap"}}},
        {"adaptation", {{"horizon_steps", 3}, {"terminal_time_seconds", 0.3},
            {"u_catalogue", {-2.5, 0.0, 2.5}}, {"v_catalogue", {-1.0, 0.0, 1.0}},
            {"information_pattern", "open-loop control sequence; adversary chooses a full disturbance sequence"},
            {"objective", "minimize maximum terminal squared position gap; monotone-equivalent to source absolute-gap reward"},
            {"safe_state", "unbounded four-dimensional state"},
            {"discrete_stage_map", "p1+=0.01*v1+0.09*u; v1+=u; p2+=0.1*v2+0.0045*v; v2+=0.1*v"}}},
        {"algorithm", "csl.finite-action-minimax.numerical"},
        {"assurance", "numerical; exhaustive over all 27 fixed control plans and 27 disturbance sequences per plan"},
        {"environment", {{"compiler_id", CSL_ENV717_COMPILER_ID},
            {"compiler_version", CSL_ENV717_COMPILER_VERSION},
            {"build_type", CSL_ENV717_BUILD_TYPE},
            {"architecture", CSL_ENV717_ARCHITECTURE}, {"requested_workers", 1},
            {"solver_parallelism", "single-threaded"}}},
        {"objective_value", result->value}, {"worst_terminal_gap", std::sqrt(result->value)},
        {"minimizing_plan_indices", std::move(minimizing)}, {"plan_count", result->plans.size()},
        {"plans", std::move(plans)}, {"near_optimal_tolerance", tolerance},
        {"timing", {{"scope", "finite_action_minimax call; request setup and JSON output excluded"},
            {"warmup_calls", 1}, {"measured_calls", measured_ns.size()},
            {"measured_wall_ns", measured_ns}, {"median_wall_ns", ordered_ns[3]},
            {"min_wall_ns", ordered_ns.front()}, {"max_wall_ns", ordered_ns.back()},
            {"limiter_profile", "not collected; no comparative speed claim"}}},
        {"driver_sha256", CSL_ENV717_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_SOURCE_COMMIT}};
    record["feedback"] = feedback_result().record;
    return record;
}
}

int main() {
    try {
        std::cout << result_record().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "two-points pilot failed: " << error.what() << '\n';
        return 2;
    }
}
