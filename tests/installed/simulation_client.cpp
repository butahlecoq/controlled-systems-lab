#include <csl/simulation/nonlinear_replay.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::simulation;
    Plant plant;
    plant.identity = {"installed.quadratic-step", "1", "public analytic fixture"};
    plant.parameters = std::vector<PlantParameter>{{"gain", 1.0, "dimensionless"}};
    plant.initial_state = Vector{0.0};
    plant.times = std::vector<double>{0.0, 1.0, 2.0};
    plant.time_unit = "s";
    plant.state_units = {"dimensionless"};
    plant.control_units = {"dimensionless"};
    plant.objective_name = "terminal state";
    plant.objective_unit = "dimensionless";
    plant.integration = IntegrationMethod::exact_discrete_map;
    plant.hold = ControlHold::constant_on_interval;
    plant.numerical = NumericalPolicy{0.0, 0.0};
    plant.transition = [](std::span<const double> x, std::span<const double> u,
        std::span<const PlantParameter> p, double, double) {
        return Vector{x[0] + u[0] + p[0].value*u[0]*u[0]};
    };
    plant.objective = [](std::span<const double> x, std::span<const PlantParameter>) {
        return x[0];
    };
    const std::vector<Vector> controls{{0.5}, {0.5}};
    const auto result = replay(plant, controls);
    if (result.status != ReplayStatus::complete || result.states.size() != 3
        || result.states.back() != Vector{1.5} || result.original_objective != 1.5)
        return 1;
    std::cout << "Installed simulation client: independent nonlinear terminal 1.5 passed\n";
}
