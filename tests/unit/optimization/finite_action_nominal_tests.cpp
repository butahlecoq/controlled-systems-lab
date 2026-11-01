#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_nominal.hpp>
#include "two_points_fixture.hpp"

#include <cmath>

using namespace csl;
using namespace csl::optimization;

TEST_CASE("nominal finite-plan comparison keeps exact and enclosure scores distinct") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-test-source");
    FiniteActionNominalRequest request{
        source.problem,
        {"nominal-test"},
        source.system,
        {4.5, 0.0, 0.0, 0.0},
        source.actions,
        {{1.0}, {1.0}, {1.0}},
        source.admissible_states,
        source.objective,
    };

    const auto outcome = finite_action_nominal(request, {27, 1000, 100000, 1000, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    const auto& result = std::get<FiniteActionNominalResult>(outcome);
    CHECK(result.problem == source.problem);
    CHECK(result.request == request.request);
    REQUIRE(result.tracks.size() == 5);
    for(std::size_t index = 0; index < result.tracks.size(); ++index) {
        const auto& track = result.tracks[index];
        REQUIRE(std::holds_alternative<NominalTrackSelected>(track.outcome));
        const auto& selected = std::get<NominalTrackSelected>(track.outcome);
        REQUIRE(selected.attempts.size() == 27);
        CHECK(selected.coverage == NominalSearchCoverage::complete);
        CHECK(selected.selected_attempt < selected.attempts.size());
        CHECK(selected.replay.states.size() == 4);
        CHECK(selected.replay.states.back()[2] > 0.0);
        CHECK(selected.replay.states.back()[3] == doctest::Approx(0.3));
        CHECK(selected.replay.controls.size() == 3);
        CHECK(selected.replay.disturbances == request.nominal_disturbances);
        CHECK(std::isfinite(selected.replay.terminal_objective));
        if(index == 0) {
            CHECK(selected.score_kind == NominalScoreKind::exact_deterministic_objective);
            CHECK(selected.candidate_score == doctest::Approx(selected.replay.terminal_objective));
        } else {
            CHECK(selected.score_kind == NominalScoreKind::numerical_outer_enclosure_estimate);
        }
    }
}
