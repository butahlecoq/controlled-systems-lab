#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/optimization/finite_action_parallelotope_minimax.hpp>
#include <doctest/doctest.h>
#include <two_points_fixture.hpp>

#include <cmath>
#include <stop_token>

using namespace csl;
using namespace csl::optimization;

TEST_CASE("TwoPoints parallelotope selector scores each plan and independently "
          "replays the selected plan") {
  const auto request =
      csl::issue824::fixture::two_points_request("parallelotope-minimax-test");
  const auto answer =
      finite_action_parallelotope_minimax(request, {27, 27, 27});
  REQUIRE(
      std::holds_alternative<FiniteActionParallelotopeMinimaxResult>(answer));
  const auto &result = std::get<FiniteActionParallelotopeMinimaxResult>(answer);
  REQUIRE(result.candidate_search == CandidateSearchCoverage::complete);
  REQUIRE(result.plan_attempts.size() == 27);
  std::size_t scored = 0;
  for (const auto &attempt : result.plan_attempts) {
    REQUIRE(std::holds_alternative<ParallelotopePlanScored>(attempt));
    const auto &score = std::get<ParallelotopePlanScored>(attempt).score;
    CHECK(std::isfinite(score.terminal_frame_box_corner_maximum));
    CHECK(score.corners_evaluated == 16);
    CHECK(score.trace.stages.size() == request.system.horizon() + 1);
    ++scored;
  }
  CHECK(scored == 27);
  REQUIRE(std::holds_alternative<ParallelotopePlanSelected>(result.selection));
  const auto &selected = std::get<ParallelotopePlanSelected>(result.selection);
  CHECK(selected.candidate_attempt_index < result.plan_attempts.size());
  CHECK(selected.replay.path.size() == request.system.horizon() + 1);
  CHECK(std::isfinite(selected.replay.worst_value));
}

TEST_CASE("parallelotope selector preserves a stopped candidate and incomplete "
          "coverage") {
  const auto request =
      csl::issue824::fixture::two_points_request("parallelotope-stopped-test");
  std::stop_source cancellation;
  cancellation.request_stop();
  ExecutionContext context;
  context.cancellation = cancellation.get_token();
  const auto answer =
      finite_action_parallelotope_minimax(request, {27, 27, 27}, context);
  REQUIRE(
      std::holds_alternative<FiniteActionParallelotopeMinimaxResult>(answer));
  const auto &result = std::get<FiniteActionParallelotopeMinimaxResult>(answer);
  CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
  REQUIRE(result.plan_attempts.size() == 1);
  REQUIRE(std::holds_alternative<ParallelotopePlanStopped>(
      result.plan_attempts.front()));
  CHECK(std::get<ParallelotopePlanStopped>(result.plan_attempts.front())
            .outcome.reason == StopReason::cancelled);
}

TEST_CASE("parallelotope selector refuses candidate propagation over the point "
          "budget") {
  const auto request = csl::issue824::fixture::two_points_request(
      "parallelotope-point-limit-test");
  const auto answer = finite_action_parallelotope_minimax(request, {27, 1, 27});
  REQUIRE(
      std::holds_alternative<FiniteActionParallelotopeMinimaxResult>(answer));
  const auto &result = std::get<FiniteActionParallelotopeMinimaxResult>(answer);
  CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
  REQUIRE(result.plan_attempts.size() == 27);
  for (const auto &attempt : result.plan_attempts) {
    REQUIRE(std::holds_alternative<ParallelotopePlanUnscored>(attempt));
    CHECK(std::get<ParallelotopePlanUnscored>(attempt)
              .outcome.diagnostics.front()
              .field == "finite_parallelotope_minimax.points.limit");
  }
}
