#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/registry/registry.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/problem/contracts.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/sets/data.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include "strategy_a_lineage.hpp"
#include <algorithm>
#include <type_traits>
#include <utility>

using namespace csl;
using namespace csl::registry;
namespace {

class ProposalOnlyWorkspace final : public SynthesisWorkspace {
    CompleteFamilyProposal proposal_;
public:
    explicit ProposalOnlyWorkspace(CompleteFamilyProposal proposal):proposal_(std::move(proposal)){}
    SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override {
        SynthesisResult result;
        result.termination=Termination::completed;
        result.outcome={proposal_.identity.problem,MathematicalOutcome::optimal,
            std::get<SymbolicArgument>(proposal_.family.optimum.optimum.support),{}};
        result.objective=proposal_.family.optimum.bounds;
        result.complete_proposal=proposal_;
        return result;
    }
};

template<class T,class... R> T take(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

template<class Port> registry::PreparedProvider<Port> selected(registry::Registration<Port> entry,
    std::string representation) {
    registry::Registry<Port> provider_registry;
    registry::Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(provider_registry.add(std::move(entry)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,registry::GeometryPort>||std::is_same_v<Port,registry::ConversionPort>)
        requirements.output.relation=SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(provider_registry,method,requirements)));
}

SetHandle interval(std::string id,double lower,double upper) {
    auto inequalities=numeric::snapshot(Matrix{2,1,{1,-1}});
    auto bounds=numeric::snapshot_vector(Vector{upper,-lower});
    auto equalities=numeric::snapshot(Matrix{0,1,{}});
    auto equality_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(equality_values));
    auto set=sets::make_h({{std::move(id)},1,{"x"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
    REQUIRE(std::holds_alternative<sets::SetData>(set));
    return std::get<sets::SetData>(std::move(set)).as_handle();
}

problem::ResolvedProblem exact_problem() {
    Problem source{{"strategy-a-runtime-receipt"},
        std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
            LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1,1,{2}},{-2},1}};
    auto resolved=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}

PreparedStrategy prepare_real_strategy(const problem::ResolvedProblem& problem,const FamilyRequest& family,
    bool mismatched_verifier=false) {
    auto lp=take(adapters::lp::make_highs_registration());
    auto convex=take(adapters::convex::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection=geometry::polyhedral::make_projection_registration();
    auto affine=geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(),""),
        selected(lp,"csl.program-result.v1"),selected(converter,"csl.polyhedron.v")});
    registry::Registry<registry::GeometryPort> projections,affines;
    registry::Registry<registry::ConversionPort> conversions;
    registry::Registry<registry::LPPort> lps;
    registry::Registry<registry::ConvexPort> convexes;
    const auto pm=registry::Method{projection.identity.id,projection.identity.version};
    const auto am=registry::Method{affine.identity.id,affine.identity.version};
    const auto cm=registry::Method{converter.identity.id,converter.identity.version};
    const auto lm=registry::Method{lp.identity.id,lp.identity.version};
    const auto qm=registry::Method{convex.identity.id,convex.identity.version};
    REQUIRE_FALSE(projections.add(std::move(projection)));
    REQUIRE_FALSE(affines.add(std::move(affine)));
    REQUIRE_FALSE(conversions.add(std::move(converter)));
    REQUIRE_FALSE(lps.add(std::move(lp)));
    REQUIRE_FALSE(convexes.add(std::move(convex)));
    registry::Requirements h,v,program;
    h.output.representation={"csl.polyhedron.h"};h.output.relation=SetRelation::equivalent;
    v.output.representation={"csl.polyhedron.v"};v.output.relation=SetRelation::equivalent;
    program.output.representation={"csl.program-result.v1"};
    auto providers=take(registry::check_providers(
        registry::select_provider(projections,pm,h),registry::select_provider(affines,am,v),
        registry::select_provider(conversions,cm,h),registry::select_provider(lps,lm,program),
        registry::select_provider(convexes,qm,program)));
    auto registration=synthesis::strategy_a::make_registration(std::move(providers));
    if(mismatched_verifier)registration.complete_family_verifier_selector=[](const StrategyRequest&)
        ->std::optional<StrategyRegistration::CompleteFamilyVerifierKey> {
        return StrategyRegistration::CompleteFamilyVerifierKey{{synthesis::ts02_constant_integrator_verifier},"1"};
    };
    registry::StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(std::move(registration)));
    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation=family.representation;
    Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=family.target;
    requirements.output.completeness=Completeness::established;
    StrategyRequest request{problem,configuration,family,"1",{}};
    return take(strategies.prepare(request,requirements));
}

ExecutionContext execution_context() {
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    return context;
}

CompleteFamilyProposal exact_proposal(const problem::ResolvedProblem& problem,const FamilyRequest& family) {
    const auto lineage=synthesis::strategy_a::detail::expected_ts01_lineage(problem.identity());
    const FamilyIdentity identity{problem.identity(),family,problem.constraints().coordinates(),
        {"csl.synthesis.reach-back"},"1",lineage};
    auto relation=synthesis::strategy_ts01::ExactJointRelation::canonical();
    REQUIRE(std::holds_alternative<std::shared_ptr<const synthesis::strategy_ts01::ExactJointRelation>>(relation));
    const SymbolicArgument derivation{"T-S01 exact analytic derivation",
        "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
    const ClaimEvidence claim{problem.identity(),derivation};
    const ObjectiveBound zero{0,claim};
    CompleteOptimalFamily complete{{problem.constraints().coordinates(),family.representation,
            std::get<std::shared_ptr<const synthesis::strategy_ts01::ExactJointRelation>>(std::move(relation))},
        {claim,{zero,zero}},
        {identity,RegisteredCompletenessEvidence{{"csl.verifier.ts01-analytic"},"1","TS01-analytic-v1"}},
        Assurance::numerical};
    return {identity,std::move(complete)};
}

FamilyRequest exact_request(const problem::ResolvedProblem& problem) {
    FamilyRequest family;
    family.objective=problem.identity();
    family.profile=synthesis::strategy_ts01::profile_id;
    family.target=FamilyTarget::exact_optimal_relation;
    family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    return family;
}

TEST_CASE("Strategy A cannot publish exact T-S01 from a proposal without a runtime receipt") {
    const auto problem=exact_problem();
    const auto family=exact_request(problem);
    const auto proposal=exact_proposal(problem,family);
    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation=family.representation;

    StrategyRegistration registration;
    registration.identity={configuration.strategy,"1"};
    registration.capabilities=[](const StrategyRequest&,const Requirements& requirements)->Capability {
        return Offer{requirements.output};
    };
    registration.planner=[proposal](const StrategyRequest&,const Requirements&)
        ->std::variant<StrategyPlan,Rejection> {
        auto checked=check_pipeline();
        return compose_strategy(std::get<CheckedPipeline<>>(std::move(checked)),
            [proposal](auto,const StrategyRequest&,const Requirements&) {
                return std::make_unique<ProposalOnlyWorkspace>(proposal);
            });
    };
    registration.complete_family_verifier={{"csl.verifier.ts01-analytic"},"1"};
    registration.expected_lineage=[](const StrategyRequest& request) {
        return synthesis::strategy_a::detail::expected_ts01_lineage(request.problem.identity());
    };
    registration.complete_family_verifier_selector=[](const StrategyRequest&)
        ->std::optional<StrategyRegistration::CompleteFamilyVerifierKey> {
        return StrategyRegistration::CompleteFamilyVerifierKey{{"csl.verifier.ts01-analytic"},"1"};
    };

    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(std::move(registration)));
    StrategyRequest request{problem,configuration,family,"1",
        synthesis::strategy_a::detail::expected_ts01_lineage(problem.identity())};
    Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=FamilyTarget::exact_optimal_relation;
    requirements.output.completeness=Completeness::established;
    auto prepared=strategies.prepare(request,requirements);
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=std::get<PreparedStrategy>(std::move(prepared)).create()->run(context);
    REQUIRE(std::holds_alternative<SynthesisResult>(result));
    const auto& rejected=std::get<SynthesisResult>(result);
    CHECK(rejected.termination==Termination::contract_rejected);
    CHECK_FALSE(rejected.family);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(rejected.stop));
    CHECK(std::any_of(std::get<ContractValidationFailure>(rejected.stop).diagnostics.begin(),
        std::get<ContractValidationFailure>(rejected.stop).diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch&&
                diagnostic.field=="family.runtime_receipt";
        }));
}

TEST_CASE("Strategy A issues a fresh exact T-S01 receipt for each workspace run") {
    const auto problem=exact_problem();
    const auto family=exact_request(problem);
    auto workspace=prepare_real_strategy(problem,family).create();
    const auto first=take(workspace->run(execution_context()));
    REQUIRE(first.termination==Termination::completed);
    REQUIRE(first.family);
    CHECK(first.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(first.family->registry_verified());
    const auto second=take(workspace->run(execution_context()));
    REQUIRE(second.termination==Termination::completed);
    REQUIRE(second.family);
    CHECK(second.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(second.family->registry_verified());
    CHECK(second.family->identity()==first.family->identity());
}

TEST_CASE("Strategy A rejects an exact T-S01 receipt bound to a different selected verifier") {
    const auto problem=exact_problem();
    const auto family=exact_request(problem);
    auto workspace=prepare_real_strategy(problem,family,true).create();
    const auto outcome=workspace->run(execution_context());
    const auto result=take(std::move(outcome));
    CHECK(result.termination==Termination::contract_rejected);
    CHECK_FALSE(result.family);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    CHECK(std::any_of(std::get<ContractValidationFailure>(result.stop).diagnostics.begin(),
        std::get<ContractValidationFailure>(result.stop).diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch&&
                diagnostic.field=="family.runtime_receipt";
        }));
}

} // namespace
