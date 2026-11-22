#include <csl/optimization/running_control_cost.hpp>

#include "running_cost_evaluation.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <ranges>

namespace csl::optimization {
namespace {

Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

Diagnostic arithmetic_failure() {
    return {DiagnosticCode::unsupported, "running_cost.arithmetic",
            "Running-cost arithmetic did not produce a finite binary64 result."};
}

bool finite_values(std::span<const double> values) {
    return std::ranges::all_of(values, [](double value) { return std::isfinite(value); });
}

double stage_cost(const AbsoluteStageControlCost &stage, std::span<const double> control) {
    double total = 0.0;
    for (const auto &term : stage.terms) {
        if (const auto *quadratic = std::get_if<QuadraticControlPenalty>(&term)) {
            if (quadratic->coefficient == 0.0)
                continue;
            const auto value = detail::quadratic_stage_cost(*quadratic, control);
            if (!value)
                return std::numeric_limits<double>::quiet_NaN();
            total += *value;
        } else {
            const auto &norm = std::get<EuclideanControlPenalty>(term);
            if (norm.coefficient == 0.0)
                continue;
            double magnitude = 0.0;
            for (std::size_t row = 0; row < norm.map.rows; ++row) {
                double residual = norm.offset[row];
                for (std::size_t column = 0; column < norm.map.cols; ++column)
                    residual += norm.map.values[row * norm.map.cols + column] * control[column];
                magnitude = std::hypot(magnitude, residual);
            }
            total += norm.coefficient * magnitude;
        }
    }
    return total;
}

} // namespace

Diagnostics validate_running_control_cost(const RunningControlCost &cost,
                                          std::size_t absolute_stage_offset, std::size_t horizon,
                                          std::size_t control_dimension) {
    if (cost.stages.empty()) {
        if (!cost.objective_id.empty() || cost.original_horizon != 0)
            return {invalid(
                "running_cost",
                "An inactive running-cost schedule must have empty identity and zero original horizon.")};
        return {};
    }
    if (cost.objective_id.empty() || cost.original_horizon == 0 ||
        absolute_stage_offset > cost.original_horizon ||
        horizon > cost.original_horizon - absolute_stage_offset)
        return {invalid(
            "running_cost",
            "The objective identity and original horizon must cover the requested absolute-stage slice.")};

    std::size_t previous_stage = 0;
    bool first_stage = true;
    for (const auto &stage : cost.stages) {
        if (stage.stage >= cost.original_horizon || (!first_stage && stage.stage <= previous_stage))
            return {invalid(
                "running_cost.stages",
                "Running-cost stages must be unique, increasing, and inside the original horizon.")};
        previous_stage = stage.stage;
        first_stage = false;
        for (const auto &term : stage.terms) {
            if (const auto *quadratic = std::get_if<QuadraticControlPenalty>(&term)) {
                if (quadratic->reference.size() != control_dimension ||
                    quadratic->scales.size() != control_dimension ||
                    quadratic->weights.size() != control_dimension ||
                    quadratic->normalization_horizon != cost.original_horizon ||
                    !std::isfinite(quadratic->coefficient) || quadratic->coefficient < 0 ||
                    !finite_values(quadratic->reference) || !finite_values(quadratic->scales) ||
                    !finite_values(quadratic->weights) ||
                    !std::ranges::all_of(
                        quadratic->scales, [](double value) { return value != 0.0; }) ||
                    !std::ranges::all_of(
                        quadratic->weights, [](double value) { return value >= 0.0; }))
                    return {invalid(
                        "running_cost.quadratic",
                        "Quadratic penalty dimensions, normalization, scales, weights, or coefficient are invalid.")};
            } else {
                const auto &norm = std::get<EuclideanControlPenalty>(term);
                if (norm.map.cols != control_dimension || norm.map.rows == 0 ||
                    norm.offset.size() != norm.map.rows ||
                    norm.map.values.size() != norm.map.rows * norm.map.cols ||
                    !finite_values(norm.map.values) || !finite_values(norm.offset) ||
                    !std::isfinite(norm.coefficient) || norm.coefficient < 0)
                    return {invalid(
                        "running_cost.euclidean",
                        "Euclidean penalty dimensions, map, offset, or coefficient are invalid.")};
            }
        }
    }
    return {};
}

RunningCostEvaluation evaluate_running_control_cost(const RunningControlCost &cost,
                                                    std::size_t absolute_stage_offset,
                                                    std::size_t horizon,
                                                    std::span<const Vector> controls,
                                                    std::size_t control_dimension) {
    if (controls.size() != horizon)
        return Diagnostics{invalid("running_cost.controls",
                                   "Control history length must match the requested horizon.")};
    if (auto errors =
            validate_running_control_cost(cost, absolute_stage_offset, horizon, control_dimension);
        !errors.empty())
        return errors;
    for (const auto &control : controls)
        if (control.size() != control_dimension || !finite_values(control))
            return Diagnostics{
                invalid("running_cost.controls",
                        "Every control must be finite and match the authored control dimension.")};
    if (cost.stages.empty())
        return 0.0;

    double total = 0.0;
    for (std::size_t local_stage = 0; local_stage < horizon; ++local_stage) {
        const auto absolute_stage = absolute_stage_offset + local_stage;
        const auto found = std::lower_bound(cost.stages.begin(), cost.stages.end(), absolute_stage,
                                            [](const AbsoluteStageControlCost &row,
                                               std::size_t stage) { return row.stage < stage; });
        if (found == cost.stages.end() || found->stage != absolute_stage)
            continue;
        const auto value = stage_cost(*found, controls[local_stage]);
        if (!std::isfinite(value))
            return OperationStopped{StopReason::numerical_failure,
                                    arithmetic_failure().explanation};
        total += value;
        if (!std::isfinite(total))
            return OperationStopped{StopReason::numerical_failure,
                                    arithmetic_failure().explanation};
    }
    return total;
}

} // namespace csl::optimization
