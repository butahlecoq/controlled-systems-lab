#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

namespace {
using Json = nlohmann::json;
using State = std::array<double, 4>; // radius, radial velocity, angle, angular rate
using Action = std::array<double, 2>;
using Plan = std::array<std::uint8_t, 3>;

constexpr double gravitational_constant = 6.67448478e-20; // km^3 kg^-1 s^-2
constexpr double earth_mass_kg = 5.9726e24;
constexpr double vehicle_mass_kg = 50.0;
constexpr double sample_period_seconds = 100.0;
constexpr std::size_t inner_steps = 100;
constexpr std::size_t horizon = 20;
constexpr std::array<std::size_t, 3> block_lengths{7, 7, 6};
constexpr std::array<Action, 9> actions{{
    {-0.5, -0.5}, {-0.5, 0.0}, {-0.5, 0.5},
    {0.0, -0.5}, {0.0, 0.0}, {0.0, 0.5},
    {0.5, -0.5}, {0.5, 0.0}, {0.5, 0.5}}};
constexpr std::size_t plan_count = 9 * 9 * 9;
constexpr std::size_t warmups = 2;
constexpr std::size_t default_repetitions = 7;
constexpr double initial_radius_km = 7000.0;
constexpr double required_orbit_km = 6900.0;
constexpr double running_action_cost = 0.001;

struct PlanResult {
    std::size_t index{};
    Plan controls{};
    double objective{};
    State terminal{};
};

struct SearchResult {
    std::vector<PlanResult> plans;
    std::size_t selected_index{};
    double minimum{};
};

State derivative(const State& state, const Action& action) {
    const double radius = state[0];
    const double radial_velocity = state[1];
    const double angular_rate = state[3];
    return {
        radial_velocity,
        radius * angular_rate * angular_rate - gravitational_constant * earth_mass_kg / (radius * radius)
            + action[0] / (1000.0 * vehicle_mass_kg),
        angular_rate,
        -2.0 * angular_rate * radial_velocity / radius
            + action[1] / (radius * vehicle_mass_kg * 1000.0)};
}

State add_scaled(const State& state, const State& delta, double scale) {
    State result{};
    for(std::size_t i = 0; i < result.size(); ++i) result[i] = state[i] + scale * delta[i];
    return result;
}

State advance(State state, const Action& action) {
    constexpr double step = sample_period_seconds / static_cast<double>(inner_steps);
    for(std::size_t i = 0; i < inner_steps; ++i) {
        const auto k1 = derivative(state, action);
        const auto k2 = derivative(add_scaled(state, k1, step / 2.0), action);
        const auto k3 = derivative(add_scaled(state, k2, step / 2.0), action);
        const auto k4 = derivative(add_scaled(state, k3, step), action);
        for(std::size_t j = 0; j < state.size(); ++j)
            state[j] += step * (k1[j] + 2.0 * k2[j] + 2.0 * k3[j] + k4[j]) / 6.0;
    }
    return state;
}

double action_norm(const Action& action) {
    return std::hypot(action[0], action[1]);
}

double terminal_cost(const State& state) {
    const double target_rate = std::sqrt(gravitational_constant * earth_mass_kg /
        (required_orbit_km * required_orbit_km * required_orbit_km));
    return std::hypot(required_orbit_km - state[0], 100000.0 * (target_rate - state[3]));
}

Plan decode(std::size_t index) {
    Plan result{};
    for(auto& action : result) {
        action = static_cast<std::uint8_t>(index % actions.size());
        index /= actions.size();
    }
    return result;
}

PlanResult evaluate(std::size_t index) {
    const auto controls = decode(index);
    const double initial_rate = std::sqrt(gravitational_constant * earth_mass_kg /
        (initial_radius_km * initial_radius_km * initial_radius_km));
    State state{initial_radius_km, 0.0, 0.0, initial_rate};
    double objective = 0.0;
    std::size_t stage = 0;
    for(std::size_t block = 0; block < block_lengths.size(); ++block) {
        const auto& action = actions[controls[block]];
        for(std::size_t local = 0; local < block_lengths[block]; ++local, ++stage) {
            state = advance(state, action);
            if(stage + 1 == horizon) objective += terminal_cost(state);
            else objective += running_action_cost * action_norm(action) * sample_period_seconds;
        }
    }
    return {index, controls, objective, state};
}

SearchResult enumerate() {
    SearchResult result;
    result.plans.reserve(plan_count);
    result.minimum = std::numeric_limits<double>::infinity();
    for(std::size_t index = 0; index < plan_count; ++index) {
        auto current = evaluate(index);
        if(current.objective < result.minimum) {
            result.minimum = current.objective;
            result.selected_index = index;
        }
        result.plans.push_back(std::move(current));
    }
    return result;
}

int read_repetitions(int argc, char** argv) {
    if(argc == 1) return static_cast<int>(default_repetitions);
    if(argc != 3 || std::string_view(argv[1]) != "--repetitions")
        throw std::runtime_error("usage: csl_env717_earth_orbit [--repetitions N]");
    const int count = std::stoi(argv[2]);
    if(count < 1 || count > 100) throw std::runtime_error("repetitions must be in [1, 100]");
    return count;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const int repetitions = read_repetitions(argc, argv);
        for(std::size_t i = 0; i < warmups; ++i) (void)enumerate();
        std::vector<std::int64_t> durations_ns;
        durations_ns.reserve(static_cast<std::size_t>(repetitions));
        SearchResult result;
        for(int i = 0; i < repetitions; ++i) {
            const auto started = std::chrono::steady_clock::now();
            result = enumerate();
            const auto stopped = std::chrono::steady_clock::now();
            durations_ns.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(stopped - started).count());
        }

        Json plans = Json::array();
        for(const auto& plan : result.plans) {
            Json controls = Json::array();
            for(const auto index : plan.controls) controls.push_back(index);
            plans.push_back({{"plan_index", plan.index}, {"control_indices", std::move(controls)},
                {"objective_cost", plan.objective}, {"terminal_state", plan.terminal}});
        }
        Json output{{"schema", "csl.env717-earth-orbit/1"},
            {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
            {"source_commit", CSL_ENV717_SOURCE_COMMIT},
            {"source_file_blob", "ce97d9d223a6ba6d02ce9a8f6a2fba26ef0fdd7d"},
            {"driver_sha256", CSL_ENV717_DRIVER_SHA256},
            {"algorithm_source_sha256", CSL_ENV717_ALGORITHM_SOURCE_SHA256},
            {"compiler_id", CSL_ENV717_COMPILER_ID},
            {"compiler_version", CSL_ENV717_COMPILER_VERSION},
            {"build_type", CSL_ENV717_BUILD_TYPE},
            {"architecture", CSL_ENV717_ARCHITECTURE},
            {"plan_count", plan_count}, {"selected_plan_index", result.selected_index},
            {"minimum_objective_cost", result.minimum}, {"warmups", warmups},
            {"measured_repetitions_ns", durations_ns}, {"plans", std::move(plans)}};
        std::cout << output.dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
