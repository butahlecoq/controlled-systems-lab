#include <csl/reachability/finite_plan_box.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace csl::reachability {
namespace {
Unsupported unsupported(std::string field, std::string explanation) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
}

double outward(double value, bool upward) {
    if(!std::isfinite(value)) return value;
    return std::nextafter(value, upward ? std::numeric_limits<double>::infinity()
                                        : -std::numeric_limits<double>::infinity());
}

std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Box propagation cancelled."};
    if(context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return OperationStopped{StopReason::deadline_expired, "Box propagation deadline expired."};
    return {};
}

std::variant<BoxStage, Unsupported> bounds(const sets::SetData& set, std::string field) {
    const auto dimension = set.metadata()->set.dimension;
    BoxStage result{Vector(dimension, std::numeric_limits<double>::infinity()),
                    Vector(dimension, -std::numeric_limits<double>::infinity())};
    const auto rep = set.representation();
    if(const auto* singleton = std::get_if<sets::SingletonRepresentation>(&rep)) {
        for(std::size_t j = 0; j < dimension; ++j) {
            if(!std::isfinite(singleton->point[j]))
                return unsupported(std::move(field), "Set coordinates must be finite.");
            result.lower[j] = result.upper[j] = singleton->point[j];
        }
        return result;
    }
    const auto* vertices = std::get_if<sets::VRepresentation>(&rep);
    if(!vertices || vertices->rays.rows() != 0 || vertices->vertices.rows() == 0)
        return unsupported(std::move(field), "A nonempty bounded V set or singleton is required.");
    for(std::size_t i = 0; i < vertices->vertices.rows(); ++i)
        for(std::size_t j = 0; j < dimension; ++j) {
            const auto value = vertices->vertices(i, j);
            if(!std::isfinite(value))
                return unsupported(std::move(field), "Set coordinates must be finite.");
            result.lower[j] = std::min(result.lower[j], value);
            result.upper[j] = std::max(result.upper[j], value);
        }
    return result;
}

void add_interval(double coefficient, double lower, double upper,
                  double& output_lower, double& output_upper) {
    if(coefficient == 0.0) return;
    const auto left = coefficient > 0 ? coefficient * lower : coefficient * upper;
    const auto right = coefficient > 0 ? coefficient * upper : coefficient * lower;
    output_lower = outward(output_lower + outward(left, false), false);
    output_upper = outward(output_upper + outward(right, true), true);
}

std::variant<BoxStage, OperationStopped> step(const model::DynamicsStage& dynamics,
    const BoxStage& current, std::span<const double> control, const BoxStage& disturbance,
    const ExecutionContext& context) {
    BoxStage next{Vector(dynamics.A.rows()), Vector(dynamics.A.rows())};
    for(std::size_t i = 0; i < dynamics.A.rows(); ++i) {
        if(const auto stop = stopped(context)) return *stop;
        double lower = dynamics.offset[i];
        double upper = dynamics.offset[i];
        for(std::size_t j = 0; j < dynamics.A.cols(); ++j)
            add_interval(dynamics.A(i,j), current.lower[j], current.upper[j], lower, upper);
        for(std::size_t j = 0; j < dynamics.B.cols(); ++j) {
            const auto value = dynamics.B(i,j) * control[j];
            lower = outward(lower + outward(value, false), false);
            upper = outward(upper + outward(value, true), true);
        }
        for(std::size_t j = 0; j < dynamics.E.cols(); ++j)
            add_interval(dynamics.E(i,j), disturbance.lower[j], disturbance.upper[j], lower, upper);
        if(!std::isfinite(lower) || !std::isfinite(upper))
            return OperationStopped{StopReason::numerical_failure, "Box propagation overflowed."};
        next.lower[i] = lower;
        next.upper[i] = upper;
    }
    return next;
}
}

FinitePlanBoxOutcome finite_plan_box(const FixedPlanRequest& request,
    const ExecutionContext& context) {
    const auto dimension = request.system.dimensions().state;
    const auto horizon = request.system.horizon();
    if(request.controls.size() != horizon || request.disturbances.size() != horizon ||
       request.admissible_states.size() != horizon + 1)
        return unsupported("finite_plan_box.horizon", "Controls, disturbances and safe sets must match the model horizon.");
    if(request.initial.metadata()->set.dimension != dimension)
        return unsupported("finite_plan_box.initial", "Initial set dimension differs from model.");
    const auto model_dimensions = request.system.dimensions();
    for(const auto& safe : request.admissible_states)
        if(safe.metadata()->set.dimension != dimension ||
           !std::holds_alternative<sets::UniversalRepresentation>(safe.representation()))
            return unsupported("finite_plan_box.safe_sets", "This initial box propagator supports universal state constraints only.");

    auto initial = bounds(request.initial, "finite_plan_box.initial");
    if(const auto* error = std::get_if<Unsupported>(&initial)) return *error;
    FinitePlanBoxTrace trace;
    trace.stages.push_back(std::get<BoxStage>(std::move(initial)));
    std::vector<BoxStage> disturbances;
    disturbances.reserve(horizon);
    for(const auto& set : request.disturbances) {
        auto box = bounds(set, "finite_plan_box.disturbance");
        if(const auto* error = std::get_if<Unsupported>(&box)) return *error;
        disturbances.push_back(std::get<BoxStage>(std::move(box)));
    }
    for(std::size_t k = 0; k < horizon; ++k) {
        if(const auto stop = stopped(context)) return *stop;
        const auto dynamics = request.system.stage({k});
        if(const auto* error = std::get_if<Diagnostic>(&dynamics))
            return unsupported(error->field, error->explanation);
        const auto& control = request.controls[k];
        if(control.size() != request.system.dimensions().control ||
           disturbances[k].lower.size() != request.system.dimensions().external)
            return unsupported("finite_plan_box.stage.dimension", "Control or disturbance dimension differs from model.");
        if(std::any_of(control.begin(), control.end(), [](double value) { return !std::isfinite(value); }))
            return unsupported("finite_plan_box.control", "Control coordinates must be finite.");
        const auto& stage_model = std::get<model::DynamicsStage>(dynamics);
        if(stage_model.A.rows() != dimension || stage_model.A.cols() != dimension ||
           stage_model.B.rows() != dimension || stage_model.B.cols() != model_dimensions.control ||
           stage_model.E.rows() != dimension || stage_model.E.cols() != model_dimensions.external ||
           stage_model.offset.size() != dimension)
            return unsupported("finite_plan_box.stage.model", "Dynamics stage has inconsistent dimensions.");
        auto next = step(std::get<model::DynamicsStage>(dynamics), trace.stages.back(),
                         control, disturbances[k], context);
        if(const auto* stop = std::get_if<OperationStopped>(&next)) return *stop;
        trace.stages.push_back(std::get<BoxStage>(std::move(next)));
    }
    return trace;
}
} // namespace csl::reachability
