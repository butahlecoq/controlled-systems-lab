#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <numbers>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace {
using Json = nlohmann::json;
using State = std::array<double, 2>;
using Plan = std::array<std::uint8_t, 10>;

constexpr double pi = std::numbers::pi_v<double>;
constexpr double dt = 0.05;
constexpr double gravity = 10.0;
constexpr double mass = 1.0;
constexpr double length = 1.0;
constexpr double max_speed = 8.0;
constexpr double max_torque = 2.0;
constexpr std::size_t horizon = 10;
constexpr std::size_t plan_count = 9'765'625;
constexpr std::size_t warmup_repetitions = 2;
constexpr State initial_state{1.5, 0.0};
constexpr std::array<double, 5> actions{-2.0, -1.0, 0.0, 1.0, 2.0};

struct SearchResult {
    double objective{INFINITY};
    std::size_t plan_index{};
    Plan selected_actions{};
    std::size_t minimizer_count{};
    std::size_t evaluated_plans{};
};

struct Evaluation {
    double objective{};
    State terminal{};
};

double angle_normalize(double angle) {
    double shifted = std::fmod(angle + pi, 2.0 * pi);
    if (shifted < 0.0) shifted += 2.0 * pi;
    return shifted - pi;
}

State advance(State state, double action) {
    const double torque = std::clamp(action, -max_torque, max_torque);
    const double new_velocity = std::clamp(
        state[1] + (3.0 * gravity / (2.0 * length) * std::sin(state[0]) +
                    3.0 / (mass * length * length) * torque) * dt,
        -max_speed, max_speed);
    const double new_angle = state[0] + new_velocity * dt;
    return {new_angle, new_velocity};
}

Evaluation evaluate(const Plan& plan) {
    State state = initial_state;
    double objective = 0.0;
    for (const auto action_index : plan) {
        const double action = actions[action_index];
        const double angle_cost = angle_normalize(state[0]);
        objective += angle_cost * angle_cost + 0.1 * state[1] * state[1] +
            0.001 * action * action;
        state = advance(state, action);
    }
    return {objective, state};
}

SearchResult enumerate() {
    SearchResult best;
    for (std::size_t plan_index = 0; plan_index < plan_count; ++plan_index) {
        std::size_t digits = plan_index;
        Plan plan{};
        for (std::size_t stage = 0; stage < horizon; ++stage) {
            plan[stage] = static_cast<std::uint8_t>(digits % actions.size());
            digits /= actions.size();
        }
        const auto current = evaluate(plan);
        if (current.objective < best.objective) {
            best.objective = current.objective;
            best.plan_index = plan_index;
            best.selected_actions = plan;
            best.minimizer_count = 1;
        } else if (current.objective == best.objective) {
            ++best.minimizer_count;
            if (plan_index < best.plan_index) {
                best.plan_index = plan_index;
                best.selected_actions = plan;
            }
        }
        ++best.evaluated_plans;
    }
    return best;
}

Json trajectory_json(const Plan& plan) {
    State state = initial_state;
    Json rows = Json::array();
    rows.push_back({{"step", 0}, {"time_seconds", 0.0},
        {"theta_rad", state[0]}, {"theta_dot_rad_s", state[1]},
        {"action_torque_nm", actions[plan[0]]}});
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        const double action = actions[plan[stage]];
        state = advance(state, action);
        rows.push_back({{"step", stage + 1}, {"time_seconds", (stage + 1) * dt},
            {"theta_rad", state[0]}, {"theta_dot_rad_s", state[1]},
            {"action_torque_nm", stage + 1 < horizon ? actions[plan[stage + 1]] : 0.0}});
    }
    return rows;
}

Json state_json(const State& state) { return {state[0], state[1]}; }

std::int64_t median(std::vector<std::int64_t> values) {
    std::sort(values.begin(), values.end());
    if (values.size() % 2 == 1) return values[values.size() / 2];
    return values[values.size() / 2 - 1] / 2 + values[values.size() / 2] / 2;
}

Json result_record(const SearchResult& best,
    const std::vector<std::int64_t>& elapsed_ns, std::size_t measured_repetitions) {
    const auto minmax = std::minmax_element(elapsed_ns.begin(), elapsed_ns.end());
    Json selected_indices = Json::array();
    Json selected_actions = Json::array();
    Plan zero_plan{};
    zero_plan.fill(2);
    for (const auto index : best.selected_actions) {
        selected_indices.push_back(index);
        selected_actions.push_back(actions[index]);
    }
    const auto baseline = evaluate(zero_plan);
    const Json measurement = {
        {"schema", "csl.env717-runtime-measurement/1"},
        {"metric", "finite_catalogue_enumeration_elapsed"}, {"unit", "ns"},
        {"scope", "steady_clock interval for decoding and evaluating every fixed 10-action plan over the source dynamics; excludes JSON generation, Python replay, plotting, and report writes"},
        {"worker_threads", 1}, {"warmup_repetitions", warmup_repetitions},
        {"measured_repetitions", measured_repetitions}, {"successful_repetitions", elapsed_ns.size()},
        {"failed_repetitions", 0}, {"raw_elapsed_ns", elapsed_ns},
        {"median_elapsed_ns", median(elapsed_ns)}, {"minimum_elapsed_ns", *minmax.first},
        {"maximum_elapsed_ns", *minmax.second}, {"timing_clock", "std::chrono::steady_clock"},
        {"comparison", "single-adapter descriptive measurement; no comparator or speedup claim"}};
    return {
        {"schema", "csl.env717-pendulum/1"},
        {"environment", "Pendulum-v0"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_notebook", "Environments/Pendulum/Pendulum.ipynb"},
        {"source_notebook_blob", "db58eb7779d84a3a5032288734d61f6d6dcdba09"},
        {"simulator_repository", "openai/gym"}, {"simulator_version", "v0.21.0"},
        {"simulator_commit", "c755d5c35a25ab118746e2ba885894ff66fb8c43"},
        {"simulator_source", "gym/envs/classic_control/pendulum.py"},
        {"simulator_source_blob", "10ced4d43d218fbf0bb344b3bbc006fcaa7f8362"},
        {"simulator_registry_source", "gym/envs/__init__.py"},
        {"simulator_registry_blob", "a90b0370730e74d783971a1a3f0771c5a2fb572e"},
        {"simulator_license", "MIT"},
        {"upstream_repository_license", "no license declared in upstream optimal_control repository metadata; this report re-expresses equations and copies no upstream implementation"},
        {"source_model", {
            {"state_order", {"theta_rad", "theta_dot_rad_s"}},
            {"sample_period_seconds", dt}, {"gravity_m_s2", gravity}, {"mass_kg", mass},
            {"length_m", length}, {"max_speed_rad_s", max_speed}, {"max_torque_nm", max_torque},
            {"dynamics", "new_theta_dot=clip(theta_dot+(3*g/(2*l)*sin(theta)+3/(m*l^2)*u)*dt,-8,8); new_theta=theta+new_theta_dot*dt"},
            {"step_cost", "angle_normalize(theta)^2 + 0.1*theta_dot^2 + 0.001*u^2, evaluated before the state update; reward is its negative"},
            {"reset", "Gym Pendulum-v0 samples theta uniformly from [-pi,pi] and theta_dot from [-1,1]"},
            {"time_limit_steps", 200}, {"observation", "[cos(theta), sin(theta), theta_dot]"}}},
        {"pilot_adaptation", {
            {"initial_state", initial_state}, {"initial_state_choice", "authored reproducible state inside the Gym reset support"},
            {"action_catalogue_torque_nm", actions}, {"horizon_steps", horizon},
            {"horizon_seconds", horizon * dt}, {"plan_count", best.evaluated_plans},
            {"semantics", "fixed open-loop action sequences; one torque per 0.05-second source step; no disturbance"},
            {"objective", "minimize the sum of source per-step costs over the finite horizon"},
            {"claim_boundary", "exact minimum over this 5^10 binary64 finite catalogue and authored initial state only; not continuous-action or full-horizon optimality"}}},
        {"search", {{"complete_plan_count", plan_count}, {"evaluated_plan_count", best.evaluated_plans},
            {"minimizer_count", best.minimizer_count}, {"selected_plan_index", best.plan_index},
            {"complete", best.evaluated_plans == plan_count}}},
        {"finite_catalogue_optimum", {
            {"objective_cost", best.objective}, {"reward", -best.objective},
            {"selected_action_indices", selected_indices}, {"selected_actions_torque_nm", selected_actions},
            {"terminal_state", state_json(evaluate(best.selected_actions).terminal)},
            {"trajectory", trajectory_json(best.selected_actions)}}},
        {"zero_torque_baseline", {{"objective_cost", baseline.objective},
            {"reward", -baseline.objective}, {"terminal_state", state_json(baseline.terminal)},
            {"trajectory", trajectory_json(zero_plan)}}},
        {"runtime_measurement", measurement},
        {"provenance", {{"driver_sha256", CSL_ENV717_PENDULUM_DRIVER_SHA256},
            {"source_commit", CSL_ENV717_PENDULUM_SOURCE_COMMIT},
            {"compiler_id", CSL_ENV717_PENDULUM_COMPILER_ID},
            {"compiler_version", CSL_ENV717_PENDULUM_COMPILER_VERSION},
            {"build_type", CSL_ENV717_PENDULUM_BUILD_TYPE},
            {"architecture", CSL_ENV717_PENDULUM_ARCHITECTURE}}},
        {"claims", Json::array({"source-step equations and reward are independently re-expressed",
            "the best plan is exact over the declared finite catalogue under binary64 evaluation",
            "timings are descriptive for one implementation and do not compare algorithms"})}};
}
} // namespace

int main(int argc, char** argv) {
    try {
        std::size_t measured_repetitions = 7;
        if (argc == 3 && std::string_view(argv[1]) == "--measure") {
            const std::string_view value(argv[2]);
            const auto parsed = std::from_chars(value.data(), value.data() + value.size(), measured_repetitions);
            if (value.empty() || parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                measured_repetitions == 0 || measured_repetitions > 1000)
                throw std::invalid_argument("measurement repetitions must be in 1..1000");
        } else if (argc != 1) {
            throw std::invalid_argument("usage: csl_env717_pendulum [--measure REPETITIONS]");
        }
        std::vector<std::int64_t> elapsed_ns;
        elapsed_ns.reserve(measured_repetitions);
        SearchResult best;
        for (std::size_t repetition = 0; repetition < warmup_repetitions + measured_repetitions; ++repetition) {
            const auto started = std::chrono::steady_clock::now();
            auto current = enumerate();
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - started).count();
            if (elapsed <= 0) throw std::runtime_error("nonpositive enumeration duration");
            if (repetition >= warmup_repetitions) elapsed_ns.push_back(elapsed);
            if (repetition + 1 == warmup_repetitions + measured_repetitions) best = current;
        }
        std::cout << result_record(best, elapsed_ns, measured_repetitions).dump(2) << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Pendulum finite-action pilot failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
