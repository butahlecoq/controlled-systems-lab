#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/validator.hpp>
#include <csl/sets/data.hpp>
#include <cmath>
#include <iostream>
#include <limits>

using namespace csl;
using namespace csl::registry;
namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lower,double upper) {
    return take(sets::make_h({std::move(id),1,{"u"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{upper,-lower})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
Problem source() {
    return {{"ts01"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},
            {1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,QuadraticTerminal{{1,1,{2}},{-2},1}};
}
problem::ResolvedProblem resolve(Problem p) {
    return take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
StrategyRequest request(problem::ResolvedProblem p) {
    FamilyRequest family;family.profile="ts01_exact_integrator";family.objective=p.identity();
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.ts01-analytic"};
    configuration.representation=family.representation;
    return {std::move(p),configuration,std::move(family),{}};
}
ExecutionContext execution() {
    ExecutionContext result;result.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    return result;
}
SynthesisResult run(StrategyRequest request_) {
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    Requirements requirements;requirements.output.representation=request_.family.representation;
    requirements.output.family=request_.family.target;
    requirements.output.completeness=Completeness::established;
    auto prepared=take(strategies.prepare(request_,requirements));
    auto workspace=prepared.create();
    return take(workspace->run(execution()));
}
bool rejected(Problem p) {
    auto request_=request(resolve(std::move(p)));
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    Requirements requirements;requirements.output.representation=request_.family.representation;
    requirements.output.family=request_.family.target;
    requirements.output.completeness=Completeness::established;
    return std::holds_alternative<Rejection>(strategies.prepare(request_,requirements));
}
}

TEST_CASE("registered T-S01 exact profile publishes its canonical complete family") {
    const auto result=run(request(resolve(source())));
    REQUIRE(result.termination==Termination::completed);
    REQUIRE(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.family);
    REQUIRE(result.family->target()==FamilyTarget::exact_optimal_relation);
    const auto& identity=result.family->identity();
    CHECK(identity.problem==result.outcome.subject);
    CHECK(identity.request.target==FamilyTarget::exact_optimal_relation);
    CHECK(identity.strategy==ModuleId{"csl.synthesis.ts01-analytic"});
    CHECK(identity.strategy_version=="1");
    CHECK(identity.lineage.empty());
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    CHECK(complete.relation.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(complete.optimum.optimum.problem==identity.problem);
    CHECK(complete.assurance==Assurance::numerical);
    const auto* relation=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete.relation.payload.get());
    REQUIRE(relation);
    const auto h=relation->h_polyhedron().representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(h));
    CHECK(std::get<sets::HRepresentation>(h).inequalities.rows()==4);
    CHECK(std::get<sets::HRepresentation>(h).equalities.rows()==4);
    const auto& h_data=std::get<sets::HRepresentation>(h);
    CHECK(h_data.inequalities(0,3)==1);
    CHECK(h_data.upper_bounds[0]==1);
    CHECK(h_data.equalities(0,0)==1);
    CHECK(h_data.equality_values[2]==1);
    CHECK(h_data.equalities(3,3)==1);
    CHECK(h_data.equalities(3,4)==1);
    CHECK(relation->h_polyhedron().metadata()->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"});
    CHECK(relation->contains(Vector{0,0,1,0,1}));
    CHECK(relation->contains(Vector{0,0.25,1,0.25,0.75}));
    CHECK(relation->contains(Vector{0,1,1,1,0}));
    const auto epsilon=std::ldexp(1.0,-53);
    CHECK(relation->contains(Vector{0,1.0-epsilon,1,1.0-epsilon,epsilon}));
    CHECK_FALSE(relation->contains(Vector{0,0,0,0,0}));
    CHECK_FALSE(relation->contains(Vector{0,1,2,1,1}));
    CHECK_FALSE(relation->contains(Vector{0,1,1,1,std::numeric_limits<double>::denorm_min()}));
}

TEST_CASE("T-S01 admission rejects objective, dynamics, controls, initial and temporal mutations") {
    auto p=source();p.objective=ResidualNormTerminal{{1,1,{1}},{1}};
    CHECK(rejected(p));
    p=source();p.objective=QuadraticTerminal{{1,1,{1}},{-2},1};
    CHECK(rejected(p));
    p=source();p.objective=QuadraticTerminal{{1,1,{2}},{-2},0};
    CHECK(rejected(p));
    p=source();auto altered=std::make_shared<SystemModel>(*p.model);
    std::get<LinearStage>(altered->dynamics.stages).A.values[0]=0;p.model=std::move(altered);
    CHECK(rejected(p));
    p=source();altered=std::make_shared<SystemModel>(*p.model);
    std::get<LinearStage>(altered->dynamics.stages).B.values[0]=2;p.model=std::move(altered);
    CHECK(rejected(p));
    p=source();altered=std::make_shared<SystemModel>(*p.model);
    std::get<LinearStage>(altered->dynamics.stages).offset[0]=1;p.model=std::move(altered);
    CHECK(rejected(p));
    p=source();p.controls=ContinuousDomain{{interval("u0",-1,1),interval("u1",0,1)}};
    CHECK(rejected(p));
    p=source();p.initial=KnownInitial{{1}};
    CHECK(rejected(p));
    p=source();p.states[1]=interval("restricted-state",0,1);
    CHECK(rejected(p));
    p=source();p.temporal=TemporalConstraints{SparseMatrix{1,5,{0,1},{0},{1}},{Interval{0,0}}};
    CHECK(rejected(p));
}

TEST_CASE("T-S01 publication binds the immutable request, coordinates and registered strategy") {
    const auto result=run(request(resolve(source())));
    REQUIRE(result.family);
    const auto original=result.family->identity();
    for(const auto mutation:{0,1,2,3}) {
        auto forged=original;
        if(mutation==0)forged.request.profile="other";
        if(mutation==1)forged.coordinates.horizon=3;
        if(mutation==2)forged.strategy.value="csl.synthesis.other";
        if(mutation==3)forged.strategy_version="2";
        const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
        const auto attempted=FamilyPublisher::publish(forged,complete);
        CHECK(std::holds_alternative<Diagnostics>(attempted));
    }
}

TEST_CASE("T-S01 registry rejects mismatched request and selected strategy identity") {
    auto base=request(resolve(source()));
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    Requirements requirements;requirements.output.representation=base.family.representation;
    requirements.output.family=base.family.target;requirements.output.completeness=Completeness::established;
    auto wrong=base;wrong.family.profile="other";
    CHECK(std::holds_alternative<Rejection>(strategies.prepare(wrong,requirements)));
    wrong=base;wrong.family.target=FamilyTarget::candidate_relaxation;
    requirements.output.family=wrong.family.target;
    CHECK(std::holds_alternative<Rejection>(strategies.prepare(wrong,requirements)));
    requirements.output.family=base.family.target;
    wrong=base;wrong.configuration.strategy={"csl.synthesis.unregistered"};
    CHECK(std::holds_alternative<Rejection>(strategies.prepare(wrong,requirements)));
    CHECK(std::holds_alternative<Rejection>(strategies.prepare(base,requirements,"2")));
}

TEST_CASE("generic numerical and unchecked certificate strings cannot publish complete families") {
    const auto result=run(request(resolve(source())));
    REQUIRE(result.family);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto identity=result.family->identity();
    auto fake=std::make_shared<const JointRelationPayload>();
    const auto arbitrary=SymbolicArgument{"looks like a proof","not a trusted analytic capability"};
    for(const auto& support:std::vector<std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence>>{
        NumericalCoverageEvidence{"always-pass",{0,0},{"verifier"},"residual below invented tolerance"},
        ValidatedCoverageEvidence{"artifact:unverified","checker:unregistered","exact-looking"}}) {
        const auto completeness_support=std::holds_alternative<NumericalCoverageEvidence>(support)?
            std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence,Ts01AnalyticCoverageEvidence>{std::get<NumericalCoverageEvidence>(support)}:
            std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence,Ts01AnalyticCoverageEvidence>{std::get<ValidatedCoverageEvidence>(support)};
        CompleteOptimalFamily untrusted{{complete.relation.coordinates,identity.request.representation,fake},
            {{identity.problem,arbitrary},{}},{identity,completeness_support},Assurance::numerical};
        CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,std::move(untrusted))));
    }
}
