#pragma once

#include <csl/optimization/convex_backend.hpp>

namespace csl::examples::quadcopter_mpc {

struct NominalProblem {
    Matrix A, B, Q, QN, R;
    Vector initial, reference;
    std::size_t horizon{};
    std::vector<Interval> state_bounds, input_bounds;
};

// The source task uses a full state/control history, in x0..xN,u0..uN-1 order.
optimization::ConvexDataResult<ConvexProgram> compile(const NominalProblem&);

double evaluate_source_cost(const NominalProblem&, std::span<const double> states,
                            std::span<const double> controls);
double evaluate_running_stage(const NominalProblem&, std::span<const double> state,
                              std::span<const double> control);

} // namespace csl::examples::quadcopter_mpc
