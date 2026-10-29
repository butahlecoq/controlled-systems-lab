#pragma once

#include "model.hpp"

namespace csl::mpc01::evidence {

struct TrajectoryDiagnostics {
    double dynamics_residual{};
    double state_bound_violation{};
    double control_bound_violation{};
};

TrajectoryDiagnostics check_trajectory(const MpcCase& problem, const Trajectory& trajectory);

} // namespace csl::mpc01::evidence
