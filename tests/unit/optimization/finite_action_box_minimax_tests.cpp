#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_box_minimax.hpp>
#include <two_points_fixture.hpp>

using namespace csl;
using namespace csl::optimization;

TEST_CASE("box-scored plan is replayed through the exact finite disturbance catalogues") {
    const auto request = csl::issue824::fixture::two_points_request("box-minimax-test");
    const auto approximate = finite_action_box_minimax(request, {27,27,27,16});
    REQUIRE(std::holds_alternative<FiniteActionBoxMinimaxResult>(approximate));
    const auto& result = std::get<FiniteActionBoxMinimaxResult>(approximate);
    REQUIRE(result.plan_scores.size() == 27);
    REQUIRE(result.selected_action_indices.size() == 3);
    REQUIRE(result.replayed_worst_disturbance_indices.size() == 3);
    REQUIRE(result.replayed_worst_disturbance_values.size() == 3);
    REQUIRE(result.replayed_worst_path.size() == 4);
    Vector state{4.5,0.0,0.0,0.0};
    CHECK(result.replayed_worst_path.front() == state);
    for(std::size_t stage = 0; stage < result.selected_action_indices.size(); ++stage) {
        const auto next = request.system.step({stage}, state,
            request.actions.catalogue[result.selected_action_indices[stage]],
            result.replayed_worst_disturbance_values[stage]);
        REQUIRE(std::holds_alternative<Vector>(next));
        state = std::get<Vector>(next);
        CHECK(result.replayed_worst_path[stage + 1] == state);
    }
    const auto replayed_cost = evaluate(request.objective, state);
    REQUIRE(std::holds_alternative<double>(replayed_cost));
    CHECK(std::get<double>(replayed_cost) == result.selected_replay_value);
    REQUIRE(result.selected_box_trace.stages.size() == 4);
    const auto exact = finite_action_minimax(request, {27,27,0.0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(exact));
    const auto& exact_result = std::get<FiniteMinimaxOptimal>(exact);
    CHECK(result.selected_replay_value >= exact_result.value);
    CHECK(result.selected_box_score >= result.selected_replay_value);
}

TEST_CASE("box minimax enforces the separate full-history replay budget") {
    const auto request = csl::issue824::fixture::two_points_request("box-budget-test");
    const auto result = finite_action_box_minimax(request, {27,27,0,16});
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics[0].field ==
        "finite_box_minimax.replay.capacity");
}
