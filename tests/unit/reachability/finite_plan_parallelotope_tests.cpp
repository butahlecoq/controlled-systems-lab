#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <doctest/doctest.h>
#include <two_points_fixture.hpp>

#include <cmath>

using namespace csl;
using namespace csl::reachability;

namespace {
template <class T> T take(std::variant<T, Diagnostic> result) {
  REQUIRE(std::holds_alternative<T>(result));
  return std::get<T>(std::move(result));
}

FixedPlanRequest two_points_request() {
  const auto full =
      csl::issue824::fixture::two_points_request("two-points-parallelotope");
  return {
      full.system,       full.initial,           {{-2.5}, {-2.5}, {-2.5}},
      full.disturbances, full.admissible_states, {"two-points-parallelotope"}};
}
sets::SetData planar_safe(std::string id, double bound) {
  return take(sets::make_h({{std::move(id)}, 2, {"x1", "x2"}},
      {take(numeric::snapshot(Matrix{4,2,{1,0,-1,0,0,1,0,-1}})),
       take(numeric::snapshot_vector(Vector{bound,bound,bound,bound})),
       take(numeric::snapshot(Matrix{0,2,{}})), take(numeric::snapshot_vector(Vector{}))}));
}
FixedPlanRequest planar_request() {
  const SystemModel model{{{2,1,0}, TimeDomain::discrete,
      LinearStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {0,0}}}, {}};
  const auto system = take(csl::model::snapshot(model, Vector{0,1}));
  const auto initial = take(sets::make_v({{"planar-initial"},2,{"x1","x2"}},
      {take(numeric::snapshot(Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}})),
       take(numeric::snapshot(Matrix{0,2,{}}))}));
  const auto disturbance = take(sets::make_singleton({{"planar-disturbance"},0,{}},
      take(numeric::snapshot_vector(Vector{}))));
  return {system, initial, {{0}}, {disturbance},
      {planar_safe("planar-safe-initial",2), planar_safe("planar-safe-terminal",2)},
      {"planar-parallelotope"}};
}
} // namespace

TEST_CASE(
    "fixed non-axis frame encloses every finite TwoPoints reachable state") {
  const auto request = two_points_request();
  const auto enclosure = finite_plan_parallelotope(request);
  REQUIRE(std::holds_alternative<FinitePlanParallelotopeTrace>(enclosure));
  const auto exact = fixed_plan_disturbance(request, 27);
  REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
  const auto &trace = std::get<FinitePlanParallelotopeTrace>(enclosure);
  CHECK(trace.relation == SetRelation::outer);
  const auto &stages = std::get<FixedPlanReachable>(exact).stages;
  REQUIRE(trace.frame.rows == 4);
  REQUIRE(trace.frame.cols == 4);
  REQUIRE(trace.stages.size() == stages.size());

  // Independently transform every exact finite-history vertex through the
  // integer inverse frame Q^-1 and check full 4D coordinate inclusion.
  constexpr int inverse[4][4] = {
      {1, -1, 1, -1}, {0, 1, -1, 1}, {0, 0, 1, -1}, {0, 0, 0, 1}};
  for (std::size_t stage = 0; stage < stages.size(); ++stage) {
    const auto repr = stages[stage].representation();
    const auto *points = std::get_if<sets::VRepresentation>(&repr);
    REQUIRE(points != nullptr);
    for (std::size_t row = 0; row < points->vertices.rows(); ++row)
      for (std::size_t i = 0; i < 4; ++i) {
        double coordinate = 0.0;
        for (std::size_t j = 0; j < 4; ++j)
          coordinate +=
              static_cast<double>(inverse[i][j]) * points->vertices(row, j);
        CHECK(trace.stages[stage].lower[i] <= coordinate);
        CHECK(trace.stages[stage].upper[i] >= coordinate);
      }
  }
  CHECK(trace.frame.values[1] == 1.0);
  CHECK(trace.frame.values[4] == 0.0);
  CHECK(trace.frame.values[5] == 1.0);
}

TEST_CASE("parallelotope route supports bounded two-state LV-shaped propagation") {
  auto request = planar_request();
  const auto result = finite_plan_parallelotope(request);
  REQUIRE(std::holds_alternative<FinitePlanParallelotopeTrace>(result));
  const auto& trace = std::get<FinitePlanParallelotopeTrace>(result);
  CHECK(trace.relation == SetRelation::outer);
  REQUIRE(trace.frame.rows == 2);
  REQUIRE(trace.frame.cols == 2);
  CHECK(trace.frame.values == Vector{1,0,0,1});
  REQUIRE(trace.stages.size() == 2);
  CHECK(trace.stages[1].lower[0] <= -1.0);
  CHECK(trace.stages[1].upper[1] >= 1.0);

  request.admissible_states[1] = planar_safe("planar-too-narrow",0.5);
  const auto outside = finite_plan_parallelotope(request);
  REQUIRE(std::holds_alternative<Unsupported>(outside));
  CHECK(std::get<Unsupported>(outside).diagnostics.front().field ==
      "finite_plan_parallelotope.safe_sets");
}

TEST_CASE("parallelotope keeps its four-state universal-safe-set profile refusal") {
  auto request = two_points_request();
  auto bounded = take(sets::make_v(
      {{"bounded-four-state-safe"}, 4, {}},
      {take(numeric::snapshot(Matrix{1, 4, {0.0, 0.0, 0.0, 0.0}})),
       take(numeric::snapshot(Matrix{0, 4, {}}))}));
  request.admissible_states[1] = std::move(bounded);

  const auto result = finite_plan_parallelotope(request);
  REQUIRE(std::holds_alternative<Unsupported>(result));
  const auto& diagnostic = std::get<Unsupported>(result).diagnostics[0];
  CHECK(diagnostic.field == "finite_plan_parallelotope.safe_sets");
  CHECK(diagnostic.explanation == "Universal state constraints are the only supported profile.");
}
