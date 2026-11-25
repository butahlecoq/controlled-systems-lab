#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>
#include <two_points_fixture.hpp>

#include <limits>

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

sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take_zono(sets::make_v({{std::move(id)}, dimension, {}},
        {take_zono(numeric::snapshot(std::move(points))),
         take_zono(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

FiniteActionMinimaxRequest residual_request(Matrix map) {
    constexpr std::size_t horizon = 2;
    const SystemModel authored{{{2,1,2}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0.5,0,1}}, {2,1,{1,0}}, {2,2,{0,0,0,0}}, {0,0}}}, {}};
    const auto system = take_zono(model::snapshot(authored, Vector{0,1,2}));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("planar-disturbance", 2, Matrix{4,2,{-1,-1,-1,1,1,-1,1,1}}));
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take_zono(sets::make_universal({{"planar-safe"},2,{}})));
    const auto rows = map.rows;
    const auto objective = std::get<Objective>(snapshot(ResidualNormTerminal{
        std::move(map), Vector(rows, 1.0), std::vector<double>(rows, 0.5)}));
    return {{"planar-residual"}, {"planar-residual-run"}, system,
        vertices("planar-initial", 2, Matrix{1,2,{0.25,-0.5}}), {1, {{0}, {0}, {1}}},
        std::move(disturbances), std::move(safe), objective};
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
    const auto answer = finite_action_zonotope_minimax(analytic_request(), {3,2,2,4,0});
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

TEST_CASE("one certified corner gives the same scores as ordinary enumeration") {
    const auto request = analytic_request();
    const auto exhaustive = finite_action_zonotope_minimax(request, {3, 2, 2, 4, 16});
    const auto reduced = finite_action_zonotope_minimax(request, {3, 2, 2, 4, 1});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(exhaustive));
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(reduced));
    const auto &regular = std::get<FiniteActionZonotopeMinimaxResult>(exhaustive);
    const auto &certified = std::get<FiniteActionZonotopeMinimaxResult>(reduced);
    REQUIRE(certified.plan_attempts.size() == regular.plan_attempts.size());
    for (std::size_t i = 0; i < regular.plan_attempts.size(); ++i) {
        const auto *scored = std::get_if<ZonotopePlanScored>(&certified.plan_attempts[i]);
        REQUIRE(scored);
        CHECK(scored->score.factor_corners_evaluated == 1);
        CHECK(scored->score.terminal_factor_corner_maximum ==
              doctest::Approx(std::get<ZonotopePlanScored>(regular.plan_attempts[i])
                                  .score.terminal_factor_corner_maximum)
                  .epsilon(1e-14));
    }
    REQUIRE(certified.candidate_search == CandidateSearchCoverage::complete);
    CHECK(std::get<ZonotopePlanSelected>(certified.selection).candidate_attempt_index == 1);
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

TEST_CASE("candidate-attempt limit retains scored rows before the stopped plan") {
    auto request = analytic_request();
    const auto answer = finite_action_zonotope_minimax(request, {3,2,2,4,16,1});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 2);
    CHECK(std::holds_alternative<ZonotopePlanScored>(result.plan_attempts.front()));
    REQUIRE(std::holds_alternative<ZonotopePlanStopped>(result.plan_attempts.back()));
    const auto stopped_index = result.plan_attempts.size() - 1;
    const auto& stopped = std::get<ZonotopeCandidateSearchStopped>(result.selection);
    CHECK(stopped.candidate_attempt_index == stopped_index);
    CHECK(stopped.outcome.reason == StopReason::resource_limit);
    CHECK(std::get<ZonotopePlanStopped>(result.plan_attempts.back()).action_indices ==
        std::vector<std::size_t>{stopped_index});
}

TEST_CASE("candidate-attempt limit avoids reserving the full large catalog") {
    constexpr std::size_t horizon = std::numeric_limits<std::size_t>::digits - 1;
    const SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{0}}, {1,1,{0}}, {0}}}, {}};
    Vector times(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        times[stage] = static_cast<double>(stage);
    const auto system = take_zono(model::snapshot(authored, times));
    const auto initial = take_zono(sets::make_singleton({{"large-catalog-initial"},1,{"x"}},
        take_zono(numeric::snapshot_vector(Vector{0}))));
    std::vector<sets::SetData> disturbances;
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage < horizon; ++stage)
        disturbances.push_back(scalar_vertices("large-catalog-disturbance", Matrix{1,1,{0}}));
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take_zono(sets::make_universal({{"large-catalog-safe"},1,{"x"}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{1}}, {0}, 0}));
    const FiniteActionMinimaxRequest request{{"large-catalog"}, {"capped-search"}, system,
        initial, {1, {{0}, {1}}}, std::move(disturbances), std::move(safe), objective};
    const auto answer = finite_action_zonotope_minimax(request,
        {std::numeric_limits<std::size_t>::max(), 1, 1, 1, 1, 1});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 2);
    REQUIRE(std::holds_alternative<ZonotopePlanUnscored>(result.plan_attempts.front()));
    CHECK(std::get<ZonotopePlanUnscored>(result.plan_attempts.front()).outcome.diagnostics.front().field ==
        "finite_plan_zonotope.generators.limit");
    REQUIRE(std::holds_alternative<ZonotopePlanStopped>(result.plan_attempts.back()));
    CHECK(std::get<ZonotopePlanStopped>(result.plan_attempts.back()).outcome.reason ==
        StopReason::resource_limit);
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

TEST_CASE("planar residual terminal sweep matches exhaustive factor enumeration") {
    const auto request = residual_request({2,2,{1,0,0,1}});
    const auto exhaustive = finite_action_zonotope_minimax(request, {9,512,512,64,4096});
    const auto planar = finite_action_zonotope_minimax(request, {9,512,512,64,32});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(exhaustive));
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(planar));
    const auto& full = std::get<FiniteActionZonotopeMinimaxResult>(exhaustive);
    const auto& swept = std::get<FiniteActionZonotopeMinimaxResult>(planar);
    REQUIRE(full.plan_attempts.size() == 9);
    REQUIRE(swept.plan_attempts.size() == full.plan_attempts.size());
    CHECK(swept.candidate_search == CandidateSearchCoverage::complete);
    for(std::size_t index = 0; index < full.plan_attempts.size(); ++index) {
        REQUIRE(std::holds_alternative<ZonotopePlanScored>(full.plan_attempts[index]));
        REQUIRE(std::holds_alternative<ZonotopePlanScored>(swept.plan_attempts[index]));
        const auto& ordinary = std::get<ZonotopePlanScored>(full.plan_attempts[index]).score;
        const auto& reduced = std::get<ZonotopePlanScored>(swept.plan_attempts[index]).score;
        CHECK(ordinary.terminal_scorer == "factor-corner-enumeration/1");
        CHECK(reduced.terminal_scorer == "exact-planar-residual-sweep/1");
        CHECK(reduced.factor_corners_evaluated == 2 * reduced.terminal_generators + 1);
        CHECK(reduced.terminal_factor_corner_maximum >= ordinary.terminal_factor_corner_maximum);
        CHECK(reduced.terminal_factor_corner_maximum ==
              doctest::Approx(ordinary.terminal_factor_corner_maximum).epsilon(1e-14));
    }
    REQUIRE(std::holds_alternative<ZonotopePlanSelected>(full.selection));
    REQUIRE(std::holds_alternative<ZonotopePlanSelected>(swept.selection));
    CHECK(std::get<ZonotopePlanSelected>(swept.selection).candidate_attempt_index ==
          std::get<ZonotopePlanSelected>(full.selection).candidate_attempt_index);
}

TEST_CASE("nonplanar residual image preserves the factor-corner refusal") {
    const auto answer = finite_action_zonotope_minimax(
        residual_request({3,2,{1,0,0,1,0.5,0.5}}), {9,512,512,64,32});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 9);
    for(const auto& attempt : result.plan_attempts) {
        REQUIRE(std::holds_alternative<ZonotopePlanUnscored>(attempt));
        CHECK(std::get<ZonotopePlanUnscored>(attempt).outcome.diagnostics.front().field ==
            "finite_zonotope_minimax.corners");
    }
}

TEST_CASE("planar vertex budget exhaustion preserves the resource refusal") {
    const auto answer = finite_action_zonotope_minimax(
        residual_request({2,2,{1,0,0,1}}), {9,512,512,64,4});
    REQUIRE(std::holds_alternative<FiniteActionZonotopeMinimaxResult>(answer));
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(answer);
    CHECK(result.candidate_search == CandidateSearchCoverage::incomplete);
    REQUIRE(result.plan_attempts.size() == 1);
    REQUIRE(std::holds_alternative<ZonotopePlanStopped>(result.plan_attempts.front()));
    CHECK(std::get<ZonotopePlanStopped>(result.plan_attempts.front()).outcome.reason ==
          StopReason::resource_limit);
}
