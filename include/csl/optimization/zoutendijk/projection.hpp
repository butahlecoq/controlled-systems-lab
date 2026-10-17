#pragma once

#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <span>
#include <variant>

namespace csl::optimization::zoutendijk {

struct ProjectionPolicy {
    std::size_t max_iterations{1000};
};

struct ProjectionSuccess {
    Vector point;
    double distance;
    double quadratic_objective;
    double stationarity_residual;
    std::size_t iterations;
};

enum class ProjectionStopReason {
    cancelled, deadline_expired, resource_limit, numerical_failure, operation_rejected, contract_rejected
};
struct ProjectionStopped {
    ProjectionStopReason reason;
    Vector last_feasible_iterate;
    std::size_t iterations;
};

using ProjectionOutcome = std::variant<ProjectionSuccess, ProjectionStopped, Diagnostics, Unsupported>;

// Minimize 0.5 * ||x - target||^2 over feasible_set. The caller supplies a
// start that is checked against the set under context.numerical; this routine
// never manufactures feasibility evidence or silently repairs the start.
ProjectionOutcome project(const LinearProgram& feasible_set,
    std::span<const double> target, std::span<const double> feasible_start,
    LPWorkspace& direction_workspace, const ExecutionContext& context,
    ProjectionPolicy policy = {});

} // namespace csl::optimization::zoutendijk
