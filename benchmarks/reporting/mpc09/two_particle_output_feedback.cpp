#include <nlohmann/json.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/controllers/observed_replay.hpp>
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
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
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
double sensor(double relative_position, double error) { return relative_position + error; }

struct MeasuredSample {
    std::size_t channel{};
    std::size_t state_stage{};
    double value{};
    std::size_t released_stage{};
    ObservationTiming released_timing{ObservationTiming::before_decision};
};

std::string history_key(const std::vector<MeasuredSample>& history, std::size_t decision_stage) {
    std::ostringstream key;
    key << std::setprecision(std::numeric_limits<double>::max_digits10);
    key << decision_stage << '|';
    for(const auto& sample : history)
        key << sample.channel << ':' << sample.state_stage << ':' << sample.released_stage << ':'
            << static_cast<int>(sample.released_timing) << ':' << sample.value << ',';
    return key.str();
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
    const std::vector<MeasuredSample>& history, const std::vector<double>& used_controls) {
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
            for(const auto& sample : history) {
                if(sample.state_stage >= states.size()) { admissible = false; break; }
                const double residual = sample.value - gap(states[sample.state_stage]);
                cost += residual * residual;
                admissible = admissible && std::abs(residual) <= residual_bound + 1e-10;
            }
            if(admissible) result.push_back({states.back(), std::move(states), initial, v_indices, cost});
        }
    };
    visit(visit, 0);
    return result;
}

const Candidate& best_candidate(const std::vector<Candidate>& found) {
    if(found.empty()) throw std::runtime_error("MHE found no prior/disturbance row compatible with the observation history");
    return *std::min_element(found.begin(), found.end(),
        [](const Candidate& a, const Candidate& b) {
            if(std::abs(a.residual_cost - b.residual_cost) > 1e-12)
                return a.residual_cost < b.residual_cost;
            if(a.initial_index != b.initial_index) return a.initial_index < b.initial_index;
            return a.disturbance_indices < b.disturbance_indices;
        });
}

std::vector<State> posterior_states(const AffineStep& map,
    const std::vector<MeasuredSample>& history, const std::vector<double>& used_controls) {
    std::vector<State> result;
    for(const auto& candidate : candidates(map, history, used_controls)) {
        bool matches = true;
        for(const auto& sample : history) {
            bool sample_matches = false;
            for(const auto error : errors) {
                if(sample.state_stage < candidate.trajectory.size() &&
                    std::abs(sensor(gap(candidate.trajectory[sample.state_stage]), error) - sample.value) <= 1e-12) {
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
    if(!std::holds_alternative<T>(value)) {
        const auto detail = std::visit([](const auto& failure) -> std::string {
            using Failure = std::decay_t<decltype(failure)>;
            if constexpr(requires { failure.field; failure.explanation; })
                return failure.field + ": " + failure.explanation;
            else return "unexpected CSL outcome " + std::string(typeid(Failure).name());
        }, value);
        throw std::runtime_error("CSL rejected report input: " + detail);
    }
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

double first_action(const AffineStep& map, const std::vector<MeasuredSample>& history,
    const std::vector<double>& used_controls, bool robust) {
    const auto key = history_key(history, used_controls.size());
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
        current.push_back(best_candidate(found_candidates).state);
    }
    const std::size_t remaining = static_cast<std::size_t>(horizon) - used_controls.size();
    const double best_action = csl_minimax_first_action(map, current, remaining, planning_calls[0] + planning_calls[1]);
    cache.emplace(key, best_action);
    prior_actions.emplace(key, used_controls);
    ++planning_calls[robust ? 1 : 0];
    return best_action;
}

model::LinearSystem make_replay_system(const AffineStep& map,
    std::optional<std::size_t> sample_one_release_stage = std::nullopt) {
    Matrix a{4, 4, {}};
    for(const auto& row : map.a) a.values.insert(a.values.end(), row.begin(), row.end());
    Matrix b{4, 1, Vector(map.b.begin(), map.b.end())};
    Matrix e{4, 1, Vector(map.e.begin(), map.e.end())};
    std::vector<LinearStage> stages(static_cast<std::size_t>(horizon),
        LinearStage{a, b, e, Vector(map.offset.begin(), map.offset.end())});
    Dynamics dynamics{{4, 1, 1}, TimeDomain::discrete, std::move(stages)};

    ObservationStage observation{Matrix{1, 4, {1.0, 0.0, -1.0, 0.0}},
        Matrix{1, 1, {0.0}}, Matrix{1, 1, {0.0}}, Matrix{1, 1, {1.0}}, Vector{0.0}};
    const auto pre = [](std::size_t stage) {
        return ObservationPoint{{stage}, ObservationTiming::before_decision};
    };
    std::vector<ObservationSample> schedule;
    schedule.reserve(static_cast<std::size_t>(horizon + 1));
    for(std::size_t sample = 0; sample <= static_cast<std::size_t>(horizon); ++sample) {
        const bool delayed = sample_one_release_stage && sample == 1;
        schedule.push_back({{sample}, delayed ? ObservationPoint{{0}, ObservationTiming::after_decision} : pre(sample),
            delayed ? pre(*sample_one_release_stage) : pre(sample), std::nullopt});
    }
    SystemModel authored{std::move(dynamics), {{std::move(observation), std::move(schedule)}}};
    std::vector<double> times(static_cast<std::size_t>(horizon + 1));
    for(std::size_t k = 0; k < times.size(); ++k) times[k] = static_cast<double>(k) * dt;
    return take(model::snapshot(authored, times));
}

std::vector<MeasuredSample> measured_history(
    std::span<const controllers::ReleasedObservation> released) {
    std::vector<MeasuredSample> history;
    history.reserve(released.size());
    for(const auto& sample : released)
        history.push_back({sample.channel.value, sample.sample.value, sample.value.values.at(0),
            sample.released_at.stage.value, sample.released_at.timing});
    return history;
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
    const auto system = make_replay_system(map);
    for(std::size_t row_id = 0; row_id < rows.size(); ++row_id) {
        const auto& row = rows[row_id];
        controllers::ReplayInputs inputs;
        inputs.initial_state.assign(initial_states[row.initial_index].begin(), initial_states[row.initial_index].end());
        for(const auto disturbance : row.disturbances) inputs.external.push_back({disturbance});
        std::vector<Vector> measurement_errors;
        for(const auto error : row.errors) measurement_errors.push_back({error});
        inputs.measurement_errors = {std::move(measurement_errors)};

        std::vector<double> used_controls;
        std::vector<double> residual_costs;
        std::vector<std::size_t> posterior_sizes;
        std::vector<std::vector<State>> posteriors;
        const auto estimator = [&](StageIndex, std::span<const controllers::ReleasedObservation> released) {
            const auto history = measured_history(released);
            const auto found = candidates(map, history, used_controls);
            const auto& estimate = best_candidate(found);
            residual_costs.push_back(estimate.residual_cost);
            auto posterior = posterior_states(map, history, used_controls);
            posterior_sizes.push_back(posterior.size());
            posteriors.push_back(std::move(posterior));
            return Vector(estimate.state.begin(), estimate.state.end());
        };
        const auto controller = [&](StageIndex, std::span<const controllers::ReleasedObservation> released,
            std::span<const double>) {
            const auto history = measured_history(released);
            const auto action = first_action(map, history, used_controls, robust);
            used_controls.push_back(action);
            return Vector{action};
        };
        auto replay = controllers::replay_observed_policy(system, inputs, estimator, controller);
        auto* record = std::get_if<controllers::ReplayRecord>(&replay);
        if(!record) throw std::runtime_error("reviewed observed-policy replay rejected an authored MPC-09 row");

        Json trace = Json::array();
        for(std::size_t k = 0; k < record->decisions.size(); ++k) {
            const auto& decision = record->decisions[k];
            Json observations = Json::array();
            for(const auto& sample : decision.available) {
                observations.push_back({{"channel", sample.channel.value}, {"sample", sample.sample.value},
                    {"released_stage", sample.released_at.stage.value},
                    {"released_after_decision", sample.released_at.timing == ObservationTiming::after_decision},
                    {"value", sample.value.values}});
            }
            const auto& state = record->states[k];
            trace.push_back({{"stage", k}, {"state", state},
                {"relative_position", state.at(0) - state.at(2)},
                {"available_observations", std::move(observations)},
                {"estimate", decision.estimate}, {"posterior_size", posterior_sizes.at(k)},
                {"posterior_states", posteriors.at(k)}, {"mhe_residual_cost", residual_costs.at(k)},
                {"action", decision.action.at(0)}, {"disturbance", inputs.external[k].at(0)}});
        }
        Json released_observations = Json::array();
        for(const auto& sample : record->released)
            released_observations.push_back({{"channel", sample.channel.value},
                {"sample", sample.sample.value}, {"released_stage", sample.released_at.stage.value},
                {"released_after_decision", sample.released_at.timing == ObservationTiming::after_decision},
                {"value", sample.value.values}});
        const double cost = std::abs(record->states.back().at(0) - record->states.back().at(2));
        worst = std::max(worst, cost);
        if(cost > capture_radius + 1e-12) ++violations;
        runs.push_back({{"row_id", row_id}, {"initial_index", row.initial_index},
            {"disturbances", row.disturbances}, {"measurement_errors", row.errors},
            {"states", record->states}, {"decisions", std::move(trace)},
            {"released_observations", std::move(released_observations)}, {"terminal_gap", cost},
            {"terminal_capture", cost <= capture_radius + 1e-12}});
    }
    return {{"label", robust ? "set_based_robust_receding" : "certainty_equivalent_receding"},
        {"worst_terminal_gap", worst}, {"terminal_capture_violations", violations},
        {"rows_evaluated", rows.size()}, {"distinct_histories_optimized", planning_calls[robust ? 1 : 0]},
        {"runs", std::move(runs)}};
}

controllers::ReplayRecord timing_replay(const AffineStep& map, std::size_t release_stage) {
    const auto system = make_replay_system(map, release_stage);
    controllers::ReplayInputs inputs;
    inputs.initial_state.assign(initial_states[0].begin(), initial_states[0].end());
    inputs.external = {{0.0}, {-3.0}, {-3.0}};
    inputs.measurement_errors = {{{-0.2}, {-0.2}, {0.2}, {-0.2}}};
    std::vector<double> used_controls;
    const auto estimator = [&](StageIndex, std::span<const controllers::ReleasedObservation> released) {
        const auto history = measured_history(released);
        const auto found = candidates(map, history, used_controls);
        const auto& estimate = best_candidate(found);
        return Vector(estimate.state.begin(), estimate.state.end());
    };
    const auto controller = [&](StageIndex, std::span<const controllers::ReleasedObservation> released,
        std::span<const double>) {
        const auto history = measured_history(released);
        const auto action = first_action(map, history, used_controls, false);
        used_controls.push_back(action);
        return Vector{action};
    };
    auto replay = controllers::replay_observed_policy(system, inputs, estimator, controller);
    auto* record = std::get_if<controllers::ReplayRecord>(&replay);
    if(!record) throw std::runtime_error("reviewed delayed-measurement replay rejected its fixture");
    return std::move(*record);
}

Json record_json(const controllers::ReplayRecord& record) {
    Json decisions = Json::array();
    for(const auto& decision : record.decisions) {
        Json observations = Json::array();
        for(const auto& sample : decision.available)
            observations.push_back({{"sample", sample.sample.value}, {"value", sample.value.values},
                {"released_stage", sample.released_at.stage.value},
                {"released_after_decision", sample.released_at.timing == ObservationTiming::after_decision}});
        decisions.push_back({{"stage", decision.stage.value}, {"observations", std::move(observations)},
            {"estimate", decision.estimate}, {"action", decision.action}});
    }
    Json released = Json::array();
    for(const auto& sample : record.released)
        released.push_back({{"sample", sample.sample.value}, {"value", sample.value.values},
            {"released_stage", sample.released_at.stage.value},
            {"released_after_decision", sample.released_at.timing == ObservationTiming::after_decision}});
    return {{"states", record.states}, {"decisions", std::move(decisions)},
        {"released_observations", std::move(released)}};
}

Json observation_timing_checks(const AffineStep& map) {
    const auto delayed = timing_replay(map, 2);
    const auto missed_until_terminal = timing_replay(map, 3);
    const auto& decision_stage_one = delayed.decisions.at(1);
    const auto& decision_stage_two_delayed = delayed.decisions.at(2);
    const auto& decision_stage_two_missed = missed_until_terminal.decisions.at(2);
    if(decision_stage_one.available.size() != 1 || decision_stage_two_delayed.available.size() != 3 ||
        decision_stage_two_missed.available.size() != 2)
        throw std::runtime_error("missed/delayed replay released a sample at the wrong decision event");
    if(decision_stage_two_delayed.action == decision_stage_two_missed.action)
        throw std::runtime_error("delayed sample did not change the later controller action in the fixture");
    const auto failed = candidates(map, {{0, 0, 1000.0, 0, ObservationTiming::before_decision}}, {});
    return {{"schema", "csl.mpc09-observation-timing-check/2"},
        {"disturbances", {0.0, -3.0, -3.0}},
        {"measurement_errors", {-0.2, -0.2, 0.2, -0.2}},
        {"delayed_sample_available_at_stage", 2},
        {"decision_1", record_json(delayed).at("decisions").at(1)},
        {"decision_2_with_delayed_sample", record_json(delayed).at("decisions").at(2)},
        {"decision_2_without_sample_until_terminal", record_json(missed_until_terminal).at("decisions").at(2)},
        {"released_after_terminal", record_json(missed_until_terminal).at("released_observations")},
        {"later_action_changed_after_sample_release", true},
        {"states", delayed.states},
        {"inconsistent_history", {{"status", failed.empty() ? "no_compatible_hypothesis" : "unexpected_candidate"},
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
            {"mhe_residual_bound", residual_bound},
            {"observation", "relative position plus error in {-0.2,+0.2}; available before every decision"},
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
