#include <csl/reachability/finite_plan_ellipsoid.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace csl::reachability {
namespace {
using Stage = FinitePlanEllipsoidTrace::Stage;

struct Interval { double lower; double upper; };

Unsupported unsupported(std::string field, std::string message) {
  return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

std::optional<OperationStopped> stopped(const ExecutionContext& context) {
  if (context.cancellation.stop_requested())
    return OperationStopped{StopReason::cancelled, "Ellipsoid propagation cancelled."};
  if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
    return OperationStopped{StopReason::deadline_expired, "Ellipsoid propagation deadline expired."};
  return {};
}

double down(double value) {
  return std::nextafter(value, -std::numeric_limits<double>::infinity());
}
double up(double value) {
  return std::nextafter(value, std::numeric_limits<double>::infinity());
}

std::optional<Interval> add(Interval left, Interval right) {
  const double lo = left.lower + right.lower;
  const double hi = left.upper + right.upper;
  if (!std::isfinite(lo) || !std::isfinite(hi)) return {};
  return Interval{down(lo), up(hi)};
}

std::variant<std::pair<Vector, Vector>, Unsupported> bounds(
    const sets::SetData& set, const std::string& field) {
  const auto dimension = set.metadata()->set.dimension;
  Vector lower(dimension, std::numeric_limits<double>::infinity());
  Vector upper(dimension, -std::numeric_limits<double>::infinity());
  const auto representation = set.representation();
  if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
    for (std::size_t i = 0; i < dimension; ++i) {
      if (!std::isfinite(singleton->point[i]))
        return unsupported(field, "Set coordinates must be finite.");
      lower[i] = upper[i] = singleton->point[i];
    }
    return std::pair{std::move(lower), std::move(upper)};
  }
  const auto* vertices = std::get_if<sets::VRepresentation>(&representation);
  if (!vertices || vertices->vertices.rows() == 0 || vertices->rays.rows() != 0)
    return unsupported(field, "A nonempty bounded V set or singleton is required.");
  for (std::size_t row = 0; row < vertices->vertices.rows(); ++row)
    for (std::size_t column = 0; column < dimension; ++column) {
      const double value = vertices->vertices(row, column);
      if (!std::isfinite(value)) return unsupported(field, "Set coordinates must be finite.");
      lower[column] = std::min(lower[column], down(value));
      upper[column] = std::max(upper[column], up(value));
    }
  return std::pair{std::move(lower), std::move(upper)};
}

std::optional<std::pair<double, double>> midpoint_radius(double lower,
                                                          double upper,
                                                          double dimension_scale) {
  const double center = lower * 0.5 + upper * 0.5;
  if (!std::isfinite(center)) return {};
  const double half_width = up(std::max(center - lower, upper - center));
  const double scaled = up(dimension_scale * half_width);
  if (!std::isfinite(scaled)) return {};
  return std::pair{center, scaled};
}

std::variant<Stage, Unsupported> enclose_box(const Vector& lower,
                                             const Vector& upper) {
  const double scale = std::sqrt(static_cast<double>(lower.size()));
  if (!std::isfinite(scale) || lower.empty())
    return unsupported("finite_plan_ellipsoid.dimension", "State dimension must be positive.");
  Stage result{Vector(lower.size()), Vector(lower.size())};
  for (std::size_t i = 0; i < lower.size(); ++i) {
    const auto values = midpoint_radius(lower[i], upper[i], scale);
    if (!values) return unsupported("finite_plan_ellipsoid.radius", "Ellipsoid radius overflowed.");
    result.center[i] = values->first;
    result.radii[i] = values->second;
  }
  return result;
}

std::optional<double> ellipsoid_support_radius(
    const model::DynamicsStage& dynamics, std::size_t row,
    const Vector& radii, bool include_control, const Vector& disturbance_radii) {
  double sum_squares = 0.0;
  for (std::size_t column = 0; column < radii.size(); ++column) {
    const double product = up(std::abs(dynamics.A(row, column)) * radii[column]);
    const double square = up(product * product);
    sum_squares = up(sum_squares + square);
    if (!std::isfinite(sum_squares)) return {};
  }
  double radius = up(std::sqrt(sum_squares));
  if (!std::isfinite(radius)) return {};
  for (std::size_t column = 0; column < disturbance_radii.size(); ++column) {
    const double product = up(std::abs(dynamics.E(row, column)) * disturbance_radii[column]);
    radius = up(radius + product);
    if (!std::isfinite(radius)) return {};
  }
  (void)include_control;
  return radius;
}

std::variant<Stage, Unsupported, OperationStopped> step(
    const model::DynamicsStage& dynamics, const Stage& current,
    std::span<const double> control, const Vector& disturbance_center,
    const Vector& disturbance_radii, const ExecutionContext& context) {
  const std::size_t dimension = dynamics.A.rows();
  Vector lower(dimension), upper(dimension);
  for (std::size_t row = 0; row < dimension; ++row) {
    if (const auto stop = stopped(context)) return *stop;
    Interval center{dynamics.offset[row], dynamics.offset[row]};
    for (std::size_t column = 0; column < current.center.size(); ++column) {
      const double coefficient = dynamics.A(row, column);
      const Interval term{down(coefficient * current.center[column]),
                          up(coefficient * current.center[column])};
      const auto sum = add(center, term);
      if (!sum) return unsupported("finite_plan_ellipsoid.center", "State center propagation overflowed.");
      center = *sum;
    }
    for (std::size_t column = 0; column < control.size(); ++column) {
      const double value = dynamics.B(row, column) * control[column];
      const auto sum = add(center, {down(value), up(value)});
      if (!sum) return unsupported("finite_plan_ellipsoid.center", "Control center propagation overflowed.");
      center = *sum;
    }
    for (std::size_t column = 0; column < disturbance_center.size(); ++column) {
      const double value = dynamics.E(row, column) * disturbance_center[column];
      const auto sum = add(center, {down(value), up(value)});
      if (!sum) return unsupported("finite_plan_ellipsoid.center", "Disturbance center propagation overflowed.");
      center = *sum;
    }
    const auto source_radius = ellipsoid_support_radius(
        dynamics, row, current.radii, false, disturbance_radii);
    if (!source_radius)
      return unsupported("finite_plan_ellipsoid.radius", "Stage support radius overflowed.");
    const double center_value = center.lower * 0.5 + center.upper * 0.5;
    const double center_error = up(std::max(center_value - center.lower,
                                            center.upper - center_value));
    const double half_width = up(*source_radius + center_error);
    if (!std::isfinite(center_value) || !std::isfinite(half_width))
      return unsupported("finite_plan_ellipsoid.stage", "Stage enclosure overflowed.");
    lower[row] = down(center_value - half_width);
    upper[row] = up(center_value + half_width);
  }
  auto result = enclose_box(lower, upper);
  if (const auto* failure = std::get_if<Unsupported>(&result)) return *failure;
  return std::get<Stage>(std::move(result));
}
} // namespace

FinitePlanEllipsoidOutcome finite_plan_ellipsoid(
    const FixedPlanRequest& request, const ExecutionContext& context) {
  const auto dimensions = request.system.dimensions();
  const auto horizon = request.system.horizon();
  if (request.controls.size() != horizon || request.disturbances.size() != horizon ||
      request.admissible_states.size() != horizon + 1)
    return unsupported("finite_plan_ellipsoid.horizon", "Controls, disturbances and safe sets must match the model horizon.");
  if (request.initial.metadata()->set.dimension != dimensions.state)
    return unsupported("finite_plan_ellipsoid.initial", "Initial set dimension differs from model.");
  if (dimensions.state == 0)
    return unsupported("finite_plan_ellipsoid.dimension", "State dimension must be positive.");
  if (request.controls.size() != horizon)
    return unsupported("finite_plan_ellipsoid.controls", "Control count differs from model horizon.");
  for (std::size_t stage = 0; stage < horizon; ++stage)
    if (request.controls[stage].size() != dimensions.control ||
        request.disturbances[stage].metadata()->set.dimension != dimensions.external)
      return unsupported("finite_plan_ellipsoid.dimensions", "Control or disturbance dimensions differ from model.");
  for (const auto& safe : request.admissible_states)
    if (safe.metadata()->set.dimension != dimensions.state ||
        !std::holds_alternative<sets::UniversalRepresentation>(safe.representation()))
      return unsupported("finite_plan_ellipsoid.safe_sets", "Only universal state constraints are supported.");

  auto initial_bounds = bounds(request.initial, "finite_plan_ellipsoid.initial");
  if (const auto* failure = std::get_if<Unsupported>(&initial_bounds)) return *failure;
  const auto& [initial_lower, initial_upper] = std::get<std::pair<Vector, Vector>>(initial_bounds);
  auto initial = enclose_box(initial_lower, initial_upper);
  if (const auto* failure = std::get_if<Unsupported>(&initial)) return *failure;

  FinitePlanEllipsoidTrace trace;
  trace.stages.push_back(std::get<Stage>(std::move(initial)));
  std::vector<std::pair<Vector, Vector>> disturbance_bounds;
  disturbance_bounds.reserve(horizon);
  for (const auto& disturbance : request.disturbances) {
    auto values = bounds(disturbance, "finite_plan_ellipsoid.disturbances");
    if (const auto* failure = std::get_if<Unsupported>(&values)) return *failure;
    disturbance_bounds.push_back(std::get<std::pair<Vector, Vector>>(std::move(values)));
  }
  for (std::size_t stage = 0; stage < horizon; ++stage) {
    if (const auto stop = stopped(context)) return *stop;
    auto dynamics = request.system.stage({stage});
    if (const auto* error = std::get_if<Diagnostic>(&dynamics))
      return unsupported(error->field, error->explanation);
    const auto& [d_lower, d_upper] = disturbance_bounds[stage];
    Vector d_center(d_lower.size()), d_radius(d_lower.size());
    for (std::size_t i = 0; i < d_lower.size(); ++i) {
      const auto midpoint = midpoint_radius(d_lower[i], d_upper[i], 1.0);
      if (!midpoint) return unsupported("finite_plan_ellipsoid.disturbances", "Disturbance bounds overflowed.");
      d_center[i] = midpoint->first;
      d_radius[i] = up(std::max(d_center[i] - d_lower[i], d_upper[i] - d_center[i]));
    }
    auto next = step(std::get<model::DynamicsStage>(dynamics), trace.stages.back(),
                     request.controls[stage], d_center, d_radius, context);
    if (const auto* failure = std::get_if<Unsupported>(&next)) return *failure;
    if (const auto* stop = std::get_if<OperationStopped>(&next)) return *stop;
    trace.stages.push_back(std::get<Stage>(std::move(next)));
  }
  return trace;
}
} // namespace csl::reachability
