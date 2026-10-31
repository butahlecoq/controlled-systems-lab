#include <csl/reachability/finite_plan_zonotope.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <numeric>
#include <span>

namespace csl::reachability {
namespace {

struct Interval { double lower; double upper; };
struct Box { Vector lower; Vector upper; };

Unsupported unsupported(std::string field, std::string explanation) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
}

std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Zonotope propagation cancelled."};
    if(context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return OperationStopped{StopReason::deadline_expired, "Zonotope propagation deadline expired."};
    return {};
}

double down(double value) {
    return std::nextafter(value, -std::numeric_limits<double>::infinity());
}

double up(double value) {
    return std::nextafter(value, std::numeric_limits<double>::infinity());
}

std::optional<Interval> multiply(double lhs, double rhs) {
    if(lhs == 0.0 || rhs == 0.0) return Interval{0.0, 0.0};
    const auto value = lhs * rhs;
    if(!std::isfinite(value)) return {};
    return Interval{down(value), up(value)};
}

std::optional<Interval> sum(Interval lhs, Interval rhs) {
    if(lhs.lower == 0.0 && lhs.upper == 0.0) return rhs;
    if(rhs.lower == 0.0 && rhs.upper == 0.0) return lhs;
    const auto lower = lhs.lower + rhs.lower;
    const auto upper = lhs.upper + rhs.upper;
    if(!std::isfinite(lower) || !std::isfinite(upper)) return {};
    return Interval{down(lower), up(upper)};
}

std::optional<double> positive_difference_up(double larger, double smaller) {
    const auto value = larger - smaller;
    if(!std::isfinite(value) || value < 0.0) return {};
    return value == 0.0 ? value : up(value);
}

std::optional<double> interval_radius(Interval interval, double center) {
    const auto lower = positive_difference_up(center, interval.lower);
    const auto upper = positive_difference_up(interval.upper, center);
    if(!lower || !upper) return {};
    return std::max(*lower, *upper);
}

std::optional<double> add_up(double lhs, double rhs) {
    const auto value = lhs + rhs;
    if(!std::isfinite(value)) return {};
    return value == 0.0 ? value : up(value);
}

std::variant<Box, Unsupported, OperationStopped> bounds(const sets::SetData& set, std::string field,
    const ExecutionContext& context) {
    const auto dimension = set.metadata()->set.dimension;
    Box result{Vector(dimension, std::numeric_limits<double>::infinity()),
        Vector(dimension, -std::numeric_limits<double>::infinity())};
    const auto representation = set.representation();
    if(const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        for(std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
            const auto value = singleton->point[coordinate];
            if(!std::isfinite(value))
                return unsupported(std::move(field), "Set coordinates must be finite.");
            result.lower[coordinate] = result.upper[coordinate] = value;
        }
        return result;
    }
    const auto* vertices = std::get_if<sets::VRepresentation>(&representation);
    if(!vertices || vertices->vertices.rows() == 0 || vertices->rays.rows() != 0)
        return unsupported(std::move(field), "A nonempty bounded V set or singleton is required.");
    for(std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
        if(const auto stop = stopped(context)) return *stop;
        for(std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
            const auto value = vertices->vertices(row, coordinate);
            if(!std::isfinite(value))
                return unsupported(std::move(field), "Set coordinates must be finite.");
            result.lower[coordinate] = std::min(result.lower[coordinate], value);
            result.upper[coordinate] = std::max(result.upper[coordinate], value);
        }
    }
    return result;
}

std::variant<FinitePlanZonotopeTrace::Stage, Unsupported, OperationStopped> axis_zonotope(
    const sets::SetData& set, std::string field, std::string factor_prefix,
    std::size_t generator_limit, const ExecutionContext& context) {
    auto bounded = bounds(set, std::move(field), context);
    if(const auto* error = std::get_if<Unsupported>(&bounded)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&bounded)) return *stop;
    const auto& box = std::get<Box>(bounded);
    const auto dimension = box.lower.size();
    FinitePlanZonotopeTrace::Stage result{Vector(dimension), {}, {}};
    Vector radii(dimension);
    std::vector<std::size_t> active_coordinates;
    active_coordinates.reserve(dimension);
    for(std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        // std::midpoint avoids overflowing when the endpoints have the same sign.
        result.center[coordinate] = std::midpoint(box.lower[coordinate], box.upper[coordinate]);
        const auto below = positive_difference_up(result.center[coordinate], box.lower[coordinate]);
        const auto above = positive_difference_up(box.upper[coordinate], result.center[coordinate]);
        if(!below || !above)
            return unsupported("finite_plan_zonotope.input.radius", "A finite outward coordinate radius could not be stored.");
        radii[coordinate] = std::max(*below, *above);
        if(radii[coordinate] > 0.0) active_coordinates.push_back(coordinate);
    }
    if(active_coordinates.size() > generator_limit)
        return unsupported("finite_plan_zonotope.generators.limit",
            "Initial or disturbance coordinate generators exceed the caller limit.");
    if(dimension != 0 && active_coordinates.size() > std::numeric_limits<std::size_t>::max() / dimension)
        return unsupported("finite_plan_zonotope.input.capacity", "Generator matrix size overflows.");
    result.generators = Matrix{dimension, active_coordinates.size(),
        Vector(dimension * active_coordinates.size(), 0.0)};
    result.factors.reserve(active_coordinates.size());
    for(std::size_t column = 0; column < active_coordinates.size(); ++column) {
        const auto coordinate = active_coordinates[column];
        result.generators.values[coordinate * active_coordinates.size() + column] = radii[coordinate];
        result.factors.push_back({factor_prefix + "/" + std::to_string(coordinate)});
    }
    return result;
}

std::variant<FinitePlanZonotopeTrace::Stage, Unsupported, OperationStopped> propagate(
    const model::DynamicsStage& dynamics, const FinitePlanZonotopeTrace::Stage& current,
    const FinitePlanZonotopeTrace::Stage& disturbance, std::span<const double> control,
    std::size_t generator_limit, const ExecutionContext& context, std::size_t stage) {
    const auto n = dynamics.A.rows();
    const auto q = disturbance.center.size();
    const auto current_count = current.factors.size();
    const auto disturbance_count = disturbance.factors.size();
    if(n != dynamics.A.cols() || n != current.center.size() || dynamics.B.rows() != n ||
       dynamics.B.cols() != control.size() || dynamics.E.rows() != n ||
       dynamics.E.cols() != q || dynamics.offset.size() != n ||
       current.generators.rows != n || current.generators.cols != current_count ||
       disturbance.generators.rows != q || disturbance.generators.cols != disturbance_count)
        return unsupported("finite_plan_zonotope.stage.dimension", "Dynamics and generator dimensions differ.");
    if(disturbance_count > std::numeric_limits<std::size_t>::max() - n ||
       current_count > std::numeric_limits<std::size_t>::max() - disturbance_count - n)
        return unsupported("finite_plan_zonotope.stage.capacity", "Generator count overflows.");
    const auto column_count = current_count + disturbance_count + n;
    if(column_count > generator_limit)
        return unsupported("finite_plan_zonotope.generators.limit",
            "Stage generator count exceeds the caller limit.");
    if(n != 0 && column_count > std::numeric_limits<std::size_t>::max() / n)
        return unsupported("finite_plan_zonotope.stage.capacity", "Generator matrix size overflows.");

    FinitePlanZonotopeTrace::Stage result{
        Vector(n), Matrix{n, column_count, Vector(n * column_count, 0.0)}, {}};
    Vector rounding(n, 0.0);
    for(std::size_t row = 0; row < n; ++row) {
        if(const auto stop = stopped(context)) return *stop;
        Interval center{dynamics.offset[row], dynamics.offset[row]};
        const auto accumulate_center = [&](double coefficient, double value) -> bool {
            const auto term = multiply(coefficient, value);
            if(!term) return false;
            const auto next = sum(center, *term);
            if(!next) return false;
            center = *next;
            return true;
        };
        for(std::size_t coordinate = 0; coordinate < n; ++coordinate)
            if(!accumulate_center(dynamics.A(row, coordinate), current.center[coordinate]))
                return OperationStopped{StopReason::numerical_failure, "Zonotope center propagation overflowed."};
        for(std::size_t coordinate = 0; coordinate < control.size(); ++coordinate)
            if(!accumulate_center(dynamics.B(row, coordinate), control[coordinate]))
                return OperationStopped{StopReason::numerical_failure, "Zonotope control offset overflowed."};
        for(std::size_t coordinate = 0; coordinate < q; ++coordinate)
            if(!accumulate_center(dynamics.E(row, coordinate), disturbance.center[coordinate]))
                return OperationStopped{StopReason::numerical_failure, "Zonotope disturbance offset overflowed."};
        result.center[row] = std::midpoint(center.lower, center.upper);
        const auto center_error = interval_radius(center, result.center[row]);
        if(!center_error)
            return OperationStopped{StopReason::numerical_failure, "Zonotope center rounding could not be bounded."};
        rounding[row] = *center_error;

        const auto transform_column = [&](std::size_t output_column, std::size_t terms,
            const auto& coefficient) -> bool {
            Interval image{0.0, 0.0};
            for(std::size_t coordinate = 0; coordinate < terms; ++coordinate) {
                const auto term = coefficient(coordinate);
                if(!term) return false;
                const auto next = sum(image, *term);
                if(!next) return false;
                image = *next;
            }
            const auto value = std::midpoint(image.lower, image.upper);
            const auto error = interval_radius(image, value);
            if(!std::isfinite(value) || !error) return false;
            const auto next_error = add_up(rounding[row], *error);
            if(!next_error) return false;
            rounding[row] = *next_error;
            result.generators.values[row * column_count + output_column] = value;
            return true;
        };
        for(std::size_t column = 0; column < current_count; ++column)
            if(!transform_column(column, n, [&](std::size_t coordinate) {
                return multiply(dynamics.A(row, coordinate),
                    current.generators.values[coordinate * current_count + column]);
            })) return OperationStopped{StopReason::numerical_failure,
                "Zonotope state generator could not be enclosed."};
        for(std::size_t column = 0; column < disturbance_count; ++column)
            if(!transform_column(current_count + column, q, [&](std::size_t coordinate) {
                return multiply(dynamics.E(row, coordinate),
                    disturbance.generators.values[coordinate * disturbance_count + column]);
            })) return OperationStopped{StopReason::numerical_failure,
                "Zonotope disturbance generator could not be enclosed."};
        result.generators.values[row * column_count + current_count + disturbance_count + row] = rounding[row];
    }

    result.factors = current.factors;
    result.factors.reserve(column_count);
    for(const auto& factor : disturbance.factors)
        result.factors.push_back({"stage/" + std::to_string(stage) + "/" + factor.value});
    for(std::size_t coordinate = 0; coordinate < n; ++coordinate)
        result.factors.push_back({"roundoff/" + std::to_string(stage) + "/" + std::to_string(coordinate)});
    return result;
}

} // namespace

FinitePlanZonotopeOutcome finite_plan_zonotope(const FixedPlanRequest& request,
    FinitePlanZonotopeLimits limits, const ExecutionContext& context) {
    const auto n = request.system.dimensions().state;
    const auto horizon = request.system.horizon();
    if(request.controls.size() != horizon || request.disturbances.size() != horizon ||
       request.admissible_states.size() != horizon + 1)
        return unsupported("finite_plan_zonotope.horizon", "Controls, disturbances and safe sets must match the model horizon.");
    if(request.initial.metadata()->set.dimension != n)
        return unsupported("finite_plan_zonotope.initial", "Initial set dimension differs from model.");
    for(const auto& safe : request.admissible_states)
        if(safe.metadata()->set.dimension != n ||
           !std::holds_alternative<sets::UniversalRepresentation>(safe.representation()))
            return unsupported("finite_plan_zonotope.safe_sets", "Universal state constraints are the only supported profile.");

    auto initial = axis_zonotope(request.initial, "finite_plan_zonotope.initial",
        "finite-plan-zonotope/initial", limits.max_generators_per_stage, context);
    if(const auto* error = std::get_if<Unsupported>(&initial)) return *error;
    if(const auto* stop = std::get_if<OperationStopped>(&initial)) return *stop;
    FinitePlanZonotopeTrace trace;
    trace.stages.push_back(std::get<FinitePlanZonotopeTrace::Stage>(std::move(initial)));
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(const auto stop = stopped(context)) return *stop;
        auto disturbance = axis_zonotope(request.disturbances[stage],
            "finite_plan_zonotope.disturbance", "finite-plan-zonotope/disturbance/" +
                std::to_string(stage), limits.max_generators_per_stage, context);
        if(const auto* error = std::get_if<Unsupported>(&disturbance)) return *error;
        if(const auto* stop = std::get_if<OperationStopped>(&disturbance)) return *stop;
        const auto dynamics = request.system.stage({stage});
        if(const auto* error = std::get_if<Diagnostic>(&dynamics))
            return unsupported(error->field, error->explanation);
        const auto& control = request.controls[stage];
        if(control.size() != request.system.dimensions().control ||
           std::any_of(control.begin(), control.end(), [](double value) { return !std::isfinite(value); }))
            return unsupported("finite_plan_zonotope.control", "Control coordinates must be finite and dimensionally valid.");
        auto next = propagate(std::get<model::DynamicsStage>(dynamics), trace.stages.back(),
            std::get<FinitePlanZonotopeTrace::Stage>(disturbance), control,
            limits.max_generators_per_stage, context, stage);
        if(const auto* error = std::get_if<Unsupported>(&next)) return *error;
        if(const auto* stop = std::get_if<OperationStopped>(&next)) return *stop;
        trace.stages.push_back(std::get<FinitePlanZonotopeTrace::Stage>(std::move(next)));
    }
    return trace;
}

} // namespace csl::reachability
