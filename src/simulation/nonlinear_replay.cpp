#include <csl/simulation/nonlinear_replay.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
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
    result.integration_limits = plant.integration_limits;
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
    const bool adaptive = plant.integration == IntegrationMethod::adaptive_rk4_step_doubling;
    if (adaptive)
        prerequisite(plant.integration_limits.has_value(), "plant.integration_limits");
    else
        prerequisite(plant.numerical.has_value(), "plant.tolerances");
    prerequisite(adaptive ? static_cast<bool>(plant.dynamics) : static_cast<bool>(plant.transition),
        adaptive ? "plant.dynamics" : "plant.transition");
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
    if (plant.integration != IntegrationMethod::exact_discrete_map && !adaptive)
        return invalid("plant.integration", "The declared integration method is unsupported.");
    if (plant.hold != ControlHold::constant_on_interval)
        return invalid("plant.control_hold", "Only one constant control per interval is supported.");
    if (plant.numerical && (!finite_nonnegative(plant.numerical->absolute_tolerance)
        || !finite_nonnegative(plant.numerical->relative_tolerance)))
        return invalid("plant.tolerances", "Tolerances must be finite and nonnegative.");
    if (!adaptive && !plant.numerical)
        return invalid("plant.tolerances", "Exact-map replay requires its declared numerical policy.");
    if (adaptive && (!plant.integration_limits ||
        !finite_nonnegative(plant.integration_limits->absolute_tolerance) ||
        !finite_nonnegative(plant.integration_limits->relative_tolerance) ||
        (plant.integration_limits->absolute_tolerance == 0.0 &&
         plant.integration_limits->relative_tolerance == 0.0) ||
        plant.integration_limits->max_attempts_per_interval == 0))
        return invalid("plant.integration_limits", "Adaptive RK4 needs positive tolerances and a nonzero attempt budget.");
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
    if (adaptive) {
        result.integration_receipts.reserve(controls.size());
    }
    for (std::size_t stage=0; stage<controls.size(); ++stage) {
        if (interrupted()) return finish();
        Vector next;
        if (!adaptive) {
            try {
                next = plant.transition(result.states.back(), controls[stage], result.parameters,
                    (*plant.times)[stage], (*plant.times)[stage+1]);
            } catch (...) {
                result.status = ReplayStatus::callback_failure;
                result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.transition",
                    "The declared plant transition callback raised an exception."});
                return finish();
            }
        } else {
            const auto& limits = *plant.integration_limits;
            const double start = (*plant.times)[stage], end = (*plant.times)[stage + 1];
            auto derivative = [&](double time, std::span<const double> state) {
                auto value = plant.dynamics(time, state, controls[stage], result.parameters);
                if (value.size() != state.size())
                    throw std::domain_error("continuous-dynamics state dimension changed");
                return value;
            };
            auto rk4 = [&](double time, double step, const Vector& state) {
                const auto k1 = derivative(time, state);
                Vector y2(state.size()), y3(state.size()), y4(state.size());
                for (std::size_t i=0; i<state.size(); ++i) y2[i]=state[i]+step*k1[i]/2;
                const auto k2 = derivative(time+step/2, y2);
                for (std::size_t i=0; i<state.size(); ++i) y3[i]=state[i]+step*k2[i]/2;
                const auto k3 = derivative(time+step/2, y3);
                for (std::size_t i=0; i<state.size(); ++i) y4[i]=state[i]+step*k3[i];
                const auto k4 = derivative(time+step, y4);
                Vector output(state.size());
                for (std::size_t i=0; i<state.size(); ++i)
                    output[i]=state[i]+step*(k1[i]+2*k2[i]+2*k3[i]+k4[i])/6;
                return output;
            };
            auto state = result.states.back();
            double time = start, step = end-start;
            IntegrationIntervalReceipt receipt{0, 0, Vector(state.size(), 0.0)};
            try {
                while (time < end) {
                    if (interrupted()) return finish();
                    if (receipt.accepted_steps + receipt.rejected_steps >= limits.max_attempts_per_interval) {
                        result.status = ReplayStatus::resource_limit;
                        result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.integration_limits.max_attempts_per_interval",
                            "Adaptive RK4 exhausted the declared interval attempt budget."});
                        return finish();
                    }
                    double next_time = std::min(time+step, end);
                    const double upper_spacing = std::abs(std::nextafter(end,
                        std::numeric_limits<double>::infinity()) - end);
                    const double lower_spacing = std::abs(end - std::nextafter(end,
                        -std::numeric_limits<double>::infinity()));
                    const double resolution = std::isfinite(upper_spacing)
                        ? std::max(upper_spacing, lower_spacing) : lower_spacing;
                    if (next_time < end && end-next_time <= 2.0*resolution)
                        next_time = end;
                    const double half_time = time+(next_time-time)/2;
                    if (!(next_time > time) || !(half_time > time && half_time < next_time)) {
                        result.status = ReplayStatus::numerical_failure;
                        result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.times",
                            "Binary64 time cannot resolve the next RK4 integration step at stage " +
                            std::to_string(stage) + " (t=" + std::to_string(time) + ", next=" +
                            std::to_string(next_time) + ", end=" + std::to_string(end) + ")."});
                        return finish();
                    }
                    const double h = next_time-time;
                    const auto full = rk4(time, h, state);
                    const auto first = rk4(time, half_time-time, state);
                    const auto two_half = rk4(half_time, next_time-half_time, first);
                    if (full.size() != state.size() || first.size() != state.size() ||
                        two_half.size() != state.size() || !finite(full) || !finite(first) || !finite(two_half)) {
                        result.status = ReplayStatus::numerical_failure;
                        result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.dynamics",
                            "The ODE callback or RK4 step produced a nonfinite or wrong-dimension state."});
                        return finish();
                    }
                    double ratio = 0.0;
                    Vector estimates(state.size());
                    for (std::size_t i=0; i<state.size(); ++i) {
                        estimates[i] = std::abs(two_half[i]-full[i])/15.0;
                        const double scale = limits.absolute_tolerance + limits.relative_tolerance *
                            std::max(std::abs(state[i]), std::abs(two_half[i]));
                        if (!std::isfinite(estimates[i]) || !std::isfinite(scale) || scale <= 0.0) {
                            result.status = ReplayStatus::numerical_failure;
                            result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.integration_limits",
                                "RK4 error estimate or tolerance scale is nonfinite."});
                            return finish();
                        }
                        ratio = std::max(ratio, estimates[i]/scale);
                    }
                    if (ratio > 1.0) {
                        ++receipt.rejected_steps;
                        step = h/2.0;
                        continue;
                    }
                    state = two_half;
                    time = next_time;
                    ++receipt.accepted_steps;
                    for (std::size_t i=0; i<state.size(); ++i)
                        receipt.max_accepted_local_error_estimates[i] = std::max(
                            receipt.max_accepted_local_error_estimates[i], estimates[i]);
                    if (time < end) step = ratio < 1.0/32.0 ? std::min(2.0*h, end-time) : std::min(h, end-time);
                }
            } catch (...) {
                result.status = ReplayStatus::callback_failure;
                result.diagnostics.push_back({DiagnosticCode::invalid_claim, "plant.dynamics",
                    "The declared continuous-dynamics callback raised an exception."});
                return finish();
            }
            next = std::move(state);
            result.integration_receipts.push_back(receipt);
            if (std::holds_alternative<IntegrationResidualUnavailable>(result.integration_residual))
                result.integration_residual = AvailableIntegrationResidual{
                    "Per-state maximum accepted local RK4 step-doubling estimate |y_two_half-y_full|/15; observed estimate, not a certified global error bound.", {}};
            auto& available = std::get<AvailableIntegrationResidual>(result.integration_residual);
            for (std::size_t coordinate=0; coordinate<receipt.max_accepted_local_error_estimates.size(); ++coordinate)
                available.measurements.push_back({"interval[" + std::to_string(stage) + "].state[" +
                    std::to_string(coordinate) + "]", receipt.max_accepted_local_error_estimates[coordinate],
                    plant.state_units[coordinate]});
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
