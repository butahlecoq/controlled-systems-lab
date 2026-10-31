#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_box_minimax.hpp>

using namespace csl;
using namespace csl::optimization;

namespace {
template<class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(points)), take(numeric::snapshot(Matrix{0,dimension,{}}))}));
}
sets::SetData universal(std::string id, std::size_t dimension) {
    return take(sets::make_universal({{std::move(id)}, dimension, {}}));
}
FiniteActionMinimaxRequest two_points_request() {
    constexpr std::size_t horizon = 3;
    const SystemModel authored{{{4,1,1}, TimeDomain::discrete,
        LinearStage{{4,4,{1.0,0.01,0.0,0.0, 0.0,0.0,0.0,0.0,
                          0.0,0.0,1.0,0.1, 0.0,0.0,0.0,1.0}},
                    {4,1,{0.09,1.0,0.0,0.0}}, {4,1,{0.0,0.0,0.0045,0.1}},
                    {0.0,0.0,0.0,0.0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{0.0,0.1,0.2,0.3}));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("d", 1, Matrix{3,1,{-1.0,0.0,1.0}}));
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(universal("safe" + std::to_string(stage), 4));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        {4,4,{2.0,0.0,-2.0,0.0, 0.0,0.0,0.0,0.0,
              -2.0,0.0,2.0,0.0, 0.0,0.0,0.0,0.0}}, {0.0,0.0,0.0,0.0}, 0.0}));
    return {{"env717-two-points-short-horizon-v1"}, {"box-minimax-test"}, system,
        vertices("initial", 4, Matrix{1,4,{4.5,0.0,0.0,0.0}}),
        {1,{{-2.5},{0.0},{2.5}}}, std::move(disturbances), std::move(safe), objective};
}
}

TEST_CASE("box-scored plan is replayed through the exact finite disturbance catalogues") {
    const auto request = two_points_request();
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
