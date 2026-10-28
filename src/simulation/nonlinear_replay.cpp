#include <csl/simulation/nonlinear_replay.hpp>
#include <algorithm>
#include <cmath>
#include <utility>

namespace csl::simulation {
namespace {
bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](double value) { return std::isfinite(value); });
}
bool finite_nonnegative(double value) { return std::isfinite(value) && value >= 0.0; }
}

ReplayRecord replay(const Plant& plant, std::span<const Vector> controls,
    const ExecutionContext& context) {
    const auto started = std::chrono::steady_clock::now();
    ReplayRecord result;
    result.plant = plant.identity;
    if (plant.parameters) result.parameters = *plant.parameters;
    result.declared_initial_state = plant.initial_state;
    if (plant.times) result.times = *plant.times;
    result.time_unit = plant.time_unit;
    result.state_units = plant.state_units;
    result.control_units = plant.control_units;
    result.objective_name = plant.objective_name;
    result.objective_unit = plant.objective_unit;
    result.integration = plant.integration;
    result.hold = plant.hold;
    result.numerical = plant.numerical;
    result.integration_residual = plant.integration == IntegrationMethod::exact_discrete_map
        ? IntegrationResidualEvidence{IntegrationResidualNotApplicable{}}
        : IntegrationResidualEvidence{IntegrationResidualUnavailable{
            IntegrationResidualUnavailableReason::not_recorded}};
    result.controls.assign(controls.begin(), controls.end());
    const auto finish = [&]() -> ReplayRecord {
        result.replay_time = std::chrono::steady_clock::now() - started;
        return std::move(result);
    };
    const auto prerequisite = [&](bool present, const char* field) {
        if (!present) result.missing_prerequisites.emplace_back(field);
    };
    prerequisite(!plant.identity.name.empty(), "plant.identity.name");
    prerequisite(!plant.identity.version.empty(), "plant.identity.version");
    prerequisite(!plant.identity.source.empty(), "plant.identity.source");
    prerequisite(plant.parameters.has_value(), "plant.parameters");
    prerequisite(plant.initial_state.has_value(), "plant.initial_state");
    prerequisite(plant.times.has_value(), "plant.times");
    prerequisite(!plant.time_unit.empty(), "plant.time_unit");
    prerequisite(!plant.state_units.empty(), "plant.state_units");
    prerequisite(!plant.control_units.empty(), "plant.control_units");
    prerequisite(!plant.objective_name.empty(), "plant.objective_name");
    prerequisite(!plant.objective_unit.empty(), "plant.objective_unit");
    prerequisite(plant.integration.has_value(), "plant.integration");
    prerequisite(plant.hold.has_value(), "plant.control_hold");
    prerequisite(plant.numerical.has_value(), "plant.tolerances");
    prerequisite(static_cast<bool>(plant.transition), "plant.transition");
    prerequisite(static_cast<bool>(plant.objective), "plant.objective");
    if (plant.times && plant.times->size() >= 2)
        prerequisite(controls.size() == plant.times->size()-1, "controls.complete_history");
    if (!result.missing_prerequisites.empty()) return finish();

    const auto invalid = [&](std::string field, std::string explanation) {
        result.status = ReplayStatus::invalid_input;
        result.diagnostics.push_back({DiagnosticCode::invalid_input,
            std::move(field), std::move(explanation)});
        return finish();
    };
    if (plant.times->size() < 2)
        return invalid("plant.times", "At least one physical transition interval is required.");
    if (plant.integration != IntegrationMethod::exact_discrete_map)
        return invalid("plant.integration", "Only an exact discrete transition map is supported.");
    if (plant.hold != ControlHold::constant_on_interval)
        return invalid("plant.control_hold", "Only one constant control per interval is supported.");
    if (!finite_nonnegative(plant.numerical->absolute_tolerance)
        || !finite_nonnegative(plant.numerical->relative_tolerance))
        return invalid("plant.tolerances", "Tolerances must be finite and nonnegative.");
    for (std::size_t index=0; index<plant.parameters->size(); ++index) {
        const auto& parameter = (*plant.parameters)[index];
        if (parameter.name.empty() || parameter.unit.empty() || !std::isfinite(parameter.value))
            return invalid("plant.parameters[" + std::to_string(index) + "]",
                "Each parameter needs a name, unit and finite value.");
    }
    if (plant.initial_state->size() != plant.state_units.size() || !finite(*plant.initial_state))
        return invalid("plant.initial_state", "Initial state must match declared units and be finite.");
    for (const auto& unit : plant.state_units)
        if (unit.empty()) return invalid("plant.state_units", "State units must be named.");
    for (const auto& unit : plant.control_units)
        if (unit.empty()) return invalid("plant.control_units", "Control units must be named.");
    if (!finite(*plant.times))
        return invalid("plant.times", "Physical times must be finite.");
    for (std::size_t stage=0; stage+1<plant.times->size(); ++stage)
        if ((*plant.times)[stage+1] <= (*plant.times)[stage])
            return invalid("plant.times", "Physical times must increase strictly.");
    for (std::size_t stage=0; stage<controls.size(); ++stage)
        if (controls[stage].size() != plant.control_units.size() || !finite(controls[stage]))
            return invalid("controls[" + std::to_string(stage) + "]",
                "Every control must match declared units and be finite.");

    const auto interrupted = [&]() {
        if (context.cancellation.stop_requested()) {
            result.status = ReplayStatus::cancelled;
            return true;
        }
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline) {
            result.status = ReplayStatus::resource_limit;
            return true;
        }
        return false;
    };
    result.states.push_back(*plant.initial_state);
    for (std::size_t stage=0; stage<controls.size(); ++stage) {
        if (interrupted()) return finish();
        Vector next;
        try {
            next = plant.transition(result.states.back(), controls[stage], result.parameters,
                (*plant.times)[stage], (*plant.times)[stage+1]);
        } catch (...) {
            result.status = ReplayStatus::callback_failure;
            result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.transition",
                "The declared plant transition callback raised an exception."});
            return finish();
        }
        if (interrupted()) return finish();
        if (next.size() != plant.state_units.size()) {
            result.status = ReplayStatus::callback_failure;
            result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.transition",
                "The declared plant transition returned the wrong state dimension."});
            return finish();
        }
        if (!finite(next)) {
            result.status = ReplayStatus::numerical_failure;
            result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.transition",
                "The declared plant transition returned a nonfinite state."});
            return finish();
        }
        result.states.push_back(std::move(next));
    }
    if (interrupted()) return finish();
    double objective;
    try {
        objective = plant.objective(result.states.back(), result.parameters);
    } catch (...) {
        result.status = ReplayStatus::callback_failure;
        result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.objective",
            "The declared plant objective callback raised an exception."});
        return finish();
    }
    if (interrupted()) return finish();
    result.original_objective = objective;
    if (!std::isfinite(*result.original_objective)) {
        result.original_objective.reset();
        result.status = ReplayStatus::numerical_failure;
        result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.objective",
            "The declared plant objective returned a nonfinite value."});
        return finish();
    }
    result.status = ReplayStatus::complete;
    return finish();
}

} // namespace csl::simulation
