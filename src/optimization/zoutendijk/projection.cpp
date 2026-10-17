#include <csl/optimization/zoutendijk/projection.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <utility>

namespace csl::optimization::zoutendijk {
namespace {
Diagnostics invalid(std::string field, std::string message) {
    return {{DiagnosticCode::invalid_input, std::move(field), std::move(message)}};
}
bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](double value) { return std::isfinite(value); });
}
bool within(const ResidualMeasure& residual, NumericalPolicy policy) {
    const double allowed = policy.absolute_tolerance + policy.relative_tolerance * residual.scale;
    return std::isfinite(allowed) && residual.violation <= allowed;
}
double activity(const numeric::MatrixView& matrix, std::size_t row, std::span<const double> x) {
    double value = 0;
    for (std::size_t col = 0; col < x.size(); ++col)
        value = std::fma(matrix(row, col), x[col], value);
    return value;
}
double tolerance(double value, double bound, NumericalPolicy policy) {
    return policy.absolute_tolerance + policy.relative_tolerance * std::max(std::abs(value), std::abs(bound));
}
bool close_to(double value, double bound, NumericalPolicy policy) {
    return std::isfinite(tolerance(value, bound, policy)) && std::abs(value - bound) <= tolerance(value, bound, policy);
}
ProjectionStopReason stop_reason(Termination termination) {
    switch (termination) {
    case Termination::cancelled: return ProjectionStopReason::cancelled;
    case Termination::resource_limit: return ProjectionStopReason::resource_limit;
    case Termination::operation_rejected: return ProjectionStopReason::operation_rejected;
    case Termination::contract_rejected: return ProjectionStopReason::contract_rejected;
    case Termination::completed:
    case Termination::numerical_failure: return ProjectionStopReason::numerical_failure;
    }
    return ProjectionStopReason::numerical_failure;
}
SparseMatrix copy_matrix(const LinearProgram& program) {
    const auto csr = std::get<numeric::CsrInput>(program.constraints().descriptor());
    return {csr.rows, csr.cols, {csr.row_offsets.begin(), csr.row_offsets.end()},
        {csr.column_indices.begin(), csr.column_indices.end()}, {csr.values.begin(), csr.values.end()}};
}
ProjectionStopped stopped(Termination termination, const Vector& point, std::size_t iterations) {
    return {stop_reason(termination), point, iterations};
}
}

ProjectionOutcome project(const LinearProgram& feasible_set,
    std::span<const double> target, std::span<const double> feasible_start,
    LPWorkspace& direction_workspace, const ExecutionContext& context, ProjectionPolicy policy) {
    const auto n = feasible_set.variables().size();
    const auto numerical = context.numerical;
    if (target.size() != n || feasible_start.size() != n)
        return invalid("zoutendijk.shape", "Target, feasible start, and feasible set dimensions must agree.");
    if (!finite(target) || !finite(feasible_start) || !std::isfinite(numerical.absolute_tolerance) ||
        numerical.absolute_tolerance < 0 || !std::isfinite(numerical.relative_tolerance) ||
        numerical.relative_tolerance < 0 || policy.max_iterations == 0)
        return invalid("zoutendijk.input", "Finite values, nonnegative tolerances, and a positive iteration limit are required.");
    if (n > std::numeric_limits<std::size_t>::max() / 2)
        return invalid("zoutendijk.capacity", "Direction split-variable count overflows size_t.");

    auto check_input = make_linear_program({feasible_set.identity(), Vector(n, 0), 0,
        copy_matrix(feasible_set), {feasible_set.variables().begin(), feasible_set.variables().end()},
        {feasible_set.rows().begin(), feasible_set.rows().end()}});
    if (const auto* errors = std::get_if<Diagnostics>(&check_input)) return *errors;
    const auto& checked_set = std::get<LinearProgram>(check_input);
    auto initial_evaluation = evaluate_primal(checked_set, feasible_start, numerical, { {"csl.zoutendijk.feasibility"}, "1" });
    if (const auto* errors = std::get_if<Diagnostics>(&initial_evaluation)) return *errors;
    const auto initial = std::get<PrimalEvaluation>(initial_evaluation);
    if (!within(initial.residuals.rows, numerical) || !within(initial.residuals.variables, numerical))
        return invalid("zoutendijk.start", "The supplied start is not feasible within the declared numerical policy.");

    Vector x(feasible_start.begin(), feasible_start.end());
    const auto& matrix = checked_set.constraints();
    const auto row_count = checked_set.rows().size();
    if (n > (std::numeric_limits<std::size_t>::max() - 1) / 2 ||
        row_count > (std::numeric_limits<std::size_t>::max() - 2 * n - 1) / 2)
        return invalid("zoutendijk.capacity", "Maximum active direction rows overflow size_t.");
    for (std::size_t iteration = 0; iteration < policy.max_iterations; ++iteration) {
        if (context.cancellation.stop_requested()) return stopped(Termination::cancelled, x, iteration);
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return ProjectionStopped{ProjectionStopReason::deadline_expired, x, iteration};

        Vector gradient(n);
        for (std::size_t j = 0; j < n; ++j) gradient[j] = x[j] - target[j];
        if (!finite(gradient)) return stopped(Termination::numerical_failure, x, iteration);
        double gradient_scale = 1;
        for (const double value : gradient) gradient_scale = std::max(gradient_scale, std::abs(value));
        const double grad_tolerance = numerical.absolute_tolerance + numerical.relative_tolerance * gradient_scale;
        if (!std::isfinite(grad_tolerance)) return stopped(Termination::numerical_failure, x, iteration);
        Vector direction_objective(2 * n);
        for (std::size_t j = 0; j < n; ++j) {
            direction_objective[j] = gradient[j];
            direction_objective[n + j] = -gradient[j];
        }
        SparseMatrix direction_matrix{0, 2 * n, {0}, {}, {}};
        std::vector<Interval> direction_rows;
        const auto add_facet = [&](auto coefficient_at, Interval bound) {
            for (std::size_t j = 0; j < n; ++j) {
                const double value = coefficient_at(j);
                if (value != 0) {
                    direction_matrix.column_indices.push_back(j);
                    direction_matrix.values.push_back(value);
                }
            }
            for (std::size_t j = 0; j < n; ++j) {
                const double value = coefficient_at(j);
                if (value != 0) {
                    direction_matrix.column_indices.push_back(n + j);
                    direction_matrix.values.push_back(-value);
                }
            }
            ++direction_matrix.rows;
            direction_matrix.row_offsets.push_back(direction_matrix.values.size());
            direction_rows.push_back(bound);
        };
        for (std::size_t i = 0; i < row_count; ++i) {
            const double value = activity(matrix, i, x);
            if (!std::isfinite(value)) return stopped(Termination::numerical_failure, x, iteration);
            const auto& bound = checked_set.rows()[i];
            if (bound.upper && close_to(value, *bound.upper, numerical))
                add_facet([&](std::size_t j) { return matrix(i, j); }, { {}, 0 });
            if (bound.lower && close_to(value, *bound.lower, numerical))
                add_facet([&](std::size_t j) { return matrix(i, j); }, { 0, {} });
        }
        for (std::size_t j = 0; j < n; ++j) {
            if (checked_set.variables()[j].upper && close_to(x[j], *checked_set.variables()[j].upper, numerical))
                add_facet([&](std::size_t k) { return k == j ? 1.0 : 0.0; }, { {}, 0 });
            if (checked_set.variables()[j].lower && close_to(x[j], *checked_set.variables()[j].lower, numerical))
                add_facet([&](std::size_t k) { return k == j ? 1.0 : 0.0; }, { 0, {} });
        }
        const auto normalization_row = direction_matrix.rows++;
        for (std::size_t j = 0; j < 2 * n; ++j) {
            direction_matrix.column_indices.push_back(j); direction_matrix.values.push_back(1);
        }
        direction_matrix.row_offsets.push_back(direction_matrix.values.size());
        direction_rows.push_back({{}, 1});
        (void)normalization_row;
        std::string id = feasible_set.identity().program.value + "/zoutendijk/direction/" + std::to_string(iteration);
        auto direction_program = make_linear_program({{feasible_set.identity().problem, {std::move(id)}},
            std::move(direction_objective), 0, std::move(direction_matrix),
            std::vector<Interval>(2 * n, Interval{0, 1}), std::move(direction_rows)});
        if (const auto* errors = std::get_if<Diagnostics>(&direction_program)) return *errors;
        const auto& lp = std::get<LinearProgram>(direction_program);
        auto solved = direction_workspace.solve(lp, context);
        if (const auto* unsupported = std::get_if<Unsupported>(&solved)) return *unsupported;
        const auto& answer = std::get<ProgramResult>(solved);
        if (auto errors = check_program_result(answer, lp, Assurance::numerical); !errors.empty()) return errors;
        if (answer.termination != Termination::completed || answer.outcome.value != MathematicalOutcome::optimal || !answer.primal)
            return stopped(answer.termination == Termination::completed ? Termination::numerical_failure : answer.termination,
                x, iteration);
        auto direction_check = evaluate_primal(lp, *answer.primal, numerical, {{"csl.zoutendijk.direction"}, "1"});
        if (const auto* errors = std::get_if<Diagnostics>(&direction_check)) return *errors;
        const auto direction_residuals = std::get<PrimalEvaluation>(direction_check).residuals;
        if (!within(direction_residuals.rows, numerical) || !within(direction_residuals.variables, numerical))
            return stopped(Termination::numerical_failure, x, iteration);
        Vector d(n);
        for (std::size_t j = 0; j < n; ++j) d[j] = (*answer.primal)[j] - (*answer.primal)[n + j];
        double slope = 0, norm_squared = 0;
        for (std::size_t j = 0; j < n; ++j) {
            slope = std::fma(gradient[j], d[j], slope);
            norm_squared = std::fma(d[j], d[j], norm_squared);
        }
        if (!std::isfinite(slope) || !std::isfinite(norm_squared))
            return stopped(Termination::numerical_failure, x, iteration);
        const double stationarity = std::max(0.0, -slope);
        if (slope >= -grad_tolerance || norm_squared == 0) {
            double distance = 0;
            for (std::size_t j = 0; j < n; ++j) distance = std::hypot(distance, x[j] - target[j]);
            const double quadratic = 0.5 * distance * distance;
            if (!std::isfinite(distance) || !std::isfinite(quadratic))
                return stopped(Termination::numerical_failure, x, iteration);
            return ProjectionSuccess{std::move(x), distance, quadratic, stationarity, iteration};
        }

        double maximum_step = std::numeric_limits<double>::infinity();
        for (std::size_t i = 0; i < row_count; ++i) {
            const auto& bound = checked_set.rows()[i];
            const double value = activity(matrix, i, x);
            double derivative = 0;
            for (std::size_t j = 0; j < n; ++j) derivative = std::fma(matrix(i, j), d[j], derivative);
            if (derivative > 0 && bound.upper) maximum_step = std::min(maximum_step, (*bound.upper - value) / derivative);
            if (derivative < 0 && bound.lower) maximum_step = std::min(maximum_step, (*bound.lower - value) / derivative);
        }
        for (std::size_t j = 0; j < n; ++j) {
            if (d[j] > 0 && checked_set.variables()[j].upper)
                maximum_step = std::min(maximum_step, (*checked_set.variables()[j].upper - x[j]) / d[j]);
            if (d[j] < 0 && checked_set.variables()[j].lower)
                maximum_step = std::min(maximum_step, (*checked_set.variables()[j].lower - x[j]) / d[j]);
        }
        const double exact_step = -slope / norm_squared;
        const double step = std::min(maximum_step, exact_step);
        if (!(step > 0) || !std::isfinite(step)) return stopped(Termination::numerical_failure, x, iteration);
        Vector candidate = x;
        for (std::size_t j = 0; j < n; ++j) candidate[j] = std::fma(step, d[j], candidate[j]);
        if (!finite(candidate)) return stopped(Termination::numerical_failure, x, iteration + 1);
        auto check = evaluate_primal(checked_set, candidate, numerical, {{"csl.zoutendijk.feasibility"}, "1"});
        if (const auto* errors = std::get_if<Diagnostics>(&check)) return *errors;
        const auto residuals = std::get<PrimalEvaluation>(check).residuals;
        if (!within(residuals.rows, numerical) || !within(residuals.variables, numerical))
            return stopped(Termination::numerical_failure, x, iteration + 1);
        x = std::move(candidate);
    }
    return stopped(Termination::resource_limit, x, policy.max_iterations);
}
} // namespace csl::optimization::zoutendijk
