#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/registry/registry.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <variant>
#include <vector>

using namespace csl;
using namespace csl::synthesis;

namespace {
SetHandle interval(std::string id,double lower,double upper) {
    const auto a=numeric::snapshot(Matrix{2,1,{-1,1}});
    const auto b=numeric::snapshot_vector(Vector{-lower,upper});
    const auto e=numeric::snapshot(Matrix{0,1,{}});
    const auto f=numeric::snapshot_vector({});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(a));
    REQUIRE(std::holds_alternative<numeric::VectorView>(b));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(e));
    REQUIRE(std::holds_alternative<numeric::VectorView>(f));
    auto set=sets::make_h({SetId{std::move(id)},1,{"coordinate"}},
        {std::get<numeric::MatrixView>(a),std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(f)});
    REQUIRE(std::holds_alternative<sets::SetData>(set));
    return std::get<sets::SetData>(std::move(set)).as_handle();
}

SetHandle identity_reset() {
    const auto a=numeric::snapshot(Matrix{0,2,{}});
    const auto b=numeric::snapshot_vector({});
    const auto e=numeric::snapshot(Matrix{1,2,{1,-1}});
    const auto f=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(a));
    REQUIRE(std::holds_alternative<numeric::VectorView>(b));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(e));
    REQUIRE(std::holds_alternative<numeric::VectorView>(f));
    auto set=sets::make_h({SetId{"contract.identity-reset"},2,{"pre","post"}},
        {std::get<numeric::MatrixView>(a),std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(f)});
    REQUIRE(std::holds_alternative<sets::SetData>(set));
    return std::get<sets::SetData>(std::move(set)).as_handle();
}

SetHandle h_relation(std::string id,std::size_t dimension,std::vector<std::string> labels,
    Matrix inequalities,Vector upper_bounds,Matrix equalities,Vector equality_values) {
    const auto a=numeric::snapshot(inequalities);
    const auto b=numeric::snapshot_vector(upper_bounds);
    const auto e=numeric::snapshot(equalities);
    const auto f=numeric::snapshot_vector(equality_values);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(a));
    REQUIRE(std::holds_alternative<numeric::VectorView>(b));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(e));
    REQUIRE(std::holds_alternative<numeric::VectorView>(f));
    auto set=sets::make_h({SetId{std::move(id)},dimension,std::move(labels)},
        {std::get<numeric::MatrixView>(a),std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(f)});
    REQUIRE(std::holds_alternative<sets::SetData>(set));
    return std::get<sets::SetData>(std::move(set)).as_handle();
}

SetHandle reset_one_to_two(std::string id) {
    return h_relation(std::move(id),3,{"pre","post.p","post.q"},Matrix{0,3,{}},{},
        Matrix{2,3,{-1,1,0,0,0,1}},Vector{0,0});
}

SetHandle set_valued_reset_one_to_two(std::string id) {
    // p=pre and q is an existential reset coordinate in [0,1].
    return h_relation(std::move(id),3,{"pre","post.p","post.q"},
        Matrix{2,3,{0,0,-1,0,0,1}},Vector{0,1},
        Matrix{1,3,{-1,1,0}},Vector{0});
}

SetHandle reset_two_to_one(std::string id) {
    return h_relation(std::move(id),3,{"pre.p","pre.q","post"},Matrix{0,3,{}},{},
        Matrix{1,3,{-1,-1,1}},Vector{0});
}

std::pair<model::HybridSystem,model::HybridRequest> interval_system() {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("contract.control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"transition"},{"source"},{"target"},{interval("contract.guard",0,0.5)},
            {identity_reset()}}}};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{1},0},"terminal value","unit"}}};
    return {std::move(system),std::move(request)};
}

std::pair<model::HybridSystem,model::HybridRequest> two_stage_dimension_change_system() {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={Singleton{{0}},Singleton{{0}}};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"middle"},2,0,{"p","q"},{}};
    middle.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    middle.control_sets={UniversalSet{0},UniversalSet{0}};
    middle.invariants={UniversalSet{2},UniversalSet{2},UniversalSet{2}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0},UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{2,{source,middle,target},{
        {{"expand"},{"source"},{"middle"},{UniversalSet{1},UniversalSet{1}},
            {reset_one_to_two("contract.expand.0"),reset_one_to_two("contract.expand.1")}},
        {{"finish"},{"middle"},{"target"},{UniversalSet{2},UniversalSet{2}},
            {reset_two_to_one("contract.finish.0"),reset_two_to_one("contract.finish.1")}}
    }};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{1},0},"terminal value","unit"}}};
    return {std::move(system),std::move(request)};
}

std::pair<model::HybridSystem,model::HybridRequest> two_stage_scalar_interval_system() {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("contract.two-stage.source-control.0",0,1),
        interval("contract.two-stage.source-control.1",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"middle"},1,1,{"z"},{"v"}};
    middle.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    middle.control_sets={interval("contract.two-stage.middle-control.0",0,1),
        interval("contract.two-stage.middle-control.1",0,1)};
    middle.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0},UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{2,{source,middle,target},{
        {{"first"},{"source"},{"middle"},{UniversalSet{1},UniversalSet{1}},
            {identity_reset(),identity_reset()}},
        {{"second"},{"middle"},{"target"},{UniversalSet{1},UniversalSet{1}},
            {identity_reset(),identity_reset()}}
    }};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{1},0},"terminal value","unit"}}};
    return {std::move(system),std::move(request)};
}

std::pair<model::HybridSystem,model::HybridRequest> parallel_interval_system() {
    auto [system,request]=interval_system();
    system.edges.push_back({{"full-transition"},{"source"},{"target"},
        {UniversalSet{1}},{identity_reset()}});
    return {std::move(system),std::move(request)};
}

model::HybridPath two_stage_dimension_change_path() {
    return {{{"source"},{"middle"},{"target"}},{{"expand"},{"finish"}}};
}

bool has_dimension_change_relation(const sets::HRepresentation& relation) {
    const Matrix expected_equalities{8,8,{
        1,0,0,0,0,0,0,0,
        -1,-1,1,0,0,0,0,0,
        0,1,0,0,0,0,0,0,
        0,0,-1,1,0,0,0,0,
        0,0,0,0,1,0,0,0,
        0,0,0,-1,0,1,0,0,
        0,0,0,0,-1,0,1,0,
        0,0,0,0,0,-1,-1,1}};
    const Vector expected_values(8,0.0);
    if(relation.inequalities.rows()!=0 || relation.upper_bounds.size()!=0 ||
       relation.equalities.rows()!=expected_equalities.rows ||
       relation.equalities.cols()!=expected_equalities.cols ||
       relation.equality_values.size()!=expected_values.size()) return false;
    for(std::size_t row=0;row<expected_equalities.rows;++row) {
        if(relation.equality_values[row]!=expected_values[row]) return false;
        for(std::size_t column=0;column<expected_equalities.cols;++column)
            if(relation.equalities(row,column)!=expected_equalities.values[row*expected_equalities.cols+column]) return false;
    }
    return true;
}

bool contains(const sets::HRepresentation& h,double value) {
    for(std::size_t row=0;row<h.inequalities.rows();++row)
        if(h.inequalities(row,0)*value>h.upper_bounds[row]) return false;
    for(std::size_t row=0;row<h.equalities.rows();++row)
        if(h.equalities(row,0)*value!=h.equality_values[row]) return false;
    return true;
}

}

TEST_CASE("public projected hybrid reachability returns the guarded terminal interval") {
    auto [system,request]=interval_system();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    ProjectedStateHybridReachabilityAdapter adapter{16};
    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{4,16,128});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachability=std::get<HybridPathReachability>(result);
    CHECK(reachability.path==path);
    REQUIRE(reachability.projected_state.has_value());
    CHECK(reachability.joint_relation.metadata()->set.dimension==4);
    const auto projected=reachability.projected_state->terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(projected));
    const auto& interval=std::get<sets::HRepresentation>(projected);
    bool lower_is_tight=false;
    bool upper_is_tight=false;
    for(std::size_t row=0;row<interval.inequalities.rows();++row) {
        const auto coefficient=interval.inequalities(row,0);
        const auto bound=interval.upper_bounds[row];
        CHECK((coefficient<0.0?0.0:0.5*coefficient)<=bound);
        if(coefficient<0.0) lower_is_tight=lower_is_tight || bound/(-coefficient)==0.0;
        if(coefficient>0.0) upper_is_tight=upper_is_tight || bound/coefficient==0.5;
    }
    CHECK(lower_is_tight);
    CHECK(upper_is_tight);
    CHECK(contains(interval,0.0));
    CHECK(contains(interval,0.25));
    CHECK(contains(interval,0.5));
    CHECK_FALSE(contains(interval,-0.01));
    CHECK_FALSE(contains(interval,0.51));
}

TEST_CASE("public projected hybrid reachability rejects provider admission before workspace creation") {
    auto [system,request]=interval_system();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    int admissions=0;
    int workspace_creations=0;
    registry::Registry<registry::GeometryPort> registry;
    registry::Registration<registry::GeometryPort> registration{
        {ModuleId{"contract.reject-projection"},"1"},
        [&admissions](const OperationRequest& operation,const registry::Requirements&)
            -> registry::Capability {
            ++admissions;
            if(!operation.identity.request.value.starts_with("terminal-state:"))
                return Diagnostics{{DiagnosticCode::evidence_mismatch,"contract.projection.identity",
                    "The provider expected the terminal projection request"}};
            return Diagnostics{{DiagnosticCode::unsupported,"contract.projection.limit",
                "The provider rejects projection admission"}};
        },
        [&workspace_creations](const OperationRequest&) -> std::unique_ptr<SetOperatorWorkspace> {
            ++workspace_creations;
            return {};
        }};
    REQUIRE_FALSE(registry.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    const auto prepared=registry::prepare_provider(registry::select_provider(registry,
        {ModuleId{"contract.reject-projection"},std::string{"1"}},requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared));
    ProjectedStateHybridReachabilityAdapter adapter{
        std::get<registry::PreparedProvider<registry::GeometryPort>>(prepared),16};

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{4,16,128});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="contract.projection.limit");
    CHECK(admissions==1);
    CHECK(workspace_creations==0);
}

TEST_CASE("public general projected hybrid reachability retains a dimension-changing path") {
    auto [system,request]=two_stage_dimension_change_system();
    const auto path=two_stage_dimension_change_path();
    GeneralProjectedStateHybridReachabilityAdapter adapter{64};

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{16,128,1024});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachability=std::get<HybridPathReachability>(result);
    CHECK(reachability.path==path);
    CHECK(reachability.joint_relation.metadata()->set.dimension==8);
    const auto relation=reachability.joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(relation));
    CHECK(has_dimension_change_relation(std::get<sets::HRepresentation>(relation)));
    const std::vector<std::string> expected_labels{
        "post:0:6:source:1:x","control:0:6:source:1:u","pre:1:6:source:1:x",
        "post:1:6:middle:1:p","post:1:6:middle:1:q",
        "pre:2:6:middle:1:p","pre:2:6:middle:1:q","post:2:6:target:1:y"};
    CHECK(reachability.joint_relation.metadata()->coordinate_labels==expected_labels);
    const std::vector<model::HybridRelationOperationKind> expected_operations{
        model::HybridRelationOperationKind::initial_state,
        model::HybridRelationOperationKind::post_state_invariant,
        model::HybridRelationOperationKind::mode_flow,
        model::HybridRelationOperationKind::continuous_control,
        model::HybridRelationOperationKind::pre_reset_invariant,
        model::HybridRelationOperationKind::transition_guard,
        model::HybridRelationOperationKind::reset_relation,
        model::HybridRelationOperationKind::post_state_invariant,
        model::HybridRelationOperationKind::mode_flow,
        model::HybridRelationOperationKind::continuous_control,
        model::HybridRelationOperationKind::pre_reset_invariant,
        model::HybridRelationOperationKind::transition_guard,
        model::HybridRelationOperationKind::reset_relation,
        model::HybridRelationOperationKind::post_state_invariant};
    const std::vector<std::size_t> expected_rows_added{1,0,1,1,0,0,2,0,2,0,0,0,1,0};
    const std::vector<std::size_t> expected_stages{0,0,0,0,1,0,0,1,1,1,2,1,1,2};
    const std::vector<std::string> expected_modes{
        "source","source","source","source","source","","","middle",
        "middle","middle","middle","","","target"};
    const std::vector<std::string> expected_edges{
        "","","","","","expand","expand","","","","","finish","finish",""};
    REQUIRE(reachability.relation_operations.size()==expected_operations.size());
    for(std::size_t index=0;index<expected_operations.size();++index) {
        const auto& operation=reachability.relation_operations[index];
        CHECK(operation.operation==expected_operations[index]);
        CHECK(operation.stage==expected_stages[index]);
        CHECK(operation.mode.has_value()==!expected_modes[index].empty());
        if(operation.mode) CHECK(operation.mode->value==expected_modes[index]);
        CHECK(operation.edge.has_value()==!expected_edges[index].empty());
        if(operation.edge) CHECK(operation.edge->value==expected_edges[index]);
        CHECK(operation.implementation_id=="csl.model.hybrid.joint-h-composer");
        CHECK(operation.implementation_version=="1");
        CHECK(operation.joint_variables==8);
        CHECK(operation.rows_added==expected_rows_added[index]);
        const auto cumulative_rows=index==0?expected_rows_added[index]:
            reachability.relation_operations[index-1].cumulative_rows+expected_rows_added[index];
        CHECK(operation.cumulative_rows==cumulative_rows);
        CHECK(operation.cumulative_matrix_elements==cumulative_rows*8);
    }
    REQUIRE(reachability.projected_state.has_value());
    const auto projected=reachability.projected_state->terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(projected));
    const auto& terminal=std::get<sets::HRepresentation>(projected);
    CHECK(reachability.projected_state->terminal_state_set.metadata()->set.dimension==1);
    CHECK(contains(terminal,0.0));
    CHECK_FALSE(contains(terminal,0.25));
}

TEST_CASE("general projected reachability independently checks an existential dimension-changing reset") {
    auto [system,request]=two_stage_dimension_change_system();
    system.edges.front().reset_relations.front()=
        set_valued_reset_one_to_two("contract.expand.existential-reset");
    const auto path=two_stage_dimension_change_path();
    GeneralProjectedStateHybridReachabilityAdapter adapter{64};

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{16,128,1024});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachability=std::get<HybridPathReachability>(result);
    CHECK(reachability.path==path);
    REQUIRE(reachability.joint_relation.metadata()!=nullptr);
    CHECK(reachability.joint_relation.metadata()->set.dimension==8);
    CHECK(reachability.joint_relation.metadata()->coordinate_labels==std::vector<std::string>{
        "post:0:6:source:1:x","control:0:6:source:1:u","pre:1:6:source:1:x",
        "post:1:6:middle:1:p","post:1:6:middle:1:q",
        "pre:2:6:middle:1:p","pre:2:6:middle:1:q","post:2:6:target:1:y"});

    const auto joint=reachability.joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(joint));
    const auto& relation=std::get<sets::HRepresentation>(joint);
    // The raw model gives x0=u0=0, p=x_pre=0, and existential q in [0,1].
    // Identity middle flow and y=p+q therefore give exactly y in [0,1].
    // Check the reset relation itself in its local coordinate order (pre,p,q).
    const auto reset_data=sets::from_handle(system.edges.front().reset_relations.front());
    REQUIRE(std::holds_alternative<sets::SetData>(reset_data));
    const auto reset_representation=std::get<sets::SetData>(reset_data).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(reset_representation));
    const auto& reset=std::get<sets::HRepresentation>(reset_representation);
    REQUIRE(reset.inequalities.rows()==2);
    REQUIRE(reset.equalities.rows()==1);
    CHECK(reset.inequalities(0,0)==0.0);
    CHECK(reset.inequalities(0,1)==0.0);
    CHECK(reset.inequalities(0,2)==-1.0);
    CHECK(reset.upper_bounds[0]==0.0);
    CHECK(reset.inequalities(1,0)==0.0);
    CHECK(reset.inequalities(1,1)==0.0);
    CHECK(reset.inequalities(1,2)==1.0);
    CHECK(reset.upper_bounds[1]==1.0);
    CHECK(reset.equalities(0,0)==-1.0);
    CHECK(reset.equalities(0,1)==1.0);
    CHECK(reset.equalities(0,2)==0.0);
    CHECK(reset.equality_values[0]==0.0);

    REQUIRE(reachability.projected_state.has_value());
    const auto& evidence=*reachability.projected_state;
    const auto projected=evidence.terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(projected));
    const auto& terminal=std::get<sets::HRepresentation>(projected);
    CHECK(evidence.terminal_state_set.metadata()->set.dimension==1);
    CHECK(contains(terminal,0.0));
    CHECK(contains(terminal,0.5));
    CHECK(contains(terminal,1.0));
    CHECK_FALSE(contains(terminal,-0.01));
    CHECK_FALSE(contains(terminal,1.01));
    bool lower_is_tight=false;
    bool upper_is_tight=false;
    for(std::size_t row=0;row<terminal.inequalities.rows();++row) {
        const auto coefficient=terminal.inequalities(row,0);
        const auto bound=terminal.upper_bounds[row];
        if(coefficient<0.0) lower_is_tight=lower_is_tight || bound/(-coefficient)==0.0;
        if(coefficient>0.0) upper_is_tight=upper_is_tight || bound/coefficient==1.0;
    }
    CHECK(lower_is_tight);
    CHECK(upper_is_tight);

    REQUIRE(reachability.relation_operations.size()==14);
    const auto reset_operation=std::find_if(reachability.relation_operations.begin(),
        reachability.relation_operations.end(),[](const auto& operation) {
            return operation.operation==model::HybridRelationOperationKind::reset_relation&&
                operation.edge==std::optional<model::HybridEdgeId>{{"expand"}};
        });
    REQUIRE(reset_operation!=reachability.relation_operations.end());
    CHECK(reset_operation->rows_added==3);
    CHECK(reset_operation->joint_variables==8);
    const auto total_relation_rows=relation.inequalities.rows()+relation.equalities.rows();
    CHECK(evidence.input_rows==total_relation_rows);
    CHECK(evidence.output_rows==terminal.inequalities.rows()+terminal.equalities.rows());
    CHECK(evidence.maximum_projection_rows==64);
    CHECK(evidence.input_rows<=evidence.maximum_projection_rows);
    CHECK(evidence.output_rows<=evidence.maximum_projection_rows);
}

TEST_CASE("general projected hybrid reachability matches an independent two-stage interval oracle") {
    auto [system,request]=two_stage_scalar_interval_system();
    const model::HybridPath path{{{"source"},{"middle"},{"target"}},{{"first"},{"second"}}};
    GeneralProjectedStateHybridReachabilityAdapter adapter{64};

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{8,64,512});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachability=std::get<HybridPathReachability>(result);
    REQUIRE(reachability.projected_state.has_value());
    const auto& evidence=*reachability.projected_state;
    CHECK(reachability.path==path);
    CHECK(evidence.terminal_state_set.metadata()->set.dimension==1);
    const auto projected=evidence.terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(projected));
    const auto& terminal=std::get<sets::HRepresentation>(projected);

    // From x0=0, u and v in [0,1], identity resets, and x+=control, the raw
    // two-stage model gives y=u+v. Thus the exact terminal projection is
    // [0,2], independently of the production relation composer and projector.
    CHECK(contains(terminal,0.0));
    CHECK(contains(terminal,0.5));
    CHECK(contains(terminal,1.0));
    CHECK(contains(terminal,1.5));
    CHECK(contains(terminal,2.0));
    CHECK_FALSE(contains(terminal,-0.01));
    CHECK_FALSE(contains(terminal,2.01));
    bool lower_is_tight=false;
    bool upper_is_tight=false;
    for(std::size_t row=0;row<terminal.inequalities.rows();++row) {
        const auto coefficient=terminal.inequalities(row,0);
        const auto bound=terminal.upper_bounds[row];
        CHECK(coefficient*0.0<=bound);
        CHECK(coefficient*2.0<=bound);
        if(coefficient<0.0) lower_is_tight=lower_is_tight || bound/(-coefficient)==0.0;
        if(coefficient>0.0) upper_is_tight=upper_is_tight || bound/coefficient==2.0;
    }
    CHECK(lower_is_tight);
    CHECK(upper_is_tight);
    const auto input_representation=reachability.joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(input_representation));
    const auto& input=std::get<sets::HRepresentation>(input_representation);
    REQUIRE_FALSE(reachability.relation_operations.empty());
    const auto& final_operation=reachability.relation_operations.back();
    CHECK(reachability.joint_relation.metadata()->set.dimension==7);
    CHECK(final_operation.joint_variables==7);
    CHECK(evidence.input_rows==input.inequalities.rows()+input.equalities.rows());
    CHECK(evidence.input_rows<=evidence.maximum_projection_rows);
    CHECK(evidence.output_rows==terminal.inequalities.rows()+terminal.equalities.rows());
    CHECK(evidence.output_rows<=evidence.maximum_projection_rows);
    CHECK(final_operation.cumulative_rows==input.inequalities.rows()+input.equalities.rows());
    CHECK(final_operation.cumulative_matrix_elements==final_operation.cumulative_rows*
        final_operation.joint_variables);
}

TEST_CASE("hybrid reachability portfolio preserves projected branches and aggregates provider resources") {
    auto [system,request]=parallel_interval_system();
    GeneralProjectedStateHybridReachabilityAdapter adapter{16};
    const auto result=compute_hybrid_reachability_portfolio(adapter,system,request,
        {1,2},{4,16,128});
    REQUIRE(std::holds_alternative<HybridReachabilityPortfolio>(result));
    const auto& portfolio=std::get<HybridReachabilityPortfolio>(result);
    REQUIRE(portfolio.branches.size()==2);

    const model::HybridPath half_path{{{"source"},{"target"}},{{"transition"}}};
    const model::HybridPath full_path{{{"source"},{"target"}},{{"full-transition"}}};
    const auto branch_for=[&](const model::HybridPath& path) -> const HybridPathReachability& {
        const auto found=std::find_if(portfolio.branches.begin(),portfolio.branches.end(),
            [&](const auto& branch) { return branch.path==path; });
        REQUIRE(found!=portfolio.branches.end());
        return *found;
    };
    const auto& half=branch_for(half_path);
    const auto& full=branch_for(full_path);
    REQUIRE(half.projected_state.has_value());
    REQUIRE(full.projected_state.has_value());
    const auto half_h=std::get<sets::HRepresentation>(
        half.projected_state->terminal_state_set.representation());
    const auto full_h=std::get<sets::HRepresentation>(
        full.projected_state->terminal_state_set.representation());
    CHECK(contains(half_h,0.0));
    CHECK(contains(half_h,0.25));
    CHECK(contains(half_h,0.5));
    CHECK_FALSE(contains(half_h,0.75));
    CHECK(contains(full_h,0.0));
    CHECK(contains(full_h,0.5));
    CHECK(contains(full_h,1.0));
    CHECK_FALSE(contains(full_h,1.25));

    REQUIRE(portfolio.projection_resources.size()==1);
    const auto& projection=portfolio.projection_resources.front();
    CHECK(projection.port=="geometry");
    CHECK(projection.actual_provider_id==std::optional<std::string>{"csl.geometry.polyhedral-projection"});
    CHECK(projection.branch_count==2);
    CHECK(projection.total_input_rows==12);
    CHECK(projection.max_input_rows==7);
    CHECK(projection.total_output_rows==6);
    CHECK(projection.max_output_rows==4);
    CHECK(projection.maximum_projection_rows==16);

    const auto shared_initial=std::find_if(portfolio.operation_resources.begin(),
        portfolio.operation_resources.end(),[](const auto& item) {
            return item.operation==model::HybridRelationOperationKind::initial_state;
        });
    REQUIRE(shared_initial!=portfolio.operation_resources.end());
    CHECK(shared_initial->branch_count==2);
    CHECK(shared_initial->max_joint_variables==4);
    const auto half_guard=std::find_if(portfolio.operation_resources.begin(),
        portfolio.operation_resources.end(),[&](const auto& item) {
            return item.operation==model::HybridRelationOperationKind::transition_guard&&
                item.edge==std::optional<model::HybridEdgeId>{{"transition"}};
        });
    const auto full_guard=std::find_if(portfolio.operation_resources.begin(),
        portfolio.operation_resources.end(),[&](const auto& item) {
            return item.operation==model::HybridRelationOperationKind::transition_guard&&
                item.edge==std::optional<model::HybridEdgeId>{{"full-transition"}};
        });
    REQUIRE(half_guard!=portfolio.operation_resources.end());
    REQUIRE(full_guard!=portfolio.operation_resources.end());
    CHECK(half_guard->branch_count==1);
    CHECK(half_guard->max_rows_added==2);
    CHECK(full_guard->branch_count==1);
    CHECK(full_guard->max_rows_added==0);
}

TEST_CASE("hybrid reachability portfolio preflights every provider operation before workspace creation") {
    auto [system,request]=parallel_interval_system();
    int admissions=0;
    int workspace_creations=0;
    registry::Registry<registry::GeometryPort> registry;
    registry::Registration<registry::GeometryPort> registration{
        {ModuleId{"contract.portfolio-reject-second-projection"},"1"},
        [&admissions](const OperationRequest&,const registry::Requirements& requirements) -> registry::Capability {
            ++admissions;
            if(admissions==2)
                return Diagnostics{{DiagnosticCode::unsupported,"contract.portfolio.second_rejected",
                    "The second path projection is rejected during portfolio preflight"}};
            return registry::Offer{requirements.output};
        },
        [&workspace_creations](const OperationRequest&) -> std::unique_ptr<SetOperatorWorkspace> {
            ++workspace_creations;
            return {};
        }};
    REQUIRE_FALSE(registry.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    const auto prepared=registry::prepare_provider(registry::select_provider(registry,
        {ModuleId{"contract.portfolio-reject-second-projection"},std::string{"1"}},requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared));
    GeneralProjectedStateHybridReachabilityAdapter adapter{
        std::get<registry::PreparedProvider<registry::GeometryPort>>(prepared),16};

    const auto result=compute_hybrid_reachability_portfolio(adapter,system,request,
        {1,2},{4,16,128});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="contract.portfolio.second_rejected");
    CHECK(admissions==2);
    CHECK(workspace_creations==0);
}

TEST_CASE("public general projected preflight admits the exact joint relation before workspace creation") {
    auto [system,request]=two_stage_dimension_change_system();
    const auto path=two_stage_dimension_change_path();
    const std::vector<std::string> expected_labels{
        "post:0:6:source:1:x","control:0:6:source:1:u","pre:1:6:source:1:x",
        "post:1:6:middle:1:p","post:1:6:middle:1:q",
        "pre:2:6:middle:1:p","pre:2:6:middle:1:q","post:2:6:target:1:y"};
    int admissions=0;
    int workspace_creations=0;
    bool observed_exact_relation=false;
    registry::Registry<registry::GeometryPort> registry;
    registry::Registration<registry::GeometryPort> registration{
        {ModuleId{"contract.inspect-general-projection"},"1"},
        [&admissions,&observed_exact_relation,expected_labels](const OperationRequest& operation,
            const registry::Requirements&) -> registry::Capability {
            ++admissions;
            const auto* projection=std::get_if<Projection>(&operation.operation);
            if(!projection || !operation.identity.request.value.starts_with("terminal-state:"))
                return Diagnostics{{DiagnosticCode::evidence_mismatch,"contract.general_projection.identity",
                    "The provider expected the terminal projection request"}};
            const auto imported=sets::from_handle(projection->input);
            if(!std::holds_alternative<sets::SetData>(imported))
                return Diagnostics{{DiagnosticCode::invalid_input,"contract.general_projection.input",
                    "The provider expected an importable joint relation"}};
            const auto& data=std::get<sets::SetData>(imported);
            const auto representation=data.representation();
            if(!std::holds_alternative<sets::HRepresentation>(representation))
                return Diagnostics{{DiagnosticCode::unsupported,"contract.general_projection.representation",
                    "The provider expected an H-represented joint relation"}};
            const auto& h=std::get<sets::HRepresentation>(representation);
            if(data.metadata()->set.dimension!=8 ||
               data.metadata()->coordinate_labels!=expected_labels ||
               projection->coordinates!=std::vector<std::size_t>{7} ||
               !has_dimension_change_relation(h))
                return Diagnostics{{DiagnosticCode::evidence_mismatch,"contract.general_projection.relation",
                    "The provider expected the complete labelled relation and terminal coordinate"}};
            observed_exact_relation=true;
            return Diagnostics{{DiagnosticCode::unsupported,"contract.general_projection.rejected",
                "The provider rejected the admitted operation before workspace creation"}};
        },
        [&workspace_creations](const OperationRequest&) -> std::unique_ptr<SetOperatorWorkspace> {
            ++workspace_creations;
            return {};
        }};
    REQUIRE_FALSE(registry.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    const auto prepared=registry::prepare_provider(registry::select_provider(registry,
        {ModuleId{"contract.inspect-general-projection"},std::string{"1"}},requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared));
    GeneralProjectedStateHybridReachabilityAdapter adapter{
        std::get<registry::PreparedProvider<registry::GeometryPort>>(prepared),64};

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{16,128,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="contract.general_projection.rejected");
    CHECK(admissions==1);
    CHECK(observed_exact_relation);
    CHECK(workspace_creations==0);
}
