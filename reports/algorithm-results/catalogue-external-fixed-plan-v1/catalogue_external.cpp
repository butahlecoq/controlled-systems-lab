#include <csl/model/discrete_catalogue.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>

namespace {
using namespace csl;
using namespace csl::reachability;
namespace catalogue = csl::model::catalogue;
using Json = nlohmann::json;

template <class T, class... Errors>
T require(std::variant<T, Errors...> value, const char *message) {
  if (auto *accepted = std::get_if<T>(&value)) {
    return std::move(*accepted);
  }
  throw std::runtime_error(message);
}

Json matrix(const Matrix &value) {
  return {
      {"rows", value.rows}, {"columns", value.cols}, {"row_major", value.values}};
}

Json points(const sets::SetData &set) {
  const auto geometry = set.representation();
  if (const auto *singleton =
          std::get_if<sets::SingletonRepresentation>(&geometry)) {
    const auto values = singleton->point.values();
    return Json::array({Vector(values.begin(), values.end())});
  }
  const auto &vertices = std::get<sets::VRepresentation>(geometry).vertices;
  std::vector<Vector> result(vertices.rows(), Vector(vertices.cols()));
  for (std::size_t i = 0; i < vertices.rows(); ++i) {
    for (std::size_t j = 0; j < vertices.cols(); ++j) {
      result[i][j] = vertices(i, j);
    }
  }
  return result;
}

Json encode(const FixedPlanReachable &trace) {
  Json stages = Json::array();
  for (const auto &stage : trace.stages) {
    stages.push_back({{"points", points(stage)}});
  }
  return {
      {"status", "complete"}, {"assurance", "numerical"}, {"stages", stages}};
}

template <class T> Json encode(const T &trace) {
  Json stages = Json::array();
  for (const auto &stage : trace.stages) {
    if constexpr (std::is_same_v<T, FinitePlanZonotopeTrace>) {
      stages.push_back(
          {{"center", stage.center}, {"generators", matrix(stage.generators)}});
    } else if constexpr (std::is_same_v<T, FinitePlanEllipsoidTrace>) {
      stages.push_back({{"center", stage.center}, {"radii", stage.radii}});
    } else {
      stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
    }
  }
  Json result = {
      {"status", "complete"}, {"assurance", "numerical"}, {"stages", stages}};
  if constexpr (std::is_same_v<T, FinitePlanParallelotopeTrace>) {
    result["frame"] = matrix(trace.frame);
  }
  return result;
}

Json encode(const Unsupported &error) {
  Json diagnostics = Json::array();
  for (const auto &diagnostic : error.diagnostics) {
    diagnostics.push_back(
        {{"field", diagnostic.field}, {"message", diagnostic.explanation}});
  }
  return {{"status", "unsupported"}, {"diagnostics", diagnostics}};
}

Json encode(const OperationStopped &error) {
  constexpr std::array reasons{"cancelled", "deadline", "resource-limit",
                               "numerical-failure"};
  return {{"status", "stopped"},
          {"reason", reasons.at(static_cast<std::size_t>(error.reason))},
          {"detail", error.diagnostics}};
}

Json encode(const FixedPlanViolation &error) {
  return {{"status", "violation"},
          {"stage", error.stage},
          {"state", error.violating_successor}};
}

Json encode(const FixedPlanEmpty &error) {
  return {{"status", "empty"}, {"stage", error.stage}};
}

template <class Variant> Json outcome(const Variant &value) {
  return std::visit([](const auto &row) { return encode(row); }, value);
}

Json run(const catalogue::DiscreteModelInfo &info) {
  const auto packet = require(catalogue::make_discrete_model(info.id),
                              "missing catalogue model");
  const auto &dynamics = packet.coefficients;
  const auto n = packet.initial_state.size();
  const auto q = dynamics.E.cols;
  const auto m = dynamics.B.cols;
  const auto dt = packet.time_step.value;
  const auto system =
      require(model::snapshot(packet.system_model(), Vector{0, dt, 2 * dt}),
              "invalid two-step grid");
  const std::string id(info.id);
  const auto initial =
      require(sets::make_singleton(
                  {{id + "/x0"}, n, {}},
                  require(numeric::snapshot_vector(packet.initial_state),
                          "invalid initial value")),
              "invalid initial set");
  const auto universal = require(sets::make_universal({{id + "/world"}, n, {}}),
                                 "invalid universal set");

  const Vector center = packet.nominal_external.value_or(Vector(q, 0.0));
  std::vector<std::size_t> axes;
  for (std::size_t column = 0; column < q && axes.size() < 2; ++column) {
    for (std::size_t row = 0; row < n; ++row) {
      if (dynamics.E.values[row * q + column] != 0.0) {
        axes.push_back(column);
        break;
      }
    }
  }
  auto perturbed_axes = axes;
  if (perturbed_axes.empty() && q > 0) {
    perturbed_axes.push_back(0);
  }
  std::vector<Vector> disturbances{center};
  for (const auto column : perturbed_axes) {
    const double delta = 0.1 * std::max(1.0, std::abs(center[column]));
    for (const double sign : {-1, 1}) {
      auto member = center;
      member[column] += sign * delta;
      disturbances.push_back(std::move(member));
    }
  }
  Vector flat;
  for (const auto &point : disturbances) {
    flat.insert(flat.end(), point.begin(), point.end());
  }
  const auto shape = require(
      sets::make_v(
          {{id + "/external-cross"}, q, {}},
          {require(numeric::snapshot(Matrix{disturbances.size(), q, flat}),
                   "invalid disturbance vertices"),
           require(numeric::snapshot(Matrix{0, q, {}}),
                   "invalid disturbance rays")}),
      "invalid disturbance set");
  const std::vector<Vector> controls(2, Vector(m, 0.0));
  const FixedPlanRequest request{system,
                                 initial,
                                 controls,
                                 {shape, shape},
                                 {universal, universal, universal},
                                 {id + "/external-fixed-plan/1"}};
  return {{"model_id", id},
          {"model_title", info.title},
          {"source_sha256", info.source.sha256},
          {"profile", "authored-external-fixed-plan/1"},
          {"dt", dt},
          {"x0", packet.initial_state},
          {"A", matrix(dynamics.A)},
          {"B", matrix(dynamics.B)},
          {"E", matrix(dynamics.E)},
          {"offset", dynamics.offset},
          {"active_axes", axes},
          {"perturbed_axes", perturbed_axes},
          {"external_center", center},
          {"disturbance_vertices", disturbances},
          {"controls", controls},
          {"outcomes",
           {{"polytope", outcome(fixed_plan_disturbance(request, 25))},
            {"box", outcome(finite_plan_box(request))},
            {"zonotope", outcome(finite_plan_zonotope(request, {512}))},
            {"parallelotope", outcome(finite_plan_parallelotope(request))},
            {"ellipsoid", outcome(finite_plan_ellipsoid(request))}}}};
}
} // namespace

int main() {
  try {
    for (const auto &info : catalogue::discrete_models()) {
      std::cout << run(info).dump() << '\n';
    }
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
