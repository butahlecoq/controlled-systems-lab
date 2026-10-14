#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/problem/validator.hpp>
#include <csl/registry/registry.hpp>
#include <atomic>
#include <future>

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
        const bool third=request.profile=="profile-b";
        const ModuleId verifier{third?"test.verifier.third":"test.verifier.second"};
        const std::string verifier_version=third?"8":"7";
        const std::string proof_text=third?"third-verifier-proof":"second-verifier-proof";
        FamilyIdentity identity{problem.identity(),request,problem.constraints().coordinates(),strategy,version,{}};
        JointRelation relation{identity.coordinates,request.representation,std::make_shared<const JointRelationPayload>()};
        const ClaimEvidence claim{identity.problem,SymbolicArgument{"second verifier theorem","compiled test catalog"}};
        const ObjectiveBound bound{2,claim};
        CompleteOptimalFamily complete{relation,{claim,{bound,bound}},
            {identity,RegisteredCompletenessEvidence{verifier,verifier_version,proof_text}},Assurance::numerical};
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
TEST_CASE("complete-family verifier selection is frozen per immutable request profile") {
    const auto problem=resolved_problem();
    auto registration=second_verifier_registration();
    std::atomic<std::size_t> planner_calls=0;
    auto original_planner=std::move(registration.planner);
    registration.planner=[&planner_calls,planner=std::move(original_planner)](const StrategyRequest& request,const Requirements& requirements) {
        ++planner_calls;
        return planner(request,requirements);
    };
    registration.complete_family_verifier_selector=[](const StrategyRequest& request)
        ->std::optional<StrategyRegistration::CompleteFamilyVerifierKey> {
        if(request.family.profile=="profile-a")
            return StrategyRegistration::CompleteFamilyVerifierKey{{"test.verifier.second"},"7"};
        if(request.family.profile=="profile-b")
            return StrategyRegistration::CompleteFamilyVerifierKey{{"test.verifier.third"},"8"};
        if(request.family.profile=="profile-unknown-verifier")
            return StrategyRegistration::CompleteFamilyVerifierKey{{"test.verifier.not-compiled"},"99"};
        return std::nullopt;
    };
    StrategyRegistry registry;REQUIRE_FALSE(registry.add(std::move(registration)).has_value());
    const auto make_request=[&](const std::string& profile) {
        auto family=family_request(problem);family.profile=profile;
        StrategyRequest request{problem,StrategyConfiguration{ModuleId{"test.strategy.second"},{},{},{},{},{},{},{},family.representation},family,"",{}};
        return request;
    };
    const auto requirements_for=[](const StrategyRequest& request) {
        Requirements requirements;requirements.output.representation=request.family.representation;
        requirements.output.family=request.family.target;requirements.output.completeness=Completeness::established;
        return requirements;
    };
    auto prepare_async=[&registry,&make_request,&requirements_for](const std::string& profile) {
        return std::async(std::launch::async,[&registry,&make_request,&requirements_for,profile] {
            auto request=make_request(profile);
            return registry.prepare(request,requirements_for(request));
        });
    };
    auto future_a=prepare_async("profile-a");
    auto future_b=prepare_async("profile-b");
    auto a=future_a.get();
    auto b=future_b.get();
    REQUIRE(std::holds_alternative<PreparedStrategy>(a));
    REQUIRE(std::holds_alternative<PreparedStrategy>(b));
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto outcome_b=std::get<PreparedStrategy>(std::move(b)).create()->run(context);
    auto outcome_a=std::get<PreparedStrategy>(std::move(a)).create()->run(context);
    REQUIRE(std::holds_alternative<SynthesisResult>(outcome_b));
    REQUIRE(std::holds_alternative<SynthesisResult>(outcome_a));
    auto result_b=std::get<SynthesisResult>(std::move(outcome_b));
    auto result_a=std::get<SynthesisResult>(std::move(outcome_a));
    CHECK(planner_calls.load()==2);
    REQUIRE(result_a.family);REQUIRE(result_b.family);
    const auto evidence=[](const OptimalFamily& family)->const RegisteredCompletenessEvidence& {
        return std::get<RegisteredCompletenessEvidence>(std::get<CompleteOptimalFamily>(family.outcome()).completeness.support);
    };
    CHECK(evidence(*result_a.family).verifier==ModuleId{"test.verifier.second"});
    CHECK(evidence(*result_a.family).verifier_version=="7");
    CHECK(evidence(*result_b.family).verifier==ModuleId{"test.verifier.third"});
    CHECK(evidence(*result_b.family).verifier_version=="8");
    auto missing=registry.prepare(make_request("profile-c"),requirements_for(make_request("profile-c")));
    REQUIRE(std::holds_alternative<Rejection>(missing));
    CHECK(std::get<Rejection>(missing).diagnostics.front().field=="family.verifier.profile");
    CHECK(planner_calls.load()==2);
    auto unknown_verifier=registry.prepare(make_request("profile-unknown-verifier"),
        requirements_for(make_request("profile-unknown-verifier")));
    REQUIRE(std::holds_alternative<Rejection>(unknown_verifier));
    CHECK(std::get<Rejection>(unknown_verifier).diagnostics.front().field=="family.verifier");
    CHECK(planner_calls.load()==2);
}
TEST_CASE("a profile cannot publish evidence from another selected verifier") {
    const auto problem=resolved_problem();auto registration=second_verifier_registration();
    registration.complete_family_verifier_selector=[](const StrategyRequest&)
        ->std::optional<StrategyRegistration::CompleteFamilyVerifierKey> {
        return StrategyRegistration::CompleteFamilyVerifierKey{{"test.verifier.third"},"8"};
    };
    StrategyRegistry registry;REQUIRE_FALSE(registry.add(std::move(registration)).has_value());
    auto family=family_request(problem);family.profile="profile-a";
    StrategyRequest request{problem,StrategyConfiguration{ModuleId{"test.strategy.second"},{},{},{},{},{},{},{},family.representation},family,"",{}};
    Requirements requirements;requirements.output.representation=family.representation;
    requirements.output.family=family.target;requirements.output.completeness=Completeness::established;
    auto prepared=registry.prepare(request,requirements);REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
    ExecutionContext context;context.numerical=family.numerical;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=std::get<SynthesisResult>(std::get<PreparedStrategy>(std::move(prepared)).create()->run(context));
    CHECK_FALSE(result.family);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    CHECK(std::get<ContractValidationFailure>(result.stop).diagnostics.front().field=="family.proposal.verifier");
}
