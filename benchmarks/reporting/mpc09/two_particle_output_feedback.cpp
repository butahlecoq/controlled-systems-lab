#include <nlohmann/json.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>
#include <csl/numeric/data.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace {
using Json = nlohmann::json;
using namespace csl;
using State = std::array<double, 4>;
constexpr int horizon = 3;
constexpr int rk4_steps = 20;
constexpr double dt = 0.2;
constexpr double sensor_resolution = 0.1;
constexpr double residual_bound = 0.25;
constexpr double capture_radius = 1.0;
constexpr std::array<double, 3> actions{-3.0, 0.0, 3.0};
constexpr std::array<double, 3> disturbances{-3.0, 0.0, 3.0};
constexpr std::array<double, 2> errors{-0.2, 0.2};
constexpr std::array<State, 2> initial_states{{
    {0.0, 0.0, -0.2, 0.0}, {0.0, 0.0, 0.2, 0.0}}};

struct AffineStep {
    std::array<std::array<double, 4>, 4> a{};
    State b{};
    State e{};
    State offset{};
};

State derivative(const State& x, double u, double v) {
    return {x[1], -10.0 * x[1] + 10.0 * u, x[3], v};
}

State rk4_step(State x, double u, double v) {
    const double h = dt / static_cast<double>(rk4_steps);
    for(int i = 0; i < rk4_steps; ++i) {
        const auto k1 = derivative(x, u, v);
        State stage{};
        for(std::size_t j = 0; j < x.size(); ++j) stage[j] = x[j] + h * k1[j] / 2.0;
        const auto k2 = derivative(stage, u, v);
        for(std::size_t j = 0; j < x.size(); ++j) stage[j] = x[j] + h * k2[j] / 2.0;
        const auto k3 = derivative(stage, u, v);
        for(std::size_t j = 0; j < x.size(); ++j) stage[j] = x[j] + h * k3[j];
        const auto k4 = derivative(stage, u, v);
        for(std::size_t j = 0; j < x.size(); ++j)
            x[j] += h * (k1[j] + 2.0 * k2[j] + 2.0 * k3[j] + k4[j]) / 6.0;
    }
    return x;
}

AffineStep make_affine_step() {
    AffineStep map;
    const State zero{};
    map.offset = rk4_step(zero, 0.0, 0.0);
    for(std::size_t j = 0; j < zero.size(); ++j) {
        State basis{};
        basis[j] = 1.0;
        const auto column = rk4_step(basis, 0.0, 0.0);
        for(std::size_t i = 0; i < zero.size(); ++i) map.a[i][j] = column[i] - map.offset[i];
    }
    const auto control = rk4_step(zero, 1.0, 0.0);
    const auto disturbance = rk4_step(zero, 0.0, 1.0);
    for(std::size_t i = 0; i < zero.size(); ++i) {
        map.b[i] = control[i] - map.offset[i];
        map.e[i] = disturbance[i] - map.offset[i];
    }
    return map;
}

State advance(const AffineStep& map, const State& x, double u, double v) {
    State next = map.offset;
    for(std::size_t i = 0; i < x.size(); ++i) {
        next[i] += map.b[i] * u + map.e[i] * v;
        for(std::size_t j = 0; j < x.size(); ++j) next[i] += map.a[i][j] * x[j];
    }
    return next;
}

double gap(const State& x) { return x[0] - x[2]; }
double terminal_cost(const State& x) { return std::abs(gap(x)); }
double sensor(double relative_position, double error) {
    const double scaled = (relative_position + error) / sensor_resolution;
    return std::round(scaled) * sensor_resolution;
}

std::string history_key(const std::vector<double>& history, const std::vector<double>& used) {
    (void)used;
    std::string key;
    for(const auto y : history) key += std::to_string(std::llround(y * 10.0)) + ",";
    return key;
}

bool same_state(const State& a, const State& b) {
    for(std::size_t i = 0; i < a.size(); ++i)
        if(std::abs(a[i] - b[i]) > 1e-10) return false;
    return true;
}

struct Candidate {
    State state{};
    std::vector<State> trajectory;
    std::size_t initial_index{};
    std::vector<std::size_t> disturbance_indices;
    double residual_cost{};
};

std::vector<Candidate> candidates(const AffineStep& map,
    const std::vector<double>& history, const std::vector<double>& used_controls) {
    std::vector<Candidate> result;
    std::vector<std::size_t> v_indices(used_controls.size());
    const auto visit = [&](const auto& self, std::size_t stage) -> void {
        if(stage != v_indices.size()) {
            for(std::size_t i = 0; i < disturbances.size(); ++i) {
                v_indices[stage] = i;
                self(self, stage + 1);
            }
            return;
        }
        for(std::size_t initial = 0; initial < initial_states.size(); ++initial) {
            State x = initial_states[initial];
            std::vector<State> states{x};
            for(std::size_t k = 0; k < used_controls.size(); ++k) {
                x = advance(map, x, used_controls[k], disturbances[v_indices[k]]);
                states.push_back(x);
            }
            double cost = 0.0;
            bool admissible = true;
            for(std::size_t k = 0; k < history.size(); ++k) {
                const double residual = history[k] - gap(states[k]);
                cost += residual * residual;
                admissible = admissible && std::abs(residual) <= residual_bound + 1e-10;
            }
            if(admissible) result.push_back({states.back(), std::move(states), initial, v_indices, cost});
        }
    };
    visit(visit, 0);
    return result;
}

std::vector<State> posterior_states(const AffineStep& map,
    const std::vector<double>& history, const std::vector<double>& used_controls) {
    std::vector<State> result;
    for(const auto& candidate : candidates(map, history, used_controls)) {
        bool matches = true;
        for(std::size_t k = 0; k < history.size(); ++k) {
            bool sample_matches = false;
            for(const auto error : errors) {
                if(std::abs(sensor(gap(candidate.trajectory[k]), error) - history[k]) <= 1e-12) {
                    sample_matches = true;
                    break;
                }
            }
            matches = matches && sample_matches;
        }
        if(matches && std::none_of(result.begin(), result.end(), [&](const auto& x) {
            return same_state(x, candidate.state);
        })) result.push_back(candidate.state);
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::map<std::string, double> action_cache[2];
std::map<std::string, std::vector<double>> history_actions[2];
std::size_t planning_calls[2]{};

template<class T, class... R>
T take(std::variant<T, R...> value) {
    if(!std::holds_alternative<T>(value)) throw std::runtime_error("CSL rejected a finite minimax report input");
    return std::get<T>(std::move(value));
}

sets::SetData make_vertex_set(const std::vector<State>& points, std::string id) {
    Matrix vertices{points.size(), 4, {}};
    for(const auto& point : points) vertices.values.insert(vertices.values.end(), point.begin(), point.end());
    Matrix rays{0, 4, {}};
    return take(sets::make_v({{std::move(id)}, 4, {"position_1", "velocity_1", "position_2", "velocity_2"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

sets::SetData make_disturbance_set(std::size_t stage) {
    Matrix vertices{disturbances.size(), 1,
        {disturbances[0], disturbances[1], disturbances[2]}};
    Matrix rays{0, 1, {}};
    return take(sets::make_v({{"mpc09-v-" + std::to_string(stage)}, 1, {"v"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

double csl_minimax_first_action(const AffineStep& map, const std::vector<State>& current,
    std::size_t remaining, std::size_t request_number) {
    using namespace csl::optimization;
    Matrix a{4, 4, {}};
    for(const auto& row : map.a) a.values.insert(a.values.end(), row.begin(), row.end());
    Matrix b{4, 1, Vector(map.b.begin(), map.b.end())};
    Matrix e{4, 1, Vector(map.e.begin(), map.e.end())};
    std::vector<LinearStage> stages;
    stages.reserve(remaining);
    for(std::size_t k = 0; k < remaining; ++k)
        stages.push_back({a, b, e, Vector(map.offset.begin(), map.offset.end())});
    const Dynamics dynamics{{4, 1, 1}, TimeDomain::discrete, std::move(stages)};
    SystemModel authored_model{dynamics, {}};
    std::vector<double> times(remaining + 1);
    for(std::size_t k = 0; k < times.size(); ++k) times[k] = static_cast<double>(k) * dt;
    const auto system = take(model::snapshot(authored_model, times));

    const FiniteDomain control_domain{1, {{actions[0]}, {actions[1]}, {actions[2]}}};
    std::vector<sets::SetData> disturbance_sets, safe_sets;
    disturbance_sets.reserve(remaining);
    for(std::size_t k = 0; k < remaining; ++k) disturbance_sets.push_back(make_disturbance_set(k));
    safe_sets.reserve(remaining + 1);
    for(std::size_t k = 0; k <= remaining; ++k)
        safe_sets.push_back(take(sets::make_universal({{"mpc09-safe-" + std::to_string(k)}, 4,
            {"position_1", "velocity_1", "position_2", "velocity_2"}})));
    const auto objective = take(optimization::snapshot(TerminalObjective{ResidualNormTerminal{
        Matrix{1, 4, {1.0, 0.0, -1.0, 0.0}}, Vector{0.0}}}));
    const FiniteActionMinimaxRequest request{{"mpc09-two-particle"},
        {"mpc09-request-" + std::to_string(request_number)}, system,
        make_vertex_set(current, "mpc09-belief-" + std::to_string(request_number)), control_domain,
        std::move(disturbance_sets), std::move(safe_sets), objective};
    const auto outcome = finite_action_minimax(request, {27, 100000, 1e-12});
    const auto* optimal = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!optimal || optimal->minimizing_plan_indices.empty())
        throw std::runtime_error("CSL finite-action minimax did not return a feasible output-feedback plan");
    const auto& record = optimal->plans.at(optimal->minimizing_plan_indices.front());
    const auto* feasible = std::get_if<FinitePlanFeasible>(&record);
    if(!feasible || feasible->action_indices.empty())
        throw std::runtime_error("CSL finite-action minimax retained an invalid optimal plan record");
    return actions.at(feasible->action_indices.front());
}

double first_action(const AffineStep& map, const std::vector<double>& history,
    const std::vector<double>& used_controls, bool robust) {
    const auto key = history_key(history, used_controls);
    auto& cache = action_cache[robust ? 1 : 0];
    auto& prior_actions = history_actions[robust ? 1 : 0];
    if(const auto found = cache.find(key); found != cache.end()) {
        if(prior_actions.at(key) != used_controls)
            throw std::runtime_error("identical released observation histories imply different prior actions");
        return found->second;
    }
    auto found_candidates = candidates(map, history, used_controls);
    if(found_candidates.empty()) throw std::runtime_error("MHE found no prior/disturbance row compatible with the observation history");
    std::vector<State> current;
    if(robust) {
        current = posterior_states(map, history, used_controls);
        if(current.empty()) throw std::runtime_error("finite posterior is empty for an authored observation history");
    } else {
        const auto best = std::min_element(found_candidates.begin(), found_candidates.end(),
            [](const Candidate& a, const Candidate& b) {
                if(std::abs(a.residual_cost - b.residual_cost) > 1e-12)
                    return a.residual_cost < b.residual_cost;
                if(a.initial_index != b.initial_index) return a.initial_index < b.initial_index;
                return a.disturbance_indices < b.disturbance_indices;
            });
        current.push_back(best->state);
    }
    const std::size_t remaining = static_cast<std::size_t>(horizon) - used_controls.size();
    const double best_action = csl_minimax_first_action(map, current, remaining, planning_calls[0] + planning_calls[1]);
    cache.emplace(key, best_action);
    prior_actions.emplace(key, used_controls);
    ++planning_calls[robust ? 1 : 0];
    return best_action;
}

struct RunRow {
    std::size_t initial_index{};
    std::vector<double> disturbances;
    std::vector<double> errors;
};

void enumerate_rows(std::vector<RunRow>& rows, std::vector<double>& vs,
    std::vector<double>& es, std::size_t initial) {
    if(vs.size() == horizon && es.size() == horizon + 1) {
        rows.push_back({initial, vs, es});
        return;
    }
    if(vs.size() < horizon) {
        for(const auto v : disturbances) {
            vs.push_back(v);
            enumerate_rows(rows, vs, es, initial);
            vs.pop_back();
        }
    } else {
        for(const auto error : errors) {
            es.push_back(error);
            enumerate_rows(rows, vs, es, initial);
            es.pop_back();
        }
    }
}

Json evaluate_arm(const AffineStep& map, const std::vector<RunRow>& rows, bool robust) {
    Json runs = Json::array();
    double worst = -1.0;
    std::size_t violations = 0;
    for(std::size_t row_id = 0; row_id < rows.size(); ++row_id) {
        const auto& row = rows[row_id];
        State x = initial_states[row.initial_index];
        std::vector<double> history, used_controls;
        Json trace = Json::array();
        for(int stage = 0; stage <= horizon; ++stage) {
            const double y = sensor(gap(x), row.errors[static_cast<std::size_t>(stage)]);
            history.push_back(y);
            Json point{{"stage", stage}, {"state", x}, {"relative_position", gap(x)},
                {"observation", y}};
            if(stage < horizon) {
                const auto estimates = candidates(map, history, used_controls);
                const auto estimate = std::min_element(estimates.begin(), estimates.end(),
                    [](const Candidate& a, const Candidate& b) {
                        if(std::abs(a.residual_cost - b.residual_cost) > 1e-12)
                            return a.residual_cost < b.residual_cost;
                        if(a.initial_index != b.initial_index) return a.initial_index < b.initial_index;
                        return a.disturbance_indices < b.disturbance_indices;
                    });
                const auto posterior = posterior_states(map, history, used_controls);
                const double u = first_action(map, history, used_controls, robust);
                point["estimate"] = estimate->state;
                point["posterior_size"] = posterior.size();
                point["posterior_states"] = posterior;
                point["mhe_residual_cost"] = estimate->residual_cost;
                point["control"] = u;
                point["disturbance"] = row.disturbances[static_cast<std::size_t>(stage)];
                used_controls.push_back(u);
                x = advance(map, x, u, row.disturbances[static_cast<std::size_t>(stage)]);
            }
            trace.push_back(std::move(point));
        }
        const double cost = terminal_cost(x);
        worst = std::max(worst, cost);
        if(cost > capture_radius + 1e-12) ++violations;
        runs.push_back({{"row_id", row_id}, {"initial_index", row.initial_index},
            {"disturbances", row.disturbances}, {"measurement_errors", row.errors},
            {"trace", std::move(trace)}, {"terminal_gap", cost},
            {"terminal_capture", cost <= capture_radius + 1e-12}});
    }
    return {{"label", robust ? "set_based_robust_receding" : "certainty_equivalent_receding"},
        {"worst_terminal_gap", worst}, {"terminal_capture_violations", violations},
        {"rows_evaluated", rows.size()}, {"distinct_histories_optimized", planning_calls[robust ? 1 : 0]},
        {"runs", std::move(runs)}};
}

Json observation_timing_checks(const AffineStep& map) {
    const std::vector<double> controls{0.0, 0.0};
    const std::array<double, 2> v_path{-3.0, 3.0};
    const std::array<double, 2> noise_path{-0.2, 0.2};
    State truth = initial_states[0];
    const double y0 = sensor(gap(truth), noise_path[0]);
    truth = advance(map, truth, controls[0], v_path[0]);
    const double y1 = sensor(gap(truth), noise_path[1]);
    truth = advance(map, truth, controls[1], v_path[1]);

    const std::vector<double> at_decision_one{y0};
    const auto missed_estimate = candidates(map, at_decision_one, {controls[0]});
    const auto missed_posterior = posterior_states(map, at_decision_one, {controls[0]});
    if(missed_estimate.empty() || missed_posterior.empty())
        throw std::runtime_error("missing-observation check discarded every prior hypothesis");

    const std::vector<double> delayed_history{y0, y1};
    const auto delayed_estimate = candidates(map, delayed_history, controls);
    const auto delayed_posterior = posterior_states(map, delayed_history, controls);
    if(delayed_estimate.empty() || delayed_posterior.empty())
        throw std::runtime_error("delayed-observation check discarded every prior hypothesis");

    const auto failed = candidates(map, {1000.0}, {controls[0]});
    return {{"schema", "csl.mpc09-observation-timing-check/1"},
        {"control_history", controls}, {"disturbance_history", v_path},
        {"noise_history", noise_path},
        {"released_samples_at_decision_1", Json::array({{{"state_stage", 0}, {"available_stage", 0}, {"value", y0}}})},
        {"decision_1", {{"sample_at_stage_1", "missed"},
            {"state_hypothesis_count", missed_estimate.size()},
            {"posterior_state_count", missed_posterior.size()},
            {"hidden_state_was_read", false}}},
        {"released_samples_at_decision_2", Json::array({
            {{"state_stage", 0}, {"available_stage", 0}, {"value", y0}},
            {{"state_stage", 1}, {"available_stage", 2}, {"value", y1}}})},
        {"decision_2", {{"delayed_stage_1_sample_released", true},
            {"state_hypothesis_count", delayed_estimate.size()},
            {"posterior_state_count", delayed_posterior.size()},
            {"estimate", std::min_element(delayed_estimate.begin(), delayed_estimate.end(),
                [](const Candidate& a, const Candidate& b) {
                    if(std::abs(a.residual_cost-b.residual_cost)>1e-12) return a.residual_cost<b.residual_cost;
                    if(a.initial_index!=b.initial_index) return a.initial_index<b.initial_index;
                    return a.disturbance_indices<b.disturbance_indices;
                })->state},
            {"posterior_states", delayed_posterior}}},
        {"inconsistent_history", {{"status", failed.empty()?"no_compatible_hypothesis":"unexpected_candidate"},
            {"candidate_count", failed.size()}}}};
}

Json run() {
    const auto map = make_affine_step();
    std::vector<RunRow> rows;
    std::vector<double> vs, es;
    for(std::size_t initial = 0; initial < initial_states.size(); ++initial)
        enumerate_rows(rows, vs, es, initial);
    const auto ce = evaluate_arm(map, rows, false);
    const auto robust = evaluate_arm(map, rows, true);
    return {{"schema", "csl.mpc09-two-particle-output-feedback/1"},
        {"source", {{"repository", "https://github.com/imm-rl-lab/differential_game_gym"},
            {"repository_commit", "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8"},
            {"file_blob", "7e7d326f8ff81f7dacc05ac72848eeaac6a03021"},
            {"license", "Apache-2.0"}}},
        {"adaptation", {{"scenario_id", "mpc09-two-particle-output-feedback-v1"},
            {"horizon_steps", horizon}, {"horizon_seconds", horizon * dt},
            {"state_order", {"position_1", "velocity_1", "position_2", "velocity_2"}},
            {"initial_states", initial_states}, {"control_catalogue", actions},
            {"disturbance_catalogue", disturbances}, {"measurement_error_catalogue", errors},
            {"sensor_resolution", sensor_resolution}, {"mhe_residual_bound", residual_bound},
            {"observation", "relative position plus {-0.2,+0.2}, rounded to 0.1; available before every decision"},
            {"initial_quantifier", "universal over two listed initial states"},
            {"disturbance_semantics", "independent adversarial finite catalogue per transition"},
            {"information_pattern", "same ordered observation history and past actions imply the same controller action"},
            {"mhe", "full-history constrained least squares; zero prior/arrival cost; residual bound 0.25; lexicographic ties"},
            {"future_observation_branching", "receding controllers replan after each observation; their lookahead is open-loop in future controls"},
            {"capture_radius", capture_radius},
            {"rows", rows.size()},
            {"limits", {"Finite rows only; no continuous-noise, statistical-confidence, or global output-feedback optimality claim.",
                "The source RL task used continuous actions and a longer horizon; this is an explicit finite observation adaptation."}}}},
        {"controllers", Json::array({ce, robust})},
        {"observation_timing_checks", observation_timing_checks(map)}};
}
} // namespace

int main() {
    try {
        std::cout << run().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "mpc09 output-feedback report failed: " << error.what() << '\n';
        return 1;
    }
}
