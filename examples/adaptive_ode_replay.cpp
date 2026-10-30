#include <csl/simulation/nonlinear_replay.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <numbers>
#include <span>
#include <vector>

int main() {
    using namespace csl;
    using namespace csl::simulation;

    Plant plant;
    plant.identity = {"analytic.harmonic-oscillator", "1", "TEST-22 analytic reference"};
    plant.parameters = std::vector<PlantParameter>{};
    plant.initial_state = Vector{1.0, 0.0};
    constexpr std::size_t intervals = 64;
    plant.times.emplace();
    plant.times->reserve(intervals + 1);
    for (std::size_t i = 0; i <= intervals; ++i)
        plant.times->push_back(2.0 * std::numbers::pi * static_cast<double>(i) / intervals);
    plant.time_unit = "s";
    plant.state_units = {"1", "1"};
    plant.control_units = {"1"};
    plant.objective_name = "terminal position";
    plant.objective_unit = "1";
    plant.integration = IntegrationMethod::adaptive_rk4_step_doubling;
    plant.hold = ControlHold::constant_on_interval;
    plant.integration_limits = IntegrationLimits{1e-11, 1e-11, 10000};
    plant.dynamics = [](double, std::span<const double> state, std::span<const double>,
        std::span<const PlantParameter>) { return Vector{state[1], -state[0]}; };
    plant.objective = [](std::span<const double> state, std::span<const PlantParameter>) {
        return state[0];
    };
    const std::vector<Vector> controls(intervals, Vector{0.0});
    const auto replayed = replay(plant, controls);
    if (replayed.status != ReplayStatus::complete || replayed.states.size() != intervals + 1 ||
        !std::holds_alternative<AvailableIntegrationResidual>(replayed.integration_residual)) {
        std::cerr << "Replay failed with status " << static_cast<int>(replayed.status) << '\n';
        for (const auto& diagnostic : replayed.diagnostics)
            std::cerr << diagnostic.field << ": " << diagnostic.explanation << '\n';
        return 1;
    }

    std::cout << "# schema=csl.example.adaptive-ode-replay/1\n"
        << "# method=adaptive_rk4_step_doubling\n"
        << "# absolute_tolerance=" << std::setprecision(17) << plant.integration_limits->absolute_tolerance << '\n'
        << "# relative_tolerance=" << plant.integration_limits->relative_tolerance << '\n'
        << "# max_attempts_per_interval=" << plant.integration_limits->max_attempts_per_interval << '\n'
        << "# interval_count=" << intervals << '\n'
        << "time,x,y,reference_x,reference_y\n";
    for (std::size_t i = 0; i < replayed.states.size(); ++i) {
        const double time = replayed.times[i];
        std::cout << time << ',' << replayed.states[i][0] << ',' << replayed.states[i][1]
            << ',' << std::cos(time) << ',' << -std::sin(time) << '\n';
    }
    const auto& receipts = replayed.integration_receipts;
    std::size_t accepted = 0, rejected = 0;
    double max_x_estimate = 0.0, max_y_estimate = 0.0;
    for (const auto& receipt : receipts) {
        accepted += receipt.accepted_steps;
        rejected += receipt.rejected_steps;
        max_x_estimate = std::max(max_x_estimate, receipt.max_accepted_local_error_estimates[0]);
        max_y_estimate = std::max(max_y_estimate, receipt.max_accepted_local_error_estimates[1]);
    }
    const double final_error = std::hypot(replayed.states.back()[0] - 1.0, replayed.states.back()[1]);
    std::cout << "# accepted_steps=" << accepted << '\n'
        << "# rejected_steps=" << rejected << '\n'
        << "# max_local_error_estimate_x=" << max_x_estimate << '\n'
        << "# max_local_error_estimate_y=" << max_y_estimate << '\n'
        << "# final_state_error=" << final_error << '\n';
    return final_error < 1e-8 ? 0 : 2;
}
