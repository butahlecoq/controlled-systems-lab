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
using State = std::array<double, 4>;
using ControlIndices = std::array<std::uint8_t, 14>;

constexpr std::size_t horizon = 14;
constexpr std::size_t plan_count = std::size_t{1} << horizon;
constexpr double gravity = 9.8;
constexpr double cart_mass = 1.0;
constexpr double pole_mass = 0.1;
constexpr double total_mass = cart_mass + pole_mass;
constexpr double half_pole_length = 0.5;
constexpr double polemass_length = pole_mass * half_pole_length;
constexpr double force_magnitude = 10.0;
constexpr double time_step = 0.02;
constexpr double cart_position_threshold = 2.4;
constexpr double pole_angle_threshold = 12.0 * 2.0 * std::numbers::pi / 360.0;
constexpr std::size_t warmup_repetitions = 5;
constexpr std::array<double, 2> forces{-force_magnitude, force_magnitude};
constexpr State initial_state{0.0, 0.0, 0.0, 0.0};

struct Transition {
    State state;
    bool terminated;
};

Transition advance_state(const State& state, std::uint8_t control_index) {
    const double x = state[0];
    const double x_dot = state[1];
    const double theta = state[2];
    const double theta_dot = state[3];
    const double force = forces[control_index];
    const double cos_theta = std::cos(theta);
    const double sin_theta = std::sin(theta);
    const double temp = (force + polemass_length * theta_dot * theta_dot * sin_theta) / total_mass;
    const double theta_acc = (gravity * sin_theta - cos_theta * temp) /
        (half_pole_length * (4.0 / 3.0 - pole_mass * cos_theta * cos_theta / total_mass));
    const double x_acc = temp - polemass_length * theta_acc * cos_theta / total_mass;
    const State next{x + time_step * x_dot, x_dot + time_step * x_acc,
        theta + time_step * theta_dot, theta_dot + time_step * theta_acc};
    const bool terminated = next[0] < -cart_position_threshold ||
        next[0] > cart_position_threshold || next[2] < -pole_angle_threshold ||
        next[2] > pole_angle_threshold;
    return {next, terminated};
}

struct Candidate {
    std::size_t plan_index;
    ControlIndices controls;
    State terminal_state;
    std::size_t reward;
    std::size_t steps_executed;
    bool terminated;
};

Candidate evaluate(std::size_t plan_index) {
    Candidate result{plan_index, {}, initial_state, 0, 0, false};
    for (std::size_t stage = 0; stage < horizon; ++stage)
        result.controls[stage] = static_cast<std::uint8_t>((plan_index >> stage) & 1U);
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        const auto transition = advance_state(result.terminal_state, result.controls[stage]);
        result.terminal_state = transition.state;
        ++result.steps_executed;
        ++result.reward; // Gym 0.21 CartPole pays +1 on the termination step.
        if (transition.terminated) {
            result.terminated = true;
            break;
        }
    }
    return result;
}

std::vector<Candidate> enumerate_candidates() {
    std::vector<Candidate> candidates;
    candidates.reserve(plan_count);
    for (std::size_t index = 0; index < plan_count; ++index)
        candidates.push_back(evaluate(index));
    return candidates;
}

Json state_json(const State& state) { return {state[0], state[1], state[2], state[3]}; }

Json make_result(const std::vector<Candidate>& candidates,
    const std::vector<std::int64_t>& elapsed_ns, std::size_t measured_repetitions) {
    std::size_t maximum_reward = 0;
    std::size_t transition_count = 0;
    std::size_t terminated_plan_count = 0;
    std::size_t terminated_before_horizon_count = 0;
    for (const auto& candidate : candidates) {
        maximum_reward = std::max(maximum_reward, candidate.reward);
        transition_count += candidate.steps_executed;
        terminated_plan_count += static_cast<std::size_t>(candidate.terminated);
        terminated_before_horizon_count += static_cast<std::size_t>(
            candidate.terminated && candidate.steps_executed < horizon);
    }
    Json plans = Json::array();
    Json maximizers = Json::array();
    for (const auto& candidate : candidates) {
        plans.push_back({{"plan_index", candidate.plan_index}, {"control_indices", candidate.controls},
            {"reward", candidate.reward}, {"steps_executed", candidate.steps_executed},
            {"terminated", candidate.terminated}, {"terminal_state", state_json(candidate.terminal_state)}});
        if (candidate.reward == maximum_reward) maximizers.push_back(candidate.plan_index);
    }
    const auto sorted_ns = [&elapsed_ns] {
        auto values = elapsed_ns;
        std::sort(values.begin(), values.end());
        return values;
    }();
    const std::int64_t median_ns = sorted_ns.size() % 2 == 1 ? sorted_ns[sorted_ns.size() / 2] :
        sorted_ns[sorted_ns.size() / 2 - 1] / 2 + sorted_ns[sorted_ns.size() / 2] / 2;
    return {{"schema", "csl.env717-cartpole/1"},
        {"scenario_id", "env717-cartpole-center-start-14-step-finite-catalogue-v1"},
        {"reference_variant", "equation-replayed Gym CartPole-v1 finite-horizon adaptation"},
        {"upstream_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"upstream_environment_notebook", "Environments/CartPole/CartPole.ipynb"},
        {"upstream_environment_notebook_blob", "21d1122b701df85e21b5225fdbd42ff9f3bd702e"},
        {"upstream_learning_notebook", "CartPole_with_DCEM.ipynb"},
        {"upstream_learning_notebook_blob", "5af9324376c342da177a411394730ccc3f7edd5b"},
        {"upstream_solver", "Solvers/OneAgentSolver.py"},
        {"upstream_solver_blob", "87485e23497e286022d76c6f2e70e0469aa18584"},
        {"upstream_dependency_status", "the upstream repository does not pin Gym; adopted Gym v0.21.0 because the pinned solver expects the legacy reset/step API"},
        {"simulator_repository", "openai/gym"}, {"simulator_version", "v0.21.0"},
        {"simulator_commit", "c755d5c35a25ab118746e2ba885894ff66fb8c43"},
        {"simulator_source", "gym/envs/classic_control/cartpole.py"},
        {"simulator_source_blob", "e11adcba6f413017e8661e8990dde668a63a129c"},
        {"simulator_registry_source", "gym/envs/__init__.py"},
        {"simulator_registry_blob", "a90b0370730e74d783971a1a3f0771c5a2fb572e"},
        {"simulator_license", "MIT"},
        {"upstream_repository_license", "no license declared in repository metadata; this report independently re-expresses the equations and copies no upstream implementation"},
        {"state_order", {"cart_position_m", "cart_velocity_m_per_s", "pole_angle_rad", "pole_angular_velocity_rad_per_s"}},
        {"source_parameters", {{"gravity_m_per_s2", gravity}, {"cart_mass_kg", cart_mass},
            {"pole_mass_kg", pole_mass}, {"pole_half_length_m", half_pole_length},
            {"force_magnitude_newtons", force_magnitude}, {"sample_period_seconds", time_step},
            {"cart_position_termination_threshold_m", cart_position_threshold},
            {"pole_angle_termination_threshold_rad", pole_angle_threshold},
            {"registered_cartpole_v1_time_limit_steps", 500},
            {"reset_support", {{-0.05, 0.05}, {-0.05, 0.05}, {-0.05, 0.05}, {-0.05, 0.05}}},
            {"initial_state", initial_state},
            {"integrator", "explicit Euler using old position and angle rates"},
            {"reward", "+1 per action, including the first terminal action"},
            {"termination", "strict cart position or pole angle threshold; stop immediately on done"}}},
        {"adaptation", {{"horizon_environment_steps", horizon},
            {"finite_action_catalogue", {{0, "push left", -force_magnitude}, {1, "push right", force_magnitude}}},
            {"plan_count", candidates.size()}, {"plan_encoding", "bit k selects action at environment step k; all binary plans enumerated"},
            {"initial_state_choice", "the exact zero vector, the midpoint of the source reset support"},
            {"time_limit_handling", "the 14-step pilot horizon is shorter than CartPole-v1's 500-step wrapper cap"},
            {"semantics", "finite open-loop action sequences; action history is fixed before the first transition"},
            {"claim_boundary", "maximum reward over this initial state and 14-step finite action catalogue only; not a learned policy or the original 500-step task"}}},
        {"objective_value", maximum_reward}, {"maximizing_plan_indices", maximizers},
        {"enumeration", {{"plan_count", candidates.size()}, {"transition_count", transition_count},
            {"terminated_plan_count", terminated_plan_count},
            {"terminated_before_horizon_count", terminated_before_horizon_count},
            {"all_plans_completed", candidates.size() == plan_count}}},
        {"performance", {{"metric", "finite_catalogue_enumeration_elapsed"}, {"unit", "ns"},
            {"scope", "steady_clock interval around allocation, dynamics propagation, termination checks, and reward evaluation for all 16384 plans; excludes JSON construction and serialization"},
            {"worker_threads", 1}, {"warmup_repetitions", warmup_repetitions},
            {"measured_repetitions", measured_repetitions}, {"raw_elapsed_ns", elapsed_ns},
            {"median_elapsed_ns", median_ns}, {"minimum_elapsed_ns", sorted_ns.front()},
            {"maximum_elapsed_ns", sorted_ns.back()}, {"timing_clock", "std::chrono::steady_clock"}}},
        {"driver_sha256", CSL_ENV717_CARTPOLE_DRIVER_SHA256},
        {"source_commit", CSL_ENV717_CARTPOLE_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_CARTPOLE_COMPILER_ID},
            {"compiler_version", CSL_ENV717_CARTPOLE_COMPILER_VERSION},
            {"build_type", CSL_ENV717_CARTPOLE_BUILD_TYPE},
            {"architecture", CSL_ENV717_CARTPOLE_ARCHITECTURE}}},
        {"plans", plans}};
}
}

int main(int argc, char** argv) {
    try {
        std::size_t measured_repetitions = 9;
        if (argc == 3 && std::string_view(argv[1]) == "--measure") {
            const std::string_view value(argv[2]);
            const auto parsed = std::from_chars(value.data(), value.data() + value.size(), measured_repetitions);
            if (value.empty() || parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                measured_repetitions == 0 || measured_repetitions > 1000)
                throw std::invalid_argument("measurement repetitions must be in 1..1000");
        } else if (argc != 1) {
            throw std::invalid_argument("usage: csl_env717_cartpole [--measure REPETITIONS]");
        }
        std::vector<Candidate> candidates;
        std::vector<std::int64_t> elapsed_ns;
        elapsed_ns.reserve(measured_repetitions);
        for (std::size_t repetition = 0; repetition < warmup_repetitions + measured_repetitions; ++repetition) {
            const auto start = std::chrono::steady_clock::now();
            auto current = enumerate_candidates();
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - start).count();
            if (elapsed <= 0) throw std::runtime_error("nonpositive enumeration duration");
            if (repetition >= warmup_repetitions) elapsed_ns.push_back(elapsed);
            if (repetition + 1 == warmup_repetitions + measured_repetitions)
                candidates = std::move(current);
        }
        std::cout << make_result(candidates, elapsed_ns, measured_repetitions).dump(2) << '\n';
    } catch (const std::exception& error) {
        std::cerr << "CartPole finite-action pilot failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
