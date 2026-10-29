#pragma once

#include "model.hpp"

#include <span>
#include <variant>

namespace csl::mpc01 {

struct CscMatrix {
    std::size_t rows{}, columns{};
    std::vector<std::size_t> column_offsets;
    std::vector<std::size_t> row_indices;
    Vector values;
};

enum class ObjectiveTransform { unchanged, residual_norm_squared };

struct SparseQp {
    CscMatrix hessian;
    CscMatrix constraints;
    Vector linear;
    Vector variable_lower;
    Vector variable_upper;
    Vector row_lower;
    Vector row_upper;
    double objective_offset{};
    ObjectiveTransform objective_transform{ObjectiveTransform::unchanged};
};

struct OcpQpStage {
    std::optional<StageDynamics> dynamics;
    Matrix q, r, s;
    Vector q_linear, r_linear;
    std::optional<Box> state_bounds;
    std::optional<Box> control_bounds;
};

struct OcpQp {
    Vector initial_state;
    std::vector<OcpQpStage> stages;
    double objective_offset{};
    ObjectiveTransform objective_transform{ObjectiveTransform::unchanged};
};

using MappingResult = std::variant<SparseQp, OcpQp, ValidationError>;

MappingResult make_osqp_problem(const MpcCase&);
MappingResult make_hpipm_problem(const MpcCase&);
double original_terminal_objective(const MpcCase&, std::span<const double> terminal_state);

} // namespace csl::mpc01
