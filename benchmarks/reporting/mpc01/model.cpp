#include "model.hpp"

#include <csl/problem/resolved_problem.hpp>

#include <algorithm>
#include <span>
#include <type_traits>

namespace csl::mpc01 {
namespace {

std::optional<ValidationError> matrix_shape(const Matrix& matrix,
                                            std::size_t rows,
                                            std::size_t columns,
                                            const std::string& path) {
    if (matrix.size() != rows) {
        return ValidationError{path, "row count does not match the model dimension"};
    }
    if (std::any_of(matrix.begin(), matrix.end(),
                    [columns](const Vector& row) { return row.size() != columns; })) {
        return ValidationError{path, "matrix is ragged or has the wrong column count"};
    }
    return std::nullopt;
}

std::optional<ValidationError> box_shape(const std::optional<Box>& box,
                                         std::size_t dimension,
                                         const std::string& path) {
    if (!box) return std::nullopt;
    if (box->lower.size() != dimension || box->upper.size() != dimension) {
        return ValidationError{path, "bound vector has the wrong dimension"};
    }
    for (std::size_t i = 0; i < dimension; ++i) {
        if (box->lower[i] > box->upper[i]) {
            return ValidationError{path, "lower bound exceeds upper bound"};
        }
    }
    return std::nullopt;
}

} // namespace

std::optional<ValidationError> validate(const MpcCase& problem) {
    const auto nx = problem.state_dimension();
    if (problem.id.empty() || problem.version.empty() || problem.source_kind.empty() ||
        problem.source_ref.empty() || problem.canonical_input_sha256.size() != 64 ||
        problem.canonical_input_bytes.empty()) {
        return ValidationError{"identity", "case identity and a SHA-256 input digest are required"};
    }
    const auto input_span = std::as_bytes(std::span{problem.canonical_input_bytes.data(),
                                                    problem.canonical_input_bytes.size()});
    const auto content = csl::problem::snapshot_content(input_span);
    if (const auto* diagnostic = std::get_if<csl::Diagnostic>(&content)) {
        return ValidationError{"canonical_input_bytes", diagnostic->explanation};
    }
    const auto& resolved_content = std::get<csl::problem::ResolvedContent>(content);
    if (csl::problem::hex(resolved_content.digest()) != problem.canonical_input_sha256) {
        return ValidationError{"canonical_input_sha256", "digest does not match the retained canonical input bytes"};
    }
    if (nx == 0 || problem.horizon() == 0 || problem.stages.size() != problem.horizon() + 1) {
        return ValidationError{"dimensions", "nonempty states and horizon+1 stage records are required"};
    }
    if (problem.dynamics.size() != problem.horizon()) {
        return ValidationError{"dynamics", "one dynamics record is required per transition"};
    }
    const auto nu = problem.control_dimension();
    if (nu == 0) return ValidationError{"dynamics[0].B", "control dimension must be nonzero"};
    for (std::size_t t = 0; t < problem.horizon(); ++t) {
        const auto& stage = problem.dynamics[t];
        const auto prefix = "dynamics[" + std::to_string(t) + "].";
        if (auto error = matrix_shape(stage.a, nx, nx, prefix + "A")) return error;
        if (auto error = matrix_shape(stage.b, nx, nu, prefix + "B")) return error;
        if (stage.affine.size() != nx) {
            return ValidationError{prefix + "affine", "offset dimension does not match the state"};
        }
    }
    for (std::size_t t = 0; t <= problem.horizon(); ++t) {
        const auto prefix = "stages[" + std::to_string(t) + "].";
        if (auto error = box_shape(problem.stages[t].state, nx, prefix + "state")) return error;
        if (t < problem.horizon()) {
            if (auto error = box_shape(problem.stages[t].control, nu, prefix + "control")) return error;
        } else if (problem.stages[t].control) {
            return ValidationError{prefix + "control", "a terminal stage has no control"};
        }
    }
    return std::visit([nx](const auto& cost) -> std::optional<ValidationError> {
        using Cost = std::decay_t<decltype(cost)>;
        if constexpr (std::is_same_v<Cost, QuadraticTerminalCost>) {
            if (auto error = matrix_shape(cost.q, nx, nx, "terminal_cost.Q")) return error;
            if (cost.linear.size() != nx) {
                return ValidationError{"terminal_cost.linear", "vector dimension does not match the state"};
            }
        } else {
            if (cost.w.empty() || cost.target.size() != cost.w.size()) {
                return ValidationError{"terminal_cost.target", "target dimension must match residual rows"};
            }
            if (auto error = matrix_shape(cost.w, cost.w.size(), nx, "terminal_cost.W")) return error;
        }
        return std::nullopt;
    }, problem.terminal_cost);
}

} // namespace csl::mpc01
