#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/optimization/finite_action_graph.hpp>

#include <array>
#include <algorithm>
#include <limits>

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

template<class Port>
registry::PreparedProvider<Port> prepare(registry::Registration<Port> registration,
        std::string representation) {
    registry::Registry<Port> providers;
    const registry::Method method{registration.identity.id, registration.identity.version};
    REQUIRE_FALSE(providers.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr(std::is_same_v<Port, registry::LPPort>)
        requirements.output.assurance = Assurance::numerical;
    else requirements.output.relation = SetRelation::equivalent;
    auto selected = registry::prepare_provider(registry::select_provider(providers, method, requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<Port>>(selected));
    return std::get<registry::PreparedProvider<Port>>(std::move(selected));
}

registry::PreparedProvider<registry::GeometryPort> reachable_set_provider() {
    auto lp_result = optimization::phase_one::make_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result));
    auto lp = std::get<registry::Registration<registry::LPPort>>(std::move(lp_result));
    auto hull = geometry::make_lp_hull_reducer_registration();
    geometry::AffineSumDependencies dependencies{
        prepare(std::move(hull), "csl.hull-reduction.v1"),
        prepare(lp, "csl.program-result.v1"), std::nullopt};
    auto registration = geometry::make_affine_sum_registration(std::move(dependencies));
    return prepare(std::move(registration), "csl.polyhedron.v");
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

TEST_CASE("registered affine-sum reachable envelopes guard every discrete child") {
    auto request = viability_request();
    auto predecessor = projection_provider();
    auto reachable = reachable_set_provider();
    const auto outcome = finite_action_stage_layered_graph(request, {4,32}, predecessor, reachable);
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& result = std::get<FiniteActionGraphResult>(outcome);
    REQUIRE(result.has_viable_path);
    CHECK(result.reachable_envelope_calls == 6); // affine image + Minkowski sum per expanded parent
    CHECK(result.nodes[result.selected_nodes[1]].reachable_envelope_contains == true);
    CHECK(result.nodes[result.selected_nodes[2]].reachable_envelope_contains == true);
    CHECK(result.nodes[result.selected_nodes[1]].action_index == 1);
}

TEST_CASE("each selected numerical set route filters original discrete edges before Bellman selection") {
    const std::array routes{NominalRepresentation::box,NominalRepresentation::zonotope,
        NominalRepresentation::parallelotope,NominalRepresentation::ellipsoid};
    for(const auto route:routes) {
        auto request=viability_request();
        request.admissible_states[0]=h_box({-0.1,-0.1},{0.1,0.1},"graph-approximate-stage0");
        request.admissible_states[1]=h_box({0.9,-0.1},{1.1,0.1},"graph-approximate-stage1");
        request.admissible_states[2]=h_box({-0.1,-0.1},{2.1,0.1},"graph-approximate-stage2");
        auto provider=projection_provider();
        const auto outcome=finite_action_stage_layered_graph(request,{4,32,route,128},provider);
        REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
        const auto& result=std::get<FiniteActionGraphResult>(outcome);
        MESSAGE("representation=" << static_cast<int>(route) << " calls=" << result.representation_filter_calls
            << " rejected=" << result.representation_filter_rejections);
        for(const auto& node:result.nodes)
            if(node.representation_filter_passed.has_value()) MESSAGE(node.representation_filter_outcome);
        REQUIRE(result.has_viable_path);
        CHECK(result.representation_filter_calls>0);
        CHECK(result.nodes[result.selected_nodes[1]].action_index==1);
        CHECK(result.nodes[result.selected_nodes[1]].representation_filter_passed==true);
        CHECK(result.nodes[result.selected_nodes[2]].representation_filter_passed==true);
        CHECK(result.nodes[result.selected_nodes[1]].representation_outer_lower.size()==2);
        CHECK(result.nodes[result.selected_nodes[1]].representation_outer_upper.size()==2);
    }
}

TEST_CASE("selected approximations enclose the complete multi-action cloud and preserve center-action lineage") {
    const SystemModel authored{{{2,2,0},TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}},{2,2,{1,0,0,1}},{2,0,{}},{0,0}}},{}};
    const auto system=std::get<model::LinearSystem>(model::snapshot(authored,Vector{0,1}));
    const auto safe=h_box({-2,-2},{2,2},"multi-action-cloud-safe");
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{2,2,{2,0,0,2}},{0,0},0}));
    FiniteActionNominalRequest request{{"multi-action-cloud"},{"multi-action-cloud-run"},system,
        {0,0},{2,{{-1,-1},{-1,1},{1,-1},{1,1},{0,0}}},{Vector{}},
        {safe,safe},objective};
    const std::array representations{NominalRepresentation::box,NominalRepresentation::zonotope,
        NominalRepresentation::parallelotope,NominalRepresentation::ellipsoid};
    for(const auto representation:representations) {
        const auto outcome=finite_action_stage_layered_graph(request,
            {8,32,representation,64,representation},projection_provider());
        REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
        const auto& graph=std::get<FiniteActionGraphResult>(outcome);
        REQUIRE(graph.has_viable_path);
        REQUIRE(graph.action_cloud_calls==1);
        REQUIRE(graph.action_cloud_envelopes.size()==1);
        const auto& cloud=graph.action_cloud_envelopes.front();
        CHECK(cloud.action_witnesses.size()==request.actions.catalogue.size());
        REQUIRE(cloud.outer_lower.size()==2);
        REQUIRE(cloud.outer_upper.size()==2);
        CHECK(cloud.outer_upper[0]-cloud.outer_lower[0]>1.0);
        CHECK(cloud.outer_upper[1]-cloud.outer_lower[1]>1.0);
        CHECK(cloud.outer_inside_authored_stage_set==std::optional<bool>{true});
        for(const auto& witness:cloud.action_witnesses)CHECK(witness.contained_in_outer);
        const auto center=std::find_if(cloud.action_witnesses.begin(),cloud.action_witnesses.end(),
            [](const auto& witness){return witness.action_index==4;});
        REQUIRE(center!=cloud.action_witnesses.end());
        CHECK((center->child_state==Vector{0,0}));
        REQUIRE(graph.selected_nodes.size()==2);
        CHECK(graph.nodes[graph.selected_nodes[1]].action_index==4);
    }
}

TEST_CASE("outer edge filter refusal stays distinct from discrete graph infeasibility") {
    auto request=viability_request();
    auto provider=projection_provider();
    const auto outcome=finite_action_stage_layered_graph(request,
        {4,32,NominalRepresentation::box,128},provider);
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& result=std::get<FiniteActionGraphResult>(outcome);
    CHECK_FALSE(result.has_viable_path);
    CHECK(result.representation_filter_calls>0);
    CHECK(result.representation_filter_rejections>0);
    CHECK(std::ranges::any_of(result.nodes,[](const auto& node) {
        return node.representation_filter_outcome=="outer_enclosure_not_contained_in_stage_set";
    }));
}

TEST_CASE("graph rejects malformed source cost before numerical evaluation") {
    auto request = viability_request();
    std::get<QuadraticControlPenalty>(request.running_cost.stages.front().terms.front()).scales[0] = 0.0;
    auto provider = projection_provider();
    const auto outcome = finite_action_stage_layered_graph(request, {4,32}, provider);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    const auto& diagnostics = std::get<Unsupported>(outcome).diagnostics;
    REQUIRE_FALSE(diagnostics.empty());
    CHECK(diagnostics.front().field == "finite_graph.running_cost.quadratic");
}

TEST_CASE("zero-weight overflow coordinates are skipped and non-finite scores never reach ranking") {
    auto request = viability_request();
    auto& zero_weight = std::get<QuadraticControlPenalty>(request.running_cost.stages.front().terms.front());
    zero_weight.scales[0] = 1e-309;
    zero_weight.weights[0] = 0.0;
    auto provider = projection_provider();
    auto outcome = finite_action_stage_layered_graph(request, {4,32}, provider);
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    CHECK(std::isfinite(std::get<FiniteActionGraphResult>(outcome).total_objective));

    request = viability_request();
    auto& overflow = std::get<QuadraticControlPenalty>(request.running_cost.stages.front().terms.front());
    overflow.scales[0] = 1e-309;
    outcome = finite_action_stage_layered_graph(request, {4,32}, provider);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics.front().field == "finite_graph.running_cost.overflow");
}

TEST_CASE("finite but individually valid edge costs cannot overflow accumulated Bellman values") {
    auto request = viability_request();
    for(auto& stage : request.running_cost.stages)
        std::get<QuadraticControlPenalty>(stage.terms.front()).weights[0] = 2.0;
    for(auto& stage : request.running_cost.stages)
        std::get<QuadraticControlPenalty>(stage.terms.front()).coefficient = 1e308;
    auto provider = projection_provider();
    const auto outcome = finite_action_stage_layered_graph(request, {4,32}, provider);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    const auto field=std::get<Unsupported>(outcome).diagnostics.front().field;
    CHECK((field == "finite_graph.ranking.overflow" || field == "finite_graph.bellman.overflow"));
}

TEST_CASE("graph ranking preserves a positive quadratic cost when coefficient division underflows") {
    const SystemModel authored{{{2,1,0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}, {}};
    const auto system = std::get<model::LinearSystem>(model::snapshot(authored, Vector{0,1}));
    const auto safe = h_box({-10,-10},{10,10},"tiny-cost-safe");
    const auto objective = std::get<Objective>(snapshot(LinearTerminal{{0,0},0}));
    FiniteActionNominalRequest request{{"tiny-cost-graph"},{"tiny-cost-graph-run"},system,
        {0,0}, {1, {{1},{0}}}, {{}}, {safe,safe}, objective,
        {"tiny-cost-objective",2,{{0, {QuadraticControlPenalty{{0},{1e-150},{1},
            std::numeric_limits<double>::denorm_min(),2}}}}}};
    const auto result = finite_action_stage_layered_graph(request,{4,16},projection_provider());
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(result));
    const auto& graph = std::get<FiniteActionGraphResult>(result);
    REQUIRE(graph.has_viable_path);
    CHECK(graph.nodes[graph.selected_nodes[1]].action_index == 1);
    CHECK(graph.total_objective == 0.0);
    const auto costly = std::find_if(graph.nodes.begin(),graph.nodes.end(),[](const auto& node) {
        return node.stage == 1 && node.action_index == 0;
    });
    REQUIRE(costly != graph.nodes.end());
    // Independent binary-input evaluation: denorm_min * (1 / 1e-150)^2 / 2.
    CHECK(costly->edge_running_cost > 0.0);
    CHECK(costly->edge_running_cost == doctest::Approx(2.4703282292062326e-24).epsilon(1e-15));
    CHECK(costly->edge_running_cost / 2.4703282292062326e-24 ==
        doctest::Approx(1.0).epsilon(1e-15).scale(0.0));
}
