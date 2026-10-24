#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/application/comparison.hpp>
#include <csl/problem/validator.hpp>

#include <memory>

namespace {
csl::problem::ResolvedProblem zero_problem() {
    using namespace csl;
    LinearStage transition{{0,0,{}},{0,0,{}},{0,0,{}},{}};
    auto model=std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{0,0,0},TimeDomain::discrete,std::move(transition)}, {}});
    Problem authored{{"application-test"},std::move(model),{0},KnownInitial{{}},ContinuousDomain{{}},
        {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved=problem::resolve(authored,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}
csl::application::ComparisonRequest request_for(const csl::problem::ResolvedProblem& problem) {
    using namespace csl;
    FamilyRequest family;family.profile="ts01_exact_integrator";family.objective=problem.identity();
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration reach_back;reach_back.strategy={"csl.synthesis.reach-back"};reach_back.representation=family.representation;
    StrategyConfiguration direct_joint;direct_joint.strategy={"csl.synthesis.strategy-b"};direct_joint.representation=family.representation;
    return {problem,family,{reach_back,direct_joint}};
}

csl::registry::StrategyRegistration rejecting(std::string id,int& capability_calls,int& planner_calls) {
    using namespace csl;
    registry::StrategyRegistration entry;
    entry.identity={{std::move(id)},"1"};
    entry.capabilities=[&capability_calls](const registry::StrategyRequest&,const registry::Requirements&) {
        ++capability_calls;
        return registry::Capability{Diagnostics{{DiagnosticCode::unsupported,"test.capability","deliberate test rejection"}}};
    };
    entry.planner=[&planner_calls](const registry::StrategyRequest&,const registry::Requirements&)
        ->std::variant<registry::StrategyPlan,registry::Rejection> {
        ++planner_calls;
        return registry::Rejection{};
    };
    return entry;
}

class NoopWorkspace final : public csl::SynthesisWorkspace {
public:
    csl::SynthesisResult solve(const csl::problem::ResolvedProblem&,
        const csl::FamilyRequest&, const csl::ExecutionContext&) override { return {}; }
};

csl::registry::StrategyRegistration accepting(std::string id) {
    using namespace csl;
    registry::StrategyRegistration entry;
    entry.identity={{std::move(id)},"1"};
    entry.complete_family_verifier={ModuleId{"csl.verifier.ts01-analytic"},"1"};
    entry.capabilities=[](const registry::StrategyRequest&,const registry::Requirements& requirements) {
        return registry::Capability{registry::Offer{requirements.output}};
    };
    entry.planner=[](const registry::StrategyRequest&,const registry::Requirements&)
        ->std::variant<registry::StrategyPlan,registry::Rejection> {
        auto checked=registry::check_pipeline();
        if(auto* rejection=std::get_if<registry::Rejection>(&checked))return *rejection;
        return registry::compose_strategy(std::get<registry::CheckedPipeline<>>(std::move(checked)),
            [](auto,const registry::StrategyRequest&,const registry::Requirements&) {
                return std::make_unique<NoopWorkspace>();
            });
    };
    return entry;
}
}

TEST_CASE("comparison admission rejects unguarded profiles before registry access") {
    const auto problem=zero_problem();
    auto request=request_for(problem);request.family.profile="nominal_open_loop";
    const csl::registry::StrategyRegistry empty;
    const auto result=csl::application::prepare_comparison(request,empty);
    REQUIRE(std::holds_alternative<csl::application::UnsupportedComparison>(result));
    const auto& diagnostics=std::get<csl::application::UnsupportedComparison>(result).diagnostics;
    REQUIRE(diagnostics.size()==1);
    CHECK(diagnostics[0].field=="comparison.family.profile");
}

TEST_CASE("both capability rejections are reported without planner or workspace creation") {
    const auto problem=zero_problem();
    const auto request=request_for(problem);
    csl::registry::StrategyRegistry registry;
    int capability_calls=0,planner_calls=0;
    REQUIRE_FALSE(registry.add(rejecting("csl.synthesis.reach-back",capability_calls,planner_calls)));
    REQUIRE_FALSE(registry.add(rejecting("csl.synthesis.strategy-b",capability_calls,planner_calls)));

    const auto result=csl::application::prepare_comparison(request,registry);
    REQUIRE(std::holds_alternative<csl::application::RejectedComparison>(result));
    const auto& comparison=std::get<csl::application::RejectedComparison>(result);
    REQUIRE(comparison.strategies.size()==2);
    CHECK(comparison.strategy_indices==std::vector<std::size_t>{0,1});
    CHECK(capability_calls==2);
    CHECK(planner_calls==0);
}

TEST_CASE("comparison preserves the identity of a one-sided capability rejection") {
    const auto problem=zero_problem();
    const auto request=request_for(problem);
    csl::registry::StrategyRegistry registry;
    REQUIRE_FALSE(registry.add(accepting("csl.synthesis.reach-back")));
    int capability_calls=0,planner_calls=0;
    REQUIRE_FALSE(registry.add(rejecting("csl.synthesis.strategy-b",capability_calls,planner_calls)));

    const auto result=csl::application::prepare_comparison(request,registry);
    REQUIRE(std::holds_alternative<csl::application::RejectedComparison>(result));
    const auto& comparison=std::get<csl::application::RejectedComparison>(result);
    REQUIRE(comparison.strategies.size()==1);
    CHECK(comparison.strategy_indices==std::vector<std::size_t>{1});
    CHECK(comparison.strategies[0].provenance.requested.id==csl::ModuleId{"csl.synthesis.strategy-b"});
    REQUIRE(comparison.strategies[0].diagnostics.size()==1);
    CHECK(comparison.strategies[0].diagnostics[0].field=="test.capability");
    CHECK(capability_calls==1);
    CHECK(planner_calls==0);
}
