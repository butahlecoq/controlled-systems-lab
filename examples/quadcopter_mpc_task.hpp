#pragma once

#include <csl/optimization/nominal_quadratic_history.hpp>

namespace csl::examples::quadcopter_mpc {

struct NominalProblem {
    Matrix A, B, Q, QN, R;
    Vector initial, reference;
    std::size_t horizon{};
    std::vector<Interval> state_bounds, input_bounds;
};

// Translate authored source costs and constraints to the public history-QP
// contract; evaluation below remains a literal source-formula implementation.
optimization::NominalQuadraticHistoryTask make_task(const NominalProblem &);

double evaluate_source_cost(const NominalProblem &, std::span<const double> states,
                            std::span<const double> controls);
double evaluate_running_stage(const NominalProblem &, std::span<const double> state,
                              std::span<const double> control);
bool source_history_feasible(const NominalProblem &, std::span<const double> states,
                             std::span<const double> controls, double tolerance = 1e-7);

} // namespace csl::examples::quadcopter_mpc
