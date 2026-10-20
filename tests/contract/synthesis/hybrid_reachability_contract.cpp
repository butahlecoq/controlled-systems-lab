#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/registry/registry.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>

#include <memory>
#include <string>
#include <utility>

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
            if(!operation.identity.request.value.starts_with("preflight:"))
                return Diagnostics{{DiagnosticCode::evidence_mismatch,"contract.projection.identity",
                    "The provider expected its preflight request"}};
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
