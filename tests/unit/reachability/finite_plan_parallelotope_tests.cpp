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
