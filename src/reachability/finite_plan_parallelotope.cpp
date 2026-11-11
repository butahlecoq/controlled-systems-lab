#include <csl/reachability/finite_plan_parallelotope.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <span>

namespace csl::reachability {
namespace {

struct Interval {
  double lo;
  double hi;
};

Unsupported unsupported(std::string field, std::string message) {
  return {
      {{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

std::optional<OperationStopped>
stop_if_needed(const ExecutionContext &context) {
  if (context.cancellation.stop_requested())
    return OperationStopped{StopReason::cancelled,
                            "Parallelotope propagation cancelled."};
  if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
    return OperationStopped{StopReason::deadline_expired,
                            "Parallelotope propagation deadline expired."};
  return {};
}

double down(double x) {
  return std::nextafter(x, -std::numeric_limits<double>::infinity());
}
double up(double x) {
  return std::nextafter(x, std::numeric_limits<double>::infinity());
}

std::optional<Interval> add(Interval a, Interval b) {
  const double lo = a.lo + b.lo;
  const double hi = a.hi + b.hi;
  if (!std::isfinite(lo) || !std::isfinite(hi))
    return {};
  return Interval{down(lo), up(hi)};
}

std::optional<Interval> multiply(Interval a, Interval b) {
  const double products[] = {a.lo * b.lo, a.lo * b.hi, a.hi * b.lo,
                             a.hi * b.hi};
  if (std::any_of(std::begin(products), std::end(products),
                  [](double x) { return !std::isfinite(x); }))
    return {};
  const auto [minimum, maximum] =
      std::minmax_element(std::begin(products), std::end(products));
  return Interval{down(*minimum), up(*maximum)};
}

// The fixed unit-upper-triangular frame and exact integer inverse:
// Q=[1 1 0 0; 0 1 1 0; 0 0 1 1; 0 0 0 1].
constexpr int q[4][4] = {
    {1, 1, 0, 0}, {0, 1, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}};
constexpr int qi[4][4] = {
    {1, -1, 1, -1}, {0, 1, -1, 1}, {0, 0, 1, -1}, {0, 0, 0, 1}};

std::optional<std::vector<Interval>> transform(std::span<const Interval> x,
                                               const int matrix[4][4]) {
  std::vector<Interval> result(4, {0.0, 0.0});
  for (std::size_t i = 0; i < 4; ++i)
    for (std::size_t j = 0; j < 4; ++j) {
      if (matrix[i][j] == 0)
        continue;
      auto term = multiply({static_cast<double>(matrix[i][j]),
                            static_cast<double>(matrix[i][j])},
                           x[j]);
      if (!term)
        return {};
      auto next = add(result[i], *term);
      if (!next)
        return {};
      result[i] = *next;
    }
  return result;
}

template <class MatrixLike>
std::optional<Interval> coefficient(const MatrixLike &source,
                                    std::size_t output, std::size_t input,
                                    const int left[4][4], const int right[4][4],
                                    bool right_identity = false) {
  Interval total{0, 0};
  for (std::size_t i = 0; i < 4; ++i)
    for (std::size_t j = 0; j < (right_identity ? 1 : 4); ++j) {
      const int l = left[output][i];
      const int r = right_identity ? 1 : right[j][input];
      if (l == 0 || r == 0)
        continue;
      const auto factor = l * r;
      const auto source_col = right_identity ? input : j;
      auto term =
          multiply({source(i, source_col), source(i, source_col)},
                   {static_cast<double>(factor), static_cast<double>(factor)});
      if (!term)
        return {};
      auto next = add(total, *term);
      if (!next)
        return {};
      total = *next;
    }
  return total;
}

std::optional<Interval> vector_coordinate(std::span<const double> values,
                                          std::size_t output,
                                          const int left[4][4]) {
  Interval total{0, 0};
  for (std::size_t i = 0; i < 4; ++i) {
    if (left[output][i] == 0)
      continue;
    auto term = multiply({values[i], values[i]},
                         {static_cast<double>(left[output][i]),
                          static_cast<double>(left[output][i])});
    if (!term)
      return {};
    auto next = add(total, *term);
    if (!next)
      return {};
    total = *next;
  }
  return total;
}

std::variant<ParallelotopeStage, Unsupported, OperationStopped>
set_bounds_in_frame(const sets::SetData &set, std::string field,
                    const int matrix[4][4], const ExecutionContext &context) {
  if (set.metadata()->set.dimension != 4)
    return unsupported(std::move(field),
                       "The initial profile supports four-state sets only.");
  ParallelotopeStage result{
      Vector(4, std::numeric_limits<double>::infinity()),
      Vector(4, -std::numeric_limits<double>::infinity())};
  const auto repr = set.representation();
  if (const auto *singleton =
          std::get_if<sets::SingletonRepresentation>(&repr)) {
    std::vector<Interval> point(4);
    for (std::size_t i = 0; i < 4; ++i) {
      if (!std::isfinite(singleton->point[i]))
        return unsupported(std::move(field), "Set coordinates must be finite.");
      point[i] = {singleton->point[i], singleton->point[i]};
    }
    const auto transformed = transform(point, matrix);
    if (!transformed)
      return OperationStopped{StopReason::numerical_failure,
                              "Input transform overflowed."};
    for (std::size_t i = 0; i < 4; ++i) {
      result.lower[i] = (*transformed)[i].lo;
      result.upper[i] = (*transformed)[i].hi;
    }
    return result;
  }
  const auto *vertices = std::get_if<sets::VRepresentation>(&repr);
  if (!vertices || vertices->vertices.rows() == 0 || vertices->rays.rows() != 0)
    return unsupported(std::move(field),
                       "A nonempty bounded V set or singleton is required.");
  for (std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
    if (const auto stop = stop_if_needed(context))
      return *stop;
    std::vector<Interval> point(4);
    for (std::size_t j = 0; j < 4; ++j) {
      const double value = vertices->vertices(row, j);
      if (!std::isfinite(value))
        return unsupported(std::move(field), "Set coordinates must be finite.");
      point[j] = {value, value};
    }
    const auto transformed = transform(point, matrix);
    if (!transformed)
      return OperationStopped{StopReason::numerical_failure,
                              "Input transform overflowed."};
    for (std::size_t i = 0; i < 4; ++i) {
      result.lower[i] = std::min(result.lower[i], (*transformed)[i].lo);
      result.upper[i] = std::max(result.upper[i], (*transformed)[i].hi);
    }
  }
  return result;
}

std::variant<ParallelotopeStage, Unsupported, OperationStopped>
coordinate_bounds(const sets::SetData &set, const ExecutionContext &context) {
  const auto dimension = set.metadata()->set.dimension;
  ParallelotopeStage result{
      Vector(dimension, std::numeric_limits<double>::infinity()),
      Vector(dimension, -std::numeric_limits<double>::infinity())};
  const auto repr = set.representation();
  const auto include = [&](std::span<const double> point) -> bool {
    for (std::size_t i = 0; i < dimension; ++i) {
      if (!std::isfinite(point[i]))
        return false;
      result.lower[i] = std::min(result.lower[i], point[i]);
      result.upper[i] = std::max(result.upper[i], point[i]);
    }
    return true;
  };
  if (const auto *singleton =
          std::get_if<sets::SingletonRepresentation>(&repr)) {
    if (!include(singleton->point.values()))
      return unsupported("finite_plan_parallelotope.disturbance",
                         "Set coordinates must be finite.");
    return result;
  }
  const auto *vertices = std::get_if<sets::VRepresentation>(&repr);
  if (!vertices || vertices->vertices.rows() == 0 || vertices->rays.rows() != 0)
    return unsupported("finite_plan_parallelotope.disturbance",
                       "A nonempty bounded V set or singleton is required.");
  for (std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
    if (const auto stop = stop_if_needed(context))
      return *stop;
    Vector point(dimension);
    for (std::size_t i = 0; i < dimension; ++i)
      point[i] = vertices->vertices(row, i);
    if (!include(point))
      return unsupported("finite_plan_parallelotope.disturbance",
                         "Set coordinates must be finite.");
  }
  return result;
}

} // namespace

FinitePlanParallelotopeOutcome
finite_plan_parallelotope(const FixedPlanRequest &request,
                          const ExecutionContext &context) {
  if (const auto stopped = stop_if_needed(context))
    return *stopped;
  constexpr std::size_t n = 4;
  const auto horizon = request.system.horizon();
  if (request.system.dimensions().state != n ||
      request.controls.size() != horizon ||
      request.disturbances.size() != horizon ||
      request.admissible_states.size() != horizon + 1)
    return unsupported("finite_plan_parallelotope.dimensions",
                       "The four-state model and horizon fields must agree.");
  for (const auto &safe : request.admissible_states)
    if (safe.metadata()->set.dimension != n ||
        !std::holds_alternative<sets::UniversalRepresentation>(
            safe.representation()))
      return unsupported(
          "finite_plan_parallelotope.safe_sets",
          "Universal state constraints are the only supported profile.");

  auto initial = set_bounds_in_frame(
      request.initial, "finite_plan_parallelotope.initial", qi, context);
  if (const auto *error = std::get_if<Unsupported>(&initial))
    return *error;
  if (const auto *stopped = std::get_if<OperationStopped>(&initial))
    return *stopped;
  FinitePlanParallelotopeTrace trace{
      Matrix{4, 4, Vector(16, 0.0)}, {}, Assurance::numerical};
  for (std::size_t i = 0; i < 4; ++i)
    for (std::size_t j = 0; j < 4; ++j)
      trace.frame.values[i * 4 + j] = static_cast<double>(q[i][j]);
  trace.stages.push_back(std::get<ParallelotopeStage>(std::move(initial)));

  for (std::size_t k = 0; k < horizon; ++k) {
    if (const auto stopped = stop_if_needed(context))
      return *stopped;
    auto disturbances = coordinate_bounds(request.disturbances[k], context);
    if (const auto *error = std::get_if<Unsupported>(&disturbances))
      return *error;
    if (const auto *stopped = std::get_if<OperationStopped>(&disturbances))
      return *stopped;
    const auto dyn = request.system.stage({k});
    if (const auto *error = std::get_if<Diagnostic>(&dyn))
      return unsupported(error->field, error->explanation);
    const auto &d = std::get<model::DynamicsStage>(dyn);
    if (d.A.rows() != 4 || d.A.cols() != 4 || d.B.rows() != 4 ||
        d.E.rows() != 4 || d.offset.size() != 4 ||
        request.controls[k].size() != d.B.cols())
      return unsupported(
          "finite_plan_parallelotope.stage.dimension",
          "Dynamics dimensions differ from the four-state profile.");
    std::vector<Interval> current(4);
    const auto &previous = trace.stages.back();
    for (std::size_t j = 0; j < 4; ++j)
      current[j] = {previous.lower[j], previous.upper[j]};

    // y' = Q^-1 (A Q y + Bv + Ew + c). Enclose every coefficient transform.
    if (request.disturbances[k].metadata()->set.dimension != d.E.cols())
      return unsupported("finite_plan_parallelotope.stage.dimension",
                         "Dynamics and disturbance dimensions differ from the "
                         "four-state profile.");
    std::vector<std::vector<Interval>> mapped(4, std::vector<Interval>(4));
    std::vector<std::vector<Interval>> control_map(
        4, std::vector<Interval>(d.B.cols()));
    std::vector<std::vector<Interval>> disturbance_map(
        4, std::vector<Interval>(d.E.cols()));
    for (std::size_t i = 0; i < 4; ++i) {
      for (std::size_t j = 0; j < 4; ++j) {
        const auto m = coefficient(d.A, i, j, qi, q);
        if (!m)
          return OperationStopped{StopReason::numerical_failure,
                                  "Dynamics transform overflowed."};
        mapped[i][j] = *m;
      }
      for (std::size_t t = 0; t < d.E.cols(); ++t) {
        const auto e = coefficient(d.E, i, t, qi, q, true);
        if (!e)
          return OperationStopped{StopReason::numerical_failure,
                                  "Disturbance transform overflowed."};
        disturbance_map[i][t] = *e;
      }
      for (std::size_t c = 0; c < d.B.cols(); ++c) {
        const auto b = coefficient(d.B, i, c, qi, q, true);
        if (!b)
          return OperationStopped{StopReason::numerical_failure,
                                  "Control transform overflowed."};
        control_map[i][c] = *b;
      }
    }
    ParallelotopeStage next{Vector(4), Vector(4)};
    for (std::size_t i = 0; i < 4; ++i) {
      Interval image{0, 0};
      for (std::size_t j = 0; j < 4; ++j) {
        auto term = multiply(mapped[i][j], current[j]);
        if (!term)
          return OperationStopped{StopReason::numerical_failure,
                                  "State propagation overflowed."};
        auto sum = add(image, *term);
        if (!sum)
          return OperationStopped{StopReason::numerical_failure,
                                  "State propagation overflowed."};
        image = *sum;
      }
      auto offset = vector_coordinate(d.offset.values(), i, qi);
      if (!offset)
        return OperationStopped{StopReason::numerical_failure,
                                "Offset transform overflowed."};
      auto with_offset = add(image, *offset);
      if (!with_offset)
        return OperationStopped{StopReason::numerical_failure,
                                "Offset propagation overflowed."};
      image = *with_offset;
      for (std::size_t c = 0; c < d.B.cols(); ++c) {
        const auto u = request.controls[k][c];
        if (!std::isfinite(u))
          return unsupported("finite_plan_parallelotope.control",
                             "Controls must be finite.");
        auto term = multiply(control_map[i][c], {u, u});
        if (!term)
          return OperationStopped{StopReason::numerical_failure,
                                  "Control propagation overflowed."};
        auto sum = add(image, *term);
        if (!sum)
          return OperationStopped{StopReason::numerical_failure,
                                  "Control propagation overflowed."};
        image = *sum;
      }
      const auto &disturbance_box = std::get<ParallelotopeStage>(disturbances);
      for (std::size_t t = 0; t < d.E.cols(); ++t) {
        auto term = multiply(disturbance_map[i][t], {disturbance_box.lower[t],
                                                     disturbance_box.upper[t]});
        if (!term)
          return OperationStopped{StopReason::numerical_failure,
                                  "Disturbance propagation overflowed."};
        auto sum = add(image, *term);
        if (!sum)
          return OperationStopped{StopReason::numerical_failure,
                                  "Disturbance propagation overflowed."};
        image = *sum;
      }
      next.lower[i] = image.lo;
      next.upper[i] = image.hi;
    }
    trace.stages.push_back(std::move(next));
  }
  return trace;
}

} // namespace csl::reachability
