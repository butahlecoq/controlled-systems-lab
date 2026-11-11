#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/optimization/finite_action_graph.hpp>

#include <array>
#include <algorithm>
#include <limits>
#include <set>
#include <string>

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

TEST_CASE("forward GeometryPort receipts uniquely identify every parent at a shared stage") {
    auto request=viability_request();
    request.admissible_states[1]=h_box({-2,-2},{2,2},"multi-parent-middle");
    request.admissible_states[2]=h_box({-3,-2},{3,2},"multi-parent-terminal");
    std::vector<FiniteGraphGeometryInvocation> observed;
    const auto outcome=finite_action_stage_layered_graph(request,
        {4,32,std::nullopt,1000,std::nullopt},projection_provider(),reachable_set_provider(),{},
        [&](const auto& call){observed.push_back(call);});
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& graph=std::get<FiniteActionGraphResult>(outcome);
    REQUIRE(graph.has_viable_path);
    REQUIRE(graph.layers.size()==3);
    REQUIRE(graph.layers[1].size()>=2);
    std::set<std::size_t> parent_ids;
    std::set<std::string> request_ids,output_ids,affine_inputs,action_hull_inputs;
    std::size_t affine_calls=0,sum_calls=0;
    for(const auto& call:graph.reachable_geometry_invocations)if(call.absolute_stage==1) {
        parent_ids.insert(call.parent_node_id);
        request_ids.insert(call.request_id);
        output_ids.insert(call.ideal_output_id);
        if(call.operation=="affine-image") {
            ++affine_calls;
            REQUIRE(call.input_ids.size()==1);
            affine_inputs.insert(call.input_ids.front());
        } else if(call.operation=="minkowski-sum") {
            ++sum_calls;
            REQUIRE(call.input_ids.size()==2);
            action_hull_inputs.insert(call.input_ids[1]);
            CHECK(call.input_ids[0]==request.request.value+"/graph-forward-affine-stage-1-parent-"+
                std::to_string(call.parent_node_id)+"/output");
        }
    }
    CHECK(parent_ids.size()>=2);
    CHECK(affine_calls==parent_ids.size());
    CHECK(sum_calls==parent_ids.size());
    CHECK(request_ids.size()==affine_calls+sum_calls);
    CHECK(output_ids.size()==affine_calls+sum_calls);
    CHECK(affine_inputs.size()==affine_calls);
    CHECK(action_hull_inputs.size()==1);
    REQUIRE(observed.size()==graph.reachable_geometry_invocations.size());
    for(std::size_t i=0;i<observed.size();++i) {
        CHECK(observed[i].absolute_stage==graph.reachable_geometry_invocations[i].absolute_stage);
        CHECK(observed[i].parent_node_id==graph.reachable_geometry_invocations[i].parent_node_id);
        CHECK(observed[i].request_id==graph.reachable_geometry_invocations[i].request_id);
    }
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
        CHECK(cloud.stage==0);
        CHECK(cloud.output_stage==1);
        CHECK(cloud.parent_time==doctest::Approx(0.0));
        CHECK(cloud.output_time==doctest::Approx(1.0));
        CHECK(cloud.action_witnesses.size()==request.actions.catalogue.size());
        REQUIRE(cloud.outer_lower.size()==2);
        REQUIRE(cloud.outer_upper.size()==2);
        CHECK(cloud.outer_upper[0]-cloud.outer_lower[0]>1.0);
        CHECK(cloud.outer_upper[1]-cloud.outer_lower[1]>1.0);
        CHECK(cloud.outer_inside_authored_stage_set==std::optional<bool>{true});
        for(const auto& witness:cloud.action_witnesses) {
            CHECK(witness.accepted_by_selected_shape_numerical_membership);
            CHECK(witness.contained_in_coordinate_outer_box);
            CHECK_FALSE(witness.membership_method.empty());
            CHECK(witness.membership_tolerance_scale>0.0);
            CHECK(witness.membership_tolerance_rule=="max(64*epsilon*global-coordinate-scale,64*denorm_min)");
        }
        if(representation==NominalRepresentation::box)CHECK(std::holds_alternative<FiniteGraphBoxShape>(cloud.selected_outer_shape));
        if(representation==NominalRepresentation::zonotope)CHECK(std::holds_alternative<FiniteGraphZonotopeShape>(cloud.selected_outer_shape));
        if(representation==NominalRepresentation::parallelotope)CHECK(std::holds_alternative<FiniteGraphParallelotopeShape>(cloud.selected_outer_shape));
        if(representation==NominalRepresentation::ellipsoid)CHECK(std::holds_alternative<FiniteGraphEllipsoidShape>(cloud.selected_outer_shape));
        const auto center=std::find_if(cloud.action_witnesses.begin(),cloud.action_witnesses.end(),
            [](const auto& witness){return witness.action_index==4;});
        REQUIRE(center!=cloud.action_witnesses.end());
        CHECK((center->child_state==Vector{0,0}));
        REQUIRE(graph.selected_nodes.size()==2);
        CHECK(graph.nodes[graph.selected_nodes[1]].action_index==4);
    }
}

TEST_CASE("shape membership rejects points admitted only by a coordinate bounding box") {
    FiniteGraphActionCloudEnvelope box;
    box.outer_lower={-1,-1};box.outer_upper={1,1};
    box.selected_outer_shape=FiniteGraphBoxShape{{-0.5,-0.5},{0.5,0.5}};
    const auto box_membership=finite_graph_action_cloud_membership(box,Vector{0.75,0.0});
    CHECK(box_membership.supported);
    CHECK_FALSE(box_membership.contained);

    FiniteGraphActionCloudEnvelope parallel;
    parallel.outer_lower={-0.2,-0.2};parallel.outer_upper={0.2,0.2};
    parallel.selected_outer_shape=FiniteGraphParallelotopeShape{
        Matrix{2,2,{1,1,0,1}},{-0.1,-0.1},{0.1,0.1}};
    const Vector outside_parallelotope{0.0,0.19};
    CHECK((outside_parallelotope[0]>=parallel.outer_lower[0] && outside_parallelotope[0]<=parallel.outer_upper[0]));
    CHECK((outside_parallelotope[1]>=parallel.outer_lower[1] && outside_parallelotope[1]<=parallel.outer_upper[1]));
    const auto parallel_membership=finite_graph_action_cloud_membership(parallel,outside_parallelotope);
    CHECK(parallel_membership.supported);
    CHECK_FALSE(parallel_membership.contained);

    FiniteGraphActionCloudEnvelope ellipsoid;
    ellipsoid.outer_lower={-0.2,-0.1};ellipsoid.outer_upper={0.2,0.1};
    ellipsoid.selected_outer_shape=FiniteGraphEllipsoidShape{{0,0},{0.2,0.1}};
    const Vector outside_ellipsoid{0.18,0.09};
    CHECK((outside_ellipsoid[0]>=ellipsoid.outer_lower[0] && outside_ellipsoid[0]<=ellipsoid.outer_upper[0]));
    CHECK((outside_ellipsoid[1]>=ellipsoid.outer_lower[1] && outside_ellipsoid[1]<=ellipsoid.outer_upper[1]));
    const auto ellipsoid_membership=finite_graph_action_cloud_membership(ellipsoid,outside_ellipsoid);
    CHECK(ellipsoid_membership.supported);
    CHECK_FALSE(ellipsoid_membership.contained);

    FiniteGraphActionCloudEnvelope zonotope;
    zonotope.outer_lower={-1,-1};zonotope.outer_upper={1,1};
    zonotope.selected_outer_shape=FiniteGraphZonotopeShape{{0,0},Matrix{2,1,{1,1}}};
    const Vector outside_zonotope{1,-1};
    CHECK((outside_zonotope[0]>=zonotope.outer_lower[0] && outside_zonotope[0]<=zonotope.outer_upper[0]));
    CHECK((outside_zonotope[1]>=zonotope.outer_lower[1] && outside_zonotope[1]<=zonotope.outer_upper[1]));
    const auto zonotope_membership=finite_graph_action_cloud_membership(zonotope,outside_zonotope);
    CHECK(zonotope_membership.supported);
    CHECK_FALSE(zonotope_membership.contained);

    zonotope.selected_outer_shape=FiniteGraphZonotopeShape{{0,0},Matrix{2,4,{1,0,1,0,0,1,0,1}}};
    const auto repeated_generators=finite_graph_action_cloud_membership(zonotope,Vector{1.5,0.0});
    CHECK(repeated_generators.supported);
    CHECK(repeated_generators.contained);
    REQUIRE(repeated_generators.witness_coordinates.size()==4);
    CHECK(repeated_generators.witness_coordinates[0]==doctest::Approx(1.0));
    CHECK(repeated_generators.witness_coordinates[2]==doctest::Approx(0.5));
    zonotope.selected_outer_shape=FiniteGraphZonotopeShape{{0,0},Matrix{2,2,{1,1,1,-1}}};
    const auto unsupported_rotated=finite_graph_action_cloud_membership(zonotope,Vector{0,0});
    CHECK_FALSE(unsupported_rotated.supported);
    CHECK_FALSE(unsupported_rotated.contained);
    CHECK(unsupported_rotated.method.find("inconclusive")!=std::string::npos);
}

TEST_CASE("orbit box child 27 ULP below strict bounds uses selected-shape numerical membership") {
    FiniteGraphActionCloudEnvelope cloud;
    cloud.outer_lower={6999.48247958194861,-0.00358794570065600277,0.323390168309409032,0.00107790439878146507};
    cloud.outer_upper={6999.58956566931192,-0.00137641395188615816,0.323405424830231158,0.00107821867254362380};
    cloud.selected_outer_shape=FiniteGraphBoxShape{cloud.outer_lower,cloud.outer_upper};
    const Vector child{6999.48247958195589,-0.00358794570065601448,0.323391194438154561,0.00107793517071765521};
    CHECK(child[1]<cloud.outer_lower[1]);
    auto twenty_seven_ulps_below=cloud.outer_lower[1];
    for(int i=0;i<27;++i)
        twenty_seven_ulps_below=std::nextafter(twenty_seven_ulps_below,-std::numeric_limits<double>::infinity());
    CHECK(child[1]==twenty_seven_ulps_below);

    const auto membership=finite_graph_action_cloud_membership(cloud,child);
    CHECK(membership.supported);
    CHECK(membership.contained);
    CHECK(membership.method=="coordinate-membership-in-selected-box");
    CHECK(membership.tolerance_scale==doctest::Approx(6999.58956566931192));
    CHECK(membership.tolerance==doctest::Approx(std::max(
        64.0*std::numeric_limits<double>::epsilon()*membership.tolerance_scale,
        64.0*std::numeric_limits<double>::denorm_min())));
    CHECK(membership.reconstruction_residual>0.0);
    CHECK(membership.reconstruction_residual<membership.tolerance);

    const auto outside=finite_graph_action_cloud_membership(cloud,Vector{child[0],
        cloud.outer_lower[1]-10.0*membership.tolerance,child[2],child[3]});
    CHECK(outside.supported);
    CHECK_FALSE(outside.contained);
}

TEST_CASE("public shape membership refuses malformed and non-finite shape payloads") {
    const auto nan=std::numeric_limits<double>::quiet_NaN();
    const auto inf=std::numeric_limits<double>::infinity();
    FiniteGraphActionCloudEnvelope cloud;
    cloud.outer_lower={-2,-2};cloud.outer_upper={2,2};
    const Vector point{0,0};
    const auto refused=[&](FiniteGraphActionCloudShape shape) {
        cloud.selected_outer_shape=std::move(shape);
        const auto membership=finite_graph_action_cloud_membership(cloud,point);
        CHECK_FALSE(membership.supported);
        CHECK_FALSE(membership.contained);
        CHECK_FALSE(membership.method.empty());
    };
    refused(FiniteGraphBoxShape{{nan,-1},{1,1}});
    refused(FiniteGraphParallelotopeShape{Matrix{2,2,{1,0,0,inf}},{-1,-1},{1,1}});
    refused(FiniteGraphEllipsoidShape{{nan,0},{1,1}});
    refused(FiniteGraphZonotopeShape{{nan,0},Matrix{2,0,{}}});
    refused(FiniteGraphZonotopeShape{{0,0},Matrix{2,1,{inf,0}}});
}

TEST_CASE("a zero-generator zonotope is a singleton with an explicit witness") {
    FiniteGraphActionCloudEnvelope cloud;
    cloud.outer_lower={-1,-1};cloud.outer_upper={1,1};
    cloud.selected_outer_shape=FiniteGraphZonotopeShape{{0,0},Matrix{2,0,{}}};
    const auto contained=finite_graph_action_cloud_membership(cloud,Vector{0,0});
    CHECK(contained.supported);
    CHECK(contained.contained);
    CHECK(contained.witness_coordinates.empty());
    const auto excluded=finite_graph_action_cloud_membership(cloud,Vector{0.1,0});
    CHECK(excluded.supported);
    CHECK_FALSE(excluded.contained);
}

TEST_CASE("action-cloud lift preserves the source nominal external E*w contribution") {
    const SystemModel authored{{{2,2,2},TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}},{2,2,{1,0,0,1}},{2,2,{1,0,0,1}},{0,0}}},{}};
    const auto system=std::get<model::LinearSystem>(model::snapshot(authored,Vector{0,1}));
    const auto safe=h_box({-2,-2},{2,2},"external-cloud-safe");
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{2,2,{2,0,0,2}},{1,0},0}));
    FiniteActionNominalRequest request{{"external-cloud"},{"external-cloud-run"},system,
        {0,0},{2,{{0,0}}},{{1,0}},{safe,safe},objective};
    const auto outcome=finite_action_stage_layered_graph(request,
        {4,16,NominalRepresentation::box,16,NominalRepresentation::box},projection_provider());
    REQUIRE(std::holds_alternative<FiniteActionGraphResult>(outcome));
    const auto& graph=std::get<FiniteActionGraphResult>(outcome);
    REQUIRE(graph.has_viable_path);
    REQUIRE(graph.action_cloud_envelopes.size()==1);
    const auto& cloud=graph.action_cloud_envelopes.front();
    CHECK((cloud.source_nominal_external==Vector{1,0}));
    CHECK((cloud.lifted_external_contribution==Vector{1,0}));
    CHECK((cloud.auxiliary_offset==Vector{1,0}));
    REQUIRE(cloud.action_witnesses.size()==1);
    CHECK((cloud.action_witnesses.front().child_state==Vector{1,0}));
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
