#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/values.hpp>
#include <csl/execution/contracts.hpp>
#include <chrono>
#include <functional>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace csl::simulation {

struct PlantParameter { std::string name; double value; std::string unit; };
struct PlantIdentity { std::string name, version, source; };
enum class IntegrationMethod { exact_discrete_map };
enum class ControlHold { constant_on_interval };

using DiscreteTransition = std::function<Vector(std::span<const double> state,
    std::span<const double> control, std::span<const PlantParameter> parameters,
    double start_time, double end_time)>;
using TerminalObjective = std::function<double(std::span<const double> terminal_state,
    std::span<const PlantParameter> parameters)>;

// The callbacks specify an independent plant. The declaration is retained in
// replay output so that controls, units and physical timing can be audited.
struct Plant {
    PlantIdentity identity;
    std::optional<std::vector<PlantParameter>> parameters;
    std::optional<Vector> initial_state;
    std::optional<std::vector<double>> times;
    std::vector<std::string> state_units, control_units;
    std::string objective_name, objective_unit;
    std::optional<IntegrationMethod> integration;
    std::optional<ControlHold> hold;
    std::optional<NumericalPolicy> numerical;
    DiscreteTransition transition;
    TerminalObjective objective;
};

enum class ReplayStatus { complete, unavailable, invalid_input, numerical_failure,
    callback_failure, cancelled, resource_limit };
struct ReplayRecord {
    ReplayStatus status{ReplayStatus::unavailable};
    PlantIdentity plant;
    std::vector<PlantParameter> parameters;
    std::vector<std::string> state_units, control_units;
    std::string objective_name, objective_unit;
    std::optional<IntegrationMethod> integration;
    std::optional<ControlHold> hold;
    std::optional<NumericalPolicy> numerical;
    std::vector<double> times;
    std::vector<Vector> controls, states;
    std::optional<double> original_objective;
    std::chrono::steady_clock::duration replay_time{};
    std::vector<std::string> missing_prerequisites;
    Diagnostics diagnostics;
};

// Consumes a complete ordered control history. This is sampled plant replay,
// with no claim about nonlinear optimality or historical B04 reproduction.
ReplayRecord replay(const Plant&, std::span<const Vector> controls,
    const ExecutionContext& context = {});

} // namespace csl::simulation
