#include "trajectory_evidence.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <span>

namespace csl::mpc01::evidence {
namespace {

double box_violation(std::span<const double> value, const std::optional<Box>& box) {
    if (!box) return 0.0;
    double violation = 0.0;
    for (std::size_t i = 0; i < value.size(); ++i) {
        if (std::isfinite(box->lower[i])) violation = std::max(violation, box->lower[i] - value[i]);
        if (std::isfinite(box->upper[i])) violation = std::max(violation, value[i] - box->upper[i]);
    }
    return std::max(0.0, violation);
}

TrajectoryDiagnostics invalid_trajectory() {
    const auto infinity = std::numeric_limits<double>::infinity();
    return {infinity, infinity, infinity};
}

} // namespace

TrajectoryDiagnostics check_trajectory(const MpcCase& problem, const Trajectory& trajectory) {
    if (trajectory.states.size() != problem.horizon() + 1 ||
        trajectory.controls.size() != problem.horizon()) return invalid_trajectory();
    for (const auto& state : trajectory.states) {
        if (!std::all_of(state.begin(), state.end(), [](double value) { return std::isfinite(value); }))
            return invalid_trajectory();
    }
    for (const auto& control : trajectory.controls) {
        if (!std::all_of(control.begin(), control.end(), [](double value) { return std::isfinite(value); }))
            return invalid_trajectory();
    }

    TrajectoryDiagnostics result;
    result.state_bound_violation = box_violation(trajectory.states.front(),
        Box{problem.initial_state, problem.initial_state});
    for (std::size_t t = 0; t <= problem.horizon(); ++t) {
        result.state_bound_violation = std::max(result.state_bound_violation,
            box_violation(trajectory.states[t], problem.stages[t].state));
        if (t < problem.horizon()) {
            result.control_bound_violation = std::max(result.control_bound_violation,
                box_violation(trajectory.controls[t], problem.stages[t].control));
        }
    }
    for (std::size_t t = 0; t < problem.horizon(); ++t) {
        const auto& dynamics = problem.dynamics[t];
        for (std::size_t i = 0; i < problem.state_dimension(); ++i) {
            double predicted = dynamics.affine[i];
            for (std::size_t j = 0; j < problem.state_dimension(); ++j)
                predicted += dynamics.a[i][j] * trajectory.states[t][j];
            for (std::size_t j = 0; j < problem.control_dimension(); ++j)
                predicted += dynamics.b[i][j] * trajectory.controls[t][j];
            const double residual = std::abs(trajectory.states[t + 1][i] - predicted);
            result.dynamics_residual = std::isfinite(residual)
                ? std::max(result.dynamics_residual, residual)
                : std::numeric_limits<double>::infinity();
        }
    }
    return result;
}

} // namespace csl::mpc01::evidence
