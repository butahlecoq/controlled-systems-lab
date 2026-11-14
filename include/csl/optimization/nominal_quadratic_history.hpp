#pragma once

#include <csl/optimization/convex_backend.hpp>
#include <csl/problem/contracts.hpp>

#include <cstddef>
#include <optional>
#include <vector>

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

// Stage-local convex budget sum(max(u[i], 0)) <= upper_bound. Indices must be
// unique within one budget and name control coordinates in that stage, never
// history variables or auxiliary columns. Separate budgets may overlap.
struct ControlPositivePartBudget {
    std::vector<std::size_t> control_indices;
    double upper_bound;
};

// A nominal, zero-external, discrete affine task with one cost per transition
// and a separate terminal cost. State histories are x[0..T], controls u[0..T-1].
// State/control interval arrays are either empty or have T+1/T rows respectively;
// an empty inner row denotes no coordinate bounds at that stage. Temporal
// constraints address only these canonical state/control coordinates.
struct NominalQuadraticHistoryTask {
    ProgramIdentity identity;
    std::vector<LinearStage> dynamics; // x[k+1] = A[k]x[k] + B[k]u[k] + a[k]
    KnownInitial initial;
    std::vector<std::vector<Interval>> state_bounds;
    std::vector<std::vector<Interval>> control_bounds;
    std::optional<TemporalConstraints> temporal;
    std::vector<QuadraticHistoryStageCost> running_costs;
    QuadraticTerminal terminal_cost;
    // Empty or T stage entries. The compiler adds private epigraph columns;
    // they follow the canonical state/control prefix and are described below.
    std::vector<std::vector<ControlPositivePartBudget>> control_positive_part_budgets;
};

enum class HistoryAuxiliaryKind { positive_part_witness };

struct HistoryAuxiliaryBlock {
    HistoryAuxiliaryKind kind;
    std::size_t stage;
    std::size_t budget_index;
    std::size_t first_variable; // one witness follows per control_indices entry
    std::vector<std::size_t> control_indices;
};

// Describes every solver coordinate. Base history coordinates retain their
// canonical order: x[0..T], then u[0..T-1]. Auxiliary witness columns follow.
struct HistoryVariableLayout {
    std::size_t horizon{};
    std::size_t state_dimension{};
    std::size_t control_dimension{};
    std::size_t state_variable_count{};
    std::size_t control_variable_count{};
    std::size_t base_variable_count{};
    std::size_t auxiliary_variable_count{};
    std::size_t total_variable_count{};
    std::vector<HistoryAuxiliaryBlock> auxiliary_blocks;

    std::optional<std::size_t> state_index(std::size_t stage,
                                           std::size_t coordinate) const noexcept;
    std::optional<std::size_t> control_index(std::size_t stage,
                                             std::size_t coordinate) const noexcept;
    bool accepts_primal_size(std::size_t size) const noexcept;
};

struct CompiledNominalQuadraticHistory {
    ConvexProgram program;
    HistoryVariableLayout layout;
};

// Compiles an authored nominal affine discrete task to the canonical history
// QP and its solver-coordinate layout. It validates dimensions and finite arithmetic, assembles
// initial/dynamics/bound/temporal rows, and preserves the supplied polynomial
// convention without adding horizon normalization or inferring a task by model ID.
// Positive-part constraints use private epigraph columns, described in layout.
ConvexDataResult<CompiledNominalQuadraticHistory>
compile_nominal_quadratic_history(const NominalQuadraticHistoryTask &);

} // namespace csl::optimization
