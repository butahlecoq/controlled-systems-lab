#include <csl/optimization/history_cost.hpp>
#include <csl/optimization/objectives.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <ranges>
#include <type_traits>

namespace csl::optimization {
namespace {

Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

Diagnostic unsupported(std::string field, std::string explanation) {
    return {DiagnosticCode::unsupported, std::move(field), std::move(explanation)};
}

OperationStopped numerical_failure(std::string explanation) {
    return {StopReason::numerical_failure, std::move(explanation)};
}

bool finite_values(std::span<const double> values) {
    return std::ranges::all_of(values, [](double value) { return std::isfinite(value); });
}

std::optional<std::size_t> history_dimension(const JointCoordinates& coordinates) {
    if(coordinates.dimensions.external != 0 || coordinates.horizon == std::numeric_limits<std::size_t>::max())
        return std::nullopt;
    const auto state_stages = coordinates.horizon + 1;
    if(coordinates.dimensions.state != 0 && state_stages > std::numeric_limits<std::size_t>::max() / coordinates.dimensions.state)
        return std::nullopt;
    const auto state_size = coordinates.dimensions.state * state_stages;
    if(coordinates.dimensions.control != 0 && coordinates.horizon >
       (std::numeric_limits<std::size_t>::max() - state_size) / coordinates.dimensions.control)
        return std::nullopt;
    return state_size + coordinates.dimensions.control * coordinates.horizon;
}

std::size_t terminal_offset(const JointCoordinates& coordinates) {
    return coordinates.dimensions.state * coordinates.horizon;
}

std::size_t control_offset(const JointCoordinates& coordinates) {
    return coordinates.dimensions.state * (coordinates.horizon + 1);
}

bool add_finite(double& destination, double value) {
    const auto sum = destination + value;
    if(!std::isfinite(sum)) return false;
    destination = sum;
    return true;
}

bool add_residual_norm(std::vector<WeightedHistoryResidualNorm>& destination,
        Matrix map, Vector target, Vector weights, double coefficient) {
    if(coefficient == 0.0) return true;
    destination.push_back({std::move(map), std::move(target), std::move(weights), coefficient});
    return true;
}

HistoryCostCompilation compile_failure(Diagnostic diagnostic) {
    return Diagnostics{std::move(diagnostic)};
}

} // namespace

HistoryCostCompilation compile_history_cost(const synthesis::JointHistoryRelation& history,
        const TerminalObjective& terminal, const RunningControlCost& running,
        std::size_t absolute_stage_offset) {
    const auto coordinate_dimension = history_dimension(history.coordinates);
    if(!coordinate_dimension)
        return compile_failure(invalid("history_cost.coordinates", "Canonical history dimensions overflow or include unsupported external coordinates."));
    const auto metadata = history.relation.metadata();
    if(!metadata || metadata->set.dimension != *coordinate_dimension)
        return compile_failure(invalid("history_cost.relation", "The supplied feasible relation dimension does not match its canonical history coordinates."));

    auto source_terminal = snapshot(terminal);
    if(const auto* error = std::get_if<Diagnostic>(&source_terminal)) return compile_failure(*error);
    if(const auto* stopped = std::get_if<OperationStopped>(&source_terminal)) return *stopped;
    if(std::get<Objective>(source_terminal).dimension() != history.coordinates.dimensions.state)
        return compile_failure(invalid("history_cost.terminal", "Terminal objective dimension must match the history state dimension."));

    if(auto errors = validate_running_control_cost(running, absolute_stage_offset,
            history.coordinates.horizon, history.coordinates.dimensions.control); !errors.empty())
        return errors;

    const auto n = *coordinate_dimension;
    if(n != 0 && n > std::numeric_limits<std::size_t>::max() / n)
        return compile_failure(invalid("history_cost.quadratic", "History quadratic matrix dimensions overflow."));
    HistoryQuadraticPolynomial quadratic{n, {n, n, Vector(n * n, 0.0)}, Vector(n, 0.0), 0.0};
    std::vector<WeightedHistoryResidualNorm> norms;
    const auto state_offset = terminal_offset(history.coordinates);
    const auto controls_offset = control_offset(history.coordinates);
    const auto state_dimension = history.coordinates.dimensions.state;

    const auto terminal_result = std::visit([&](const auto& source) -> std::optional<Diagnostic> {
        using T = std::decay_t<decltype(source)>;
        if constexpr(std::is_same_v<T, LinearTerminal>) {
            for(std::size_t i = 0; i < state_dimension; ++i)
                quadratic.linear[state_offset + i] = source.coefficients[i];
            quadratic.offset = source.offset;
        } else if constexpr(std::is_same_v<T, QuadraticTerminal>) {
            for(std::size_t i = 0; i < state_dimension; ++i) {
                quadratic.linear[state_offset + i] = source.linear[i];
                for(std::size_t j = 0; j < state_dimension; ++j) {
                    const auto value = 0.5 * (source.Q.values[i * state_dimension + j] +
                        source.Q.values[j * state_dimension + i]);
                    if(!std::isfinite(value)) return invalid("history_cost.terminal", "Symmetric terminal Hessian overflowed binary64.");
                    quadratic.Q.values[(state_offset + i) * n + state_offset + j] = value;
                }
            }
            quadratic.offset = source.offset;
        } else {
            Matrix map{source.map.rows, n, Vector(source.map.rows * n, 0.0)};
            for(std::size_t row = 0; row < source.map.rows; ++row)
                for(std::size_t column = 0; column < state_dimension; ++column)
                    map.values[row * n + state_offset + column] = source.map.values[row * state_dimension + column];
            auto weights = source.weights;
            if(weights.empty()) weights.assign(source.map.rows, 1.0);
            add_residual_norm(norms, std::move(map), source.target, std::move(weights), 1.0);
        }
        return std::nullopt;
    }, terminal);
    if(terminal_result) return compile_failure(*terminal_result);

    for(const auto& stage : running.stages) {
        if(stage.stage < absolute_stage_offset || stage.stage - absolute_stage_offset >= history.coordinates.horizon)
            continue;
        const auto local_stage = stage.stage - absolute_stage_offset;
        const auto control_stage_offset = controls_offset + local_stage * history.coordinates.dimensions.control;
        for(const auto& term : stage.terms) {
            if(const auto* penalty = std::get_if<QuadraticControlPenalty>(&term)) {
                for(std::size_t i = 0; i < history.coordinates.dimensions.control; ++i) {
                    const auto weight = penalty->coefficient * penalty->weights[i] /
                        static_cast<double>(penalty->normalization_horizon) /
                        (penalty->scales[i] * penalty->scales[i]);
                    const auto hessian = 2.0 * weight;
                    const auto linear = -2.0 * weight * penalty->reference[i];
                    const auto constant = weight * penalty->reference[i] * penalty->reference[i];
                    if(!std::isfinite(hessian) || !std::isfinite(linear) || !std::isfinite(constant) ||
                       !add_finite(quadratic.Q.values[(control_stage_offset + i) * n + control_stage_offset + i], hessian) ||
                       !add_finite(quadratic.linear[control_stage_offset + i], linear) ||
                       !add_finite(quadratic.offset, constant))
                        return compile_failure(unsupported("history_cost.running.quadratic", "Quadratic source terms overflow the binary64 history polynomial."));
                }
            } else {
                const auto& norm_penalty = std::get<EuclideanControlPenalty>(term);
                Matrix map{norm_penalty.map.rows, n, Vector(norm_penalty.map.rows * n, 0.0)};
                Vector target(norm_penalty.map.rows);
                for(std::size_t row = 0; row < norm_penalty.map.rows; ++row) {
                    target[row] = -norm_penalty.offset[row];
                    for(std::size_t column = 0; column < norm_penalty.map.cols; ++column)
                        map.values[row * n + control_stage_offset + column] = norm_penalty.map.values[row * norm_penalty.map.cols + column];
                }
                add_residual_norm(norms, std::move(map), std::move(target),
                    Vector(norm_penalty.map.rows, 1.0), norm_penalty.coefficient);
            }
        }
    }

    return HistoryCostProgram{history.coordinates, std::move(quadratic), std::move(norms),
        terminal, running, absolute_stage_offset};
}

HistoryCostResult evaluate_history_cost(const HistoryCostProgram& program,
        std::span<const Vector> states, std::span<const Vector> controls) {
    const auto& dimensions = program.coordinates.dimensions;
    if(states.size() != program.coordinates.horizon + 1 || controls.size() != program.coordinates.horizon)
        return Diagnostics{invalid("history_cost.history", "State and control history lengths do not match the compiled coordinates.")};
    for(const auto& state : states)
        if(state.size() != dimensions.state || !finite_values(state))
            return Diagnostics{invalid("history_cost.states", "Every state must be finite and match the compiled state dimension.")};
    for(const auto& control : controls)
        if(control.size() != dimensions.control || !finite_values(control))
            return Diagnostics{invalid("history_cost.controls", "Every control must be finite and match the compiled control dimension.")};

    auto objective = snapshot(program.terminal_source);
    if(const auto* error = std::get_if<Diagnostic>(&objective)) return Diagnostics{*error};
    if(const auto* stopped = std::get_if<OperationStopped>(&objective)) return *stopped;
    auto terminal_value = evaluate(std::get<Objective>(objective), states.back());
    if(const auto* error = std::get_if<Diagnostic>(&terminal_value)) return Diagnostics{*error};
    if(const auto* stopped = std::get_if<OperationStopped>(&terminal_value)) return *stopped;
    auto running_value = evaluate_running_control_cost(program.running_source,
        program.absolute_stage_offset, program.coordinates.horizon, controls, dimensions.control);
    if(const auto* errors = std::get_if<Diagnostics>(&running_value)) return *errors;
    if(const auto* stopped = std::get_if<OperationStopped>(&running_value)) return *stopped;
    const auto terminal = std::get<double>(terminal_value);
    const auto running = std::get<double>(running_value);
    const auto total = terminal + running;
    if(!std::isfinite(total)) return numerical_failure("Combined source objective overflowed binary64.");
    return HistoryCostEvaluation{terminal, running, total};
}

} // namespace csl::optimization
