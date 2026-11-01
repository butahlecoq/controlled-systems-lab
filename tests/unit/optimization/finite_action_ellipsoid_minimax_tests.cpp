#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_ellipsoid_minimax.hpp>
#include "two_points_fixture.hpp"

using namespace csl;
using namespace csl::optimization;

namespace {
FiniteActionMinimaxRequest request(std::string id = "ellipsoid-minimax") {
  return issue824::fixture::two_points_request(std::move(id));
}
}

TEST_CASE("ellipsoid fixed-plan selector scores the full plan catalogue and replays one plan") {
  const auto input = request();
  const auto result = finite_action_ellipsoid_minimax(input, {27, 27, 27});
  REQUIRE(std::holds_alternative<FiniteActionEllipsoidMinimaxResult>(result));
  const auto& selection = std::get<FiniteActionEllipsoidMinimaxResult>(result);
  CHECK(selection.candidate_search == CandidateSearchCoverage::complete);
  REQUIRE(selection.plan_attempts.size() == 27);
  for (const auto& attempt : selection.plan_attempts)
    CHECK(std::holds_alternative<EllipsoidPlanScored>(attempt));
  REQUIRE(std::holds_alternative<EllipsoidPlanSelected>(selection.selection));
  const auto& selected = std::get<EllipsoidPlanSelected>(selection.selection);
  const auto& score = std::get<EllipsoidPlanScored>(
      selection.plan_attempts[selected.candidate_attempt_index]).score;
  CHECK(score.terminal_support_estimate >= selected.replay.worst_value);
  CHECK(selected.replay.path.size() == input.system.horizon() + 1);
  CHECK(selected.replay.disturbance_indices.size() == input.system.horizon());
  CHECK(score.trace.stages.size() == input.system.horizon() + 1);
}

TEST_CASE("ellipsoid selector retains point-budget refusals instead of dropping plans") {
  const auto result = finite_action_ellipsoid_minimax(request("budget"), {27, 2, 27});
  REQUIRE(std::holds_alternative<FiniteActionEllipsoidMinimaxResult>(result));
  const auto& selection = std::get<FiniteActionEllipsoidMinimaxResult>(result);
  CHECK(selection.candidate_search == CandidateSearchCoverage::complete);
  REQUIRE(selection.plan_attempts.size() == 27);
  for (const auto& attempt : selection.plan_attempts) {
    REQUIRE(std::holds_alternative<EllipsoidPlanUnscored>(attempt));
    CHECK(std::get<EllipsoidPlanUnscored>(attempt).outcome.diagnostics[0].field ==
          "finite_ellipsoid_minimax.point_budget");
  }
  CHECK(std::holds_alternative<EllipsoidNoScoredCandidate>(selection.selection));
}

TEST_CASE("ellipsoid selector records candidate-attempt limits as incomplete") {
  const auto result = finite_action_ellipsoid_minimax(request("attempt-limit"), {27, 27, 27, 2});
  REQUIRE(std::holds_alternative<FiniteActionEllipsoidMinimaxResult>(result));
  const auto& selection = std::get<FiniteActionEllipsoidMinimaxResult>(result);
  CHECK(selection.candidate_search == CandidateSearchCoverage::incomplete);
  REQUIRE(selection.plan_attempts.size() == 3);
  CHECK(std::holds_alternative<EllipsoidCandidateSearchStopped>(selection.selection));
}
