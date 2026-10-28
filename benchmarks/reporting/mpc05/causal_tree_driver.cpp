#include <Highs.h>
#include <csl/optimization/finite_causal_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace {
using Game = csl::optimization::finite_causal_minimax::Game;
using StateId = csl::optimization::finite_causal_minimax::StateId;
using ActionId = csl::optimization::finite_causal_minimax::ActionId;
using Stage = csl::optimization::finite_causal_minimax::Stage;
using nlohmann::json;

void add_row(HighsLp& lp, const std::map<HighsInt, double>& coefficients,
             double lower, double upper) {
    for(const auto& [column, value] : coefficients) {
        lp.a_matrix_.index_.push_back(column);
        lp.a_matrix_.value_.push_back(value);
    }
    lp.a_matrix_.start_.push_back(static_cast<HighsInt>(lp.a_matrix_.index_.size()));
    lp.row_lower_.push_back(lower);
    lp.row_upper_.push_back(upper);
}

struct Occurrence {
    std::size_t stage;
    std::size_t state;
    std::vector<std::vector<std::size_t>> children;
};

struct TreeResult {
    bool optimal;
    double objective;
    double bound;
    double gap;
    double replayed_worst_cost;
    std::size_t decision_occurrences;
    std::size_t leaves;
    std::size_t nonanticipativity_equalities;
    std::vector<std::vector<int>> policy;
};

std::vector<Occurrence> expand_tree(const Game& game) {
    std::vector<Occurrence> occurrences{{0, game.initial_state.value, {}}};
    for(std::size_t index = 0; index < occurrences.size(); ++index) {
        const auto stage_index = occurrences[index].stage;
        if(stage_index == game.stages.size()) continue;
        const auto state = occurrences[index].state;
        const auto& stage = game.stages[stage_index];
        std::vector<std::vector<std::size_t>> children(
            stage.action_count, std::vector<std::size_t>(stage.disturbance_count));
        for(std::size_t action = 0; action < stage.action_count; ++action) {
            for(std::size_t disturbance = 0; disturbance < stage.disturbance_count; ++disturbance) {
                const auto next_state = stage.next_state[state][action][disturbance].value;
                children[action][disturbance] = occurrences.size();
                occurrences.push_back({stage_index + 1, next_state, {}});
            }
        }
        occurrences[index].children = std::move(children);
    }
    return occurrences;
}

double replay_worst(const Game& game, const std::vector<std::vector<int>>& policy,
                    std::size_t stage, std::size_t state) {
    if(stage == game.stages.size()) {
        if(!game.terminal.safe_states[state]) return std::numeric_limits<double>::infinity();
        return game.terminal.cost[state];
    }
    const auto& current = game.stages[stage];
    if(!current.safe_states[state]) return std::numeric_limits<double>::infinity();
    const int action = policy[stage][state];
    if(action < 0 || static_cast<std::size_t>(action) >= current.action_count)
        throw std::runtime_error("tree optimizer policy omitted a reachable state action");
    double worst = -std::numeric_limits<double>::infinity();
    for(const StateId next : current.next_state[state][static_cast<std::size_t>(action)])
        worst = std::max(worst, replay_worst(game, policy, stage + 1, next.value));
    return worst;
}

struct FixedPlan {
    double value;
    std::vector<std::size_t> actions;
};

FixedPlan best_fixed_plan(const Game& game, std::size_t start_stage, std::size_t start_state) {
    if(start_stage == game.stages.size())
        return {game.terminal.safe_states[start_state] ? game.terminal.cost[start_state]
                                                       : std::numeric_limits<double>::infinity(), {}};
    if(!game.stages[start_stage].safe_states[start_state])
        return {std::numeric_limits<double>::infinity(), {}};
    double best = std::numeric_limits<double>::infinity();
    std::vector<std::size_t> plan(game.stages.size() - start_stage);
    std::function<double(std::size_t, std::size_t)> worst_for_plan;
    worst_for_plan = [&](std::size_t stage_index, std::size_t state) {
        if(stage_index == game.stages.size())
            return game.terminal.safe_states[state]
                ? game.terminal.cost[state] : std::numeric_limits<double>::infinity();
        const auto& stage = game.stages[stage_index];
        if(!stage.safe_states[state]) return std::numeric_limits<double>::infinity();
        double worst = -std::numeric_limits<double>::infinity();
        for(const StateId next : stage.next_state[state][plan[stage_index - start_stage]])
            worst = std::max(worst, worst_for_plan(stage_index + 1, next.value));
        return worst;
    };
    std::vector<std::size_t> best_plan;
    std::function<void(std::size_t)> enumerate_plans;
    enumerate_plans = [&](std::size_t stage_index) {
        if(stage_index == game.stages.size()) {
            const double candidate = worst_for_plan(start_stage, start_state);
            if(candidate < best) {
                best = candidate;
                best_plan = plan;
            }
            return;
        }
        for(std::size_t action = 0; action < game.stages[stage_index].action_count; ++action) {
            plan[stage_index - start_stage] = action;
            enumerate_plans(stage_index + 1);
        }
    };
    enumerate_plans(start_stage);
    return {best, std::move(best_plan)};
}

double fixed_plan_value(const Game& game) {
    return best_fixed_plan(game, 0, game.initial_state.value).value;
}

double executed_replanning_value(const Game& game, std::size_t stage, std::size_t state,
                                std::map<std::pair<std::size_t, std::size_t>, double>& memo) {
    if(stage == game.stages.size())
        return game.terminal.safe_states[state] ? game.terminal.cost[state]
                                                : std::numeric_limits<double>::infinity();
    const auto key = std::pair{stage, state};
    if(const auto found = memo.find(key); found != memo.end()) return found->second;
    const auto plan = best_fixed_plan(game, stage, state);
    if(plan.actions.empty() || !std::isfinite(plan.value))
        return memo[key] = std::numeric_limits<double>::infinity();
    const auto& stage_model = game.stages[stage];
    double worst = -std::numeric_limits<double>::infinity();
    for(const StateId next : stage_model.next_state[state][plan.actions.front()])
        worst = std::max(worst, executed_replanning_value(game, stage + 1, next.value, memo));
    return memo[key] = worst;
}

std::pair<double, std::vector<std::vector<int>>> executed_replanning_policy(const Game& game) {
    std::vector<std::vector<int>> policy(game.stages.size());
    for(std::size_t stage = 0; stage < game.stages.size(); ++stage) {
        policy[stage].resize(game.stages[stage].state_count, -1);
        for(std::size_t state = 0; state < game.stages[stage].state_count; ++state) {
            const auto plan = best_fixed_plan(game, stage, state);
            if(!plan.actions.empty() && std::isfinite(plan.value))
                policy[stage][state] = static_cast<int>(plan.actions.front());
        }
    }
    std::map<std::pair<std::size_t, std::size_t>, double> memo;
    return {executed_replanning_value(game, 0, game.initial_state.value, memo), std::move(policy)};
}

TreeResult solve_tree(const Game& game) {
    const auto occurrences = expand_tree(game);
    std::vector<std::vector<HighsInt>> action_columns(occurrences.size());
    std::vector<HighsInt> reached_columns(occurrences.size());
    HighsLp lp;
    lp.sense_ = ObjSense::kMinimize;
    lp.col_cost_.clear();
    lp.col_lower_.clear();
    lp.col_upper_.clear();
    lp.integrality_.clear();

    auto add_binary = [&](double lower, double upper) {
        const auto column = static_cast<HighsInt>(lp.col_cost_.size());
        lp.col_cost_.push_back(0.0);
        lp.col_lower_.push_back(lower);
        lp.col_upper_.push_back(upper);
        lp.integrality_.push_back(HighsVarType::kInteger);
        return column;
    };

    std::size_t decision_occurrences = 0;
    std::size_t leaves = 0;
    std::map<std::pair<std::size_t, std::size_t>, std::vector<std::size_t>> same_state;
    for(std::size_t node = 0; node < occurrences.size(); ++node) {
        const auto& occurrence = occurrences[node];
        reached_columns[node] = add_binary(0.0, 1.0);
        const bool terminal = occurrence.stage == game.stages.size();
        if(terminal) {
            ++leaves;
            if(!game.terminal.safe_states[occurrence.state]) lp.col_upper_[reached_columns[node]] = 0.0;
            continue;
        }
        ++decision_occurrences;
        const auto& stage = game.stages[occurrence.stage];
        action_columns[node].reserve(stage.action_count);
        for(std::size_t action = 0; action < stage.action_count; ++action)
            action_columns[node].push_back(add_binary(0.0, 1.0));
        if(!stage.safe_states[occurrence.state]) lp.col_upper_[reached_columns[node]] = 0.0;
        same_state[{occurrence.stage, occurrence.state}].push_back(node);
    }
    const double min_cost = *std::min_element(game.terminal.cost.begin(), game.terminal.cost.end());
    const double max_cost = *std::max_element(game.terminal.cost.begin(), game.terminal.cost.end());
    const double big_m = max_cost - min_cost;
    const auto epigraph = static_cast<HighsInt>(lp.col_cost_.size());
    lp.col_cost_.push_back(1.0);
    lp.col_lower_.push_back(min_cost);
    lp.col_upper_.push_back(max_cost);
    lp.integrality_.push_back(HighsVarType::kContinuous);

    lp.a_matrix_.format_ = MatrixFormat::kRowwise;
    lp.a_matrix_.start_ = {0};
    lp.num_col_ = static_cast<HighsInt>(lp.col_cost_.size());
    lp.a_matrix_.num_col_ = lp.num_col_;
    lp.a_matrix_.num_row_ = 0;

    lp.col_lower_[reached_columns[0]] = 1.0;
    lp.col_upper_[reached_columns[0]] = 1.0;
    for(std::size_t node = 0; node < occurrences.size(); ++node) {
        if(occurrences[node].stage == game.stages.size()) continue;
        std::map<HighsInt, double> exactly_one;
        for(const HighsInt column : action_columns[node]) exactly_one[column] = 1.0;
        add_row(lp, exactly_one, 1.0, 1.0);
        const auto& children = occurrences[node].children;
        for(std::size_t action = 0; action < children.size(); ++action) {
            for(const std::size_t child : children[action]) {
                const auto parent_reach = reached_columns[node];
                const auto selected_action = action_columns[node][action];
                const auto child_reach = reached_columns[child];
                add_row(lp, {{child_reach, 1.0}, {parent_reach, -1.0}}, -kHighsInf, 0.0);
                add_row(lp, {{child_reach, 1.0}, {selected_action, -1.0}}, -kHighsInf, 0.0);
                add_row(lp, {{child_reach, 1.0}, {parent_reach, -1.0},
                             {selected_action, -1.0}}, -1.0, kHighsInf);
            }
        }
    }

    std::size_t nonanticipativity_equalities = 0;
    for(const auto& [key, nodes] : same_state) {
        (void)key;
        if(nodes.size() < 2) continue;
        const auto representative = nodes.front();
        for(std::size_t occurrence = 1; occurrence < nodes.size(); ++occurrence) {
            const auto node = nodes[occurrence];
            for(std::size_t action = 0; action < action_columns[representative].size(); ++action) {
                add_row(lp, {{action_columns[node][action], 1.0},
                             {action_columns[representative][action], -1.0}}, 0.0, 0.0);
                ++nonanticipativity_equalities;
            }
        }
    }

    for(std::size_t node = 0; node < occurrences.size(); ++node) {
        const auto& occurrence = occurrences[node];
        if(occurrence.stage != game.stages.size()) continue;
        const double cost = game.terminal.cost[occurrence.state];
        add_row(lp, {{epigraph, 1.0}, {reached_columns[node], -big_m}},
                cost - big_m, kHighsInf);
    }
    lp.num_row_ = static_cast<HighsInt>(lp.row_lower_.size());
    lp.a_matrix_.num_row_ = lp.num_row_;

    Highs solver;
    solver.setOptionValue("output_flag", false);
    solver.setOptionValue("threads", 1);
    solver.setOptionValue("mip_rel_gap", 0.0);
    solver.setOptionValue("mip_abs_gap", 0.0);
    solver.setOptionValue("time_limit", 30.0);
    if(solver.passModel(lp) == HighsStatus::kError || solver.run() == HighsStatus::kError)
        throw std::runtime_error("HiGHS failed to run the causal extensive-form model");
    const auto status = solver.getModelStatus();
    if(status != HighsModelStatus::kOptimal) {
        if(status == HighsModelStatus::kInfeasible)
            return {false, 0.0, 0.0, 0.0, 0.0, decision_occurrences, leaves,
                    nonanticipativity_equalities, {}};
        throw std::runtime_error("HiGHS did not prove the causal extensive-form model optimal");
    }

    const auto& solution = solver.getSolution();
    const auto& info = solver.getInfo();
    if(solution.col_value.size() != lp.col_cost_.size() ||
       !std::isfinite(info.objective_function_value) ||
       !std::isfinite(info.mip_dual_bound) || !std::isfinite(info.mip_gap))
        throw std::runtime_error("HiGHS returned incomplete causal minimax evidence");
    std::vector<std::vector<int>> policy(game.stages.size());
    for(std::size_t t = 0; t < game.stages.size(); ++t)
        policy[t].assign(game.stages[t].state_count, -1);
    for(const auto& [key, nodes] : same_state) {
        const auto representative = nodes.front();
        int selected = -1;
        for(std::size_t action = 0; action < action_columns[representative].size(); ++action)
            if(solution.col_value[action_columns[representative][action]] > 0.5) {
                if(selected != -1) throw std::runtime_error("tree policy selects multiple actions");
                selected = static_cast<int>(action);
            }
        if(selected == -1) throw std::runtime_error("tree policy omitted a state action");
        for(const std::size_t node : nodes)
            for(std::size_t action = 0; action < action_columns[node].size(); ++action)
                if(std::abs(solution.col_value[action_columns[node][action]] -
                            (static_cast<int>(action) == selected ? 1.0 : 0.0)) > 1e-6)
                    throw std::runtime_error("explicit nonanticipativity equality failed in solver output");
        policy[key.first][key.second] = selected;
    }
    const double replayed = replay_worst(game, policy, 0, game.initial_state.value);
    if(std::abs(replayed - info.objective_function_value) > 1e-7)
        throw std::runtime_error("scenario-tree objective differs from independent policy replay");
    return {true, info.objective_function_value, info.mip_dual_bound, info.mip_gap,
            replayed, decision_occurrences, leaves, nonanticipativity_equalities,
            std::move(policy)};
}

json optimizer_json(const TreeResult& result) {
    json out = { {"status", result.optimal ? "optimal" : "infeasible"},
             {"solver", std::string("HiGHS ") + highsVersion()},
             {"objective", result.optimal ? json(result.objective) : json(nullptr)},
             {"global_bound", result.optimal ? json(result.bound) : json(nullptr)},
             {"relative_gap", result.optimal ? json(result.gap) : json(nullptr)},
             {"replayed_worst_cost", result.optimal ? json(result.replayed_worst_cost) : json(nullptr)},
             {"decision_occurrences", result.decision_occurrences}, {"leaf_occurrences", result.leaves},
             {"nonanticipativity_equalities", result.nonanticipativity_equalities} };
    if(result.optimal) out["policy"] = result.policy;
    return out;
}

using LatticeState = std::array<std::int64_t, 4>;

LatticeState two_points_step(const LatticeState& state, int action, int disturbance) {
    return {state[0] + state[1] / 100 + 450 * action,
            5000 * action,
            state[2] + state[3] / 10 + 9 * disturbance,
            state[3] + 200 * disturbance};
}

std::pair<Game, std::vector<std::vector<LatticeState>>> two_points_game() {
    constexpr std::array<int, 3> codes{-1, 0, 1};
    std::vector<std::vector<LatticeState>> layers(4);
    layers[0] = {{9000, 0, 0, 0}};
    for(std::size_t t = 0; t < 3; ++t) {
        std::set<LatticeState> next;
        for(const auto& state : layers[t])
            for(const int action : codes)
                for(const int disturbance : codes)
                    next.insert(two_points_step(state, action, disturbance));
        layers[t + 1].assign(next.begin(), next.end());
    }

    std::vector<Stage> stages;
    for(std::size_t t = 0; t < 3; ++t) {
        std::map<LatticeState, std::size_t> next_ids;
        for(std::size_t i = 0; i < layers[t + 1].size(); ++i)
            next_ids.emplace(layers[t + 1][i], i);
        Stage stage{layers[t].size(), codes.size(), codes.size(),
                    std::vector<bool>(layers[t].size(), true), {}};
        stage.next_state.resize(layers[t].size());
        for(std::size_t state = 0; state < layers[t].size(); ++state) {
            stage.next_state[state].resize(codes.size());
            for(std::size_t action = 0; action < codes.size(); ++action) {
                stage.next_state[state][action].reserve(codes.size());
                for(const int disturbance : codes) {
                    const auto next = two_points_step(layers[t][state], codes[action], disturbance);
                    stage.next_state[state][action].push_back(StateId{next_ids.at(next)});
                }
            }
        }
        stages.push_back(std::move(stage));
    }

    std::vector<double> costs;
    costs.reserve(layers.back().size());
    for(const auto& state : layers.back()) {
        const double gap = static_cast<double>(state[0] - state[2]) / 2000.0;
        costs.push_back(gap * gap);
    }
    return {{std::move(stages), {layers.back().size(), std::vector<bool>(layers.back().size(), true),
                                 std::move(costs)}, StateId{0}}, std::move(layers)};
}

json run_two_points() {
    using namespace csl::optimization::finite_causal_minimax;
    auto [game, layers] = two_points_game();
    const auto bellman = solve(game, {1e-12, 1e-12});
    if(!std::holds_alternative<Result>(bellman)) throw std::runtime_error("TwoPoints Bellman input rejected");
    const auto& reference = std::get<Result>(bellman);
    const auto tree = solve_tree(game);
    const double open_loop = fixed_plan_value(game);
    const auto [replanning_value, replanning_policy] = executed_replanning_policy(game);
    if(!tree.optimal || std::abs(tree.objective - reference.initial().value) > 1e-8 ||
       std::abs(tree.bound - reference.initial().value) > 1e-8 ||
       std::abs(tree.replayed_worst_cost - reference.initial().value) > 1e-8 ||
       std::abs(open_loop - 14.58094225) > 1e-8 ||
       std::abs(replanning_value - reference.initial().value) > 1e-8)
        throw std::runtime_error("TwoPoints Bellman/tree/open-loop values disagree with the source-derived finite case");
    json layer_counts = json::array(), states = json::array(), values = json::array();
    json optimal_actions = json::array();
    for(std::size_t t = 0; t < layers.size(); ++t) {
        layer_counts.push_back(layers[t].size());
        json layer = json::array(), layer_values = json::array(), layer_actions = json::array();
        for(std::size_t i = 0; i < layers[t].size(); ++i) {
            layer.push_back(layers[t][i]);
            layer_values.push_back(reference.values_by_stage[t][i].value);
            json actions = json::array();
            for(const auto action : reference.values_by_stage[t][i].optimal_actions)
                actions.push_back(action.value);
            layer_actions.push_back(std::move(actions));
        }
        states.push_back(std::move(layer));
        values.push_back(std::move(layer_values));
        optimal_actions.push_back(std::move(layer_actions));
    }
    return {{"source_repository", "imm-rl-lab/optimal_control"},
            {"source_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
            {"source_blob", "4e71bed8ceffa1990645fb85e54d6b5b1eeb688d"},
            {"source_task", "continuous controls over 10 seconds; not reproduced"},
            {"adaptation", "3-stage finite controls/disturbances; 0.3 seconds"},
            {"coordinates", "(x1,x2,x3,x4)=(position_1,velocity_1,position_2,velocity_2)"},
            {"action_codes", {-1, 0, 1}}, {"control_values", {-2.5, 0.0, 2.5}},
            {"disturbance_codes", {-1, 0, 1}}, {"terminal_cost", "squared position gap"},
            {"layer_state_counts", std::move(layer_counts)}, {"layer_states_lattice_scale_2000", states},
            {"bellman_cost_to_go", std::move(values)}, {"bellman_optimal_actions", std::move(optimal_actions)},
            {"open_loop_fixed_plan_value", open_loop}, {"causal_bellman_value", reference.initial().value},
            {"executed_replanning_value", replanning_value}, {"executed_replanning_policy", replanning_policy},
            {"causal_tree", optimizer_json(tree)}};
}

json run_strict_gap() {
    using namespace csl::optimization::finite_causal_minimax;
    Stage first{1, 2, 3, {true},
        {{{StateId{0}, StateId{1}, StateId{2}}, {StateId{3}, StateId{4}, StateId{5}}}}};
    Stage second{6, 2, 1, std::vector<bool>(6, true),
        {{{StateId{0}}, {StateId{1}}}, {{StateId{2}}, {StateId{3}}},
         {{StateId{4}}, {StateId{5}}}, {{StateId{6}}, {StateId{7}}},
         {{StateId{8}}, {StateId{9}}}, {{StateId{10}}, {StateId{11}}}}};
    Game game{{first, second},
        {12, std::vector<bool>(12, true), {4, 0, 1, 1, 0, 4, 2, 2, 1, 5, 2, 10}}, StateId{0}};
    const auto bellman = solve(game, {0.0, 0.0});
    if(!std::holds_alternative<Result>(bellman)) throw std::runtime_error("strict-gap Bellman input rejected");
    const auto& reference = std::get<Result>(bellman);
    const auto tree = solve_tree(game);
    const double fixed_value = fixed_plan_value(game);
    const auto [replanning_value, replanning_policy] = executed_replanning_policy(game);
    if(!tree.optimal || reference.initial().value != 1.0 || tree.objective != reference.initial().value ||
       tree.bound != reference.initial().value || tree.replayed_worst_cost != reference.initial().value ||
       fixed_value != 2.0 || replanning_value != 2.0)
        throw std::runtime_error("strict-gap Bellman, tree and policy-class values disagree");
    return {{"bellman_value", reference.initial().value}, {"bellman_actions", {0}},
            {"fixed_plan_value", fixed_value}, {"executed_replanning_value", replanning_value},
            {"executed_replanning_policy", replanning_policy}, {"causal_policy_value", tree.objective},
            {"tree", optimizer_json(tree)}};
}

json run_merged_state() {
    using namespace csl::optimization::finite_causal_minimax;
    Stage first{1, 1, 2, {true}, {{{StateId{0}, StateId{0}}}}};
    Stage second{1, 2, 1, {true}, {{{StateId{0}}, {StateId{1}}}}};
    Game game{{first, second}, {2, {true, true}, {0.0, 1.0}}, StateId{0}};
    const auto tree = solve_tree(game);
    if(!tree.optimal || tree.nonanticipativity_equalities != 2 || tree.leaves != 4 ||
       tree.replayed_worst_cost != tree.objective)
        throw std::runtime_error("merged-state tree did not enforce explicit nonanticipativity");
    return {{"tree", optimizer_json(tree)}};
}

json run_lookahead() {
    using namespace csl::optimization::finite_causal_minimax;
    Stage stage{1, 2, 2, {true},
        {{{StateId{0}, StateId{1}}, {StateId{1}, StateId{0}}}}};
    Game game{{stage}, {2, {true, false}, {0.0, 0.0}}, StateId{0}};
    const auto bellman = solve(game, {0.0, 0.0});
    if(!std::holds_alternative<Result>(bellman)) throw std::runtime_error("lookahead Bellman input rejected");
    const auto& reference = std::get<Result>(bellman);
    const auto tree = solve_tree(game);
    if(reference.initial().feasible || tree.optimal)
        throw std::runtime_error("lookahead formulation granted current-disturbance information");
    return {{"bellman_feasible", reference.initial().feasible}, {"tree", optimizer_json(tree)}};
}

json run() {
    return {{"schema", "csl.mpc05-causal-tree-pilot/1"},
            {"strict_gap", run_strict_gap()}, {"merged_state", run_merged_state()},
            {"current_disturbance_lookahead", run_lookahead()}, {"two_points", run_two_points()},
            {"do_mpc_baseline", { {"stock_formulation", "unsupported as a worst-case minimax baseline"},
                {"required_change", "replace weighted scenario-sum objective with a worst-leaf epigraph; set robust horizon to the full finite horizon"},
                {"selected_implementation", "complete explicit HiGHS extensive-form MIP with state-based nonanticipativity equalities"},
                {"performance_comparison", "not measured"} }} };
}
}

int main(int argc, char** argv) {
    try {
        if(argc != 2 || std::string(argv[1]) != "--smoke")
            throw std::runtime_error("usage: csl_mpc05_causal_tree_report --smoke");
        std::cout << run().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
