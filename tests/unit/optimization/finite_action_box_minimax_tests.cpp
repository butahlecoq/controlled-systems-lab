#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_box_minimax.hpp>
#include <two_points_fixture.hpp>

using namespace csl;
using namespace csl::optimization;

namespace {
template<class T> T take_box(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

sets::SetData box_fixture_vertices(std::string id, Matrix points) {
    return take_box(sets::make_v({{std::move(id)}, 1, {"x"}},
        {take_box(numeric::snapshot(std::move(points))),
         take_box(numeric::snapshot(Matrix{0,1,{}}))}));
}

FiniteActionMinimaxRequest analytic_box_request() {
    const SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,1,{1}}, {0}}}, {}};
    const auto system = take_box(model::snapshot(authored, Vector{0,1}));
    const auto initial = take_box(sets::make_singleton({{"analytic-initial"},1,{"x"}},
        take_box(numeric::snapshot_vector(Vector{0}))));
    const auto disturbance = box_fixture_vertices("analytic-disturbance", Matrix{2,1,{-1,1}});
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= 1; ++stage)
        safe.push_back(take_box(sets::make_universal({{"analytic-safe" + std::to_string(stage)},1,{"x"}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}}, {0}, 0}));
    return {{"analytic-scalar-minimax"}, {"analytic-scalar-minimax-run"}, system, initial,
        {1, {{-1}, {0}, {1}}}, {disturbance}, std::move(safe), objective};
}
}

TEST_CASE("analytic scalar minimax selects and exactly replays the known zero-control optimum") {
    const auto input = analytic_box_request();
    const auto approximate = finite_action_box_minimax(input, {3,2,2,2});
    REQUIRE(std::holds_alternative<FiniteActionBoxMinimaxResult>(approximate));
    const auto& result = std::get<FiniteActionBoxMinimaxResult>(approximate);
    REQUIRE(result.plan_scores.size() == 3);
    CHECK(std::abs(result.plan_scores[0].terminal_box_maximum - 4) < 1e-12);
    CHECK(std::abs(result.plan_scores[1].terminal_box_maximum - 1) < 1e-12);
    CHECK(std::abs(result.plan_scores[2].terminal_box_maximum - 4) < 1e-12);
    CHECK(result.selected_action_indices == std::vector<std::size_t>{1});
    CHECK(std::abs(result.selected_box_score - 1) < 1e-12);
    CHECK(result.selected_replay_value == 1);
    REQUIRE(result.replayed_worst_path.size() == 2);
    CHECK(result.replayed_worst_path.front() == Vector{0});
    CHECK(std::abs(result.replayed_worst_path.back()[0]) == 1);

    const auto exact = finite_action_minimax(input, {3,2,0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(exact));
    CHECK(std::get<FiniteMinimaxOptimal>(exact).value == 1);
}

TEST_CASE("box-scored plan is replayed through the exact finite disturbance catalogues") {
    const auto request = csl::issue824::fixture::two_points_request("box-minimax-test");
    const auto approximate = finite_action_box_minimax(request, {27,27,27,16});
    if(const auto* unsupported = std::get_if<Unsupported>(&approximate))
        CHECK_MESSAGE(false, unsupported->diagnostics.front().field << ": " <<
            unsupported->diagnostics.front().explanation);
    if(const auto* stopped = std::get_if<OperationStopped>(&approximate))
        CHECK_MESSAGE(false, "stopped: " << stopped->diagnostics);
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
