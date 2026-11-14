#pragma once

#include <csl/controllers/discrete_mpc.hpp>
#include <csl/optimization/nominal_quadratic_history.hpp>

namespace csl::examples::quadcopter_mpc {

struct NominalProblem {
    Matrix A, B, Q, QN, R;
    Vector initial, reference;
    std::size_t horizon{};
};

// Translate authored source costs and constraints to the public history-QP
// contract; evaluation below remains a literal source-formula implementation.
optimization::NominalQuadraticHistoryTask make_task(const NominalProblem &,
                                                    std::span<const Interval> state_bounds,
                                                    std::span<const Interval> input_bounds);
controllers::AuthoredTaskChoices make_source21_choices(const NominalProblem &,
                                                       std::size_t external_dimension);

double evaluate_source_cost(const NominalProblem &, std::span<const double> states,
                            std::span<const double> controls);
double evaluate_running_stage(const NominalProblem &, std::span<const double> state,
                              std::span<const double> control);
bool source_history_feasible(const NominalProblem &, std::span<const Interval> state_bounds,
                             std::span<const Interval> input_bounds, std::span<const double> states,
                             std::span<const double> controls, double tolerance = 1e-7);

} // namespace csl::examples::quadcopter_mpc
