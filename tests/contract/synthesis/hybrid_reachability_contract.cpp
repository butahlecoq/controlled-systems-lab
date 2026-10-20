#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/registry/registry.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>

#include <memory>
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
    REQUIRE(reachability.projected_state.has_value());
    const auto projected=reachability.projected_state->terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(projected));
    const auto& terminal=std::get<sets::HRepresentation>(projected);
    CHECK(reachability.projected_state->terminal_state_set.metadata()->set.dimension==1);
    CHECK(contains(terminal,0.0));
    CHECK_FALSE(contains(terminal,0.25));
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
