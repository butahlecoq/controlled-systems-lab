// Contract fixtures only. No numerical synthesis or family construction happens here.
#include <csl/contracts.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <future>
#include <iostream>
#include <utility>

namespace {
using namespace csl;
class FixtureWorkspace final : public SynthesisWorkspace {
public:
    explicit FixtureWorkspace(ModuleId strategy) : strategy_(std::move(strategy)) {}
    SynthesisResult solve(const problem::ResolvedProblem&, const FamilyRequest&, const ExecutionContext&) override {
        throw std::logic_error("Unsupported contract fixture has no executable solve");
    }
private:
    ModuleId strategy_;
};
class FixtureStrategy final : public SynthesisStrategy {
public:
    explicit FixtureStrategy(StrategyConfiguration config) : config_(std::move(config)) {}
    Diagnostics check_capabilities(const problem::ResolvedProblem& p, const FamilyRequest& request) const override {
        auto diagnostics = check_nominal_profile(*p.description(),false,request.assurance);
        diagnostics.push_back({DiagnosticCode::unsupported,config_.strategy.value,
            "Contract fixture: no executable synthesis capability"});
        return diagnostics;
    }
    std::unique_ptr<SynthesisWorkspace> make_workspace() const override {
        return std::make_unique<FixtureWorkspace>(config_.strategy);
    }
private:
    StrategyConfiguration config_;
};
StrategyConfiguration configuration(std::string strategy) {
    return {{std::move(strategy)}, {"highs/lp"}, {"highs/qp"}, {"barycentric/hull"},
        {"polyhedral/operators"}, {"equivalent/conversion"}, {"reject/approximation"},
        {"directional/selector"}, {"joint/polyhedral"}};
}
}

int main() {
    using namespace csl;
    auto model = std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}});
    const auto problem = std::make_shared<const Problem>(Problem{
        {"example/two-step-integrator"},model,{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{UniversalSet{1},UniversalSet{1}}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}}, {},{},InformationPattern::nominal_open_loop,
        ResidualNormTerminal{{1,1,{1}},{1}}});
    FixtureStrategy reachability(configuration("reachability/backward-recovery"));
    FixtureStrategy joint(configuration("joint/trajectory-optimization"));
    auto policy = std::make_shared<const ResourcePolicy>(ResourcePolicy{2,2,1,{}});
    if (!check_resources(*policy).empty()) return 1;
    const ExecutionContext context{policy,{}, {}, {1e-8,1e-8}, "fixture/comparison"};
    // A product caller stops at the unsupported capability diagnostic.
    // Here we also allocate workspaces to demonstrate their exclusive ownership.
    auto first = reachability.make_workspace();
    auto second = joint.make_workspace();
    if (first.get() == second.get()) return 2;
    auto resolution=problem::resolve(*problem,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
    if (!std::holds_alternative<problem::ResolvedProblem>(resolution)) return 4;
    const auto resolved=std::get<problem::ResolvedProblem>(std::move(resolution));
    const FamilyRequest request{"nominal_open_loop",resolved.identity(),FamilyTarget::candidate_relaxation,
        context.numerical,Assurance::numerical,{"joint/polyhedral"},{}};
    for (auto* strategy : {&reachability,&joint}) {
        auto diagnostics = strategy->check_capabilities(resolved,request);
        for (const auto& d : diagnostics) std::cout << d.field << ": " << d.explanation << '\n';
    }
    std::cout << "Two exclusive fixture workspaces exist. No solver/family result was produced.\n";
}
