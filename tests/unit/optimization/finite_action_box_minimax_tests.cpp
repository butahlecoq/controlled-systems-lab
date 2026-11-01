#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_box_minimax.hpp>
#include <two_points_fixture.hpp>

#include <algorithm>

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

FiniteActionMinimaxRequest box_request_with_one_stopped_plan() {
    const SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1e308}}, {1,1,{0}}, {0}}}, {}};
    const auto system = take_box(model::snapshot(authored, Vector{0,1}));
    const auto initial = take_box(sets::make_singleton({{"overflow-initial"},1,{"x"}},
        take_box(numeric::snapshot_vector(Vector{0}))));
    const auto disturbance = take_box(sets::make_singleton({{"overflow-disturbance"},1,{"w"}},
        take_box(numeric::snapshot_vector(Vector{0}))));
    const auto safe = take_box(sets::make_universal({{"overflow-safe"},1,{"x"}}));
    const auto objective = std::get<Objective>(snapshot(LinearTerminal{{1}, 0}));
    return {{"box-partial-search"}, {"box-partial-search-run"}, system, initial,
        {1, {{0}, {10}}}, {disturbance}, {safe, safe}, objective};
}
}

TEST_CASE("analytic scalar minimax selects and exactly replays the known zero-control optimum") {
    const auto input = analytic_box_request();
    const auto approximate = finite_action_box_minimax(input, {3,2,2,2});
    REQUIRE(std::holds_alternative<FiniteActionBoxMinimaxResult>(approximate));
    const auto& result = std::get<FiniteActionBoxMinimaxResult>(approximate);
    CHECK(result.candidate_search == CandidateSearchCoverage::complete);
    REQUIRE(result.plan_attempts.size() == 3);
    CHECK(std::abs(std::get<BoxPlanScored>(result.plan_attempts[0]).terminal_box_maximum - 4) < 1e-12);
    CHECK(std::abs(std::get<BoxPlanScored>(result.plan_attempts[1]).terminal_box_maximum - 1) < 1e-12);
    CHECK(std::abs(std::get<BoxPlanScored>(result.plan_attempts[2]).terminal_box_maximum - 4) < 1e-12);
    const auto* selected = std::get_if<BoxPlanSelected>(&result.selection);
    REQUIRE(selected);
    CHECK(selected->candidate_attempt_index == 1);
    CHECK(selected->replay.worst_value == 1);
    REQUIRE(selected->replay.path.size() == 2);
    CHECK(selected->replay.path.front() == Vector{0});
    CHECK(std::abs(selected->replay.path.back()[0]) == 1);

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
    REQUIRE(result.candidate_search == CandidateSearchCoverage::complete);
    REQUIRE(result.plan_attempts.size() == 27);
    const auto* selected = std::get_if<BoxPlanSelected>(&result.selection);
    REQUIRE(selected);
    const auto& selected_plan = std::get<BoxPlanScored>(result.plan_attempts[selected->candidate_attempt_index]);
    REQUIRE(selected_plan.action_indices.size() == 3);
    REQUIRE(selected->replay.disturbance_indices.size() == 3);
    REQUIRE(selected->replay.disturbances.size() == 3);
    REQUIRE(selected->replay.path.size() == 4);
    Vector state{4.5,0.0,0.0,0.0};
    CHECK(selected->replay.path.front() == state);
    for(std::size_t stage = 0; stage < selected_plan.action_indices.size(); ++stage) {
        const auto next = request.system.step({stage}, state,
            request.actions.catalogue[selected_plan.action_indices[stage]],
            selected->replay.disturbances[stage]);
        REQUIRE(std::holds_alternative<Vector>(next));
        state = std::get<Vector>(next);
        CHECK(selected->replay.path[stage + 1] == state);
    }
    const auto replayed_cost = evaluate(request.objective, state);
    REQUIRE(std::holds_alternative<double>(replayed_cost));
    CHECK(std::get<double>(replayed_cost) == selected->replay.worst_value);
    REQUIRE(selected_plan.trace.stages.size() == 4);
    const auto exact = finite_action_minimax(request, {27,27,0.0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(exact));
    const auto& exact_result = std::get<FiniteMinimaxOptimal>(exact);
    CHECK(selected->replay.worst_value >= exact_result.value);
    CHECK(selected_plan.terminal_box_maximum >= selected->replay.worst_value);
}

TEST_CASE("box minimax enforces the separate full-history replay budget") {
    const auto request = csl::issue824::fixture::two_points_request("box-budget-test");
    const auto result = finite_action_box_minimax(request, {27,27,0,16});
    REQUIRE(std::holds_alternative<FiniteActionBoxMinimaxResult>(result));
    const auto& partial = std::get<FiniteActionBoxMinimaxResult>(result);
    REQUIRE(partial.candidate_search == CandidateSearchCoverage::complete);
    REQUIRE(partial.plan_attempts.size() == 27);
    const auto* refused = std::get_if<BoxPlanReplayRefused>(&partial.selection);
    REQUIRE(refused);
    CHECK(refused->reason.diagnostics[0].field == "finite_box_minimax.replay.capacity");
}

TEST_CASE("box minimax preserves scored plans when a later plan stops") {
    const auto request = box_request_with_one_stopped_plan();
    const auto outcome = finite_action_box_minimax(request, {2, 4, 4, 2});
    REQUIRE(std::holds_alternative<FiniteActionBoxMinimaxResult>(outcome));
    const auto& result = std::get<FiniteActionBoxMinimaxResult>(outcome);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 2);
    CHECK(std::holds_alternative<BoxPlanScored>(result.plan_attempts[0]));
    const auto* stopped = std::get_if<BoxPlanStopped>(&result.plan_attempts[1]);
    REQUIRE(stopped);
    CHECK(stopped->reason.reason == StopReason::numerical_failure);
    const auto* selected = std::get_if<BoxPlanSelected>(&result.selection);
    REQUIRE(selected);
    CHECK(selected->candidate_attempt_index == 0);
    CHECK(selected->replay.worst_value == 0);
}

TEST_CASE("box minimax preserves every plan refused by the corner budget") {
    const auto request = analytic_box_request();
    const auto outcome = finite_action_box_minimax(request, {3, 2, 2, 1});
    REQUIRE(std::holds_alternative<FiniteActionBoxMinimaxResult>(outcome));
    const auto& result = std::get<FiniteActionBoxMinimaxResult>(outcome);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 3);
    CHECK(std::all_of(result.plan_attempts.begin(), result.plan_attempts.end(), [](const auto& attempt) {
        return std::holds_alternative<BoxPlanUnscored>(attempt);
    }));
    CHECK(std::holds_alternative<BoxNoScoredCandidate>(result.selection));
}
