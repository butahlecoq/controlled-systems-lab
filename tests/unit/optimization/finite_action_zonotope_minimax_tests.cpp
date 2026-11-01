#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>
#include <two_points_fixture.hpp>

using namespace csl;
using namespace csl::optimization;

namespace {
template<class T> T take_zono(std::variant<T, Diagnostic> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

sets::SetData scalar_vertices(std::string id, Matrix points) {
    return take_zono(sets::make_v({{std::move(id)}, 1, {"x"}},
        {take_zono(numeric::snapshot(std::move(points))),
         take_zono(numeric::snapshot(Matrix{0,1,{}}))}));
}

FiniteActionMinimaxRequest analytic_request() {
    const SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,1,{1}}, {0}}}, {}};
    const auto system = take_zono(model::snapshot(authored, Vector{0,1}));
    const auto initial = take_zono(sets::make_singleton({{"analytic-initial"},1,{"x"}},
        take_zono(numeric::snapshot_vector(Vector{0}))));
    const auto disturbance = scalar_vertices("analytic-disturbance", Matrix{2,1,{-1,1}});
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= 1; ++stage)
        safe.push_back(take_zono(sets::make_universal({{"analytic-safe" + std::to_string(stage)},1,{"x"}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}}, {0}, 0}));
    return {{"analytic-scalar-zonotope"}, {"analytic-scalar-zonotope-run"}, system, initial,
        {1, {{-1}, {0}, {1}}}, {disturbance}, std::move(safe), objective};
}
}

TEST_CASE("analytic scalar selector scores every fixed plan and replays the minimizer") {
    const auto request = analytic_request();
    const auto answer = finite_action_zonotope_minimax(request, {3,2,2,4,16});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    REQUIRE(result.plan_attempts.size() == 3);
    CHECK(result.candidate_search == CandidateSearchCoverage::complete);
    const double expected[] = {4,1,4};
    for(std::size_t index = 0; index < 3; ++index) {
        REQUIRE(std::holds_alternative<ZonotopePlanScored>(result.plan_attempts[index]));
        const auto& score = std::get<ZonotopePlanScored>(result.plan_attempts[index]).score;
        CHECK(std::abs(score.terminal_factor_corner_maximum - expected[index]) < 1e-10);
        CHECK(score.factor_corners_evaluated == (std::size_t{1} << score.terminal_generators));
    }
    REQUIRE(std::holds_alternative<ZonotopePlanSelected>(result.selection));
    const auto& selected = std::get<ZonotopePlanSelected>(result.selection);
    CHECK(selected.candidate_attempt_index == 1);
    CHECK(std::abs(selected.replay.worst_value - 1.0) < 1e-12);
    REQUIRE(selected.replay.path.size() == 2);
    CHECK(selected.replay.path.front() == Vector{0});
    CHECK(std::abs(selected.replay.path.back()[0]) == 1.0);
    const auto exact = finite_action_minimax(request, {3,2,0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(exact));
    CHECK(selected.replay.worst_value == std::get<FiniteMinimaxOptimal>(exact).value);
}

TEST_CASE("factor corner refusal remains in every candidate row and marks search incomplete") {
    const auto answer = finite_action_zonotope_minimax(analytic_request(), {3,2,2,4,1});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    CHECK(std::holds_alternative<ZonotopeNoScoredCandidate>(result.selection));
    REQUIRE(result.plan_attempts.size() == 3);
    for(const auto& attempt : result.plan_attempts) {
        REQUIRE(std::holds_alternative<ZonotopePlanUnscored>(attempt));
        CHECK(std::get<ZonotopePlanUnscored>(attempt).outcome.diagnostics.front().field ==
            "finite_zonotope_minimax.corners");
    }
}

TEST_CASE("replay history refusal retains candidate scores and its selected attempt index") {
    const auto answer = finite_action_zonotope_minimax(analytic_request(), {3,2,1,4,16});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::complete);
    REQUIRE(result.plan_attempts.size() == 3);
    REQUIRE(std::holds_alternative<ZonotopePlanReplayRefused>(result.selection));
    const auto& refused = std::get<ZonotopePlanReplayRefused>(result.selection);
    CHECK(refused.candidate_attempt_index == 1);
    CHECK(refused.outcome.diagnostics.front().field == "finite_zonotope_minimax.replay.capacity");
    for(const auto& attempt : result.plan_attempts)
        CHECK(std::holds_alternative<ZonotopePlanScored>(attempt));
}

TEST_CASE("candidate search cancellation retains a stopped attempt and incomplete coverage") {
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.cancellation = cancellation.get_token();
    const auto answer = finite_action_zonotope_minimax(analytic_request(), {3,2,2,4,16}, context);
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 1);
    REQUIRE(std::holds_alternative<ZonotopePlanStopped>(result.plan_attempts.front()));
    const auto& attempt = std::get<ZonotopePlanStopped>(result.plan_attempts.front());
    CHECK(attempt.action_indices == std::vector<std::size_t>{0});
    CHECK(attempt.outcome.reason == StopReason::cancelled);
    REQUIRE(std::holds_alternative<ZonotopeCandidateSearchStopped>(result.selection));
    const auto& stopped = std::get<ZonotopeCandidateSearchStopped>(result.selection);
    CHECK(stopped.candidate_attempt_index == 0);
    CHECK(stopped.outcome.reason == StopReason::cancelled);
}

TEST_CASE("deadline after completed candidates retains scored rows before the stopped plan") {
    auto request = analytic_request();
    request.actions.catalogue.assign(100000, Vector{0.0});
    ExecutionContext context;
    context.deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
    const auto answer = finite_action_zonotope_minimax(request, {100000,2,2,4,16}, context);
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() > 1);
    CHECK(std::holds_alternative<ZonotopePlanScored>(result.plan_attempts.front()));
    REQUIRE(std::holds_alternative<ZonotopePlanStopped>(result.plan_attempts.back()));
    const auto stopped_index = result.plan_attempts.size() - 1;
    const auto& stopped = std::get<ZonotopeCandidateSearchStopped>(result.selection);
    CHECK(stopped.candidate_attempt_index == stopped_index);
    CHECK(stopped.outcome.reason == StopReason::deadline_expired);
    CHECK(std::get<ZonotopePlanStopped>(result.plan_attempts.back()).action_indices ==
        std::vector<std::size_t>{stopped_index});
}

TEST_CASE("pinned TwoPoints selected plan is replayed over the full finite disturbance histories") {
    const auto request = csl::issue824::fixture::two_points_request("zonotope-minimax-test");
    const auto answer = finite_action_zonotope_minimax(request, {27,27,27,64,32768});
    if(const auto* error = std::get_if<Unsupported>(&answer))
        CHECK_MESSAGE(false, error->diagnostics.front().field << ": " << error->diagnostics.front().explanation);
    if(const auto* stop = std::get_if<OperationStopped>(&answer))
        CHECK_MESSAGE(false, "stopped: " << stop->diagnostics);
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    REQUIRE(result.plan_attempts.size() == 27);
    CHECK(result.candidate_search == CandidateSearchCoverage::complete);
    REQUIRE(std::holds_alternative<ZonotopePlanSelected>(result.selection));
    const auto& selected = std::get<ZonotopePlanSelected>(result.selection);
    REQUIRE(selected.replay.path.size() == 4);
    REQUIRE(selected.replay.disturbance_indices.size() == 3);
    REQUIRE(selected.replay.disturbances.size() == 3);
    Vector state{4.5,0.0,0.0,0.0};
    CHECK(selected.replay.path.front() == state);
    for(std::size_t stage = 0; stage < selected.replay.disturbances.size(); ++stage) {
        const auto action_index = std::get<ZonotopePlanScored>(
            result.plan_attempts[selected.candidate_attempt_index]).action_indices[stage];
        const auto next = request.system.step({stage}, state, request.actions.catalogue[action_index],
            selected.replay.disturbances[stage]);
        REQUIRE(std::holds_alternative<Vector>(next));
        state = std::get<Vector>(next);
        CHECK(selected.replay.path[stage + 1] == state);
    }
    const auto replay_cost = evaluate(request.objective, state);
    REQUIRE(std::holds_alternative<double>(replay_cost));
    CHECK(std::get<double>(replay_cost) == selected.replay.worst_value);
    const auto exact_score = worst_case_vertex(selected.replay.terminal_catalogue, request.objective, 27);
    REQUIRE(std::holds_alternative<WorstCaseValue>(exact_score));
    CHECK(std::abs(std::get<WorstCaseValue>(exact_score).value - selected.replay.worst_value) < 1e-12);
}
