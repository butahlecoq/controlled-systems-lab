#pragma once

#include <csl/optimization/running_control_cost.hpp>
#include <csl/optimization/objective_contracts.hpp>
#include <csl/problem/contracts.hpp>
#include <csl/synthesis/control_recovery.hpp>

namespace csl::optimization {

struct HistoryQuadraticPolynomial {
    std::size_t dimension;
    Matrix Q;
    Vector linear;
    double offset;
};

// Each term retains its own source norm. Its value is
// coefficient * ||sqrt(weights) .* (map * history - target)||_2.
struct WeightedHistoryResidualNorm {
    Matrix map;
    Vector target;
    Vector weights;
    double coefficient;
};

struct HistoryCostProgram {
    JointCoordinates coordinates;
    HistoryQuadraticPolynomial quadratic;
    std::vector<WeightedHistoryResidualNorm> residual_norms;
    TerminalObjective terminal_source;
    RunningControlCost running_source;
    std::size_t absolute_stage_offset;
};

struct HistoryCostEvaluation {
    double terminal;
    double running;
    double total;
};

using HistoryCostCompilation = std::variant<HistoryCostProgram, Diagnostics, OperationStopped>;
using HistoryCostResult = std::variant<HistoryCostEvaluation, Diagnostics, OperationStopped>;

// Compiles the source objective over canonical [x0,...,xT,u0,...,u(T-1)]
// history coordinates. The supplied relation must be the full feasible
// history domain, not a prefiltered terminal-optimal fiber.
HistoryCostCompilation compile_history_cost(const synthesis::JointHistoryRelation &,
                                            const TerminalObjective &, const RunningControlCost &,
                                            std::size_t absolute_stage_offset);

// Evaluates the authored terminal and running formulas separately on a full
// history, then returns their sum.
HistoryCostResult evaluate_history_cost(const HistoryCostProgram &, std::span<const Vector> states,
                                        std::span<const Vector> controls);

} // namespace csl::optimization
