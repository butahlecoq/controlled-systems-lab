#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <string>

namespace csl::geometry {
namespace {

Diagnostics invalid(std::string field, std::string explanation) {
    return {{DiagnosticCode::invalid_input, std::move(field), std::move(explanation)}};
}

std::optional<LinearProgram> membership_program(const PointCloud& cloud,
        const std::vector<std::size_t>& support, std::size_t candidate) {
    const auto dimension = cloud.points[candidate].size();
    const auto count = support.size();
    if (dimension == std::numeric_limits<std::size_t>::max()) return {};
    const auto rows = dimension + 1;
    if (count && rows > std::numeric_limits<std::size_t>::max() / count) return {};
    SparseMatrix matrix{rows, count, {}, {}, {}};
    if (rows == std::numeric_limits<std::size_t>::max()) return {};
    matrix.row_offsets.reserve(rows + 1);
    matrix.column_indices.reserve(rows * count);
    matrix.values.reserve(rows * count);
    matrix.row_offsets.push_back(0);
    for (std::size_t r = 0; r < dimension; ++r) {
        for (std::size_t c = 0; c < count; ++c) {
            matrix.column_indices.push_back(c);
            matrix.values.push_back(cloud.points[support[c]][r]);
        }
        matrix.row_offsets.push_back(matrix.values.size());
    }
    for (std::size_t c = 0; c < count; ++c) {
        matrix.column_indices.push_back(c);
        matrix.values.push_back(1.0);
    }
    matrix.row_offsets.push_back(matrix.values.size());
    Vector rhs = cloud.points[candidate];
    rhs.push_back(1.0);
    std::vector<Interval> equalities;
    equalities.reserve(rows);
    for (double value : rhs) equalities.push_back({value, value});
    LinearProgramInput input{
        {cloud.problem, {"hull-membership-" + std::to_string(candidate)}},
        Vector(count, 0.0), 0.0, std::move(matrix),
        std::vector<Interval>(count, Interval{0.0, std::nullopt}),
        std::move(equalities)};
    auto created = optimization::make_linear_program(input);
    if (auto* program = std::get_if<LinearProgram>(&created)) return *program;
    return {};
}

std::optional<RemovalCertificate> certificate(const PointCloud& cloud,
        const std::vector<std::size_t>& support, std::size_t candidate, const LinearProgram& program,
        const ProgramResult& result, const ExecutionContext& context) {
    if (result.termination != Termination::completed ||
        result.outcome.value != MathematicalOutcome::optimal || !result.primal ||
        result.outcome.subject != program.identity() ||
        result.primal->size() != support.size()) return {};
    auto checked = optimization::evaluate_primal(
        program, *result.primal, context.numerical,
        {"hull-reducer.barycentric-residual", "1"});
    if (!std::holds_alternative<optimization::PrimalEvaluation>(checked)) return {};
    const auto& primal = std::get<optimization::PrimalEvaluation>(checked);
    const double primal_tolerance = context.numerical.absolute_tolerance +
        context.numerical.relative_tolerance * primal.residuals.rows.scale;
    const double variable_tolerance = context.numerical.absolute_tolerance +
        context.numerical.relative_tolerance * primal.residuals.variables.scale;
    if (!std::isfinite(primal_tolerance) || !std::isfinite(variable_tolerance) ||
        primal.residuals.rows.violation > primal_tolerance ||
        primal.residuals.variables.violation > variable_tolerance) return {};
    // Recheck the barycentric equations against the original point data rather
    // than trusting the adapter's claim or residual payload.
    Vector weights = *result.primal;
    const double tolerance = context.numerical.absolute_tolerance +
        context.numerical.relative_tolerance;
    double total = 0.0;
    for (double& weight : weights) {
        if (!std::isfinite(weight) || weight < -tolerance) return {};
        weight = std::max(0.0, weight);
        total += weight;
    }
    if (!std::isfinite(total) || total <= 0.0) return {};
    for (double& weight : weights) weight /= total;
    double normalized_total = 0.0;
    for (double weight : weights) normalized_total += weight;
    if (!std::isfinite(normalized_total)) return {};
    double max_residual = std::abs(normalized_total - 1.0);
    if (max_residual > tolerance) return {};
    for (std::size_t r = 0; r < cloud.points[candidate].size(); ++r) {
        double value = 0.0;
        for (std::size_t c = 0; c < support.size(); ++c)
            value += weights[c] * cloud.points[support[c]][r];
        if (!std::isfinite(value)) return {};
        const double residual = std::abs(value - cloud.points[candidate][r]);
        const double scale = std::max({1.0, std::abs(value), std::abs(cloud.points[candidate][r])});
        const double allowed = context.numerical.absolute_tolerance +
            context.numerical.relative_tolerance * scale;
        if (!std::isfinite(residual) || !std::isfinite(allowed) || residual > allowed) return {};
        max_residual = std::max(max_residual, residual);
    }
    std::vector<ConvexCombination> terms;
    for (std::size_t c = 0; c < support.size(); ++c)
        if (weights[c] > 0.0) terms.push_back({support[c], weights[c]});
    return RemovalCertificate{candidate, std::move(terms), program.identity(),
        {context.numerical.absolute_tolerance, context.numerical.relative_tolerance,
         max_residual, {"hull-reducer.barycentric-residual"}}};
}

bool completed_infeasibility(const ProgramResult& result) {
    return result.termination == Termination::completed &&
        result.outcome.value == MathematicalOutcome::infeasible;
}
} // namespace

HullReductionResult reduce_hull(const PointCloud& cloud, LPWorkspace& lp,
                                const ExecutionContext& context) {
    if (cloud.problem.value.empty()) return invalid("point_cloud.problem", "Problem identity is required");
    if (!std::isfinite(context.numerical.absolute_tolerance) || context.numerical.absolute_tolerance < 0 ||
        !std::isfinite(context.numerical.relative_tolerance) || context.numerical.relative_tolerance < 0 ||
        !std::isfinite(context.numerical.absolute_tolerance + context.numerical.relative_tolerance))
        return invalid("numerical", "Finite nonnegative tolerances are required");
    if (!cloud.points.empty()) {
        const auto dimension = cloud.points.front().size();
        for (const auto& point : cloud.points) {
            if (point.size() != dimension) return invalid("point_cloud.points", "All points must have equal dimension");
            if (std::any_of(point.begin(), point.end(), [](double x) { return !std::isfinite(x); }))
                return invalid("point_cloud.points", "Coordinates must be finite");
        }
    }

    HullReduction output{ReductionStatus::complete, {}, {}, 0, {}};
    output.retained.resize(cloud.points.size());
    std::iota(output.retained.begin(), output.retained.end(), std::size_t{0});
    if (output.retained.size() < 2) return output;

    std::size_t position = 0;
    while (position < output.retained.size()) {
        const auto candidate = output.retained[position];
        std::vector<std::size_t> support;
        support.reserve(output.retained.size() - 1);
        for (const auto point : output.retained) if (point != candidate) support.push_back(point);
        auto program = membership_program(cloud, support, candidate);
        if (!program) {
            output.status = ReductionStatus::incomplete;
            output.attempts.push_back({candidate, MembershipOutcome::malformed_result});
            ++position;
            continue;
        }
        ++output.lp_calls;
        auto outcome = lp.solve(*program, context);
        if (std::holds_alternative<Unsupported>(outcome)) {
            output.attempts.push_back({candidate, MembershipOutcome::unsupported});
            output.status = ReductionStatus::incomplete;
            break;
        }
        const auto& result = std::get<ProgramResult>(outcome);
        if (auto proof = certificate(cloud, support, candidate, *program, result, context)) {
            output.attempts.push_back({candidate, MembershipOutcome::feasible});
            output.removed.push_back(std::move(*proof));
            output.retained.erase(output.retained.begin() + static_cast<std::ptrdiff_t>(position));
            if (output.retained.size() == 1) break;
            continue;
        }
        if (completed_infeasibility(result)) {
            output.attempts.push_back({candidate, MembershipOutcome::infeasible});
            ++position;
            continue;
        }
        const auto stopped = result.termination == Termination::cancelled ||
            result.termination == Termination::resource_limit;
        output.attempts.push_back({candidate, stopped ? MembershipOutcome::stopped :
            (result.termination == Termination::completed ? MembershipOutcome::malformed_result :
             MembershipOutcome::numerical_failure)});
        output.status = ReductionStatus::incomplete;
        if (stopped) break;
        ++position;
    }
    return output;
}
} // namespace csl::geometry
