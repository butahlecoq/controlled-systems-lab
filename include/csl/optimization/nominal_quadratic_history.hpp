#pragma once

#include <csl/optimization/convex_backend.hpp>
#include <csl/problem/contracts.hpp>

namespace csl::optimization {

// Each stage polynomial is 1/2 [x;u]' H [x;u] + q'[x;u] + c.
// The Hessian includes state-control cross terms. Its blocks are row-major.
struct QuadraticHistoryStageCost {
    Matrix state_hessian;
    Matrix state_control_hessian;
    Matrix control_hessian;
    Vector state_linear;
    Vector control_linear;
    double offset;
};

// A nominal, zero-external, discrete affine task with one cost per transition
// and a separate terminal cost. State histories are x[0..T], controls u[0..T-1].
// State/control interval arrays are either empty or have T+1/T rows respectively;
// an empty inner row denotes no coordinate bounds at that stage.
struct NominalQuadraticHistoryTask {
    ProgramIdentity identity;
    std::vector<LinearStage> dynamics; // x[k+1] = A[k]x[k] + B[k]u[k] + a[k]
    KnownInitial initial;
    std::vector<std::vector<Interval>> state_bounds;
    std::vector<std::vector<Interval>> control_bounds;
    std::optional<TemporalConstraints> temporal;
    std::vector<QuadraticHistoryStageCost> running_costs;
    QuadraticTerminal terminal_cost;
};

// Compiles an authored nominal affine discrete task to the canonical history
// ConvexProgram. It validates dimensions and finite arithmetic, assembles
// initial/dynamics/bound/temporal rows, and preserves the supplied polynomial
// convention without adding horizon normalization or inferring a task by model ID.
ConvexDataResult<ConvexProgram>
compile_nominal_quadratic_history(const NominalQuadraticHistoryTask &);

} // namespace csl::optimization
