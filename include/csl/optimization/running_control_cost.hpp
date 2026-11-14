#pragma once

#include <csl/optimization/contracts.hpp>
#include <csl/optimization/objective_contracts.hpp>

#include <variant>

namespace csl::optimization {

// Quadratic penalties use coefficient / normalization_horizon times the sum
// of weighted, scaled squared residuals. Euclidean penalties preserve the
// source norm coefficient * ||map * u + offset||_2.
struct QuadraticControlPenalty {
    Vector reference;
    Vector scales;
    Vector weights;
    double coefficient;
    std::size_t normalization_horizon;
};
struct EuclideanControlPenalty {
    Matrix map;
    Vector offset;
    double coefficient;
};
using ControlPenalty = std::variant<QuadraticControlPenalty, EuclideanControlPenalty>;
struct AbsoluteStageControlCost {
    std::size_t stage;
    std::vector<ControlPenalty> terms;
};
struct RunningControlCost {
    std::string objective_id;
    std::size_t original_horizon;
    std::vector<AbsoluteStageControlCost> stages;
};

Diagnostics validate_running_control_cost(const RunningControlCost &,
                                          std::size_t absolute_stage_offset, std::size_t horizon,
                                          std::size_t control_dimension);

using RunningCostEvaluation = std::variant<double, Diagnostics, OperationStopped>;
RunningCostEvaluation evaluate_running_control_cost(const RunningControlCost &,
                                                    std::size_t absolute_stage_offset,
                                                    std::size_t horizon,
                                                    std::span<const Vector> controls,
                                                    std::size_t control_dimension);

} // namespace csl::optimization
