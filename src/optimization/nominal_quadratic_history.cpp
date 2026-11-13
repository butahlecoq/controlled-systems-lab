#include <csl/optimization/nominal_quadratic_history.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <ranges>
#include <utility>

namespace csl::optimization {
namespace {

using Row = std::vector<std::pair<std::size_t, double>>;

Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

bool finite(std::span<const double> values) {
    return std::ranges::all_of(values, [](double value) { return std::isfinite(value); });
}

bool product(std::size_t left, std::size_t right, std::size_t &result) {
    if (right != 0 && left > std::numeric_limits<std::size_t>::max() / right)
        return false;
    result = left * right;
    return true;
}

bool valid_matrix(const Matrix &matrix, std::size_t rows, std::size_t cols) {
    std::size_t count{};
    return matrix.rows == rows && matrix.cols == cols && product(rows, cols, count) &&
           matrix.values.size() == count && finite(matrix.values);
}

bool valid_intervals(std::span<const Interval> intervals) {
    for (const auto &interval : intervals) {
        if ((interval.lower && !std::isfinite(*interval.lower)) ||
            (interval.upper && !std::isfinite(*interval.upper)) ||
            (interval.lower && interval.upper && *interval.lower > *interval.upper))
            return false;
    }
    return true;
}

bool add(double &destination, double value) {
    const auto sum = destination + value;
    if (!std::isfinite(sum))
        return false;
    destination = sum;
    return true;
}

void append_row(std::vector<Row> &rows, std::vector<Interval> &bounds, Row row, Interval bound) {
    std::ranges::sort(row,
                      [](const auto &left, const auto &right) { return left.first < right.first; });
    Row merged;
    for (const auto &[column, value] : row) {
        if (!merged.empty() && merged.back().first == column)
            merged.back().second += value;
        else
            merged.emplace_back(column, value);
    }
    std::erase_if(merged, [](const auto &entry) { return entry.second == 0.0; });
    rows.push_back(std::move(merged));
    bounds.push_back(std::move(bound));
}

ConvexDataResult<ConvexProgram> fail(Diagnostic error) { return Diagnostics{std::move(error)}; }

} // namespace

ConvexDataResult<ConvexProgram>
compile_nominal_quadratic_history(const NominalQuadraticHistoryTask &task) {
    const auto horizon = task.dynamics.size();
    if (horizon == 0 || task.running_costs.size() != horizon)
        return fail(invalid(
            "history_qp.stages",
            "At least one transition and exactly one running cost per transition are required."));

    const auto &first = task.dynamics.front();
    const auto nx = first.A.rows;
    const auto nu = first.B.cols;
    if (nx == 0 || nu == 0 || task.initial.point.size() != nx || !finite(task.initial.point))
        return fail(
            invalid("history_qp.initial",
                    "The known initial state must be finite and match nonzero model dimensions."));
    if (task.state_bounds.size() != 0 && task.state_bounds.size() != horizon + 1)
        return fail(
            invalid("history_qp.state_bounds",
                    "State bounds must be absent or contain one entry for every state stage."));
    if (task.control_bounds.size() != 0 && task.control_bounds.size() != horizon)
        return fail(
            invalid("history_qp.control_bounds",
                    "Control bounds must be absent or contain one entry for every transition."));

    for (std::size_t k = 0; k < horizon; ++k) {
        const auto &dynamics = task.dynamics[k];
        if (!valid_matrix(dynamics.A, nx, nx) || !valid_matrix(dynamics.B, nx, nu) ||
            dynamics.E.rows != nx || dynamics.E.cols != 0 || !dynamics.E.values.empty() ||
            dynamics.offset.size() != nx || !finite(dynamics.offset))
            return fail(invalid(
                "history_qp.dynamics",
                "Each transition must have finite A, B and offset values and a zero-dimensional external channel."));
        if (!valid_matrix(task.running_costs[k].state_hessian, nx, nx) ||
            !valid_matrix(task.running_costs[k].state_control_hessian, nx, nu) ||
            !valid_matrix(task.running_costs[k].control_hessian, nu, nu) ||
            task.running_costs[k].state_linear.size() != nx ||
            task.running_costs[k].control_linear.size() != nu ||
            !finite(task.running_costs[k].state_linear) ||
            !finite(task.running_costs[k].control_linear) ||
            !std::isfinite(task.running_costs[k].offset))
            return fail(invalid(
                "history_qp.running_costs",
                "Every running quadratic must have dimension-matched finite blocks and coefficients."));
    }
    if (!valid_matrix(task.terminal_cost.Q, nx, nx) ||
        task.terminal_cost.linear.size() != nx || !finite(task.terminal_cost.linear) ||
        !std::isfinite(task.terminal_cost.offset))
        return fail(
            invalid("history_qp.terminal_cost",
                    "The terminal quadratic must have dimension-matched finite coefficients."));

    for (std::size_t k = 0; k < task.state_bounds.size(); ++k) {
        if (task.state_bounds[k].size() != 0 && task.state_bounds[k].size() != nx)
            return fail(invalid("history_qp.state_bounds",
                                "Each nonempty state-bound row must match the state dimension."));
        if (!valid_intervals(task.state_bounds[k]))
            return fail(invalid("history_qp.state_bounds",
                                "State bounds must be finite intervals with lower <= upper."));
    }
    for (const auto &stage : task.control_bounds) {
        if (stage.size() != 0 && stage.size() != nu)
            return fail(
                invalid("history_qp.control_bounds",
                        "Each nonempty control-bound row must match the control dimension."));
        if (!valid_intervals(stage))
            return fail(invalid("history_qp.control_bounds",
                                "Control bounds must be finite intervals with lower <= upper."));
    }

    std::size_t state_count{}, control_count{}, variable_count{}, hessian_size{};
    if (!product(horizon + 1, nx, state_count) || !product(horizon, nu, control_count) ||
        control_count > std::numeric_limits<std::size_t>::max() - state_count)
        return fail(invalid("history_qp.dimensions",
                            "Canonical history allocation size overflows size_t."));
    variable_count = state_count + control_count;
    if (!product(variable_count, variable_count, hessian_size))
        return fail(invalid("history_qp.dimensions",
                            "Canonical history Hessian allocation size overflows size_t."));

    if (task.temporal) {
        const auto &temporal = *task.temporal;
        const auto &map = temporal.joint_map;
        if (map.rows == std::numeric_limits<std::size_t>::max() || map.cols != variable_count ||
            map.row_offsets.size() != map.rows + 1 || temporal.bounds.size() != map.rows ||
            map.row_offsets.empty() || map.row_offsets.front() != 0 ||
            map.row_offsets.back() != map.values.size() ||
            map.column_indices.size() != map.values.size() || !finite(map.values) ||
            !valid_intervals(temporal.bounds))
            return fail(invalid(
                "history_qp.temporal",
                "Temporal constraints must be a valid finite CSR map over canonical history coordinates."));
        for (std::size_t row = 0; row < map.rows; ++row) {
            if (map.row_offsets[row] > map.row_offsets[row + 1] ||
                map.row_offsets[row + 1] > map.values.size())
                return fail(
                    invalid("history_qp.temporal",
                            "Temporal CSR row offsets must be nondecreasing and in range."));
            std::size_t previous{};
            bool first_column = true;
            for (std::size_t index = map.row_offsets[row]; index < map.row_offsets[row + 1];
                 ++index) {
                if (map.column_indices[index] >= variable_count ||
                    (!first_column && map.column_indices[index] <= previous))
                    return fail(invalid(
                        "history_qp.temporal",
                        "Temporal CSR columns must be in range and strictly increasing per row."));
                previous = map.column_indices[index];
                first_column = false;
            }
        }
    }

    Matrix hessian{variable_count, variable_count, Vector(hessian_size, 0.0)};
    Vector linear(variable_count, 0.0);
    double offset = task.terminal_cost.offset;
    const auto control_offset = state_count;
    for (std::size_t k = 0; k < horizon; ++k) {
        const auto &cost = task.running_costs[k];
        const auto x = k * nx;
        const auto u = control_offset + k * nu;
        for (std::size_t i = 0; i < nx; ++i) {
            if (!add(linear[x + i], cost.state_linear[i]))
                return fail(invalid("history_qp.cost",
                                    "Running linear objective coefficients overflow binary64."));
            for (std::size_t j = 0; j < nx; ++j)
                if (!add(hessian.values[(x + i) * variable_count + x + j],
                         cost.state_hessian.values[i * nx + j]))
                    return fail(invalid("history_qp.cost",
                                        "Running state Hessian accumulation overflows binary64."));
            for (std::size_t j = 0; j < nu; ++j) {
                const auto value = cost.state_control_hessian.values[i * nu + j];
                if (!add(hessian.values[(x + i) * variable_count + u + j], value) ||
                    !add(hessian.values[(u + j) * variable_count + x + i], value))
                    return fail(
                        invalid("history_qp.cost",
                                "Running state-control Hessian accumulation overflows binary64."));
            }
        }
        for (std::size_t i = 0; i < nu; ++i) {
            if (!add(linear[u + i], cost.control_linear[i]))
                return fail(invalid("history_qp.cost",
                                    "Running linear objective coefficients overflow binary64."));
            for (std::size_t j = 0; j < nu; ++j)
                if (!add(hessian.values[(u + i) * variable_count + u + j],
                         cost.control_hessian.values[i * nu + j]))
                    return fail(
                        invalid("history_qp.cost",
                                "Running control Hessian accumulation overflows binary64."));
        }
        if (!add(offset, cost.offset))
            return fail(
                invalid("history_qp.cost", "Objective offset accumulation overflows binary64."));
    }
    const auto terminal = horizon * nx;
    for (std::size_t i = 0; i < nx; ++i) {
        linear[terminal + i] = task.terminal_cost.linear[i];
        for (std::size_t j = 0; j < nx; ++j)
            hessian.values[(terminal + i) * variable_count + terminal + j] =
                task.terminal_cost.Q.values[i * nx + j];
    }

    std::vector<Row> rows;
    std::vector<Interval> row_bounds;
    const auto temporal_rows = task.temporal ? task.temporal->bounds.size() : 0;
    if (temporal_rows > std::numeric_limits<std::size_t>::max() - state_count)
        return fail(invalid("history_qp.constraints", "Constraint row count overflows size_t."));
    rows.reserve(state_count + temporal_rows);
    row_bounds.reserve(rows.capacity());
    for (std::size_t i = 0; i < nx; ++i)
        append_row(rows, row_bounds, {{i, 1.0}}, {task.initial.point[i], task.initial.point[i]});
    for (std::size_t k = 0; k < horizon; ++k) {
        const auto &dynamics = task.dynamics[k];
        for (std::size_t i = 0; i < nx; ++i) {
            Row row{{(k + 1) * nx + i, 1.0}};
            for (std::size_t j = 0; j < nx; ++j)
                if (dynamics.A.values[i * nx + j] != 0.0)
                    row.emplace_back(k * nx + j, -dynamics.A.values[i * nx + j]);
            for (std::size_t j = 0; j < nu; ++j)
                if (dynamics.B.values[i * nu + j] != 0.0)
                    row.emplace_back(control_offset + k * nu + j, -dynamics.B.values[i * nu + j]);
            const auto rhs = dynamics.offset[i];
            append_row(rows, row_bounds, std::move(row), {rhs, rhs});
        }
    }

    for (std::size_t k = 0; k < task.state_bounds.size(); ++k) {
        const auto &stage = task.state_bounds[k];
        if (stage.empty())
            continue;
        for (std::size_t i = 0; i < nx; ++i)
            if (stage[i].lower || stage[i].upper)
                append_row(rows, row_bounds, {{k * nx + i, 1.0}}, stage[i]);
    }
    for (std::size_t k = 0; k < task.control_bounds.size(); ++k) {
        const auto &stage = task.control_bounds[k];
        if (stage.empty())
            continue;
        for (std::size_t i = 0; i < nu; ++i)
            if (stage[i].lower || stage[i].upper)
                append_row(rows, row_bounds, {{control_offset + k * nu + i, 1.0}}, stage[i]);
    }
    if (task.temporal) {
        const auto &temporal = *task.temporal;
        for (std::size_t k = 0; k < temporal.joint_map.rows; ++k) {
            Row row;
            for (std::size_t index = temporal.joint_map.row_offsets[k];
                 index < temporal.joint_map.row_offsets[k + 1]; ++index)
                row.emplace_back(temporal.joint_map.column_indices[index],
                                 temporal.joint_map.values[index]);
            append_row(rows, row_bounds, std::move(row), temporal.bounds[k]);
        }
    }

    SparseMatrix constraints{rows.size(), variable_count, {0}, {}, {}};
    for (const auto &row : rows) {
        for (const auto &[column, value] : row) {
            constraints.column_indices.push_back(column);
            constraints.values.push_back(value);
        }
        constraints.row_offsets.push_back(constraints.values.size());
    }
    auto made = make_convex_program(
        {task.identity, QuadraticTerminal{std::move(hessian), std::move(linear), offset},
         std::move(constraints), std::vector<Interval>(variable_count), std::move(row_bounds),
         std::nullopt});
    if (auto *value = std::get_if<ConvexProgram>(&made))
        return std::move(*value);
    if (auto *errors = std::get_if<Diagnostics>(&made))
        return std::move(*errors);
    return std::get<OperationStopped>(std::move(made));
}

} // namespace csl::optimization
