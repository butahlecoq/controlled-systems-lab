#include <csl/application/comparison.hpp>
#include <csl/problem/validator.hpp>
#include <iostream>
#include <memory>

int main() {
    using namespace csl;
    LinearStage transition{{0,0,{}},{0,0,{}},{0,0,{}},{}};
    auto model=std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{0,0,0},TimeDomain::discrete,std::move(transition)}, {}});
    Problem authored{{"installed-application"},std::move(model),{0},KnownInitial{{}},ContinuousDomain{{}},
        {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    const auto resolved=problem::resolve(authored,{problem::UncertaintyStructure::stage_product_uncoupled});
    if(!std::holds_alternative<problem::ResolvedProblem>(resolved))return 1;
    const auto& problem=std::get<problem::ResolvedProblem>(resolved);

    FamilyRequest family;family.profile="unsupported-general-profile";family.objective=problem.identity();
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    const auto result=application::prepare_comparison({problem,family,{}},registry::StrategyRegistry{});
    if(!std::holds_alternative<application::UnsupportedComparison>(result))return 2;
    const auto& diagnostic=std::get<application::UnsupportedComparison>(result).diagnostics.front();
    if(diagnostic.field!="comparison.family.profile"||diagnostic.code!=DiagnosticCode::unsupported)return 3;
    std::cout<<"Installed application client: guarded profile rejection passed\n";
    return 0;
}
