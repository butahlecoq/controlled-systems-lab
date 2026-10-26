#include "problem_mapping.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <tuple>

namespace csl::mpc01 {
namespace {

struct Triplet { std::size_t row, column; double value; };

CscMatrix to_csc(std::size_t rows, std::size_t columns, std::vector<Triplet> entries) {
    std::sort(entries.begin(), entries.end(), [](const Triplet& left, const Triplet& right) {
        return std::tie(left.column, left.row) < std::tie(right.column, right.row);
    });
    CscMatrix result;
    result.rows = rows;
    result.columns = columns;
    result.column_offsets.assign(columns + 1, 0);
    for (std::size_t i = 0; i < entries.size();) {
        std::size_t j = i + 1;
        double value = entries[i].value;
        while (j < entries.size() && entries[j].column == entries[i].column &&
               entries[j].row == entries[i].row) {
            value += entries[j].value;
            ++j;
        }
        if (value != 0.0) {
            result.row_indices.push_back(entries[i].row);
            result.values.push_back(value);
            ++result.column_offsets[entries[i].column + 1];
        }
        i = j;
    }
    for (std::size_t column = 0; column < columns; ++column) {
        result.column_offsets[column + 1] += result.column_offsets[column];
    }
    return result;
}

struct QuadraticForm {
    Matrix hessian;
    Vector linear;
    double offset{};
    ObjectiveTransform transform{ObjectiveTransform::unchanged};
};

QuadraticForm solver_quadratic_form(const TerminalCost& terminal) {
    if (const auto* quadratic = std::get_if<QuadraticTerminalCost>(&terminal)) {
        return {quadratic->q, quadratic->linear, quadratic->offset,
                ObjectiveTransform::unchanged};
    }
    const auto& residual = std::get<AffineResidualNormTerminalCost>(terminal);
    const auto nx = residual.w.front().size();
    Matrix hessian(nx, Vector(nx));
    Vector linear(nx);
    double offset = 0.0;
    for (std::size_t row = 0; row < residual.w.size(); ++row) {
        offset += residual.target[row] * residual.target[row];
        for (std::size_t i = 0; i < nx; ++i) {
            linear[i] -= 2.0 * residual.w[row][i] * residual.target[row];
            for (std::size_t j = 0; j < nx; ++j) {
                hessian[i][j] += 2.0 * residual.w[row][i] * residual.w[row][j];
            }
        }
    }
    return {std::move(hessian), std::move(linear), offset,
            ObjectiveTransform::residual_norm_squared};
}

bool intersect(Box& target, const std::optional<Box>& constraint) {
    if (!constraint) return true;
    for (std::size_t i = 0; i < target.lower.size(); ++i) {
        target.lower[i] = std::max(target.lower[i], constraint->lower[i]);
        target.upper[i] = std::min(target.upper[i], constraint->upper[i]);
        if (target.lower[i] > target.upper[i]) return false;
    }
    return true;
}

std::variant<std::pair<Vector, Vector>, ValidationError> variable_bounds(const MpcCase& problem) {
    const auto nx = problem.state_dimension();
    const auto nu = problem.control_dimension();
    const auto horizon = problem.horizon();
    const auto count = (horizon + 1) * nx + horizon * nu;
    Vector lower(count, -std::numeric_limits<double>::infinity());
    Vector upper(count, std::numeric_limits<double>::infinity());
    for (std::size_t t = 0; t <= horizon; ++t) {
        Box bound{Vector(nx, -std::numeric_limits<double>::infinity()),
                  Vector(nx, std::numeric_limits<double>::infinity())};
        if (t == 0) bound = {problem.initial_state, problem.initial_state};
        if (!intersect(bound, problem.stages[t].state)) {
            return ValidationError{"stages[" + std::to_string(t) + "].state",
                                   "state bounds exclude the known initial state or are inconsistent"};
        }
        for (std::size_t i = 0; i < nx; ++i) {
            const auto index = t * nx + i;
            lower[index] = bound.lower[i];
            upper[index] = bound.upper[i];
        }
        if (t < horizon && problem.stages[t].control) {
            const auto offset = (horizon + 1) * nx + t * nu;
            for (std::size_t i = 0; i < nu; ++i) {
                lower[offset + i] = problem.stages[t].control->lower[i];
                upper[offset + i] = problem.stages[t].control->upper[i];
            }
        }
    }
    return std::pair{std::move(lower), std::move(upper)};
}

} // namespace

MappingResult make_osqp_problem(const MpcCase& problem) {
    if (auto error = validate(problem)) return *error;
    const auto nx = problem.state_dimension();
    const auto nu = problem.control_dimension();
    const auto horizon = problem.horizon();
    const auto states = (horizon + 1) * nx;
    const auto variables = states + horizon * nu;
    const auto dynamics_rows = horizon * nx;
    auto bounds = variable_bounds(problem);
    if (const auto* error = std::get_if<ValidationError>(&bounds)) return *error;
    auto [variable_lower, variable_upper] =
        std::get<std::pair<Vector, Vector>>(std::move(bounds));

    const auto cost = solver_quadratic_form(problem.terminal_cost);
    std::vector<Triplet> hessian;
    for (std::size_t i = 0; i < nx; ++i) {
        for (std::size_t j = i; j < nx; ++j) {
            const double symmetric = 0.5 * (cost.hessian[i][j] + cost.hessian[j][i]);
            if (symmetric != 0.0) hessian.push_back({horizon * nx + i, horizon * nx + j, symmetric});
        }
    }
    Vector linear(variables);
    for (std::size_t i = 0; i < nx; ++i) linear[horizon * nx + i] = cost.linear[i];

    std::vector<Triplet> constraints;
    Vector row_lower(dynamics_rows), row_upper(dynamics_rows);
    for (std::size_t t = 0; t < horizon; ++t) {
        const auto& dynamics = problem.dynamics[t];
        for (std::size_t i = 0; i < nx; ++i) {
            const auto row = t * nx + i;
            constraints.push_back({row, (t + 1) * nx + i, 1.0});
            for (std::size_t j = 0; j < nx; ++j) {
                constraints.push_back({row, t * nx + j, -dynamics.a[i][j]});
            }
            for (std::size_t j = 0; j < nu; ++j) {
                constraints.push_back({row, states + t * nu + j, -dynamics.b[i][j]});
            }
            row_lower[row] = dynamics.affine[i];
            row_upper[row] = dynamics.affine[i];
        }
    }
    return SparseQp{to_csc(variables, variables, std::move(hessian)),
                    to_csc(dynamics_rows, variables, std::move(constraints)),
                    std::move(linear), std::move(variable_lower), std::move(variable_upper),
                    std::move(row_lower), std::move(row_upper), cost.offset, cost.transform};
}

MappingResult make_hpipm_problem(const MpcCase& problem) {
    if (auto error = validate(problem)) return *error;
    auto bounds = variable_bounds(problem);
    if (const auto* error = std::get_if<ValidationError>(&bounds)) return *error;
    const auto cost = solver_quadratic_form(problem.terminal_cost);
    const auto horizon = problem.horizon();
    const auto nx = problem.state_dimension();
    const auto nu = problem.control_dimension();
    std::vector<OcpQpStage> stages;
    stages.reserve(horizon + 1);
    for (std::size_t t = 0; t < horizon; ++t) {
        stages.push_back({problem.dynamics[t], Matrix(nx, Vector(nx)), Matrix(nu, Vector(nu)),
                          Matrix(nx, Vector(nu)), Vector(nx), Vector(nu),
                          problem.stages[t].state, problem.stages[t].control});
    }
    stages.push_back({std::nullopt, cost.hessian, {}, {}, cost.linear, {},
                      problem.stages[horizon].state, {}});
    return OcpQp{problem.initial_state, std::move(stages), cost.offset, cost.transform};
}

double original_terminal_objective(const MpcCase& problem, std::span<const double> terminal_state) {
    const auto nx = problem.state_dimension();
    if (terminal_state.size() != nx) return std::numeric_limits<double>::quiet_NaN();
    if (const auto* cost = std::get_if<QuadraticTerminalCost>(&problem.terminal_cost)) {
        double value = cost->offset;
        for (std::size_t i = 0; i < nx; ++i) {
            value += cost->linear[i] * terminal_state[i];
            for (std::size_t j = 0; j < nx; ++j) {
                value += 0.5 * terminal_state[i] * cost->q[i][j] * terminal_state[j];
            }
        }
        return value;
    }
    const auto& cost = std::get<AffineResidualNormTerminalCost>(problem.terminal_cost);
    double squared = 0.0;
    for (std::size_t i = 0; i < cost.w.size(); ++i) {
        double residual = -cost.target[i];
        for (std::size_t j = 0; j < nx; ++j) residual += cost.w[i][j] * terminal_state[j];
        squared += residual * residual;
    }
    return std::sqrt(squared);
}

} // namespace csl::mpc01
