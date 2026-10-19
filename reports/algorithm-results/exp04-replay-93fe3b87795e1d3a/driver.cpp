#include <csl/simulation/nonlinear_replay.hpp>
#include <array>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <span>
#include <string_view>
#include <vector>

using namespace csl;
using namespace csl::simulation;

namespace {
Plant scalar() {
    Plant plant;
    plant.identity = {"analytic.quadratic-step", "1", "EXP-04 declared analytic toy"};
    plant.parameters = std::vector<PlantParameter>{{"quadratic_gain", 1.0, "dimensionless"}};
    plant.initial_state = Vector{0.0};
    plant.times = std::vector<double>{0.0, 1.0, 2.0};
    plant.state_units = {"dimensionless"};
    plant.control_units = {"dimensionless"};
    plant.objective_name = "terminal state";
    plant.objective_unit = "dimensionless";
    plant.integration = IntegrationMethod::exact_discrete_map;
    plant.hold = ControlHold::constant_on_interval;
    plant.numerical = NumericalPolicy{1e-12, 1e-12};
    plant.transition = [](std::span<const double> state, std::span<const double> control,
        std::span<const PlantParameter> parameters, double, double) {
        const double u = control[0];
        return Vector{state[0] + u + parameters[0].value*u*u};
    };
    plant.objective = [](std::span<const double> state, std::span<const PlantParameter>) {
        return state[0];
    };
    return plant;
}

Plant plane() {
    auto plant = scalar();
    plant.identity = {"analytic.interval-plane", "1", "EXP-04 declared two-state toy"};
    plant.initial_state = Vector{0.0, 0.0};
    plant.times = std::vector<double>{0.0, 1.0, 3.0};
    plant.state_units = {"length", "action"};
    plant.objective_name = "terminal length";
    plant.objective_unit = "length";
    plant.transition = [](std::span<const double> state, std::span<const double> control,
        std::span<const PlantParameter> parameters, double start, double end) {
        const double u = control[0];
        return Vector{state[0] + (end-start)*u + parameters[0].value*u*u, state[1]+u};
    };
    return plant;
}

struct Case {
    std::string_view name;
    Plant plant;
    std::vector<Vector> controls;
    std::vector<Vector> expected;
};

bool run(const Case& item, std::string_view phase, int repetition, int calls) {
    std::chrono::nanoseconds elapsed{};
    for (int index = 0; index < calls; ++index) {
        const auto record = replay(item.plant, item.controls);
        if (record.status != ReplayStatus::complete || record.states != item.expected ||
            !record.original_objective ||
            *record.original_objective != item.expected.back()[0] ||
            record.declared_initial_state != item.plant.initial_state ||
            record.plant.name != item.plant.identity.name ||
            record.controls != item.controls || record.times != *item.plant.times) return false;
        elapsed += std::chrono::duration_cast<std::chrono::nanoseconds>(record.replay_time);
    }
    const auto& terminal = item.expected.back();
    std::cout << phase << ',' << item.name << ',' << repetition << ',' << calls
              << ",complete,true," << elapsed.count() << ',' << terminal[0] << ','
              << (terminal.size() == 2 ? terminal[1] : 0.0) << ',' << terminal[0] << '\n';
    return true;
}
}

int main(int argc, char** argv) {
    if (argc != 2 || (std::string_view(argv[1]) != "smoke" &&
                      std::string_view(argv[1]) != "measure")) return EXIT_FAILURE;
    const std::array<Case, 4> cases{{
        {"scalar-endpoint", scalar(), {{0.0}, {1.0}}, {{0.0}, {0.0}, {2.0}}},
        {"scalar-even", scalar(), {{0.5}, {0.5}}, {{0.0}, {0.75}, {1.5}}},
        {"plane-forward", plane(), {{0.0}, {1.0}}, {{0.0,0.0}, {0.0,0.0}, {3.0,1.0}}},
        {"plane-reverse", plane(), {{1.0}, {0.0}}, {{0.0,0.0}, {2.0,1.0}, {2.0,1.0}}},
    }};
    std::cout << "phase,case,repetition,calls,status,verified,elapsed_ns,terminal_x,terminal_y,objective\n";
    if (std::string_view(argv[1]) == "smoke") {
        for (const auto& item : cases) if (!run(item, "smoke", 0, 1)) return EXIT_FAILURE;
    } else {
        for (const auto& item : cases) if (!run(item, "warmup", 0, 1000)) return EXIT_FAILURE;
        for (int repetition = 0; repetition < 7; ++repetition)
            for (int offset = 0; offset < 4; ++offset)
                if (!run(cases[(offset + repetition) % 4], "trial", repetition, 1000))
                    return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
