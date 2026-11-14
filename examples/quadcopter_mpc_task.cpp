#include "quadcopter_mpc_task.hpp"

#include <cmath>
#include <limits>
#include <algorithm>

namespace csl::examples::quadcopter_mpc {
namespace {
using Row = std::vector<std::pair<std::size_t, double>>;

bool square(const Matrix &m, std::size_t n) {
    return m.rows == n && m.cols == n && m.values.size() == n * n;
}

void validate_cost_shapes(const NominalProblem &p) {
    const auto nx = p.initial.size(), nu = p.B.cols;
    if (!p.horizon || p.reference.size() != nx || !square(p.A, nx) || p.B.rows != nx ||
        p.B.values.size() != nx * nu || !square(p.Q, nx) || !square(p.QN, nx) || !square(p.R, nu))
        throw std::invalid_argument("Inconsistent source21 objective dimensions");
}

double quadratic(const Matrix &q, const Vector &x) {
    double v = 0;
    for (std::size_t i = 0; i < x.size(); ++i)
        for (std::size_t j = 0; j < x.size(); ++j)
            v += x[i] * q.values[i * q.cols + j] * x[j];
    return v;
}

std::vector<optimization::QuadraticHistoryStageCost> source_history_costs(const NominalProblem &p) {
    validate_cost_shapes(p);
    const auto nx = p.initial.size(), nu = p.B.cols;
    const auto scaled_hessian = [](const Matrix &q) {
        Matrix result = q;
        for (auto &value : result.values)
            value *= 2.0;
        return result;
    };
    const auto tracking_linear = [&](const Matrix &q) {
        Vector result(nx, 0.0);
        for (std::size_t i = 0; i < nx; ++i)
            for (std::size_t j = 0; j < nx; ++j)
                result[i] -= 2.0 * q.values[i * nx + j] * p.reference[j];
        return result;
    };
    const auto tracking_offset = [&](const Matrix &q) { return quadratic(q, p.reference); };
    std::vector<optimization::QuadraticHistoryStageCost> running;
    running.reserve(p.horizon);
    for (std::size_t stage = 0; stage < p.horizon; ++stage)
        running.push_back({scaled_hessian(p.Q), Matrix{nx, nu, Vector(nx * nu, 0.0)},
                           scaled_hessian(p.R), tracking_linear(p.Q), Vector(nu, 0.0),
                           tracking_offset(p.Q)});
    return running;
}

QuadraticTerminal source_terminal_cost(const NominalProblem &p) {
    const auto nx = p.initial.size();
    Matrix scaled = p.QN;
    for (auto &value : scaled.values)
        value *= 2.0;
    Vector linear(nx, 0.0);
    for (std::size_t i = 0; i < nx; ++i)
        for (std::size_t j = 0; j < nx; ++j)
            linear[i] -= 2.0 * p.QN.values[i * nx + j] * p.reference[j];
    return {std::move(scaled), std::move(linear), quadratic(p.QN, p.reference)};
}
}

optimization::NominalQuadraticHistoryTask make_task(const NominalProblem &p,
                                                    std::span<const Interval> state_bounds,
                                                    std::span<const Interval> input_bounds) {
    const auto nx = p.initial.size(), nu = p.B.cols, n = p.horizon;
    const auto running = source_history_costs(p);
    if (state_bounds.size() != nx || input_bounds.size() != nu)
        throw std::invalid_argument("Inconsistent source21 history bounds");

    std::vector<LinearStage> dynamics(n, {p.A, p.B, Matrix{nx, 0, {}}, Vector(nx, 0.0)});
    std::vector<std::vector<Interval>> staged_state_bounds(
        n + 1, std::vector<Interval>(state_bounds.begin(), state_bounds.end()));
    std::vector<std::vector<Interval>> staged_control_bounds(
        n, std::vector<Interval>(input_bounds.begin(), input_bounds.end()));
    return {{{"quadcopter-mpc"}, {"source21-horizon" + std::to_string(n)}},
            std::move(dynamics),
            KnownInitial{p.initial},
            std::move(staged_state_bounds),
            std::move(staged_control_bounds),
            std::nullopt,
            running,
            source_terminal_cost(p),
            {}};
}

controllers::AuthoredTaskChoices make_source21_choices(const NominalProblem &p,
                                                       std::size_t external_dimension) {
    const auto running = source_history_costs(p);
    auto terminal = source_terminal_cost(p);
    const auto zero_inputs = std::vector<Vector>(p.horizon, Vector(external_dimension, 0.0));
    controllers::AuthoredTaskChoices choices;
    choices.problem_id = {"quadcopter-mpc"};
    choices.program_id = {"source21-horizon" + std::to_string(p.horizon)};
    choices.profile_id = "source21-osqp-mpc";
    choices.objective_id = "source21-published-quadratic-cost";
    choices.horizon_id = "source21-fixed-horizon-per-replan";
    choices.final_stage = p.horizon;
    choices.running_costs = running;
    choices.terminal_cost = std::move(terminal);
    choices.forecast_external = zero_inputs;
    choices.forecast_id = "source21-nominal-zero-external-forecast";
    choices.replay_external = zero_inputs;
    choices.replay_id = "source21-zero-external-replay";
    return choices;
}

double evaluate_source_cost(const NominalProblem &p, std::span<const double> states,
                            std::span<const double> controls) {
    const auto nx = p.initial.size(), nu = p.B.cols;
    if (states.size() != (p.horizon + 1) * nx || controls.size() != p.horizon * nu)
        return std::numeric_limits<double>::quiet_NaN();
    double result = 0;
    auto stage = [&](std::size_t k, const Matrix &q) {
        Vector d(nx);
        for (std::size_t i = 0; i < nx; ++i)
            d[i] = states[k * nx + i] - p.reference[i];
        return quadratic(q, d);
    };
    for (std::size_t k = 0; k < p.horizon; ++k) {
        result += stage(k, p.Q);
        for (std::size_t i = 0; i < nu; ++i)
            for (std::size_t j = 0; j < nu; ++j)
                result += controls[k * nu + i] * p.R.values[i * nu + j] * controls[k * nu + j];
    }
    return result + stage(p.horizon, p.QN);
}

double evaluate_running_stage(const NominalProblem &p, std::span<const double> state,
                              std::span<const double> control) {
    const auto nx = p.initial.size(), nu = p.B.cols;
    if (state.size() != nx || control.size() != nu)
        return std::numeric_limits<double>::quiet_NaN();
    Vector d(nx);
    for (std::size_t i = 0; i < nx; ++i)
        d[i] = state[i] - p.reference[i];
    double result = quadratic(p.Q, d);
    for (std::size_t i = 0; i < nu; ++i)
        for (std::size_t j = 0; j < nu; ++j)
            result += control[i] * p.R.values[i * nu + j] * control[j];
    return result;
}
bool source_history_feasible(const NominalProblem &p, std::span<const Interval> state_bounds,
                             std::span<const Interval> input_bounds, std::span<const double> states,
                             std::span<const double> controls, double tolerance) {
    const auto nx = p.initial.size(), nu = p.B.cols;
    if (state_bounds.size() != nx || input_bounds.size() != nu ||
        states.size() != (p.horizon + 1) * nx || controls.size() != p.horizon * nu ||
        !std::isfinite(tolerance) || tolerance < 0)
        return false;
    for (std::size_t i = 0; i < nx; ++i)
        if (std::abs(states[i] - p.initial[i]) > tolerance)
            return false;
    for (std::size_t k = 0; k < p.horizon; ++k)
        for (std::size_t i = 0; i < nx; ++i) {
            double next = 0;
            for (std::size_t j = 0; j < nx; ++j)
                next += p.A.values[i * nx + j] * states[k * nx + j];
            for (std::size_t j = 0; j < nu; ++j)
                next += p.B.values[i * nu + j] * controls[k * nu + j];
            if (std::abs(states[(k + 1) * nx + i] - next) > tolerance)
                return false;
        }
    for (std::size_t k = 0; k <= p.horizon; ++k)
        for (std::size_t i = 0; i < nx; ++i) {
            const auto value = states[k * nx + i];
            if (!std::isfinite(value) ||
                (state_bounds[i].lower && value < *state_bounds[i].lower - tolerance) ||
                (state_bounds[i].upper && value > *state_bounds[i].upper + tolerance))
                return false;
        }
    for (std::size_t k = 0; k < p.horizon; ++k)
        for (std::size_t i = 0; i < nu; ++i) {
            const auto value = controls[k * nu + i];
            if (!std::isfinite(value) ||
                (input_bounds[i].lower && value < *input_bounds[i].lower - tolerance) ||
                (input_bounds[i].upper && value > *input_bounds[i].upper + tolerance))
                return false;
        }
    return true;
}

} // namespace csl::examples::quadcopter_mpc
