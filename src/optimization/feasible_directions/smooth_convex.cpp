#include <csl/optimization/feasible_directions/smooth_convex.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <exception>
#include <limits>
#include <utility>

namespace csl::optimization::feasible_directions {
namespace {
Diagnostics invalid(std::string field, std::string message) {
    return {{DiagnosticCode::invalid_input, std::move(field), std::move(message)}};
}

bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](double value) { return std::isfinite(value); });
}

bool within(const ResidualMeasure& residual, NumericalPolicy numerical) {
    const double allowed = numerical.absolute_tolerance + numerical.relative_tolerance * residual.scale;
    return std::isfinite(allowed) && residual.violation <= allowed;
}

bool feasible(const LinearProgram& set, std::span<const double> point, NumericalPolicy numerical) {
    const auto checked = evaluate_primal(set, point, numerical, {{"csl.feasible-directions.feasibility"}, "1"});
    if (const auto* evaluation = std::get_if<PrimalEvaluation>(&checked))
        return within(evaluation->residuals.rows, numerical) &&
            within(evaluation->residuals.variables, numerical);
    return false;
}

SmoothStopReason map_stop(zoutendijk::ProjectionStopReason reason) {
    switch (reason) {
    case zoutendijk::ProjectionStopReason::cancelled: return SmoothStopReason::cancelled;
    case zoutendijk::ProjectionStopReason::deadline_expired: return SmoothStopReason::deadline_expired;
    case zoutendijk::ProjectionStopReason::resource_limit: return SmoothStopReason::resource_limit;
    case zoutendijk::ProjectionStopReason::operation_rejected: return SmoothStopReason::operation_rejected;
    case zoutendijk::ProjectionStopReason::contract_rejected: return SmoothStopReason::contract_rejected;
    case zoutendijk::ProjectionStopReason::numerical_failure: return SmoothStopReason::numerical_failure;
    }
    return SmoothStopReason::numerical_failure;
}
} // namespace

SmoothOutcome minimize(const LinearProgram& feasible_set, const SmoothObjective& objective,
    std::span<const double> feasible_start, LPWorkspace& projection_workspace,
    const ExecutionContext& context, SmoothPolicy policy) {
    const auto n = feasible_set.variables().size();
    const auto numerical = context.numerical;
    if (objective.dimension != n || feasible_start.size() != n)
        return invalid("feasible_directions.shape", "Objective, start, and feasible-set dimensions must agree.");
    if (objective.id.empty() || !objective.value || !objective.gradient || !finite(feasible_start) ||
        !std::isfinite(numerical.absolute_tolerance) || numerical.absolute_tolerance < 0 ||
        !std::isfinite(numerical.relative_tolerance) || numerical.relative_tolerance < 0 ||
        policy.max_iterations == 0 || policy.max_projection_iterations == 0 || policy.max_backtracks == 0 ||
        !(policy.armijo_fraction > 0 && policy.armijo_fraction < 1) ||
        !(policy.contraction > 0 && policy.contraction < 1) ||
        !(policy.minimum_step > 0 && policy.minimum_step <= 1))
        return invalid("feasible_directions.input", "Finite input, callbacks, and positive bounded line-search policy are required.");
    if (objective.claim != ObjectiveClaim::declared_convex)
        return Unsupported{{{DiagnosticCode::unsupported, "feasible_directions.objective.convexity",
            "The objective must be explicitly declared differentiable and convex; callbacks do not prove this property."}}};
    if (!feasible(feasible_set, feasible_start, numerical))
        return invalid("feasible_directions.start", "The supplied start is not feasible within the declared numerical policy.");

    Vector x(feasible_start.begin(), feasible_start.end());
    std::optional<double> value;
    std::size_t evaluations = 0;
    const auto stopped = [&](SmoothStopReason reason, std::size_t iterations) -> SmoothOutcome {
        return SmoothStopped{reason, x, value, iterations, evaluations};
    };
    if (context.cancellation.stop_requested()) return stopped(SmoothStopReason::cancelled, 0);
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return stopped(SmoothStopReason::deadline_expired, 0);
    double initial_value;
    try {
        initial_value = objective.value(x);
        ++evaluations;
    } catch (const std::exception&) {
        return stopped(SmoothStopReason::callback_failure, 0);
    } catch (...) {
        return stopped(SmoothStopReason::callback_failure, 0);
    }
    if (!std::isfinite(initial_value)) return stopped(SmoothStopReason::callback_failure, 0);
    value = initial_value;

    for (std::size_t iteration = 0; iteration < policy.max_iterations; ++iteration) {
        if (context.cancellation.stop_requested()) return stopped(SmoothStopReason::cancelled, iteration);
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return stopped(SmoothStopReason::deadline_expired, iteration);
        Vector gradient;
        try {
            gradient = objective.gradient(x);
        } catch (const std::exception&) {
            return stopped(SmoothStopReason::callback_failure, iteration);
        } catch (...) {
            return stopped(SmoothStopReason::callback_failure, iteration);
        }
        if (gradient.size() != n || !finite(gradient))
            return stopped(SmoothStopReason::callback_failure, iteration);
        Vector target(n);
        for (std::size_t j = 0; j < n; ++j) target[j] = x[j] - gradient[j];
        if (!finite(target)) return stopped(SmoothStopReason::numerical_failure, iteration);
        auto projection = zoutendijk::project(feasible_set, target, x, projection_workspace,
            context, {policy.max_projection_iterations});
        if (const auto* unsupported = std::get_if<Unsupported>(&projection)) return *unsupported;
        if (const auto* errors = std::get_if<Diagnostics>(&projection)) return *errors;
        if (const auto* failure = std::get_if<zoutendijk::ProjectionStopped>(&projection))
            return stopped(map_stop(failure->reason), iteration);
        const auto& endpoint = std::get<zoutendijk::ProjectionSuccess>(projection).point;
        if (!feasible(feasible_set, endpoint, numerical))
            return stopped(SmoothStopReason::numerical_failure, iteration);

        Vector direction(n);
        double slope = 0;
        double residual = 0;
        for (std::size_t j = 0; j < n; ++j) {
            direction[j] = endpoint[j] - x[j];
            slope = std::fma(gradient[j], direction[j], slope);
            residual = std::hypot(residual, direction[j]);
        }
        // A coordinate offset must not enlarge a projected-step stationarity threshold.
        const double threshold = numerical.absolute_tolerance + numerical.relative_tolerance;
        if (!std::isfinite(slope) || !std::isfinite(residual) || !std::isfinite(threshold))
            return stopped(SmoothStopReason::numerical_failure, iteration);
        if (residual == 0)
            return SmoothStationary{std::move(x), *value, std::move(gradient), residual,
                iteration, evaluations, StationarityReason::zero_projected_direction};
        if (slope >= 0) return stopped(SmoothStopReason::numerical_failure, iteration);
        if (residual <= threshold)
            return SmoothStationary{std::move(x), *value, std::move(gradient), residual,
                iteration, evaluations, StationarityReason::projected_gradient_tolerance};

        double step = 1;
        bool accepted = false;
        for (std::size_t backtrack = 0; backtrack < policy.max_backtracks && step >= policy.minimum_step;
            ++backtrack, step *= policy.contraction) {
            if (context.cancellation.stop_requested()) return stopped(SmoothStopReason::cancelled, iteration);
            if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
                return stopped(SmoothStopReason::deadline_expired, iteration);
            Vector candidate(n);
            for (std::size_t j = 0; j < n; ++j)
                candidate[j] = std::fma(step, direction[j], x[j]);
            if (!finite(candidate) || candidate == x || !feasible(feasible_set, candidate, numerical)) {
                continue;
            }
            double candidate_value;
            try {
                candidate_value = objective.value(candidate);
                ++evaluations;
            } catch (const std::exception&) {
                return stopped(SmoothStopReason::callback_failure, iteration);
            } catch (...) {
                return stopped(SmoothStopReason::callback_failure, iteration);
            }
            if (!std::isfinite(candidate_value)) return stopped(SmoothStopReason::callback_failure, iteration);
            const double armijo_limit = std::fma(policy.armijo_fraction * step, slope, *value);
            if (std::isfinite(armijo_limit) && candidate_value <= armijo_limit && candidate_value < *value) {
                x = std::move(candidate);
                value = candidate_value;
                accepted = true;
                break;
            }
        }
        if (!accepted) return stopped(SmoothStopReason::line_search_stall, iteration);
    }
    return stopped(SmoothStopReason::resource_limit, policy.max_iterations);
}
} // namespace csl::optimization::feasible_directions
