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
    return {std::move(p),configuration,std::move(family),{}};
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
bool rejected(Problem p) {
    auto request_=request(resolve(std::move(p)));
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    Requirements requirements;requirements.output.representation=request_.family.representation;
    requirements.output.family=request_.family.target;
    requirements.output.completeness=Completeness::established;
    return std::holds_alternative<Rejection>(strategies.prepare(request_,requirements));
}
class GenericProposalWorkspace final:public SynthesisWorkspace {
    ModuleId verifier_;std::string version_,proof_verifier_,proof_version_;
public:
    GenericProposalWorkspace(ModuleId verifier,std::string version,std::string proof_verifier,std::string proof_version)
        :verifier_(std::move(verifier)),version_(std::move(version)),proof_verifier_(std::move(proof_verifier)),proof_version_(std::move(proof_version)){}
    SynthesisResult solve(const problem::ResolvedProblem& problem,const FamilyRequest& family,const ExecutionContext&) override {
        FamilyIdentity identity{problem.identity(),family,problem.constraints().coordinates(),verifier_,version_,{}};
        JointRelation relation{identity.coordinates,family.representation,std::make_shared<const JointRelationPayload>()};
        const ClaimEvidence claim{identity.problem,SymbolicArgument{"fixture theorem","second registered verifier"}};
        OptimumEvidence optimum{claim,{}};
        CompleteOptimalFamily complete{relation,optimum,
            {identity,RegisteredCompletenessEvidence{{proof_verifier_},proof_version_,"second-verifier-proof"}},Assurance::numerical};
        SynthesisResult result{Termination::completed,
            {problem.identity(),MathematicalOutcome::optimal,claim.support,{}},{},{},{},{},{},{}};
        result.complete_proposal=CompleteFamilyProposal{identity,std::move(complete)};
        return result;
    }
};
StrategyRegistration second_verifier_registration(std::string proof_id="test.verifier.second",std::string proof_version="7") {
    const ModuleId id{"test.verifier.second"};const std::string version="7";
    return {{id,version},
        [](const StrategyRequest&,const Requirements&)->Capability {
            Output output;output.representation={"csl.polyhedron.h"};output.assurance=Assurance::numerical;
            output.family=FamilyTarget::exact_optimal_relation;output.completeness=Completeness::established;
            return Offer{output};
        },
        [proof_id=std::move(proof_id),proof_version=std::move(proof_version)](const StrategyRequest&,const Requirements&)->std::variant<StrategyPlan,Rejection> {
            auto checked=std::get<CheckedPipeline<>>(check_pipeline());
            return compose_strategy(std::move(checked),[proof_id,proof_version](auto,const StrategyRequest& request,const Requirements&) {
                return std::make_unique<GenericProposalWorkspace>(request.configuration.strategy,request.strategy_version,proof_id,proof_version);
            });
        },
        [](const StrategyRequest& request,const CompleteFamilyProposal& proposal)->Diagnostics {
            const auto* evidence=std::get_if<RegisteredCompletenessEvidence>(&proposal.family.completeness.support);
            if(proposal.identity.problem!=request.problem.identity()||proposal.identity.request!=request.family||!evidence||
                evidence->verifier!=request.configuration.strategy||evidence->verifier_version!=request.strategy_version||
                evidence->proof!="second-verifier-proof")
                return {{DiagnosticCode::evidence_mismatch,"second.verifier","Second verifier rejected its proof payload or binding"}};
            return {};
        }};
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

TEST_CASE("compiled verifier selection supports a second registered verifier and freezes it at prepare") {
    auto registration=second_verifier_registration();
    StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(registration).has_value());
    auto request_=request(resolve(source()));request_.configuration.strategy=registration.identity.id;
    request_.family.profile="second-verifier-profile";
    Requirements requirements;requirements.output.representation=request_.family.representation;
    requirements.output.family=request_.family.target;requirements.output.completeness=Completeness::established;
    auto prepared=take(strategies.prepare(request_,requirements));
    registration.complete_family_verifier=[](const StrategyRequest&,const CompleteFamilyProposal&){
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"mutated.verifier","must not replace selected verifier"}};
    };
    auto result=take(prepared.create()->run(make_execution_context()));
    REQUIRE(result.family);
    CHECK(result.family->identity().strategy==ModuleId{"test.verifier.second"});
    CHECK(result.family->identity().strategy_version=="7");
}

TEST_CASE("registry rejects unknown verifier identity and version in opaque proposal") {
    for(const auto& bad:std::vector<std::pair<std::string,std::string>>{{"unknown.verifier","7"},{"test.verifier.second","8"}}) {
        auto registration=second_verifier_registration(bad.first,bad.second);
        StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(std::move(registration)).has_value());
        auto request_=request(resolve(source()));request_.configuration.strategy={"test.verifier.second"};
        request_.family.profile="second-verifier-profile";
        Requirements requirements;requirements.output.representation=request_.family.representation;
        requirements.output.family=request_.family.target;requirements.output.completeness=Completeness::established;
        auto prepared=take(strategies.prepare(request_,requirements));
        const auto result=take(prepared.create()->run(make_execution_context()));
        CHECK(result.termination==Termination::contract_rejected);
        CHECK_FALSE(result.family);
    }
}

TEST_CASE("registry rejects replacement of an already registered T-S01 identity") {
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    CHECK(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
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

TEST_CASE("compiled T-S01 verifier rejects independent proposal relation optimum bounds identity and lineage tampering") {
    auto original_request=request(resolve(source()));
    const auto result=run(original_request);
    REQUIRE(result.family);
    const auto registration=synthesis::strategy_ts01::make_registration();
    const auto original=CompleteFamilyProposal{result.family->identity(),
        std::get<CompleteOptimalFamily>(result.family->outcome())};
    auto rejected_by_checker=[&](auto mutate) {
        auto proposal=original;mutate(proposal);
        CHECK_FALSE(registration.complete_family_verifier(original_request,proposal).empty());
    };
    rejected_by_checker([](auto& proposal){
        proposal.family.relation.payload=std::make_shared<const JointRelationPayload>();
    });
    rejected_by_checker([](auto& proposal){
        proposal.family.optimum.optimum.support=SymbolicArgument{"forged","changed theorem"};
    });
    rejected_by_checker([](auto& proposal){
        proposal.family.optimum.bounds.lower->value=-1;
    });
    rejected_by_checker([](auto& proposal){
        proposal.family.optimum.bounds.upper->value=1;
    });
    rejected_by_checker([](auto& proposal){
        proposal.identity.request.profile="different";proposal.family.completeness.binding=proposal.identity;
    });
    rejected_by_checker([](auto& proposal){
        proposal.identity.lineage.push_back({{"transform"},{"input"},{"output"},{"module"},"1"});
        proposal.family.completeness.binding=proposal.identity;
    });
    rejected_by_checker([](auto& proposal){
        auto& proof=std::get<RegisteredCompletenessEvidence>(proposal.family.completeness.support);
        proof.verifier={"unknown.verifier"};
    });
    rejected_by_checker([](auto& proposal){
        auto& proof=std::get<RegisteredCompletenessEvidence>(proposal.family.completeness.support);
        proof.verifier_version="2";
    });
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
        std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence>{
            NumericalCoverageEvidence{"always-pass",{0,0},{"verifier"},"residual below invented tolerance"}},
        std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence>{
            ValidatedCoverageEvidence{"artifact:unverified",ModuleId{"checker:unregistered"},"exact-looking"}}}) {
        const auto completeness_support=std::holds_alternative<NumericalCoverageEvidence>(support)?
            std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence,RegisteredCompletenessEvidence>{std::get<NumericalCoverageEvidence>(support)}:
            std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence,RegisteredCompletenessEvidence>{std::get<ValidatedCoverageEvidence>(support)};
        CompleteOptimalFamily untrusted{{complete.relation.coordinates,identity.request.representation,fake},
            {{identity.problem,arbitrary},{}},{identity,completeness_support},Assurance::numerical};
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
