#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/witness_selector.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/validator.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <limits>
#include <thread>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
using namespace csl;
using namespace csl::registry;
namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lower,double upper) {
    Matrix inequalities{2,1,{1,-1}};
    Matrix equalities{0,1,{}};
    const sets::Description description{SetId{std::move(id)},1,std::vector<std::string>{"u"}};
    const sets::HRepresentation representation{take(numeric::snapshot(inequalities)),
        take(numeric::snapshot_vector(Vector{upper,-lower})),take(numeric::snapshot(equalities)),
        take(numeric::snapshot_vector(Vector{}))};
    return take(sets::make_h(description,representation)).as_handle();
}
void set_quadratic_objective(Problem& problem,double hessian_value,double linear_value,double constant) {
    problem.objective.emplace<QuadraticTerminal>();
    auto& objective=std::get<QuadraticTerminal>(problem.objective);
    objective.Q.rows=1;objective.Q.cols=1;objective.Q.values=Vector{hessian_value};
    objective.linear=Vector{linear_value};objective.offset=constant;
}
Problem source() {
    Matrix state_transition{};state_transition.rows=1;state_transition.cols=1;state_transition.values=Vector{1};
    Matrix control_transition{};control_transition.rows=1;control_transition.cols=1;control_transition.values=Vector{1};
    Matrix external_transition{};external_transition.rows=1;external_transition.cols=0;
    LinearStage transition{std::move(state_transition),std::move(control_transition),std::move(external_transition),Vector{0}};
    Dynamics dynamics{{1,1,0},TimeDomain::discrete,std::move(transition)};
    auto model=std::make_shared<const SystemModel>(SystemModel{std::move(dynamics),{}});
    Problem problem{};problem.id={"ts01"};problem.model=std::move(model);problem.times={0,1,2};
    problem.initial=KnownInitial{Vector{0}};
    problem.controls=ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}};
    problem.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    problem.information=InformationPattern::nominal_open_loop;
    set_quadratic_objective(problem,2,-2,1);
    return problem;
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
    return {std::move(p),configuration,std::move(family),{},{}};
}
ExecutionContext make_execution_context() {
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
    return take(workspace->run(make_execution_context()));
}
}
TEST_CASE("oriented directions minimize controls and retain complete histories") {
    auto synthesis=run(request(resolve(source()))); REQUIRE(synthesis.family);
    Registry<LPPort> lp; REQUIRE_FALSE(lp.add(take(adapters::lp::make_highs_registration())).has_value());
    Requirements req; req.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
    Registry<SelectorPort> selectors; REQUIRE_FALSE(selectors.add(synthesis::witness_selector::make_registration(provider)).has_value());
    SelectorRequest query{*synthesis.family,{3,1e-9,{{1,-1},{-1,1},{1,-1}},42}};
    Requirements out; out.output.representation={"csl.witness-batch.v1"};
    auto prepared=take(prepare_pipeline(select(selectors,Method{{synthesis::witness_selector::selector_id},{}},query,out)));
    auto workspace=prepared.create(); auto selection=take(std::get<0>(workspace)->run(make_execution_context()));
    REQUIRE(selection.termination==Termination::completed);
    REQUIRE(selection.batch.witnesses.size()==3);
    CHECK(selection.batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});
    CHECK(selection.batch.witnesses[1].controls==std::vector<Vector>{{1},{0}});
    CHECK(selection.batch.witnesses[0].states==std::vector<Vector>{{0},{0},{1}});
    CHECK(selection.batch.witnesses[1].states==std::vector<Vector>{{0},{1},{1}});
    CHECK(selection.batch.witnesses[0].original_objective==0);
    CHECK(selection.batch.witnesses[1].original_objective==0);
    CHECK(selection.batch.requested==3); CHECK(selection.batch.returned_count()==3); CHECK(selection.batch.distinct_count()==2);
    CHECK(selection.batch.directions==query.selection.directions); CHECK(selection.batch.distinctness_tolerance==1e-9);
    CHECK(selection.batch.seed==42); CHECK(selection.batch.source_family==synthesis.family->identity());
    CHECK(selection.diagnostics.find("shortfall")!=std::string::npos);
}

TEST_CASE("reject malformed direction before provider creation and honor cancellation") {
    auto synthesis=run(request(resolve(source()))); REQUIRE(synthesis.family);
    Registry<LPPort> lp; auto backend=take(adapters::lp::make_highs_registration());
    backend.identity.id={"replacement-lp"}; auto factory=backend.factory; auto creations=std::make_shared<int>(0);
    backend.factory=[factory,creations](const auto& program){++*creations; return factory(program);};
    REQUIRE_FALSE(lp.add(std::move(backend)).has_value());
    Requirements req; req.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"replacement-lp"},{}},req)));
    auto registration=synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*synthesis.family,{2,1e-9,{{1,-1},{-1,1}},7}};
    auto workspace=registration.factory(query);
    auto bad=query.selection; bad.directions={{1}};
    REQUIRE(std::holds_alternative<Unsupported>(workspace->select(query.family,bad,make_execution_context())));
    CHECK(*creations==0);
    std::stop_source stop; stop.request_stop(); auto context=make_execution_context(); context.cancellation=stop.get_token();
    auto cancelled=take(workspace->select(query.family,query.selection,context));
    CHECK(cancelled.termination==Termination::cancelled); CHECK(cancelled.batch.witnesses.empty()); CHECK(*creations==0);
    context=make_execution_context(); context.deadline=std::chrono::steady_clock::now();
    auto expired=take(workspace->select(query.family,query.selection,context));
    CHECK(expired.termination==Termination::cancelled);
    CHECK(expired.diagnostics.find("deadline")!=std::string::npos);
    CHECK(*creations==0);
    auto valid=take(workspace->select(query.family,query.selection,make_execution_context()));
    REQUIRE(valid.batch.witnesses.size()==2); CHECK(*creations==2);
}
TEST_CASE("direction budget exhaustion is a search shortfall and invalid resource policy rejects") {
    auto synthesis=run(request(resolve(source()))); REQUIRE(synthesis.family);
    Registry<LPPort> lp; REQUIRE_FALSE(lp.add(take(adapters::lp::make_highs_registration())).has_value());
    Requirements req; req.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
    auto registration=synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*synthesis.family,{2,1e-9,{{1,-1}},9}};
    auto workspace=registration.factory(query);
    auto result=take(workspace->select(query.family,query.selection,make_execution_context()));
    REQUIRE(result.batch.witnesses.size()==1); CHECK(result.termination==Termination::completed);
    CHECK(result.diagnostics.find("shortfall")!=std::string::npos);
    auto context=make_execution_context(); context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,2,{}});
    CHECK(std::holds_alternative<Unsupported>(workspace->select(query.family,query.selection,context)));
}

TEST_CASE("distinctness uses ordered greedy joint-history infinity distance") {
    WitnessBatch batch{{},4,{"test"},{}}; batch.distinctness_tolerance=0.5;
    auto witness=[](double u){return Witness{{"p"},{{0},{u}},{{u}},0};};
    batch.witnesses={witness(0),witness(0.5),witness(1)};
    CHECK(batch.returned_count()==3); CHECK(batch.distinct_count()==2);
    batch.witnesses={witness(0.5),witness(0),witness(1)};
    CHECK(batch.distinct_count()==1);
    auto different_shape=witness(0.5);different_shape.controls={{0.5,0}};
    batch.witnesses.push_back(different_shape); CHECK(batch.distinct_count()==2);
    auto state_only=batch.witnesses[0];state_only.states[0][0]=10;batch.witnesses.push_back(state_only);
    CHECK(batch.distinct_count()==3);
}

TEST_CASE("unsupported family and late direction capability reject before any LP solve") {
    auto synthesis=run(request(resolve(source()))); REQUIRE(synthesis.family);
    Registry<LPPort> lp; auto backend=take(adapters::lp::make_highs_registration());
    auto factory=backend.factory; auto creations=std::make_shared<int>(0);
    backend.factory=[factory,creations](const auto& p){++*creations;return factory(p);};
    auto capabilities=backend.capabilities;
    backend.capabilities=[capabilities](const LinearProgram& p,const Requirements& r)->Capability {
        if(p.objective()[3]<0)return Diagnostics{{DiagnosticCode::unsupported,"test.direction","negative u0 direction is unsupported"}};
        return capabilities(p,r);
    };
    REQUIRE_FALSE(lp.add(std::move(backend)).has_value());Requirements req;req.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
    auto registration=synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*synthesis.family,{2,0,{{1,-1},{-1,1}},0}};
    auto workspace=registration.factory(query);
    CHECK(std::holds_alternative<Unsupported>(workspace->select(query.family,query.selection,make_execution_context())));
    CHECK(*creations==0);
    auto identity=query.family.identity();identity.request.target=FamilyTarget::candidate_relaxation;
    const auto relation=std::get<CompleteOptimalFamily>(query.family.outcome()).relation;
    auto candidate=take(FamilyPublisher::publish(identity,CandidateFamily{relation,HeuristicRelationEvidence{"test"},Unestablished{}}));
    CHECK(std::holds_alternative<Unsupported>(workspace->select(candidate,query.selection,make_execution_context())));
    CHECK(*creations==0);
}

namespace {
template<class Port> PreparedProvider<Port> selected(Registration<Port> entry,std::string representation) {
    Registry<Port> registry;Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());Requirements requirements;
    requirements.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,GeometryPort>||std::is_same_v<Port,ConversionPort>)requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
PreparedStrategy strategy_a(StrategyRequest request_) {
    auto lp=take(adapters::lp::make_highs_registration());auto convex=take(adapters::convex::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection=geometry::polyhedral::make_projection_registration();
    auto affine=geometry::make_affine_sum_registration({selected(geometry::make_lp_hull_reducer_registration(),""),
        selected(lp,"csl.program-result.v1"),selected(converter,"csl.polyhedron.v")});
    Registry<GeometryPort> projections,affines;Registry<ConversionPort> conversions;Registry<LPPort> lps;Registry<ConvexPort> convexes;
    Method pm{projection.identity.id,{}},am{affine.identity.id,{}},cm{converter.identity.id,{}},lm{lp.identity.id,{}},qm{convex.identity.id,{}};
    REQUIRE_FALSE(projections.add(projection));REQUIRE_FALSE(affines.add(affine));REQUIRE_FALSE(conversions.add(converter));REQUIRE_FALSE(lps.add(lp));REQUIRE_FALSE(convexes.add(convex));
    Requirements h,v,program;h.output.representation={"csl.polyhedron.h"};h.output.relation=SetRelation::equivalent;
    v.output.representation={"csl.polyhedron.v"};v.output.relation=SetRelation::equivalent;program.output.representation={"csl.program-result.v1"};
    auto providers=take(check_providers(select_provider(projections,pm,h),select_provider(affines,am,v),select_provider(conversions,cm,h),select_provider(lps,lm,program),select_provider(convexes,qm,program)));
    StrategyRegistry registry;REQUIRE_FALSE(registry.add(synthesis::strategy_a::make_registration(std::move(providers))));
    Requirements output;output.output.representation=request_.family.representation;output.output.family=request_.family.target;output.output.completeness=Completeness::established;
    return take(registry.prepare(request_,output));
}
}
TEST_CASE("one selector queries complete registered families from both strategies") {
    Registry<LPPort> lp;REQUIRE_FALSE(lp.add(take(adapters::lp::make_highs_registration())));
    Registry<ConvexPort> convex;REQUIRE_FALSE(convex.add(take(adapters::convex::make_highs_registration())));
    Requirements program;program.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},program)));
    auto selector=synthesis::witness_selector::make_registration(provider);
    for(const bool use_a:{true,false}) {
        auto synthesis_request=request(resolve(source()));
        synthesis_request.configuration.strategy={use_a?"csl.synthesis.reach-back":"csl.synthesis.strategy-b"};
        synthesis_request.configuration.lp={"csl.lp.highs"};synthesis_request.configuration.convex={"csl.convex.highs"};
        auto prepared=[&]() {
            if(use_a)return strategy_a(synthesis_request);
            StrategyRegistry registry;REQUIRE_FALSE(registry.add(synthesis::strategy_b::make_registration(lp,convex)));
            Requirements output;output.output.representation=synthesis_request.family.representation;output.output.family=synthesis_request.family.target;output.output.completeness=Completeness::established;
            return take(registry.prepare(synthesis_request,output));
        }();
        auto synthesis_workspace=prepared.create();auto result=take(synthesis_workspace->run(make_execution_context()));REQUIRE(result.family);
        SelectorRequest query{*result.family,{2,0,{{1,-1},{-1,1}},31}};
        auto workspace=selector.factory(query);auto answer=take(SelectorPort::run(*workspace,query,make_execution_context()));
        REQUIRE(answer.batch.returned_count()==2);CHECK(answer.batch.distinct_count()==2);
        CHECK(answer.batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});CHECK(answer.batch.witnesses[1].controls==std::vector<Vector>{{1},{0}});
        CHECK(answer.batch.witnesses[0].states==std::vector<Vector>{{0},{0},{1}});CHECK(answer.batch.witnesses[1].states==std::vector<Vector>{{0},{1},{1}});
        CHECK(answer.batch.source_family==result.family->identity());CHECK(answer.batch.witnesses[0].original_objective==0);CHECK(answer.batch.witnesses[1].original_objective==0);
    }
}

namespace {
class StopAfterQuery final : public LPWorkspace {
    std::unique_ptr<LPWorkspace> inner_;std::stop_source stop_;std::shared_ptr<const ResourcePolicy> expected_;
protected:
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override {
        CHECK(c.resources==expected_);auto result=inner_->solve(p,c);stop_.request_stop();return result;
    }
public:
    StopAfterQuery(std::unique_ptr<LPWorkspace> inner,std::stop_source stop,std::shared_ptr<const ResourcePolicy> expected)
        :inner_(std::move(inner)),stop_(std::move(stop)),expected_(std::move(expected)){}
};
}
TEST_CASE("mid-query cancellation retains earlier histories and forwards the immutable resource policy") {
    auto synthesis=run(request(resolve(source()))); REQUIRE(synthesis.family);
    auto context=make_execution_context();std::stop_source stop;context.cancellation=stop.get_token();
    auto backend=take(adapters::lp::make_highs_registration());auto factory=backend.factory;auto expected=context.resources;
    backend.factory=[factory,stop,expected](const LinearProgram& p){return std::make_unique<StopAfterQuery>(factory(p),stop,expected);};
    Registry<LPPort> lp;REQUIRE_FALSE(lp.add(std::move(backend)));
    Requirements req;req.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
    auto registration=synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*synthesis.family,{2,0,{{1,-1},{-1,1}},0}};
    auto workspace=registration.factory(query);auto selected=take(workspace->select(query.family,query.selection,context));
    CHECK(selected.termination==Termination::cancelled);REQUIRE(selected.batch.returned_count()==1);
    CHECK(selected.batch.witnesses[0].states==std::vector<Vector>{{0},{0},{1}});
    CHECK(selected.batch.source_family==query.family.identity());CHECK(query.family.target()==FamilyTarget::exact_optimal_relation);
}

namespace {
class DeadlineOrCapacity final : public LPWorkspace {
    std::unique_ptr<LPWorkspace> inner_;bool deadline_;std::shared_ptr<int> calls_;
protected:
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override {
        if(++*calls_==2)return ProgramResult{Termination::resource_limit,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},"provider capacity exhausted",{}};
        auto result=inner_->solve(p,c);
        if(deadline_)std::this_thread::sleep_until(*c.deadline);
        return result;
    }
public:
    DeadlineOrCapacity(std::unique_ptr<LPWorkspace> inner,bool deadline,std::shared_ptr<int> calls):inner_(std::move(inner)),deadline_(deadline),calls_(std::move(calls)){}
};
}
TEST_CASE("deadline and provider capacity remain distinct and retain earlier observations") {
    auto synthesis=run(request(resolve(source())));REQUIRE(synthesis.family);
    for(bool deadline:{true,false}) {
        auto backend=take(adapters::lp::make_highs_registration());auto factory=backend.factory;auto calls=std::make_shared<int>(0);
        backend.factory=[factory,deadline,calls](const LinearProgram& p){return std::make_unique<DeadlineOrCapacity>(factory(p),deadline,calls);};
        Registry<LPPort> lp;REQUIRE_FALSE(lp.add(std::move(backend)));Requirements req;req.output.representation={"csl.program-result.v1"};
        auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
        auto registration=synthesis::witness_selector::make_registration(provider);SelectorRequest query{*synthesis.family,{2,0,{{1,-1},{-1,1}},0}};
        auto workspace=registration.factory(query);auto context=make_execution_context();
        if(deadline)context.deadline=std::chrono::steady_clock::now()+std::chrono::seconds(1);
        auto selected=take(workspace->select(query.family,query.selection,context));
        CHECK(selected.termination==(deadline?Termination::cancelled:Termination::resource_limit));
        CHECK(selected.diagnostics.find(deadline?"deadline":"capacity")!=std::string::npos);
        REQUIRE(selected.batch.returned_count()==1);CHECK(selected.batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});
        CHECK(selected.batch.source_family==query.family.identity());
    }
}
