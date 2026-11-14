#include <csl/controllers/discrete_mpc.hpp>

#include <csl/model/linear_system.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <string_view>
#include <utility>

namespace csl::controllers {
namespace {
using Row = std::vector<std::pair<std::size_t, double>>;

Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(),
                       [](double value) { return std::isfinite(value); });
}

bool product(std::size_t left, std::size_t right, std::size_t &result) {
    if (right != 0 && left > std::numeric_limits<std::size_t>::max() / right)
        return false;
    result = left * right;
    return true;
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

Interval intersect(Interval left, const Interval &right) {
    if (right.lower && (!left.lower || *right.lower > *left.lower))
        left.lower = right.lower;
    if (right.upper && (!left.upper || *right.upper < *left.upper))
        left.upper = right.upper;
    return left;
}

void set_bound(std::vector<Interval> &bounds, std::size_t coordinate, std::optional<double> lower,
               std::optional<double> upper) {
    bounds.at(coordinate) = intersect(bounds.at(coordinate), Interval{lower, upper});
}

struct ConstraintRow {
    Vector state;
    Vector control;
    Vector external;
    Interval bound;
};

ConstraintRow empty_row(std::size_t nx, std::size_t nu, std::size_t nw, Interval bound) {
    return {Vector(nx, 0.0), Vector(nu, 0.0), Vector(nw, 0.0), std::move(bound)};
}

std::vector<std::size_t> all_control_indices(std::size_t nu) {
    std::vector<std::size_t> indices(nu);
    std::iota(indices.begin(), indices.end(), 0);
    return indices;
}

void add_control_budget(std::vector<ConstraintRow> &rows, std::size_t nx, std::size_t nu,
                        std::size_t nw, std::span<const std::size_t> control_indices,
                        double upper) {
    auto row = empty_row(nx, nu, nw, {std::nullopt, upper});
    for (const auto index : control_indices)
        row.control.at(index) = 1.0;
    rows.push_back(std::move(row));
}

void add_availability(std::vector<ConstraintRow> &rows, std::size_t nx, std::size_t nu,
                      std::size_t nw, std::size_t count, std::size_t state_offset,
                      std::size_t external_offset) {
    for (std::size_t i = 0; i < count; ++i) {
        auto row = empty_row(nx, nu, nw, {std::nullopt, 0.0});
        row.state[state_offset + i] = -1.0;
        row.control[i] = 1.0;
        row.external[external_offset + i] = -1.0;
        rows.push_back(std::move(row));
    }
}

StageLinearConstraint pack_rows(std::size_t nx, std::size_t nu, std::size_t nw,
                                const std::vector<ConstraintRow> &rows) {
    StageLinearConstraint result{Matrix{rows.size(), nx, Vector(rows.size() * nx, 0.0)},
                                 Matrix{rows.size(), nu, Vector(rows.size() * nu, 0.0)},
                                 Matrix{rows.size(), nw, Vector(rows.size() * nw, 0.0)},
                                 {}};
    result.bounds.reserve(rows.size());
    for (std::size_t row = 0; row < rows.size(); ++row) {
        std::copy(rows[row].state.begin(), rows[row].state.end(),
                  result.state_map.values.begin() + static_cast<std::ptrdiff_t>(row * nx));
        std::copy(rows[row].control.begin(), rows[row].control.end(),
                  result.control_map.values.begin() + static_cast<std::ptrdiff_t>(row * nu));
        std::copy(rows[row].external.begin(), rows[row].external.end(),
                  result.external_map.values.begin() + static_cast<std::ptrdiff_t>(row * nw));
        result.bounds.push_back(rows[row].bound);
    }
    return result;
}

struct SourceConstraints {
    std::vector<Interval> states;
    std::vector<Interval> controls;
    std::vector<optimization::ControlPositivePartBudget> control_positive_part_budgets;
    std::vector<ConstraintRow> rows;
    std::vector<ConstraintRow> terminal_rows;
    bool needs_relaxation{};
    bool needs_authored_domain{};
    bool needs_arrival_timing{};
    bool deferred{};
    std::string reason;
};

SourceConstraints source_constraints(std::size_t model_number, std::size_t nx, std::size_t nu,
                                     std::size_t nw) {
    SourceConstraints result;
    result.states.resize(nx);
    result.controls.resize(nu);
    const auto state = [&](std::size_t index, std::optional<double> lo, std::optional<double> hi) {
        set_bound(result.states, index, lo, hi);
    };
    const auto control = [&](std::size_t index, std::optional<double> lo,
                             std::optional<double> hi) {
        set_bound(result.controls, index, lo, hi);
    };
    const auto all_controls = [&](double upper) {
        for (std::size_t i = 0; i < nu; ++i)
            control(i, 0.0, upper);
    };
    const auto every_control = all_control_indices(nu);
    const auto all_states = [&](double lower, double upper) {
        for (std::size_t i = 0; i < nx; ++i)
            state(i, lower, upper);
    };

    switch (model_number) {
    case 1:
        control(0, 0.0, 15.0);
        control(1, 0.0, 12.0);
        for (std::size_t i = 0; i < nx; ++i)
            state(i, 0.0, 100.0);
        break;
    case 2:
        state(0, 0.0, 30.0);
        control(0, 0.0, 2.002);
        control(1, 0.0, 4.0);
        break;
    case 3:
        for (std::size_t i = 0; i < nu; ++i)
            control(i, 0.0, std::nullopt);
        add_control_budget(result.rows, nx, nu, nw, every_control, 8.0);
        state(0, 0.0, std::nullopt);
        state(1, 0.0, std::nullopt);
        add_availability(result.rows, nx, nu, nw, 2, 0, 0);
        result.needs_arrival_timing = true;
        break;
    case 4:
        for (std::size_t i = 0; i < nu; ++i)
            control(i, 0.0, std::nullopt);
        add_control_budget(result.rows, nx, nu, nw, every_control, 200.0);
        all_states(0.0, 1000.0);
        result.needs_relaxation = true;
        break;
    case 5:
        state(0, 0.0, 100.0);
        state(1, 0.0, 150.0);
        control(0, 0.0, 20.0);
        control(1, 0.0, 20.0);
        control(2, 0.0, 30.0);
        control(3, 0.0, 30.0);
        break;
    case 6:
        all_controls(11.0);
        add_control_budget(result.rows, nx, nu, nw, every_control, 22.0);
        for (std::size_t i = 0; i < nx; ++i)
            state(i, 0.0, std::nullopt);
        break;
    case 7:
        all_states(-20.0, 20.0);
        all_controls(10.0);
        break;
    case 8:
        state(0, -4.0, 4.0);
        control(0, 0.0, 8.0);
        control(1, 0.0, 5.0);
        break;
    case 9:
        all_states(0.0, 24.0);
        all_controls(5.0);
        result.needs_relaxation = true;
        break;
    case 10:
        for (std::size_t i = 0; i < nx; ++i)
            state(i, 0.0, std::nullopt);
        all_controls(25.0);
        result.needs_relaxation = true;
        break;
    case 11:
        for (std::size_t i = 0; i < nu; ++i)
            control(i, 0.0, std::nullopt);
        control(0, 0.0, 20.0);
        control(1, 0.0, 18.0);
        state(0, std::nullopt, 80.0);
        state(1, std::nullopt, 80.0);
        add_availability(result.rows, nx, nu, nw, 2, 0, 0);
        result.needs_arrival_timing = true;
        break;
    case 12:
        state(0, 0.0, 1500.0);
        state(1, 0.0, 500.0);
        control(0, 0.0, 200.0);
        control(1, 0.0, 180.0);
        break;
    case 13:
        all_states(0.0, 1.0);
        all_controls(4.0);
        break;
    case 14:
        control(0, 0.0, 200.0);
        control(1, 0.0, 50.0);
        state(1, 0.0, 100.0);
        break;
    case 15:
        state(0, 100.0, std::nullopt);
        state(1, std::nullopt, 1500.0);
        control(0, 0.0, 100.0);
        control(1, 0.0, 80.0);
        break;
    case 16:
        control(0, 0.0, 10.0);
        control(1, 0.0, 8.0);
        state(0, 0.0, std::nullopt);
        state(1, 0.0, std::nullopt);
        break;
    case 17:
        all_controls(2.0);
        control(0, -2.0, 2.0);
        break;
    case 18:
        for (std::size_t i = 0; i < nu; ++i)
            control(i, 0.0, std::nullopt);
        add_control_budget(result.rows, nx, nu, nw, every_control, 30.0);
        state(0, 0.0, std::nullopt);
        state(1, 0.0, std::nullopt);
        add_availability(result.rows, nx, nu, nw, 2, 0, 0);
        result.needs_arrival_timing = true;
        break;
    case 19:
        control(0, 0.0, 20.0);
        control(1, 0.0, 20.0);
        state(0, std::nullopt, 4000.0);
        state(1, std::nullopt, 2400.0);
        break;
    case 20:
        state(0, 0.0, 150.0);
        state(1, 0.0, 130.0);
        all_controls(10.0);
        break;
    case 21: {
        const double pi = std::acos(-1.0);
        state(0, -pi / 6.0, pi / 6.0);
        state(1, -pi / 6.0, pi / 6.0);
        state(5, -1.0, std::nullopt);
        for (std::size_t i = 0; i < nu; ++i)
            control(i, -0.9916, 2.4084);
        break;
    }
    case 22:
        for (std::size_t i = 0; i < 3; ++i)
            control(i, -0.25, 0.25);
        control(3, -0.3, 0.3);
        break;
    case 23:
        control(0, -0.35, 0.35);
        control(1, -4.0, 2.5);
        state(5, -0.7, 0.7);
        break;
    case 24:
    case 25:
    case 27:
        result.needs_authored_domain = true;
        result.reason =
            "Source card provides no numerical state/control bounds; an identified authored continuous domain is required.";
        break;
    case 26:
        for (std::size_t i = 0; i < nu; ++i)
            control(i, -3.0, 2.0);
        for (std::size_t follower = 1; follower < 10; ++follower) {
            auto row = empty_row(nx, nu, nw, {2.0, std::nullopt});
            row.state[(follower - 1) * 3] = 1.0;
            row.state[follower * 3] = -1.0;
            row.state[follower * 3 + 1] = -1.2;
            result.rows.push_back(row);
            result.terminal_rows.push_back(std::move(row));
        }
        break;
    case 28:
        for (std::size_t zone = 0; zone < 20; ++zone)
            state(zone * 2, -3.0, 3.0);
        all_controls(5.0);
        add_control_budget(result.rows, nx, nu, nw, every_control, 45.0);
        break;
    case 29:
        all_controls(12.0);
        add_control_budget(result.rows, nx, nu, nw, every_control, 100.0);
        break;
    case 30:
        for (std::size_t i = 0; i < nu; ++i)
            control(i, -0.2, 0.2);
        result.control_positive_part_budgets.push_back({all_control_indices(nu), 1.0});
        break;
    case 31:
        all_controls(10.0);
        for (std::size_t i = 0; i < 12; ++i)
            state(i + 12, 0.0, 100.0);
        add_availability(result.rows, nx, nu, nw, 12, 0, 0);
        result.needs_arrival_timing = true;
        break;
    case 32:
        for (std::size_t i = 0; i < 24; ++i) {
            control(i, 0.0, 10.0);
            control(i + 24, 0.0, 2.0);
        }
        add_control_budget(result.rows, nx, nu, nw, every_control, 120.0);
        break;
    case 33:
        all_controls(10.0);
        add_control_budget(result.rows, nx, nu, nw, every_control, 60.0);
        break;
    case 34:
        all_controls(10.0);
        {
            std::vector<std::size_t> gpu_controls;
            for (std::size_t index = 0; index < nu; index += 2)
                gpu_controls.push_back(index);
            add_control_budget(result.rows, nx, nu, nw, gpu_controls, 50.0);
        }
        break;
    case 35:
        all_controls(1.0);
        {
            std::vector<std::size_t> radio_controls;
            for (std::size_t index = 0; index < nu; index += 2)
                radio_controls.push_back(index);
            add_control_budget(result.rows, nx, nu, nw, radio_controls, 8.0);
        }
        break;
    default:
        result.deferred = true;
        result.reason = "No source-constraint profile is registered for this model.";
        break;
    }
    return result;
}

std::string domain_name(DomainChoice choice) {
    switch (choice) {
    case DomainChoice::source_continuous:
        return "source_continuous";
    case DomainChoice::explicit_continuous_relaxation:
        return "explicit_continuous_relaxation";
    case DomainChoice::authored_continuous_domain:
        return "authored_continuous_domain";
    }
    return "invalid";
}

bool matrix_shape(const Matrix &matrix, std::size_t rows, std::size_t cols) {
    std::size_t count{};
    return matrix.rows == rows && matrix.cols == cols && product(rows, cols, count) &&
           matrix.values.size() == count && finite(matrix.values);
}

bool valid_constraint(const StageLinearConstraint &constraint, std::size_t nx, std::size_t nu,
                      std::size_t nw) {
    return constraint.state_map.rows == constraint.bounds.size() &&
           matrix_shape(constraint.state_map, constraint.bounds.size(), nx) &&
           matrix_shape(constraint.control_map, constraint.bounds.size(), nu) &&
           matrix_shape(constraint.external_map, constraint.bounds.size(), nw) &&
           valid_intervals(constraint.bounds);
}

bool dot(std::span<const double> left, std::span<const double> right, double &value) {
    if (left.size() != right.size())
        return false;
    value = 0.0;
    for (std::size_t i = 0; i < left.size(); ++i) {
        const double product_value = left[i] * right[i];
        if (!std::isfinite(product_value) || !std::isfinite(value + product_value))
            return false;
        value += product_value;
    }
    return true;
}

bool add_row_value(Row &row, std::size_t index, double value) {
    if (value == 0.0)
        return true;
    row.emplace_back(index, value);
    return true;
}

void canonicalize(Row &row) {
    std::sort(row.begin(), row.end(),
              [](const auto &a, const auto &b) { return a.first < b.first; });
    Row compact;
    for (const auto &[index, value] : row) {
        if (!compact.empty() && compact.back().first == index)
            compact.back().second += value;
        else
            compact.emplace_back(index, value);
    }
    std::erase_if(compact, [](const auto &entry) { return entry.second == 0.0; });
    row = std::move(compact);
}

bool evaluate_stage_cost(const optimization::QuadraticHistoryStageCost &cost,
                         std::span<const double> state, std::span<const double> control,
                         double &value) {
    const auto nx = state.size(), nu = control.size();
    value = cost.offset;
    for (std::size_t i = 0; i < nx; ++i) {
        value += cost.state_linear[i] * state[i];
        for (std::size_t j = 0; j < nx; ++j)
            value += 0.5 * state[i] * cost.state_hessian.values[i * nx + j] * state[j];
        for (std::size_t j = 0; j < nu; ++j)
            value += state[i] * cost.state_control_hessian.values[i * nu + j] * control[j];
    }
    for (std::size_t i = 0; i < nu; ++i) {
        value += cost.control_linear[i] * control[i];
        for (std::size_t j = 0; j < nu; ++j)
            value += 0.5 * control[i] * cost.control_hessian.values[i * nu + j] * control[j];
    }
    return std::isfinite(value);
}

bool evaluate_terminal_cost(const QuadraticTerminal &cost, std::span<const double> state,
                            double &value) {
    const auto nx = state.size();
    value = cost.offset;
    for (std::size_t i = 0; i < nx; ++i) {
        value += cost.linear[i] * state[i];
        for (std::size_t j = 0; j < nx; ++j)
            value += 0.5 * state[i] * cost.Q.values[i * nx + j] * state[j];
    }
    return std::isfinite(value);
}

bool within(double value, const Interval &bound, const NumericalPolicy &policy) {
    const double scale = std::max(1.0, std::abs(value));
    const double tolerance = policy.absolute_tolerance + policy.relative_tolerance * scale;
    return std::isfinite(value) && (!bound.lower || value >= *bound.lower - tolerance) &&
           (!bound.upper || value <= *bound.upper + tolerance);
}

Diagnostics check_stage_constraints(const NominalMpcTask &task, std::size_t stage,
                                    std::span<const double> state, std::span<const double> control,
                                    std::span<const double> external,
                                    const NumericalPolicy &policy) {
    Diagnostics diagnostics;
    for (std::size_t i = 0; i < task.state_bounds[stage].size(); ++i)
        if (!within(state[i], task.state_bounds[stage][i], policy))
            diagnostics.push_back(
                invalid("episode.state_bounds[" + std::to_string(i) + "]",
                        "Replayed state lies outside the declared stage interval."));
    for (std::size_t i = 0; i < task.control_bounds[stage].size(); ++i)
        if (!within(control[i], task.control_bounds[stage][i], policy))
            diagnostics.push_back(
                invalid("episode.control_bounds[" + std::to_string(i) + "]",
                        "Applied control lies outside the declared stage interval."));
    if (!task.control_positive_part_budgets.empty()) {
        if (task.control_positive_part_budgets.size() != task.final_stage) {
            diagnostics.push_back(
                invalid("episode.control_positive_part_budgets",
                        "Positive-part budget stages must match the task transition count."));
        } else {
            const auto &budgets = task.control_positive_part_budgets[stage];
            for (std::size_t budget_index = 0; budget_index < budgets.size(); ++budget_index) {
                const auto &budget = budgets[budget_index];
                auto field =
                    "episode.control_positive_part_budgets[" + std::to_string(budget_index) + "]";
                if (budget.control_indices.empty() || !std::isfinite(budget.upper_bound) ||
                    budget.upper_bound < 0.0) {
                    diagnostics.push_back(invalid(
                        std::move(field),
                        "A positive-part budget needs controls and a finite nonnegative upper bound."));
                    continue;
                }
                auto indices = budget.control_indices;
                std::ranges::sort(indices);
                if (indices.back() >= control.size() ||
                    std::adjacent_find(indices.begin(), indices.end()) != indices.end()) {
                    diagnostics.push_back(invalid(
                        std::move(field),
                        "Budget control indices must be unique and within the applied control vector."));
                    continue;
                }
                double positive_sum = 0.0;
                bool finite_sum = true;
                for (const auto index : budget.control_indices) {
                    positive_sum += std::max(control[index], 0.0);
                    finite_sum = finite_sum && std::isfinite(positive_sum);
                }
                if (!finite_sum ||
                    !within(positive_sum, {std::nullopt, budget.upper_bound}, policy))
                    diagnostics.push_back(
                        invalid(std::move(field),
                                "Replayed controls violate the source sum(max(u[i], 0)) budget."));
            }
        }
    }
    if (task.stage_constraints.empty())
        return diagnostics;
    const auto &constraints = task.stage_constraints[stage];
    if (!valid_constraint(constraints, state.size(), control.size(), external.size()))
        return Diagnostics{
            invalid("episode.stage_constraints", "Replay cannot check malformed stage rows.")};
    for (std::size_t row = 0; row < constraints.bounds.size(); ++row) {
        double value = 0.0;
        for (std::size_t i = 0; i < state.size(); ++i)
            value += constraints.state_map.values[row * state.size() + i] * state[i];
        for (std::size_t i = 0; i < control.size(); ++i)
            value += constraints.control_map.values[row * control.size() + i] * control[i];
        for (std::size_t i = 0; i < external.size(); ++i)
            value += constraints.external_map.values[row * external.size() + i] * external[i];
        if (!within(value, constraints.bounds[row], policy))
            diagnostics.push_back(invalid(
                "episode.stage_constraints[" + std::to_string(row) + "]",
                "Replayed state, control and external input violate a declared source row."));
    }
    return diagnostics;
}

Diagnostics check_terminal_constraints(const NominalMpcTask &task, std::span<const double> state,
                                       const NumericalPolicy &policy) {
    Diagnostics diagnostics;
    const auto &bounds = task.state_bounds[task.final_stage];
    for (std::size_t i = 0; i < bounds.size(); ++i)
        if (!within(state[i], bounds[i], policy))
            diagnostics.push_back(
                invalid("episode.terminal_state_bounds[" + std::to_string(i) + "]",
                        "Final state lies outside the declared interval."));
    for (std::size_t constraint_index = 0;
         constraint_index < task.terminal_state_constraints.size(); ++constraint_index) {
        const auto &constraint = task.terminal_state_constraints[constraint_index];
        if (constraint.state_map.rows != constraint.bounds.size() ||
            !matrix_shape(constraint.state_map, constraint.bounds.size(), state.size()) ||
            !valid_intervals(constraint.bounds)) {
            diagnostics.push_back(invalid("episode.terminal_state_constraints",
                                          "Terminal rows must be finite state-only constraints."));
            continue;
        }
        for (std::size_t row = 0; row < constraint.bounds.size(); ++row) {
            double value = 0.0;
            for (std::size_t col = 0; col < state.size(); ++col)
                value += constraint.state_map.values[row * state.size() + col] * state[col];
            if (!within(value, constraint.bounds[row], policy))
                diagnostics.push_back(invalid("episode.terminal_state_constraints[" +
                                                  std::to_string(constraint_index) + "][" +
                                                  std::to_string(row) + "]",
                                              "Final state violates a declared terminal row."));
        }
    }
    return diagnostics;
}

std::vector<double> episode_times(const NominalMpcTask &task) {
    std::vector<double> times(task.final_stage + 1);
    for (std::size_t stage = 0; stage <= task.final_stage; ++stage)
        times[stage] = static_cast<double>(stage) * task.model.time_step.value;
    return times;
}

} // namespace

ProfileAdmission make_source_task_profile(std::string_view model_id,
                                          const AuthoredTaskChoices &choices) {
    auto loaded = model::catalogue::make_discrete_model(model_id);
    if (const auto *errors = std::get_if<Diagnostics>(&loaded))
        return *errors;
    auto data = std::get<model::catalogue::DiscreteModelData>(std::move(loaded));
    const auto nx = data.coefficients.A.rows;
    const auto nu = data.coefficients.B.cols;
    const auto nw = data.coefficients.E.cols;
    if (choices.problem_id.value.empty() || choices.program_id.value.empty() ||
        choices.profile_id.empty() || choices.objective_id.empty() || choices.horizon_id.empty() ||
        choices.forecast_id.empty() || choices.replay_id.empty())
        return Diagnostics{invalid(
            "task.choices.identity",
            "Problem, program, profile, objective, horizon and input-schedule IDs must be explicit.")};
    if (choices.final_stage == 0 ||
        choices.final_stage == std::numeric_limits<std::size_t>::max() ||
        choices.running_costs.size() != choices.final_stage ||
        choices.forecast_external.size() != choices.final_stage ||
        choices.replay_external.size() != choices.final_stage)
        return Diagnostics{invalid(
            "task.choices.horizon",
            "A positive final stage and one running cost plus forecast/replay input per transition are required.")};
    if (choices.initial_state_override &&
        (choices.initial_state_override->size() != nx || !finite(*choices.initial_state_override)))
        return Diagnostics{invalid(
            "task.choices.initial_state",
            "An authored initial state must be finite and match the source state dimension.")};
    for (const auto &external : choices.forecast_external)
        if (external.size() != nw || !finite(external))
            return Diagnostics{invalid(
                "task.choices.forecast_external",
                "Every forecast input must be finite and match the source external dimension.")};
    for (const auto &external : choices.replay_external)
        if (external.size() != nw || !finite(external))
            return Diagnostics{invalid(
                "task.choices.replay_external",
                "Every replay input must be finite and match the source external dimension.")};
    if (choices.authored_state_bounds && (choices.authored_state_bounds->size() != nx ||
                                          !valid_intervals(*choices.authored_state_bounds)))
        return Diagnostics{
            invalid("task.choices.authored_state_bounds",
                    "Authored state bounds must contain one valid interval per state coordinate.")};
    if (choices.authored_control_bounds && (choices.authored_control_bounds->size() != nu ||
                                            !valid_intervals(*choices.authored_control_bounds)))
        return Diagnostics{invalid(
            "task.choices.authored_control_bounds",
            "Authored control bounds must contain one valid interval per control coordinate.")};
    const auto catalogue = model::catalogue::discrete_models();
    const auto found = std::find_if(catalogue.begin(), catalogue.end(),
                                    [model_id](const auto &info) { return info.id == model_id; });
    if (found == catalogue.end())
        return Diagnostics{
            invalid("task.source_constraints", "Catalogue source identity is not registered.")};
    const auto model_number = static_cast<std::size_t>(std::distance(catalogue.begin(), found)) + 1;
    const auto expected_model_id = "catalogue-2026/model-" + std::to_string(model_number) + "/1";
    if (found->id != expected_model_id)
        return Diagnostics{invalid(
            "task.source_constraints",
            "Source constraint profiles require the catalogue's stable model-ID ordering.")};
    auto profile = source_constraints(model_number, nx, nu, nw);
    if (profile.states.size() != nx || profile.controls.size() != nu)
        return Diagnostics{invalid("task.source_constraints",
                                   "Source profile and catalogue dimensions disagree.")};
    TaskProvenance provenance{std::string(data.info.id),
                              std::string(data.info.source.locator),
                              choices.profile_id,
                              choices.objective_id,
                              choices.horizon_id,
                              choices.initial_state_override ? "authored override" : "catalogue x0",
                              choices.forecast_id,
                              choices.replay_id,
                              domain_name(choices.domain_choice),
                              "ideal_full_state"};

    const bool relaxed_source_integer = model_number == 9 || model_number == 10;
    const bool relaxed_source_domain = model_number == 4;
    if (relaxed_source_integer &&
        choices.domain_choice != DomainChoice::explicit_continuous_relaxation)
        return DeferredTask{
            std::string(data.info.id), choices.profile_id,
            "The source requires integer states and controls; select the named continuous relaxation explicitly.",
            provenance};
    if (relaxed_source_domain &&
        choices.domain_choice != DomainChoice::explicit_continuous_relaxation)
        return DeferredTask{
            std::string(data.info.id), choices.profile_id,
            "The source describes discrete GPU/job allocation; select the named continuous-equivalent domain explicitly.",
            provenance};
    if (profile.needs_authored_domain &&
        (choices.domain_choice != DomainChoice::authored_continuous_domain ||
         !choices.authored_state_bounds || !choices.authored_control_bounds))
        return DeferredTask{std::string(data.info.id), choices.profile_id, profile.reason,
                            provenance};
    if (profile.needs_arrival_timing &&
        choices.arrival_availability != ArrivalAvailability::before_decision)
        return DeferredTask{
            std::string(data.info.id), choices.profile_id,
            "Source availability constraints require a declared before-decision arrival timing.",
            provenance};
    if (profile.deferred)
        return DeferredTask{std::string(data.info.id), choices.profile_id, profile.reason,
                            provenance};
    if (choices.domain_choice == DomainChoice::authored_continuous_domain &&
        (!choices.authored_state_bounds || !choices.authored_control_bounds))
        return Diagnostics{invalid(
            "task.choices.authored_domain",
            "An authored continuous domain must provide both state and control intervals.")};

    for (std::size_t i = 0; i < nx; ++i)
        if (choices.authored_state_bounds)
            profile.states[i] = intersect(profile.states[i], choices.authored_state_bounds->at(i));
    for (std::size_t i = 0; i < nu; ++i)
        if (choices.authored_control_bounds)
            profile.controls[i] =
                intersect(profile.controls[i], choices.authored_control_bounds->at(i));
    if (!valid_intervals(profile.states) || !valid_intervals(profile.controls))
        return Diagnostics{invalid(
            "task.bounds.intersection",
            "Source and authored interval constraints have an empty coordinate intersection.")};

    auto initial =
        choices.initial_state_override ? *choices.initial_state_override : data.initial_state;
    std::vector<std::vector<Interval>> states(choices.final_stage + 1, profile.states);
    std::vector<std::vector<Interval>> controls(choices.final_stage, profile.controls);
    std::vector<std::vector<optimization::ControlPositivePartBudget>> positive_part_budgets(
        choices.final_stage, profile.control_positive_part_budgets);
    std::vector<StageLinearConstraint> staged;
    if (!profile.rows.empty()) {
        const auto packed = pack_rows(nx, nu, nw, profile.rows);
        staged.assign(choices.final_stage, packed);
    }
    std::vector<TerminalStateConstraint> terminal_constraints;
    if (!profile.terminal_rows.empty()) {
        const auto packed = pack_rows(nx, nu, nw, profile.terminal_rows);
        terminal_constraints.push_back({packed.state_map, packed.bounds});
    }
    for (const auto &constraint : choices.terminal_state_constraints) {
        if (constraint.state_map.rows != constraint.bounds.size() ||
            !matrix_shape(constraint.state_map, constraint.bounds.size(), nx) ||
            !valid_intervals(constraint.bounds))
            return Diagnostics{invalid(
                "task.choices.terminal_state_constraints",
                "Terminal rows must contain only finite, dimension-matched state coefficients and intervals.")};
        terminal_constraints.push_back(constraint);
    }
    return NominalMpcTask{std::move(data),
                          KnownInitial{std::move(initial)},
                          choices.problem_id,
                          choices.program_id,
                          choices.final_stage,
                          std::move(states),
                          std::move(controls),
                          std::move(staged),
                          std::move(positive_part_budgets),
                          std::move(terminal_constraints),
                          choices.running_costs,
                          choices.terminal_cost,
                          choices.forecast_external,
                          choices.replay_external,
                          choices.observation,
                          std::move(provenance)};
}

optimization::ConvexDataResult<optimization::CompiledNominalQuadraticHistory>
compile_mpc_decision(const NominalMpcTask &task, StageIndex start_stage,
                     std::span<const double> observed_state) {
    const auto nx = task.model.coefficients.A.rows;
    const auto nu = task.model.coefficients.B.cols;
    const auto nw = task.model.coefficients.E.cols;
    if (task.final_stage == std::numeric_limits<std::size_t>::max() ||
        start_stage.value >= task.final_stage || observed_state.size() != nx ||
        !finite(observed_state))
        return Diagnostics{invalid(
            "mpc.start", "Expected a finite observed state at a decision stage before final T.")};
    const auto remaining = task.final_stage - start_stage.value;
    if (task.state_bounds.size() != task.final_stage + 1 ||
        task.control_bounds.size() != task.final_stage ||
        task.running_costs.size() != task.final_stage ||
        task.forecast_external.size() != task.final_stage ||
        (!task.control_positive_part_budgets.empty() &&
         task.control_positive_part_budgets.size() != task.final_stage) ||
        (task.stage_constraints.size() != 0 && task.stage_constraints.size() != task.final_stage))
        return Diagnostics{
            invalid("mpc.task", "Task arrays must match the declared fixed final stage.")};
    std::size_t state_count{}, control_count{}, base_variable_count{};
    if (!product(remaining + 1, nx, state_count) || !product(remaining, nu, control_count) ||
        state_count > std::numeric_limits<std::size_t>::max() - control_count)
        return Diagnostics{
            invalid("mpc.dimensions", "Suffix history coordinate count overflows size_t.")};
    base_variable_count = state_count + control_count;

    optimization::NominalQuadraticHistoryTask history{
        {{task.problem_id}, {task.program_id.value + "-from-" + std::to_string(start_stage.value)}},
        {},
        KnownInitial{Vector(observed_state.begin(), observed_state.end())},
        {},
        {},
        std::nullopt,
        {},
        task.terminal_cost};
    history.dynamics.reserve(remaining);
    history.running_costs.reserve(remaining);
    history.control_positive_part_budgets.reserve(remaining);
    for (std::size_t local = 0; local < remaining; ++local) {
        const auto absolute = start_stage.value + local;
        const auto &source = task.model.coefficients;
        Vector offset = source.offset;
        for (std::size_t i = 0; i < nx; ++i)
            for (std::size_t j = 0; j < nw; ++j)
                offset[i] += source.E.values[i * nw + j] * task.forecast_external[absolute][j];
        if (!finite(offset))
            return Diagnostics{
                invalid("mpc.forecast_offset",
                        "Forecast external input produced a nonfinite affine offset.")};
        history.dynamics.push_back({source.A, source.B, Matrix{nx, 0, {}}, std::move(offset)});
        history.running_costs.push_back(task.running_costs[absolute]);
        history.control_bounds.push_back(task.control_bounds[absolute]);
        history.control_positive_part_budgets.push_back(
            task.control_positive_part_budgets.empty()
                ? std::vector<optimization::ControlPositivePartBudget>{}
                : task.control_positive_part_budgets[absolute]);
    }
    for (std::size_t local = 0; local <= remaining; ++local)
        history.state_bounds.push_back(task.state_bounds[start_stage.value + local]);

    std::size_t rows = 0;
    for (std::size_t local = 0; local < remaining; ++local) {
        if (task.stage_constraints.empty())
            continue;
        const auto &constraint = task.stage_constraints[start_stage.value + local];
        if (!valid_constraint(constraint, nx, nu, nw))
            return Diagnostics{
                invalid("mpc.stage_constraints",
                        "Stage constraint dimensions or interval bounds are invalid.")};
        if (constraint.bounds.size() > std::numeric_limits<std::size_t>::max() - rows)
            return Diagnostics{
                invalid("mpc.stage_constraints", "Stage constraint row count overflows size_t.")};
        rows += constraint.bounds.size();
    }
    for (const auto &constraint : task.terminal_state_constraints) {
        if (constraint.state_map.rows != constraint.bounds.size() ||
            !matrix_shape(constraint.state_map, constraint.bounds.size(), nx) ||
            !valid_intervals(constraint.bounds))
            return Diagnostics{
                invalid("mpc.terminal_state_constraints",
                        "Terminal constraints may contain only finite state rows at x[T].")};
        if (constraint.bounds.size() > std::numeric_limits<std::size_t>::max() - rows)
            return Diagnostics{
                invalid("mpc.terminal_state_constraints", "Terminal row count overflows size_t.")};
        rows += constraint.bounds.size();
    }
    if (rows != 0) {
        SparseMatrix map{rows, base_variable_count, std::vector<std::size_t>{0}, {}, {}};
        std::vector<Interval> bounds;
        bounds.reserve(rows);
        for (std::size_t local = 0; local < remaining; ++local) {
            if (task.stage_constraints.empty())
                continue;
            const auto absolute = start_stage.value + local;
            const auto &constraint = task.stage_constraints[absolute];
            for (std::size_t row_index = 0; row_index < constraint.bounds.size(); ++row_index) {
                Row row;
                for (std::size_t col = 0; col < nx; ++col)
                    add_row_value(row, local * nx + col,
                                  constraint.state_map.values[row_index * nx + col]);
                for (std::size_t col = 0; col < nu; ++col)
                    add_row_value(row, state_count + local * nu + col,
                                  constraint.control_map.values[row_index * nu + col]);
                canonicalize(row);
                double external_shift{};
                if (!dot(std::span(constraint.external_map.values).subspan(row_index * nw, nw),
                         task.forecast_external[absolute], external_shift))
                    return Diagnostics{invalid(
                        "mpc.stage_constraints.external",
                        "Forecast constraint shift is nonfinite or dimensionally invalid.")};
                auto bound = constraint.bounds[row_index];
                if (bound.lower)
                    bound.lower = *bound.lower - external_shift;
                if (bound.upper)
                    bound.upper = *bound.upper - external_shift;
                if ((bound.lower && !std::isfinite(*bound.lower)) ||
                    (bound.upper && !std::isfinite(*bound.upper)))
                    return Diagnostics{
                        invalid("mpc.stage_constraints.external",
                                "Forecast shifted a row bound to a nonfinite value.")};
                for (const auto &[column, value] : row) {
                    map.column_indices.push_back(column);
                    map.values.push_back(value);
                }
                map.row_offsets.push_back(map.values.size());
                bounds.push_back(bound);
            }
        }
        for (const auto &constraint : task.terminal_state_constraints) {
            for (std::size_t row_index = 0; row_index < constraint.bounds.size(); ++row_index) {
                Row row;
                for (std::size_t col = 0; col < nx; ++col)
                    add_row_value(row, remaining * nx + col,
                                  constraint.state_map.values[row_index * nx + col]);
                canonicalize(row);
                for (const auto &[column, value] : row) {
                    map.column_indices.push_back(column);
                    map.values.push_back(value);
                }
                map.row_offsets.push_back(map.values.size());
                bounds.push_back(constraint.bounds[row_index]);
            }
        }
        history.temporal = TemporalConstraints{std::move(map), std::move(bounds)};
    }
    return optimization::compile_nominal_quadratic_history(history);
}

MpcEpisodeEvidence execute_nominal_episode(const NominalMpcTask &task, EpisodePolicy policy,
                                           ConvexWorkspace &workspace,
                                           const ExecutionContext &context) {
    MpcEpisodeEvidence evidence;
    evidence.policy = policy;
    const auto nx = task.model.coefficients.A.rows;
    const auto nu = task.model.coefficients.B.cols;
    if (task.observation != ObservationSemantics::ideal_full_state || task.final_stage == 0 ||
        task.final_stage == std::numeric_limits<std::size_t>::max() ||
        task.initial.point.size() != nx || task.replay_external.size() != task.final_stage) {
        evidence.stop = EpisodeStop::compilation_rejected;
        return evidence;
    }
    if (!std::isfinite(context.numerical.absolute_tolerance) ||
        !std::isfinite(context.numerical.relative_tolerance) ||
        context.numerical.absolute_tolerance < 0.0 || context.numerical.relative_tolerance < 0.0) {
        evidence.stop = EpisodeStop::compilation_rejected;
        return evidence;
    }
    auto times = episode_times(task);
    if (!finite(times) || !std::isfinite(task.model.time_step.value) ||
        task.model.time_step.value <= 0.0) {
        evidence.stop = EpisodeStop::simulation_stopped;
        return evidence;
    }
    auto snapshot = model::snapshot(task.model.system_model(), times);
    if (const auto *failure = std::get_if<Diagnostic>(&snapshot)) {
        (void)failure;
        evidence.stop = EpisodeStop::simulation_stopped;
        return evidence;
    }
    const auto &system = std::get<model::LinearSystem>(snapshot);
    evidence.realized_states.push_back(task.initial.point);
    Vector open_loop_controls;
    double realized_objective = 0.0;

    for (std::size_t stage = 0; stage < task.final_stage; ++stage) {
        MpcDecisionEvidence decision;
        decision.stage = {stage};
        decision.observed_state = evidence.realized_states.back();
        const bool must_solve = policy == EpisodePolicy::observed_state_mpc || stage == 0;
        if (context.cancellation.stop_requested()) {
            decision.solve =
                OperationStopped{StopReason::cancelled, "Cancelled before decision solve."};
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline) {
            decision.solve = OperationStopped{StopReason::deadline_expired,
                                              "Deadline expired before decision solve."};
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        if (must_solve) {
            auto compiled = compile_mpc_decision(task, {stage}, decision.observed_state);
            if (const auto *errors = std::get_if<Diagnostics>(&compiled)) {
                decision.solve = *errors;
                evidence.decisions.push_back(std::move(decision));
                evidence.stop = EpisodeStop::compilation_rejected;
                return evidence;
            }
            if (const auto *stopped = std::get_if<OperationStopped>(&compiled)) {
                decision.solve = *stopped;
                evidence.decisions.push_back(std::move(decision));
                evidence.stop = EpisodeStop::simulation_stopped;
                return evidence;
            }
            auto compiled_history =
                std::get<optimization::CompiledNominalQuadraticHistory>(std::move(compiled));
            decision.variable_layout = compiled_history.layout;
            const auto &layout = *decision.variable_layout;
            auto program = std::move(compiled_history.program);
            decision.program_identity = program.identity();
            decision.workspace_identity = workspace.workspace_identity();
            auto outcome = workspace.solve(program, context);
            decision.attempt = workspace.last_attempt();
            if (const auto *unsupported = std::get_if<Unsupported>(&outcome)) {
                decision.solve = *unsupported;
                evidence.decisions.push_back(std::move(decision));
                evidence.stop = EpisodeStop::solver_unsupported;
                return evidence;
            }
            const auto &result = std::get<ProgramResult>(outcome);
            decision.solve = result;
            const auto diagnostics =
                optimization::check_program_result(result, program, Assurance::numerical);
            if (!result.primal || result.termination != Termination::completed ||
                result.outcome.value != MathematicalOutcome::optimal || !diagnostics.empty() ||
                !layout.accepts_primal_size(result.primal->size())) {
                evidence.decisions.push_back(std::move(decision));
                evidence.stop = EpisodeStop::solver_not_optimal;
                return evidence;
            }
            const auto remaining = task.final_stage - stage;
            decision.predicted_states.reserve(remaining + 1);
            decision.predicted_controls.reserve(remaining);
            for (std::size_t local = 0; local <= remaining; ++local) {
                Vector state;
                state.reserve(nx);
                for (std::size_t coordinate = 0; coordinate < nx; ++coordinate) {
                    const auto index = layout.state_index(local, coordinate);
                    if (!index || *index >= result.primal->size()) {
                        decision.solve = Diagnostics{invalid(
                            "mpc.history_layout", "State coordinates do not fit the solved QP.")};
                        evidence.decisions.push_back(std::move(decision));
                        evidence.stop = EpisodeStop::solver_not_optimal;
                        return evidence;
                    }
                    state.push_back((*result.primal)[*index]);
                }
                decision.predicted_states.push_back(std::move(state));
            }
            for (std::size_t local = 0; local < remaining; ++local) {
                Vector control;
                control.reserve(nu);
                for (std::size_t coordinate = 0; coordinate < nu; ++coordinate) {
                    const auto index = layout.control_index(local, coordinate);
                    if (!index || *index >= result.primal->size()) {
                        decision.solve = Diagnostics{invalid(
                            "mpc.history_layout", "Control coordinates do not fit the solved QP.")};
                        evidence.decisions.push_back(std::move(decision));
                        evidence.stop = EpisodeStop::solver_not_optimal;
                        return evidence;
                    }
                    control.push_back((*result.primal)[*index]);
                }
                decision.predicted_controls.push_back(std::move(control));
            }
            if (policy == EpisodePolicy::nominal_open_loop) {
                for (const auto &control : decision.predicted_controls)
                    open_loop_controls.insert(open_loop_controls.end(), control.begin(),
                                              control.end());
            }
        }
        if (policy == EpisodePolicy::nominal_open_loop) {
            if (open_loop_controls.size() != task.final_stage * nu) {
                evidence.stop = EpisodeStop::compilation_rejected;
                return evidence;
            }
            decision.applied_control =
                Vector(open_loop_controls.begin() + static_cast<std::ptrdiff_t>(stage * nu),
                       open_loop_controls.begin() + static_cast<std::ptrdiff_t>((stage + 1) * nu));
        } else {
            if (decision.predicted_controls.empty()) {
                evidence.stop = EpisodeStop::compilation_rejected;
                return evidence;
            }
            decision.applied_control = decision.predicted_controls.front();
        }
        double stage_cost{};
        if (!evaluate_stage_cost(task.running_costs[stage], decision.observed_state,
                                 *decision.applied_control, stage_cost)) {
            decision.solve = OperationStopped{StopReason::numerical_failure,
                                              "Realized running cost overflowed."};
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        decision.replay_constraint_diagnostics =
            check_stage_constraints(task, stage, decision.observed_state, *decision.applied_control,
                                    task.replay_external[stage], context.numerical);
        if (!decision.replay_constraint_diagnostics.empty()) {
            decision.applied_control.reset();
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        realized_objective += stage_cost;
        if (!std::isfinite(realized_objective)) {
            decision.solve =
                OperationStopped{StopReason::numerical_failure, "Realized objective overflowed."};
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        auto next = system.step({stage}, decision.observed_state, *decision.applied_control,
                                task.replay_external[stage]);
        if (const auto *stopped = std::get_if<OperationStopped>(&next)) {
            decision.solve = *stopped;
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        if (const auto *error = std::get_if<Diagnostic>(&next)) {
            decision.solve = Diagnostics{*error};
            evidence.decisions.push_back(std::move(decision));
            evidence.stop = EpisodeStop::simulation_stopped;
            return evidence;
        }
        decision.next_state = std::get<Vector>(std::move(next));
        evidence.applied_controls.push_back(*decision.applied_control);
        evidence.realized_states.push_back(*decision.next_state);
        evidence.decisions.push_back(std::move(decision));
    }
    evidence.terminal_constraint_diagnostics =
        check_terminal_constraints(task, evidence.realized_states.back(), context.numerical);
    if (!evidence.terminal_constraint_diagnostics.empty()) {
        evidence.stop = EpisodeStop::simulation_stopped;
        return evidence;
    }
    double terminal{};
    if (!evaluate_terminal_cost(task.terminal_cost, evidence.realized_states.back(), terminal) ||
        !std::isfinite(realized_objective + terminal)) {
        evidence.stop = EpisodeStop::simulation_stopped;
        return evidence;
    }
    realized_objective += terminal;
    evidence.realized_objective = realized_objective;
    evidence.stop = EpisodeStop::completed;
    return evidence;
}

} // namespace csl::controllers
