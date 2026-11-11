#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/optimization/finite_action_graph.hpp>

using namespace csl;
using namespace csl::optimization;

namespace {
sets::SetData h_box(Vector lower, Vector upper, const std::string& id) {
    const auto n = lower.size();
    Matrix a{2 * n, n, Vector(2 * n * n, 0.0)};
    Vector b;
    for(std::size_t i = 0; i < n; ++i) {
        a.values[(2 * i) * n + i] = 1.0; b.push_back(upper[i]);
        a.values[(2 * i + 1) * n + i] = -1.0; b.push_back(-lower[i]);
    }
    const auto av = numeric::snapshot(a); const auto bv = numeric::snapshot_vector(b);
    const auto ev = numeric::snapshot(Matrix{0,n,{}}); const auto fv = numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(av));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bv));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ev));
    REQUIRE(std::holds_alternative<numeric::VectorView>(fv));
    const auto made = sets::make_h({{id}, n, {"x","y"}},
        {std::get<numeric::MatrixView>(av), std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(ev), std::get<numeric::VectorView>(fv)});
    REQUIRE(std::holds_alternative<sets::SetData>(made));
    return std::get<sets::SetData>(made);
}

registry::PreparedProvider<registry::GeometryPort> projection_provider() {
    auto registration = geometry::polyhedral::make_projection_registration();
    registry::Registry<registry::GeometryPort> providers;
    REQUIRE_FALSE(providers.add(registration).has_value());
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    auto prepared = registry::prepare_provider(registry::select_provider(providers,
        {registration.identity.id, registration.identity.version}, requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::GeometryPort>>(std::move(prepared));
}

model::LinearSystem two_stage_system(double a00 = 1.0) {
    const SystemModel authored{{{2,1,0}, TimeDomain::discrete,
        std::vector<LinearStage>{
            {{2,2,{a00,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}},
            {{2,2,{a00,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}}, {}};
    const auto result = model::snapshot(authored, Vector{0,1,2});
    REQUIRE(std::holds_alternative<model::LinearSystem>(result));
    return std::get<model::LinearSystem>(result);
}

FiniteActionNominalRequest viability_request() {
    const auto stage0 = h_box({0,0},{0,0},"graph-stage0");
    const auto stage1 = h_box({1,0},{1,0},"graph-stage1");
    const auto stage2 = h_box({0,0},{2,0},"graph-stage2");
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        Matrix{2,2,{2,0,0,2}}, {0,0}, 0}));
    return {{"analytic-graph"}, {"analytic-graph-query"}, two_stage_system(), {0,0},
        {1, {{0},{1}}}, {{},{}}, {stage0,stage1,stage2}, objective,
        {"analytic-running/1",2,{{0,{{QuadraticControlPenalty{{0},{1},{1},1,2}}}},
                                  {1,{{QuadraticControlPenalty{{0},{1},{1},1,2}}}}}}, 0};
}
}

TEST_CASE("backward viability changes the selected discrete first action") {
    auto request = viability_request();
    auto provider = projection_provider();
    const auto outcome = finite_action_stage_layered_graph(request, {4,32}, provider);
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& result = std::get<FiniteActionGraphResult>(outcome);
    REQUIRE(result.has_viable_path);
    CHECK(result.search_complete);
    REQUIRE(result.selected_nodes.size() == 3);
    CHECK(result.nodes[result.selected_nodes[1]].action_index == 1);
    CHECK(result.nodes[result.selected_nodes[2]].action_index == 0);
    CHECK(result.total_objective == doctest::Approx(1.5));
    CHECK(result.predecessor_calls > 0);

    // Independent literal enumeration: without the stage-1 set [1,1], [0,0]
    // has cost zero; with it, the only best feasible history is [1,0], cost 1.5.
    double best = std::numeric_limits<double>::infinity();
    std::vector<std::size_t> best_actions;
    for(std::size_t first = 0; first < 2; ++first) for(std::size_t second = 0; second < 2; ++second) {
        const double x1 = static_cast<double>(first);
        const double x2 = x1 + static_cast<double>(second);
        const bool feasible = x1 == 1.0 && x2 >= 0.0 && x2 <= 2.0;
        const double total = 0.5 * first * first + 0.5 * second * second + x2 * x2;
        if(feasible && total < best) { best = total; best_actions = {first, second}; }
    }
    CHECK(best_actions == std::vector<std::size_t>{1,0});
    CHECK(best == doctest::Approx(result.total_objective));
}

TEST_CASE("continuous predecessor membership cannot invent a finite action") {
    auto request = viability_request();
    request.admissible_states[1] = h_box({0.5,0},{0.5,0},"continuous-only-target");
    auto provider = projection_provider();
    const auto outcome = finite_action_stage_layered_graph(request, {4,32}, provider);
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& result = std::get<FiniteActionGraphResult>(outcome);
    CHECK_FALSE(result.has_viable_path);
    CHECK(result.selected_nodes.empty());
    const Vector parent{0,0}, target{0.5,0};
    CHECK(parent[0] + 0.5 == target[0]); // A continuous control inside conv({0,1}) exists.
    CHECK(std::ranges::none_of(request.actions.catalogue,
        [&](const Vector& action) { return parent[0] + action[0] == target[0]; }));
}

TEST_CASE("interior authored center action keeps its own node and lineage") {
    const auto stage0 = h_box({0,0},{0,0},"center-stage0");
    const auto stage1 = h_box({-1,0},{1,0},"center-stage1");
    const auto stage2 = h_box({-1,0},{1,0},"center-stage2");
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        Matrix{2,2,{2,0,0,2}}, {0,0}, 0}));
    auto request = FiniteActionNominalRequest{{"center-graph"}, {"center-graph-query"}, two_stage_system(), {0,0},
        {1, {{-1},{0},{1}}}, {{},{}}, {stage0,stage1,stage2}, objective,
        {"center-running/1",2,{{0,{{QuadraticControlPenalty{{0},{1},{1},1,2}}}},
                                 {1,{{QuadraticControlPenalty{{0},{1},{1},1,2}}}}}}, 0};
    auto provider = projection_provider();
    const auto outcome = finite_action_stage_layered_graph(request, {9,32}, provider);
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& result = std::get<FiniteActionGraphResult>(outcome);
    REQUIRE(result.has_viable_path);
    REQUIRE(result.layers[1].size() == 3);
    const auto center = std::find_if(result.layers[1].begin(), result.layers[1].end(), [&](std::size_t id) {
        return result.nodes[id].action_index == 1;
    });
    REQUIRE(center != result.layers[1].end());
    CHECK(result.nodes[*center].state == Vector{0,0});
    CHECK(result.nodes[result.selected_nodes[1]].action_index == 1);
    CHECK(result.total_objective == doctest::Approx(0.0));
}
