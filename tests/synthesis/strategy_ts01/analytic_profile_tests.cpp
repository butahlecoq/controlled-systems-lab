#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/validator.hpp>
#include <csl/sets/data.hpp>
#include "compiled_verifiers.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>

using namespace csl;
using namespace csl::registry;
static_assert(!std::is_assignable_v<decltype(StrategyRegistration::complete_family_verifier)&,std::function<Diagnostics(const StrategyRequest&,const CompleteFamilyProposal&)>>,
    "Installed strategy registrations must not accept executable verifier callbacks");
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
    requirements.output.completeness=request_.family.target==FamilyTarget::exact_optimal_relation?
        Completeness::established:Completeness::unestablished;
    auto prepared=take(strategies.prepare(request_,requirements));
    auto workspace=prepared.create();
    return take(workspace->run(make_execution_context()));
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

TEST_CASE("registered T-S01 admits an explicitly scoped partial-family request") {
    auto partial=request(resolve(source()));
    partial.family.target=FamilyTarget::partial_relation;
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    Requirements requirements;
    requirements.output.representation=partial.family.representation;
    requirements.output.family=FamilyTarget::partial_relation;
    requirements.output.completeness=Completeness::unestablished;
    auto prepared_result=strategies.prepare(partial,requirements);
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared_result));
    auto prepared=std::get<PreparedStrategy>(std::move(prepared_result));
    auto workspace=prepared.create();
    auto outcome=workspace->run(make_execution_context());
    REQUIRE(std::holds_alternative<SynthesisResult>(outcome));
    const auto result=std::get<SynthesisResult>(std::move(outcome));
    REQUIRE(result.termination==Termination::completed);
    REQUIRE(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::partial_relation);
    CHECK_FALSE(result.family->registry_verified());
    CHECK(result.family->partial_registry_verified());
    CHECK_FALSE(result.partial_proposal);
    CHECK(result.family->identity().problem==partial.problem.identity());
    CHECK(result.family->identity().request==partial.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().strategy==ModuleId{"csl.synthesis.ts01-analytic"});
    CHECK(result.family->identity().strategy_version=="1");
    CHECK(result.family->identity().lineage.empty());
    const auto& family=std::get<PartialOptimalFamily>(result.family->outcome());
    CHECK(family.known_scope.description=="s=1/2");
    CHECK(family.optimal_subset.procedure=="T-S01 exact midpoint singleton");
    REQUIRE(family.optimum.bounds.lower);
    REQUIRE(family.optimum.bounds.upper);
    CHECK(family.optimum.bounds.lower->value==0);
    CHECK(family.optimum.bounds.upper->value==0);
    const auto* relation=dynamic_cast<const synthesis::strategy_ts01::MidpointJointRelation*>(family.relation.payload.get());
    REQUIRE(relation);
    const auto h=relation->h_polyhedron().representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(h));
    const auto& singleton=std::get<sets::HRepresentation>(h);
    CHECK(singleton.inequalities.rows()==0);
    CHECK(singleton.equalities.rows()==5);
    CHECK(std::holds_alternative<numeric::CsrInput>(singleton.inequalities.descriptor()));
    CHECK(std::holds_alternative<numeric::CsrInput>(singleton.equalities.descriptor()));
    const auto empty_csr=std::get<numeric::CsrInput>(singleton.inequalities.descriptor());
    CHECK(empty_csr.row_offsets.size()==1);
    CHECK(empty_csr.row_offsets[0]==0);
    CHECK(singleton.equality_values[1]==0.5);
    CHECK(singleton.equality_values[2]==1);
    CHECK(singleton.equality_values[3]==0.5);
    CHECK(singleton.equality_values[4]==0.5);
    CHECK(check_synthesis_result(result,result.family->identity()).empty());
    CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(result.family->identity(),family)));
}

TEST_CASE("T-S01 partial verifier rejects changed objective request lineage and singleton proof") {
    auto partial=request(resolve(source()));
    partial.family.target=FamilyTarget::partial_relation;
    partial.strategy_version="1";
    const auto result=run(partial);
    REQUIRE(result.family);
    const PartialFamilyProposal proposal{result.family->identity(),
        std::get<PartialOptimalFamily>(result.family->outcome())};
    const auto verifier=detail::find_compiled_partial_verifier({"csl.verifier.ts01-midpoint"},"1");
    REQUIRE(verifier);
    CHECK(verifier->verify(partial,proposal).empty());

    auto changed=partial;
    changed.family.profile="different-profile";
    CHECK_FALSE(verifier->verify(changed,proposal).empty());

    auto changed_objective_problem=source();
    set_quadratic_objective(changed_objective_problem,2,-2,2);
    changed=partial;
    changed.problem=resolve(std::move(changed_objective_problem));
    changed.family.objective=changed.problem.identity();
    CHECK_FALSE(verifier->verify(changed,proposal).empty());

    changed=partial;
    changed.configuration.strategy={"csl.synthesis.unregistered"};
    CHECK_FALSE(verifier->verify(changed,proposal).empty());

    changed=partial;
    changed.lineage.push_back({{"forged/step"},{"input"},{"output"},{"untrusted"},"1"});
    CHECK_FALSE(verifier->verify(changed,proposal).empty());

    auto forged=proposal;
    forged.family.relation.payload=std::make_shared<const JointRelationPayload>();
    CHECK_FALSE(verifier->verify(partial,forged).empty());

    forged=proposal;
    forged.family.known_scope.description="s in [0,1]";
    CHECK_FALSE(verifier->verify(partial,forged).empty());

    forged=proposal;
    forged.family.optimal_subset.every_history_optimal.support=NumericalCheck{0,0,0,{"fake.residual"}};
    CHECK_FALSE(verifier->verify(partial,forged).empty());
}

TEST_CASE("registry rejects ambiguous simultaneous complete and partial proposals") {
    class AmbiguousWorkspace final : public SynthesisWorkspace {
        SynthesisResult result_;
    public:
        explicit AmbiguousWorkspace(SynthesisResult result):result_(std::move(result)) {}
        SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override {
            return result_;
        }
    };
    auto partial=request(resolve(source()));
    partial.family.target=FamilyTarget::partial_relation;
    partial.strategy_version="1";
    auto genuine_partial=run(partial);
    REQUIRE(genuine_partial.family);
    auto complete_request=request(resolve(source()));
    complete_request.strategy_version="1";
    auto genuine_complete=run(complete_request);
    REQUIRE(genuine_complete.family);
    const auto& complete=std::get<CompleteOptimalFamily>(genuine_complete.family->outcome());
    SynthesisResult ambiguous=genuine_partial;
    ambiguous.complete_proposal=CompleteFamilyProposal{genuine_complete.family->identity(),complete};
    ambiguous.partial_proposal=PartialFamilyProposal{genuine_partial.family->identity(),
        std::get<PartialOptimalFamily>(genuine_partial.family->outcome())};

    auto registration=synthesis::strategy_ts01::make_registration();
    registration.planner=[ambiguous=std::move(ambiguous)](const StrategyRequest&,const Requirements&)
        ->std::variant<StrategyPlan,Rejection> {
        auto fixed=std::get<CheckedPipeline<>>(check_pipeline());
        return compose_strategy(std::move(fixed),[ambiguous](auto,const StrategyRequest&,const Requirements&)
            ->std::unique_ptr<SynthesisWorkspace> {
            return std::make_unique<AmbiguousWorkspace>(ambiguous);
        });
    };
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(std::move(registration)).has_value());
    Requirements requirements;requirements.output.representation=partial.family.representation;
    requirements.output.family=partial.family.target;requirements.output.completeness=Completeness::unestablished;
    auto prepared=take(strategies.prepare(partial,requirements));
    auto workspace=prepared.create();
    const auto result=take(workspace->run(make_execution_context()));
    CHECK(result.termination==Termination::contract_rejected);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    const auto& diagnostics=std::get<ContractValidationFailure>(result.stop).diagnostics;
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& diagnostic) {
        return diagnostic.field=="family.proposal.ambiguous";
    }));
}

TEST_CASE("registry fails closed for verifier keys absent from the compiled catalog") {
    for(const auto& version:std::vector<std::string>{"1","2"}) {
        auto registration=synthesis::strategy_ts01::make_registration();
        registration.complete_family_verifier={ModuleId{"unknown.compiled.verifier"},version};
        StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(std::move(registration)).has_value());
        auto request_=request(resolve(source()));
        Requirements requirements;requirements.output.representation=request_.family.representation;
        requirements.output.family=request_.family.target;requirements.output.completeness=Completeness::established;
        CHECK(std::holds_alternative<Rejection>(strategies.prepare(request_,requirements)));
    }
}

TEST_CASE("T-S01 admission rejects objective, dynamics, controls, initial and temporal mutations") {
    auto p=source();p.objective.emplace<ResidualNormTerminal>();
    auto& residual=std::get<ResidualNormTerminal>(p.objective);
    residual.map.rows=1;residual.map.cols=1;residual.map.values=Vector{1};residual.target=Vector{1};
    CHECK(rejected(p));
    p=source();set_quadratic_objective(p,1,-2,1);
    CHECK(rejected(p));
    p=source();set_quadratic_objective(p,2,-2,0);
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

TEST_CASE("compiled T-S01 verifier rejects independently tampered proposal claims") {
    auto original_request=request(resolve(source()));
    original_request.strategy_version="1";
    const auto result=run(original_request);
    REQUIRE(result.family);
    const auto verifier=detail::find_compiled_verifier({"csl.verifier.ts01-analytic"},"1");
    REQUIRE(verifier);
    const CompleteFamilyProposal original{result.family->identity(),
        std::get<CompleteOptimalFamily>(result.family->outcome())};
    CHECK(verifier->verify(original_request,original).empty());
    auto rejects_with=[&](auto mutate,const std::string& expected_field) {
        auto proposal=original;mutate(proposal);
        const auto diagnostics=verifier->verify(original_request,proposal);
        REQUIRE_FALSE(diagnostics.empty());
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[&](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch&&diagnostic.field==expected_field;
        }));
    };
    rejects_with([](auto& proposal){proposal.family.relation.payload=std::make_shared<const JointRelationPayload>();},"ts01.verifier.relation");
    rejects_with([](auto& proposal){proposal.family.optimum.optimum.support=Unestablished{};},"ts01.verifier.optimum");
    rejects_with([](auto& proposal){proposal.family.optimum.optimum.support=CertificateReference{"artifact:unchecked-optimum","unregistered.checker"};},"ts01.verifier.optimum");
    rejects_with([](auto& proposal){proposal.family.optimum.optimum.support=NumericalCheck{1e-8,1e-8,0,ModuleId{"unregistered.residual-checker"}};},"ts01.verifier.optimum");
    rejects_with([](auto& proposal){proposal.family.optimum.optimum.support=SymbolicArgument{"forged","changed theorem"};},"ts01.verifier.optimum");
    rejects_with([](auto& proposal){proposal.family.optimum.bounds.lower->value=-1;},"ts01.verifier.optimum");
    rejects_with([](auto& proposal){proposal.family.optimum.bounds.upper->value=1;},"ts01.verifier.optimum");
    rejects_with([](auto& proposal){proposal.identity.request.profile="different";proposal.family.completeness.binding=proposal.identity;},"ts01.verifier.binding");
    rejects_with([](auto& proposal){proposal.identity.coordinates.horizon=3;proposal.family.completeness.binding=proposal.identity;},"ts01.verifier.binding");
    rejects_with([](auto& proposal){proposal.identity.lineage.push_back({{"transform"},{"input"},{"output"},{"module"},"1"});proposal.family.completeness.binding=proposal.identity;},"ts01.verifier.binding");
    rejects_with([](auto& proposal){std::get<RegisteredCompletenessEvidence>(proposal.family.completeness.support).verifier={"unknown"};},"ts01.verifier.support");
    rejects_with([](auto& proposal){std::get<RegisteredCompletenessEvidence>(proposal.family.completeness.support).verifier_version="2";},"ts01.verifier.support");
    rejects_with([](auto& proposal){proposal.family.completeness.support=ValidatedCoverageEvidence{"artifact:unchecked",ModuleId{"unregistered.checker"},"exact-looking"};},"ts01.verifier.support");
    rejects_with([](auto& proposal){proposal.family.completeness.support=NumericalCoverageEvidence{"residual-only",{1e-8,1e-8},ModuleId{"unregistered.residual-checker"},"residual below tolerance"};},"ts01.verifier.support");
    auto changed_request=original_request;changed_request.family.profile="tampered";
    CHECK_FALSE(verifier->verify(changed_request,original).empty());
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
    for(const auto& support:std::vector<CompletenessSupport>{
        NumericalCoverageEvidence{"always-pass",{0,0},{"verifier"},"residual below invented tolerance"},
        ValidatedCoverageEvidence{"artifact:unverified",ModuleId{"checker:unregistered"},"exact-looking"}}) {
        CompleteOptimalFamily untrusted{{complete.relation.coordinates,identity.request.representation,fake},
            {{identity.problem,arbitrary},{}},{identity,support},Assurance::numerical};
        CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,std::move(untrusted))));
    }
}

TEST_CASE("republication cannot alter the optimum claim or either bound") {
    const auto result=run(request(resolve(source())));
    REQUIRE(result.family);
    const auto original=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto identity=result.family->identity();

    auto changed_claim=original;
    changed_claim.optimum.optimum.support=SymbolicArgument{"forged optimum","different theorem"};
    CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,changed_claim)));

    auto changed_lower=original;
    REQUIRE(changed_lower.optimum.bounds.lower);
    changed_lower.optimum.bounds.lower->value=-1;
    CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,changed_lower)));

    auto changed_upper=original;
    REQUIRE(changed_upper.optimum.bounds.upper);
    changed_upper.optimum.bounds.upper->value=1;
    CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,changed_upper)));

    auto changed_bound_evidence=original;
    REQUIRE(changed_bound_evidence.optimum.bounds.lower);
    changed_bound_evidence.optimum.bounds.lower->evidence.support=SymbolicArgument{"forged bound","different theorem"};
    CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,changed_bound_evidence)));
}

TEST_CASE("result boundary keeps its outcome and bounds aligned with sealed family evidence") {
    auto original=run(request(resolve(source())));
    REQUIRE(original.family);
    const auto identity=original.family->identity();
    CHECK(check_synthesis_result(original,identity).empty());

    auto changed_claim=original;
    changed_claim.outcome.support=SymbolicArgument{"forged top-level outcome","not the family theorem"};
    CHECK_FALSE(check_synthesis_result(changed_claim,identity).empty());

    auto changed_lower=original;
    REQUIRE(changed_lower.objective.lower);
    changed_lower.objective.lower->value=-1;
    CHECK_FALSE(check_synthesis_result(changed_lower,identity).empty());

    auto changed_upper=original;
    REQUIRE(changed_upper.objective.upper);
    changed_upper.objective.upper->value=1;
    CHECK_FALSE(check_synthesis_result(changed_upper,identity).empty());
}
