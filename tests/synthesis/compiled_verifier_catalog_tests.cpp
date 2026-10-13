#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/problem/validator.hpp>
#include <csl/registry/registry.hpp>

using namespace csl;
using namespace csl::registry;
namespace {
problem::ResolvedProblem resolved_problem() {
    const Matrix a{1,1,Vector{1}};
    const Matrix b{1,1,Vector{1}};
    const Matrix e{1,0,Vector{}};
    const Vector offset{0};
    const LinearStage transition{a,b,e,offset};
    const auto model=std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,transition},{}});
    Problem source;source.id={"compiled-verifier-test"};source.model=model;source.times={0,1,2};
    source.initial=KnownInitial{{0}};source.controls=ContinuousDomain{{UniversalSet{1},UniversalSet{1}}};
    source.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    source.information=InformationPattern::nominal_open_loop;
    source.objective=LinearTerminal{{0},0};
    auto result=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(result));
    return std::get<problem::ResolvedProblem>(std::move(result));
}
FamilyRequest family_request(const problem::ResolvedProblem& problem) {
    FamilyRequest request;request.profile="test-second-verifier";request.objective=problem.identity();
    request.target=FamilyTarget::exact_optimal_relation;request.assurance=Assurance::numerical;
    request.representation={"test.relation"};return request;
}
class SecondVerifierWorkspace final:public SynthesisWorkspace {
public:
    SynthesisResult solve(const problem::ResolvedProblem& problem,const FamilyRequest& request,const ExecutionContext&) override {
        const ModuleId strategy{"test.strategy.second"};const std::string version="7";
        FamilyIdentity identity{problem.identity(),request,problem.constraints().coordinates(),strategy,version,{}};
        JointRelation relation{identity.coordinates,request.representation,std::make_shared<const JointRelationPayload>()};
        const ClaimEvidence claim{identity.problem,SymbolicArgument{"second verifier theorem","compiled test catalog"}};
        const ObjectiveBound bound{2,claim};
        CompleteOptimalFamily complete{relation,{claim,{bound,bound}},
            {identity,RegisteredCompletenessEvidence{{"test.verifier.second"},"7","second-verifier-proof"}},Assurance::numerical};
        SynthesisResult result{Termination::completed,{identity.problem,MathematicalOutcome::optimal,claim.support,{}},
            {bound,bound},{},{},{},{}};
        result.complete_proposal=CompleteFamilyProposal{identity,std::move(complete)};
        return result;
    }
};
StrategyRegistration second_verifier_registration() {
    return {{ModuleId{"test.strategy.second"},"7"},
        [](const StrategyRequest&,const Requirements&)->Capability {
            Output output;output.representation={"test.relation"};output.assurance=Assurance::numerical;
            output.family=FamilyTarget::exact_optimal_relation;output.completeness=Completeness::established;
            return Offer{std::move(output)};
        },
        [](const StrategyRequest&,const Requirements&)->std::variant<StrategyPlan,Rejection> {
            auto checked=std::get<CheckedPipeline<>>(check_pipeline());
            return compose_strategy(std::move(checked),[](auto,const StrategyRequest&,const Requirements&) {
                return std::make_unique<SecondVerifierWorkspace>();
            });
        },
        StrategyRegistration::CompleteFamilyVerifierKey{ModuleId{"test.verifier.second"},"7"}};
}
}
TEST_CASE("a second test-only compiled verifier uses the generic complete-family publication path") {
    const auto problem=resolved_problem();auto family=family_request(problem);
    StrategyRequest request{problem,StrategyConfiguration{ModuleId{"test.strategy.second"},{},{},{},{},{},{},{},family.representation},family,"",{}};
    Requirements requirements;requirements.output.representation=family.representation;
    requirements.output.family=family.target;requirements.output.completeness=Completeness::established;
    StrategyRegistry registry;REQUIRE_FALSE(registry.add(second_verifier_registration()).has_value());
    auto prepared=std::get<PreparedStrategy>(registry.prepare(request,requirements));
    auto workspace=prepared.create();ExecutionContext context;context.numerical=family.numerical;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=std::get<SynthesisResult>(workspace->run(context));
    REQUIRE(result.family);
    CHECK(result.family->registry_verified());
    CHECK(result.family->identity().strategy==ModuleId{"test.strategy.second"});
    CHECK(std::get<RegisteredCompletenessEvidence>(std::get<CompleteOptimalFamily>(result.family->outcome()).completeness.support).verifier==ModuleId{"test.verifier.second"});
}
