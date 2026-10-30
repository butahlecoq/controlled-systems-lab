#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/values.hpp>
#include <csl/execution/contracts.hpp>
#include <chrono>
#include <cstddef>
#include <functional>
#include <optional>
#include <span>
#include <string>
#include <variant>
#include <vector>

namespace csl::simulation {

struct PlantParameter { std::string name; double value; std::string unit; bool operator==(const PlantParameter&) const = default; };
struct PlantIdentity { std::string name, version, source; bool operator==(const PlantIdentity&) const = default; };
enum class IntegrationMethod { exact_discrete_map, adaptive_rk4_step_doubling };
enum class ControlHold { constant_on_interval };
struct IntegrationLimits {
    double absolute_tolerance{1e-9};
    double relative_tolerance{1e-9};
    std::size_t max_attempts_per_interval{100000};
    bool operator==(const IntegrationLimits&) const = default;
};

using DiscreteTransition = std::function<Vector(std::span<const double> state,
    std::span<const double> control, std::span<const PlantParameter> parameters,
    double start_time, double end_time)>;
using TerminalObjective = std::function<double(std::span<const double> terminal_state,
    std::span<const PlantParameter> parameters)>;
using ContinuousDynamics = std::function<Vector(double time, std::span<const double> state,
    std::span<const double> control, std::span<const PlantParameter> parameters)>;

// The callbacks specify an independent plant. The declaration is retained in
// replay output so that controls, units and physical timing can be audited.
struct Plant {
    PlantIdentity identity;
    std::optional<std::vector<PlantParameter>> parameters;
    std::optional<Vector> initial_state;
    std::optional<std::vector<double>> times;
    std::string time_unit;
    std::vector<std::string> state_units, control_units;
    std::string objective_name, objective_unit;
    std::optional<IntegrationMethod> integration;
    std::optional<ControlHold> hold;
    std::optional<NumericalPolicy> numerical;
    std::optional<IntegrationLimits> integration_limits;
    DiscreteTransition transition;
    ContinuousDynamics dynamics;
    TerminalObjective objective;
};

enum class ReplayStatus { complete, unavailable, invalid_input, numerical_failure,
    callback_failure, cancelled, resource_limit };

enum class IntegrationResidualUnavailableReason { legacy_artifact, not_recorded };
struct IntegrationResidualNotApplicable {};
struct IntegrationResidualUnavailable {
    IntegrationResidualUnavailableReason reason{IntegrationResidualUnavailableReason::not_recorded};
};
struct IntegrationResidualMeasurement {
    std::string name;
    double value{};
    std::string unit;
    bool operator==(const IntegrationResidualMeasurement&) const = default;
};
struct AvailableIntegrationResidual {
    std::string definition;
    std::vector<IntegrationResidualMeasurement> measurements;
};
struct IntegrationIntervalReceipt {
    std::size_t accepted_steps{};
    std::size_t rejected_steps{};
    std::vector<double> max_accepted_local_error_estimates;
};
using IntegrationResidualEvidence = std::variant<IntegrationResidualNotApplicable,
    IntegrationResidualUnavailable, AvailableIntegrationResidual>;

struct ReplayRecord {
    ReplayStatus status{ReplayStatus::unavailable};
    PlantIdentity plant;
    std::vector<PlantParameter> parameters;
    std::optional<Vector> declared_initial_state;
    std::string time_unit;
    std::vector<std::string> state_units, control_units;
    std::string objective_name, objective_unit;
    std::optional<IntegrationMethod> integration;
    std::optional<ControlHold> hold;
    std::optional<NumericalPolicy> numerical;
    std::optional<IntegrationLimits> integration_limits;
    std::vector<IntegrationIntervalReceipt> integration_receipts;
    IntegrationResidualEvidence integration_residual;
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
