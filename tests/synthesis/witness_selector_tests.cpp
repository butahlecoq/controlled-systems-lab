#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/witness_selector.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/validator.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <limits>
#include <thread>
#include <cstdlib>
#include <new>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/execution/timing_collector.hpp>
#include <bit>
namespace selector_allocation_probe {
thread_local std::size_t fail_small_allocation=0;
thread_local bool injected=false;
}
#if defined(_MSC_VER)
#define CSL_SELECTOR_NOINLINE __declspec(noinline)
#else
#define CSL_SELECTOR_NOINLINE __attribute__((noinline))
#endif
CSL_SELECTOR_NOINLINE void* operator new(std::size_t size) {
    if(size==sizeof(std::size_t)&&selector_allocation_probe::fail_small_allocation&&
       --selector_allocation_probe::fail_small_allocation==0) {
        selector_allocation_probe::injected=true;throw std::bad_alloc{};
    }
    if(auto* result=std::malloc(size?size:1))return result;
    throw std::bad_alloc{};
}
CSL_SELECTOR_NOINLINE void* operator new[](std::size_t size){return ::operator new(size);}
CSL_SELECTOR_NOINLINE void operator delete(void* p)noexcept{std::free(p);}
CSL_SELECTOR_NOINLINE void operator delete[](void* p)noexcept{std::free(p);}
CSL_SELECTOR_NOINLINE void operator delete(void* p,std::size_t)noexcept{std::free(p);}
CSL_SELECTOR_NOINLINE void operator delete[](void* p,std::size_t)noexcept{std::free(p);}
#undef CSL_SELECTOR_NOINLINE
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
namespace ar=artifacts;
namespace ob=execution::observability;
class SelectorClock final:public ob::TimingClock {
    std::int64_t tick_{};
public:
    ar::ClockDomain wall_domain() const override {
        return {{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
            ar::Available<std::uint64_t>{1},"selector-test"};
    }
    std::optional<ar::ClockDomain> cpu_domain() const override{return {};}
    ar::Metric<std::int64_t> wall_now() noexcept override {
        const auto result=tick_;tick_+=10;return ar::Available<std::int64_t>{result};
    }
    ar::Metric<std::int64_t> cpu_now() noexcept override {
        return ar::Unavailable{ar::MissingReason::not_supported,{}};
    }
};
ProgramIdentity direction_program(const OptimalFamily& family,const WitnessRequest& request,
        std::size_t index) {
    const auto& direction=request.directions[index];
    const auto bits=[](double value) {return std::to_string(std::bit_cast<std::uint64_t>(value));};
    return {family.identity().problem,{"witness-selector-direction/"+std::to_string(index)+"/"+
        bits(direction[0])+"/"+bits(direction[1])}};
}
std::shared_ptr<ob::TimingCollector> selector_timing(const problem::ResolvedProblem& resolved,
        const OptimalFamily& family,const WitnessRequest& request,const registry::Provenance& provider) {
    REQUIRE(provider.actual);
    const ar::Unavailable unpinned{ar::MissingReason::not_instrumented,{}};
    const ar::ModuleIdentity strategy{family.identity().strategy,family.identity().strategy_version,unpinned};
    const ar::ModuleIdentity lp{provider.actual->id,provider.actual->version,unpinned};
    const ar::ModuleIdentity selector{{synthesis::witness_selector::selector_id},"1",unpinned};
    const auto& family_request=family.identity().request;
    ar::ConfigurationInput configuration;
    configuration.collection={true,ar::CollectionMode::detail,8,4096,8,1024};
    configuration.modules={{"lp",lp,{}},{"selector",selector,{}},{"strategy",strategy,{}}};
    configuration.numerical=family_request.numerical;
    configuration.resources={1,1,1,{}};
    configuration.output={ar::OutputKind::synthesis,family_request.assurance,family_request.target,
        family_request.representation,{request.count,request.distinctness_tolerance,request.directions,request.seed}};
    configuration.selector={selector.id,selector.version,{}};
    configuration.strategy={strategy.id,lp.id,{},{},{},{},{},selector.id,family_request.representation};
    auto resolved_configuration=take(ar::resolve_configuration(configuration));
    const ar::ClockDomain clock{{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
        ar::Available<std::uint64_t>{1},"selector-test"};
    const auto operation=std::string{"selector.lp.direction-query"};
    ob::PlanInput input{resolved,std::move(resolved_configuration),{"run"},{clock},{},1};
    input.tasks={"run"};input.operations={"operation.run",operation};
    ar::SpanDescriptor root{};root.id={0};root.task="run";root.operation="operation.run";
    root.module=strategy;root.clock=clock.id;root.requested_assurance=family_request.assurance;
    root.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    input.spans.push_back(root);
    for(std::size_t index=0;index<request.directions.size();++index) {
        ar::SpanDescriptor query{};query.id={index+1};query.parent=ar::SpanParent{{0},ar::ParentKind::nested};
        query.task="run";query.operation=operation;query.module=selector;
        query.backend=std::make_shared<const ar::ModuleIdentity>(lp);query.clock=clock.id;
        query.program=std::make_shared<const ProgramIdentity>(direction_program(family,request,index));
        query.query=index;query.requested_assurance=family_request.assurance;
        query.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
        query.observation_source="witness-selector-lp-query";
        input.spans.push_back(std::move(query));
    }
    auto plan=take(ob::make_collection_plan(std::move(input)));
    return take(ob::make_timing_collector(plan,std::make_shared<SelectorClock>(),{0},{}));
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

TEST_CASE("direction LP executions record their selector, backend, program, and query span") {
    const auto resolved=resolve(source());
    auto synthesis_result=run(request(resolved)); REQUIRE(synthesis_result.family);
    Registry<LPPort> lp; REQUIRE_FALSE(lp.add(take(adapters::lp::make_highs_registration())).has_value());
    Requirements lp_requirements;lp_requirements.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},lp_requirements)));
    Registry<SelectorPort> selectors;
    REQUIRE_FALSE(selectors.add(synthesis::witness_selector::make_registration(provider)).has_value());
    const auto family=*synthesis_result.family;
    const WitnessRequest selection_request{2,1e-9,{{1,-1},{-1,1}},17};
    SelectorRequest query{family,selection_request};
    Requirements output;output.output.representation={"csl.witness-batch.v1"};
    auto prepared=take(prepare_pipeline(select(selectors,
        Method{{synthesis::witness_selector::selector_id},{}},query,output)));
    auto workspace=prepared.create();
    const auto timer=selector_timing(resolved,family,selection_request,provider.provenance());
    auto context=make_execution_context();context.run_id="run";context.timing=timer;
    auto root=take(timer->start({0},context));
    auto selection=take(std::get<0>(workspace)->run(context));
    root.close(Termination::completed);
    REQUIRE(selection.termination==Termination::completed);
    REQUIRE(selection.batch.witnesses.size()==2);
    CHECK(selection.batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});
    CHECK(selection.batch.witnesses[1].controls==std::vector<Vector>{{1},{0}});
    const auto report=take(timer->snapshot());
    REQUIRE(report.spans.size()==3);
    for(std::size_t index=0;index<selection_request.directions.size();++index) {
        const auto& timed=report.spans[index+1];
        REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(timed.inclusive_wall_ticks));
        CHECK(std::get<ar::Available<std::uint64_t>>(timed.inclusive_wall_ticks).value==10);
        const auto& record=report.observations.description().spans[index+1];
        CHECK(record.descriptor.operation=="selector.lp.direction-query");
        CHECK(record.descriptor.module.id==ModuleId{synthesis::witness_selector::selector_id});
        REQUIRE(record.descriptor.backend);
        CHECK(record.descriptor.backend->id==provider.provenance().actual->id);
        CHECK(record.descriptor.backend->version==provider.provenance().actual->version);
        REQUIRE(record.descriptor.program);
        CHECK(*record.descriptor.program==direction_program(family,selection_request,index));
        CHECK(record.descriptor.query==index);
        REQUIRE(std::holds_alternative<ar::ReturnedSpan>(record.status));
        CHECK(std::get<ar::ReturnedSpan>(record.status).termination==Termination::completed);
    }
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

TEST_CASE("rejected witness query preserves a published outer candidate claim and identity") {
    auto synthesis=run(request(resolve(source()))); REQUIRE(synthesis.family);
    auto identity=synthesis.family->identity();
    identity.request.target=FamilyTarget::candidate_relaxation;
    const auto relation=std::get<CompleteOptimalFamily>(synthesis.family->outcome()).relation;
    const ClaimEvidence enclosure{identity.problem,SymbolicArgument{
        "T-S01 outer candidate enclosure",
        "The published relation encloses the target optimal relation."}};
    auto family=take(FamilyPublisher::publish(identity,CandidateFamily{
        relation,OuterCandidateEvidence{enclosure},Unestablished{}}));
    const auto source_identity=family.identity();
    const auto query_claim=std::get<OuterCandidateEvidence>(
        std::get<CandidateFamily>(family.outcome()).relation_to_target).enclosure;

    Registry<LPPort> lp;
    auto backend=take(adapters::lp::make_highs_registration());
    auto factory=backend.factory;
    auto lp_creations=std::make_shared<int>(0);
    backend.factory=[factory,lp_creations](const LinearProgram& program) {
        ++*lp_creations;
        return factory(program);
    };
    REQUIRE_FALSE(lp.add(std::move(backend)).has_value());
    Requirements program_output;
    program_output.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(
        lp,Method{{"csl.lp.highs"},{}},program_output)));
    auto selector=synthesis::witness_selector::make_registration(provider);
    auto selector_factory=selector.factory;
    auto selector_creations=std::make_shared<int>(0);
    selector.factory=[selector_factory,selector_creations](const SelectorRequest& request) {
        ++*selector_creations;
        return selector_factory(request);
    };
    REQUIRE_FALSE(selector.identity.id.value.empty());
    Registry<SelectorPort> selectors;
    REQUIRE_FALSE(selectors.add(std::move(selector)).has_value());
    SelectorRequest query{family,{2,0,{{1,-1},{-1,1}},23}};
    Requirements witness_output;
    witness_output.output.representation={"csl.witness-batch.v1"};
    const auto rejected=prepare_pipeline(select(selectors,
        Method{{synthesis::witness_selector::selector_id},{}},query,witness_output));

    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(*selector_creations==0);
    CHECK(*lp_creations==0);
    CHECK(query.family.identity()==source_identity);
    CHECK(query.family.target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(query.family.outcome()));
    const auto& candidate=std::get<CandidateFamily>(query.family.outcome());
    REQUIRE(std::holds_alternative<OuterCandidateEvidence>(candidate.relation_to_target));
    const auto& retained_enclosure=std::get<OuterCandidateEvidence>(candidate.relation_to_target).enclosure;
    CHECK(retained_enclosure.problem==query_claim.problem);
    REQUIRE(std::holds_alternative<SymbolicArgument>(retained_enclosure.support));
    CHECK(std::get<SymbolicArgument>(retained_enclosure.support).reference==
        "T-S01 outer candidate enclosure");
    CHECK(std::get<SymbolicArgument>(retained_enclosure.support).assumptions==
        "The published relation encloses the target optimal relation.");
    CHECK_FALSE(std::holds_alternative<PartialOptimalFamily>(query.family.outcome()));
    CHECK_FALSE(std::holds_alternative<CompleteOptimalFamily>(query.family.outcome()));
}

TEST_CASE("real T-S01 partial family is rejected by selector admission without LP creation or witnesses") {
    auto partial_request=request(resolve(source()));
    partial_request.family.target=FamilyTarget::partial_relation;
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    Requirements strategy_output;
    strategy_output.output.representation=partial_request.family.representation;
    strategy_output.output.family=FamilyTarget::partial_relation;
    strategy_output.output.completeness=Completeness::unestablished;
    auto prepared=take(strategies.prepare(partial_request,strategy_output));
    auto strategy_workspace=prepared.create();
    auto result=take(strategy_workspace->run(make_execution_context()));
    REQUIRE(result.family);
    REQUIRE(result.family->target()==FamilyTarget::partial_relation);
    REQUIRE(std::holds_alternative<PartialOptimalFamily>(result.family->outcome()));
    const auto published_identity=result.family->identity();
    const auto& published_partial=std::get<PartialOptimalFamily>(result.family->outcome());
    const auto published_scope=published_partial.known_scope.description;
    const auto published_procedure=published_partial.optimal_subset.procedure;
    const auto published_midpoint_claim=std::get<SymbolicArgument>(published_partial.optimal_subset.every_history_optimal.support);
    const auto published_optimum_claim=std::get<SymbolicArgument>(published_partial.optimum.optimum.support);
    REQUIRE(published_scope=="s=1/2");
    REQUIRE(published_procedure=="T-S01 exact midpoint singleton");
    REQUIRE(published_midpoint_claim.reference=="T-S01 exact midpoint singleton");
    REQUIRE(published_midpoint_claim.assumptions==
        "At s=1/2, (x0,x1,x2,u0,u1)=(0,1/2,1,1/2,1/2) satisfies both dynamics equations and both control bounds. Its exact objective is (1-1)^2=0, while the objective is nonnegative for every feasible history.");
    REQUIRE(published_optimum_claim.reference=="T-S01 exact midpoint optimality");
    REQUIRE(published_optimum_claim.assumptions==
        "The resolved objective is (x2-1)^2, so it is nonnegative for every feasible history. At the feasible midpoint history x2=1, hence the objective equals zero and the global optimum is zero.");
    CHECK_FALSE(result.family->registry_verified());
    CHECK(result.family->partial_registry_verified());

    auto backend=take(adapters::lp::make_highs_registration());
    auto factory=backend.factory;auto creations=std::make_shared<int>(0);
    backend.factory=[factory,creations](const LinearProgram& p){++*creations;return factory(p);};
    Registry<LPPort> lp;REQUIRE_FALSE(lp.add(std::move(backend)));
    Requirements program_output;program_output.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},program_output)));
    auto selector=synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*result.family,{2,0,{{1,-1},{-1,1}},19}};
    Requirements witness_output;witness_output.output.representation={"csl.witness-batch.v1"};

    Registry<SelectorPort> selectors;REQUIRE_FALSE(selectors.add(selector));
    auto admission_result=prepare_pipeline(select(selectors,Method{{synthesis::witness_selector::selector_id},{}},query,witness_output));
    REQUIRE(std::holds_alternative<Rejection>(admission_result));
    CHECK(std::get<Rejection>(admission_result).diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(*creations==0);

    auto workspace=selector.factory(query);
    auto direct_result=workspace->select(query.family,query.selection,make_execution_context());
    REQUIRE(std::holds_alternative<Unsupported>(direct_result));
    CHECK(std::get<Unsupported>(direct_result).diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(*creations==0);

    auto invalid_evidence=std::get<PartialOptimalFamily>(query.family.outcome());
    invalid_evidence.known_scope.description="";
    const auto invalid_publication=FamilyPublisher::publish(query.family.identity(),invalid_evidence);
    REQUIRE(std::holds_alternative<Diagnostics>(invalid_publication));
    CHECK_FALSE(std::get<Diagnostics>(invalid_publication).empty());

    CHECK(result.family->identity()==published_identity);
    CHECK(result.family->identity().problem==partial_request.problem.identity());
    CHECK(result.family->identity().request.profile=="ts01_exact_integrator");
    CHECK(result.family->identity().request.target==FamilyTarget::partial_relation);
    CHECK(result.family->identity().request.representation==RepresentationId{"csl.polyhedron.h"});
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().strategy==ModuleId{"csl.synthesis.ts01-analytic"});
    CHECK(result.family->identity().strategy_version=="1");
    CHECK(result.family->identity().lineage.empty());
    CHECK(query.family.target()==FamilyTarget::partial_relation);
    CHECK_FALSE(std::holds_alternative<CompleteOptimalFamily>(query.family.outcome()));
    CHECK(result.family->target()==FamilyTarget::partial_relation);
    REQUIRE(std::holds_alternative<PartialOptimalFamily>(result.family->outcome()));
    const auto& unchanged=std::get<PartialOptimalFamily>(result.family->outcome());
    CHECK(unchanged.known_scope.description=="s=1/2");
    CHECK(unchanged.optimal_subset.procedure=="T-S01 exact midpoint singleton");
    CHECK(std::get<SymbolicArgument>(unchanged.optimal_subset.every_history_optimal.support).reference==
        "T-S01 exact midpoint singleton");
    CHECK(std::get<SymbolicArgument>(unchanged.optimal_subset.every_history_optimal.support).assumptions==
        "At s=1/2, (x0,x1,x2,u0,u1)=(0,1/2,1,1/2,1/2) satisfies both dynamics equations and both control bounds. Its exact objective is (1-1)^2=0, while the objective is nonnegative for every feasible history.");
    CHECK(std::get<SymbolicArgument>(unchanged.optimum.optimum.support).reference==
        "T-S01 exact midpoint optimality");
    CHECK(std::get<SymbolicArgument>(unchanged.optimum.optimum.support).assumptions==
        "The resolved objective is (x2-1)^2, so it is nonnegative for every feasible history. At the feasible midpoint history x2=1, hence the objective equals zero and the global optimum is zero.");
    REQUIRE(unchanged.optimum.bounds.lower);
    REQUIRE(unchanged.optimum.bounds.upper);
    CHECK(unchanged.optimum.bounds.lower->value==0);
    CHECK(unchanged.optimum.bounds.upper->value==0);
    CHECK_FALSE(result.family->registry_verified());
    CHECK(result.family->partial_registry_verified());
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
class CorruptNominalWitnessWorkspace final : public LPWorkspace {
    std::unique_ptr<LPWorkspace> inner_;
    Vector primal_;
protected:
    ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext& context) override {
        auto result=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&result);
           solved&&solved->termination==Termination::completed&&solved->outcome.value==MathematicalOutcome::optimal)
            solved->primal=primal_;
        return result;
    }
public:
    CorruptNominalWitnessWorkspace(std::unique_ptr<LPWorkspace> inner,Vector primal)
        :inner_(std::move(inner)),primal_(std::move(primal)){}
};
}

TEST_CASE("multiple selector requests from a singleton retain duplicate and optimum evidence") {
    Problem authored;
    authored.id = {"selector-singleton-nominal-linear-exact"};
    authored.model = std::make_shared<const SystemModel>(SystemModel{{{1, 1, 0},
        TimeDomain::discrete, std::vector<LinearStage>{
            {{1, 1, {-1}}, {1, 1, {1}}, {1, 0, {}}, {0.25}},
            {{1, 1, {2}}, {1, 1, {0}}, {1, 0, {}}, {-0.5}}}}, {}});
    authored.times = {0, 1, 2};
    authored.initial = KnownInitial{{0.5}};
    authored.controls = ContinuousDomain{{interval("selector-singleton-u0", 0, 1),
        interval("selector-singleton-u1", 0, 0)}};
    authored.states = {interval("selector-singleton-x0", 0.5, 0.5),
        interval("selector-singleton-x1", 0, 1), UniversalSet{1}};
    authored.information = InformationPattern::nominal_open_loop;
    authored.objective = LinearTerminal{{1}, 0};
    const auto resolved = resolve(std::move(authored));
    auto synthesis_request = request(resolved);
    synthesis_request.family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    synthesis_request.configuration.strategy = {"csl.synthesis.reach-back"};
    synthesis_request.configuration.lp = {"csl.lp.highs"};
    synthesis_request.configuration.convex = {"csl.convex.highs"};
    auto prepared = strategy_a(synthesis_request);
    auto workspace = prepared.create();
    auto synthesized = take(workspace->run(make_execution_context()));
    REQUIRE(synthesized.family);
    REQUIRE(synthesized.family->registry_verified());
    CHECK(synthesized.outcome.value == MathematicalOutcome::optimal);
    REQUIRE(synthesized.objective.lower);
    REQUIRE(synthesized.objective.upper);
    const auto primary_identity = synthesized.family->identity();
    const auto primary_objective = synthesized.objective.lower->value;
    CHECK(primary_objective == doctest::Approx(-0.5));

    Registry<LPPort> lp;
    REQUIRE_FALSE(lp.add(take(adapters::lp::make_highs_registration())));
    Requirements program;
    program.output.representation = {"csl.program-result.v1"};
    auto provider = take(prepare_provider(select_provider(lp, Method{{"csl.lp.highs"}, {}}, program)));
    auto selector = synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*synthesized.family, {2, 1e-9, {{1, -1}, {-1, 1}}, 103}};
    auto selection = selector.factory(query);
    auto answer = take(SelectorPort::run(*selection, query, make_execution_context()));

    CHECK(answer.termination == Termination::completed);
    CHECK(answer.batch.requested == 2);
    CHECK(answer.batch.returned_count() == 2);
    CHECK(answer.batch.distinct_count() == 1);
    CHECK(answer.batch.source_family == primary_identity);
    CHECK(answer.batch.seed == 103);
    CHECK(answer.diagnostics.find("shortfall") != std::string::npos);
    for (const auto& witness : answer.batch.witnesses) {
        CHECK(witness.controls == std::vector<Vector>{{0.25}, {0}});
        CHECK(witness.states == std::vector<Vector>{{0.5}, {0}, {-0.5}});
        CHECK(witness.states[1][0] == doctest::Approx(-witness.states[0][0] + witness.controls[0][0] + 0.25));
        CHECK(witness.states[2][0] == doctest::Approx(2 * witness.states[1][0] - 0.5));
        CHECK(witness.states[1][0] >= -1e-9);
        CHECK(witness.states[1][0] <= 1.0 + 1e-9);
        CHECK(witness.original_objective == doctest::Approx(-0.5));
    }
    CHECK(synthesized.family->identity() == primary_identity);
    CHECK(synthesized.objective.lower->value == primary_objective);

    auto corrupt_backend=take(adapters::lp::make_highs_registration());
    auto factory=corrupt_backend.factory;
    const Vector nonfinite_primal{0.5, 0, -0.5, 0.25, std::numeric_limits<double>::quiet_NaN()};
    corrupt_backend.factory=[factory,nonfinite_primal](const LinearProgram& program) {
        return std::make_unique<CorruptNominalWitnessWorkspace>(factory(program),nonfinite_primal);
    };
    Registry<LPPort> corrupt_lp;
    REQUIRE_FALSE(corrupt_lp.add(std::move(corrupt_backend)));
    auto corrupt_provider=take(prepare_provider(select_provider(corrupt_lp,
        Method{{"csl.lp.highs"},{}},program)));
    auto corrupt_selector=synthesis::witness_selector::make_registration(corrupt_provider);
    auto corrupt_workspace=corrupt_selector.factory(query);
    auto corrupt_answer=take(SelectorPort::run(*corrupt_workspace,query,make_execution_context()));
    CHECK(corrupt_answer.termination==Termination::numerical_failure);
    CHECK(corrupt_answer.batch.returned_count()==0);
    CHECK(corrupt_answer.batch.source_family==primary_identity);
    CHECK(corrupt_answer.diagnostics.find("consistent")!=std::string::npos);
    CHECK(synthesized.family->identity()==primary_identity);
    CHECK(synthesized.objective.lower->value==primary_objective);
}


namespace {
class CorruptT02PrimalWorkspace final : public LPWorkspace {
    std::unique_ptr<LPWorkspace> inner_;
protected:
    ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext& context) override {
        auto result=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&result);solved&&solved->termination==Termination::completed&&
           solved->outcome.value==MathematicalOutcome::optimal)
            solved->primal=Vector{0,0,0,0,1};
        return result;
    }
public:
    explicit CorruptT02PrimalWorkspace(std::unique_ptr<LPWorkspace> inner):inner_(std::move(inner)){}
};
}
TEST_CASE("T-S02 selector rejects a backend primal outside the exact family despite loose query tolerance") {
    auto problem=source();set_quadratic_objective(problem,0,0,3);
    auto synthesis_request=request(resolve(std::move(problem)));
    synthesis_request.family.profile="ts02_constant_integrator";
    synthesis_request.configuration.strategy={"csl.synthesis.reach-back"};
    synthesis_request.configuration.lp={"csl.lp.highs"};
    auto prepared=strategy_a(synthesis_request);
    auto synthesis_workspace=prepared.create();auto synthesized=take(synthesis_workspace->run(make_execution_context()));
    REQUIRE(synthesized.family);

    auto backend=take(adapters::lp::make_highs_registration());
    auto factory=backend.factory;
    backend.factory=[factory](const LinearProgram& program) {
        return std::make_unique<CorruptT02PrimalWorkspace>(factory(program));
    };
    Registry<LPPort> lp;REQUIRE_FALSE(lp.add(std::move(backend)));
    Requirements program_output;program_output.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},program_output)));
    auto selector=synthesis::witness_selector::make_registration(provider);
    SelectorRequest query{*synthesized.family,{1,0,{{1,-1}},73}};
    auto workspace=selector.factory(query);auto context=make_execution_context();
    context.numerical.absolute_tolerance=1;context.numerical.relative_tolerance=0;
    auto answer=take(SelectorPort::run(*workspace,query,context));

    CHECK(answer.termination==Termination::numerical_failure);
    CHECK(answer.batch.returned_count()==0);
    CHECK(answer.batch.source_family==synthesized.family->identity());
    CHECK(answer.diagnostics.find("consistent")!=std::string::npos);
    CHECK(synthesized.family->target()==FamilyTarget::exact_optimal_relation);
}
TEST_CASE("one selector queries the verified constant-objective family from both strategies") {
    Registry<LPPort> lp;REQUIRE_FALSE(lp.add(take(adapters::lp::make_highs_registration())));
    Registry<ConvexPort> convex;REQUIRE_FALSE(convex.add(take(adapters::convex::make_highs_registration())));
    Requirements program;program.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},program)));
    auto selector=synthesis::witness_selector::make_registration(provider);
    for(const bool use_a:{true,false}) {
        auto problem=source();set_quadratic_objective(problem,0,0,3);
        auto synthesis_request=request(resolve(std::move(problem)));
        synthesis_request.family.profile="ts02_constant_integrator";
        synthesis_request.configuration.strategy={use_a?"csl.synthesis.reach-back":"csl.synthesis.strategy-b"};
        synthesis_request.configuration.lp={"csl.lp.highs"};
        synthesis_request.configuration.convex={"csl.convex.highs"};
        auto prepared=[&]() {
            if(use_a)return strategy_a(synthesis_request);
            StrategyRegistry registry;REQUIRE_FALSE(registry.add(synthesis::strategy_b::make_registration(lp,convex)));
            Requirements output;output.output.representation=synthesis_request.family.representation;
            output.output.family=synthesis_request.family.target;output.output.completeness=Completeness::established;
            return take(registry.prepare(synthesis_request,output));
        }();
        auto synthesis_workspace=prepared.create();auto result=take(synthesis_workspace->run(make_execution_context()));
        REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
        const auto family_identity=result.family->identity();
        SelectorRequest query{*result.family,{2,0,{{1,-1},{-1,1}},47}};
        auto workspace=selector.factory(query);
        auto answer=take(SelectorPort::run(*workspace,query,make_execution_context()));
        REQUIRE(answer.termination==Termination::completed);
        CHECK(answer.batch.requested==2);REQUIRE(answer.batch.returned_count()==2);CHECK(answer.batch.distinct_count()==2);
        CHECK(answer.batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});
        CHECK(answer.batch.witnesses[1].controls==std::vector<Vector>{{1},{0}});
        CHECK(answer.batch.witnesses[0].states==std::vector<Vector>{{0},{0},{1}});
        CHECK(answer.batch.witnesses[1].states==std::vector<Vector>{{0},{1},{1}});
        CHECK(answer.batch.witnesses[0].original_objective==3);
        CHECK(answer.batch.witnesses[1].original_objective==3);
        CHECK(answer.batch.source_family==family_identity);
        CHECK(result.family->identity()==family_identity);
        CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
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
        if(++*calls_==2) {
            if(c.deadline)std::this_thread::sleep_until(*c.deadline);
            return ProgramResult{Termination::resource_limit,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},"provider capacity exhausted",{}};
        }
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
        context.deadline=std::chrono::steady_clock::now()+std::chrono::seconds(1);
        auto selected=take(workspace->select(query.family,query.selection,context));
        CHECK(selected.termination==(deadline?Termination::cancelled:Termination::resource_limit));
        CHECK(selected.diagnostics.find(deadline?"deadline":"capacity")!=std::string::npos);
        REQUIRE(selected.batch.returned_count()==1);CHECK(selected.batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});
        CHECK(selected.batch.source_family==query.family.identity());
    }
}

namespace {
class ArmAllocationFailure final : public LPWorkspace {
    std::unique_ptr<LPWorkspace> inner_;std::size_t nth_;
protected:
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override {
        auto result=inner_->solve(p,c);selector_allocation_probe::fail_small_allocation=nth_;return result;
    }
public:
    ArmAllocationFailure(std::unique_ptr<LPWorkspace> inner,std::size_t nth):inner_(std::move(inner)),nth_(nth){}
};
}
TEST_CASE("post-solve allocation failure returns a resource stop and retains collected observations") {
    auto synthesis=run(request(resolve(source())));REQUIRE(synthesis.family);bool retained_failure=false;
    // Probe allocation positions rather than assuming an STL allocation sequence.
    for(std::size_t nth=1;nth<=32;++nth) {
        auto backend=take(adapters::lp::make_highs_registration());auto factory=backend.factory;
        backend.factory=[factory,nth](const LinearProgram& p){return std::make_unique<ArmAllocationFailure>(factory(p),nth);};
        Registry<LPPort> lp;REQUIRE_FALSE(lp.add(std::move(backend)));Requirements req;req.output.representation={"csl.program-result.v1"};
        auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
        auto registration=synthesis::witness_selector::make_registration(provider);SelectorRequest query{*synthesis.family,{1,0,{{1,-1}},0}};
        auto workspace=registration.factory(query);selector_allocation_probe::injected=false;
        std::optional<WitnessSelection> selected;bool escaped=false;
        try {selected=std::get<WitnessSelection>(workspace->select(query.family,query.selection,make_execution_context()));}
        catch(const std::bad_alloc&){escaped=true;}
        selector_allocation_probe::fail_small_allocation=0;
        CHECK_FALSE(escaped);
        if(selected&&selector_allocation_probe::injected) {
            CHECK(selected->termination==Termination::resource_limit);
            if(selected->batch.returned_count()==1) {
                retained_failure=true;CHECK(selected->batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});
                CHECK(selected->batch.source_family==query.family.identity());
            }
        }
    }
    CHECK(retained_failure);
}
