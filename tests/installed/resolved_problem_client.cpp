#include <csl/problem/validator.hpp>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;
using namespace csl::problem;
using namespace csl::registry;
void require(bool condition,const char* message) {if(!condition) throw std::runtime_error(message);}
template<class T,class... R> T accepted(std::variant<T,R...> result) {
    require(std::holds_alternative<T>(result),"unexpected publication or admission failure");return std::get<T>(std::move(result));
}
class Forward final:public SynthesisWorkspace {
public:
    SynthesisResult solve(const ResolvedProblem& problem,const FamilyRequest&,const ExecutionContext&) override {
        const auto& p=*problem.description();
        const auto model=accepted(model::snapshot(*p.model,p.times));
        const auto x0=std::get<KnownInitial>(p.initial).point;
        const auto u=std::get<Singleton>(std::get<ContinuousDomain>(p.controls).stages[0]).point;
        const auto x1=accepted(model.step({0},x0,u,{}));
        const auto cost=accepted(optimization::evaluate(accepted(optimization::snapshot(p.objective)),x1));
        const auto id=problem.identity();
        return SynthesisResult{Termination::completed,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
            {{{id,{x0,x1},{u},cost},{id,SymbolicArgument{"fixed control", "literal singleton control"}}}}, {}};
    }
};
}
int main() try {
    const auto p=[] {
        Problem input{{"display"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
            LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1},KnownInitial{{2}},
            ContinuousDomain{{Singleton{{3}}}},{UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
        return accepted(resolve(input,{UncertaintyStructure::stage_product_uncoupled,{},{}}));
    }();
    require(p.identity().value=="csl.problem.v1.sha256:167962d4127c26ae199032551dceb32e8a04bfed653cfd44e90ad6cc89a36cb4","literal identity differs");
    require(p.canonical_bytes().size()==260,"canonical width differs");
    auto factories=std::make_shared<int>(0);
    const auto prepared=[&] {
        StrategyRegistry registry;
        for(bool inverse:{false,true}) {
            require(!registry.add({{{inverse?"inverse":"forward"},"1"},
                [inverse](const StrategyRequest& request,const Requirements&) -> Capability {
                    const auto& input=*request.problem.description();
                    auto errors=check_nominal_profile(input,inverse,Assurance::numerical);
                    if(!errors.empty()) return errors;
                    const auto* controls=std::get_if<ContinuousDomain>(&input.controls);
                    if(input.times.size()!=2 || !controls || controls->stages.size()!=1 || !std::holds_alternative<Singleton>(controls->stages[0]))
                        return Diagnostics{{DiagnosticCode::unsupported,"fixture.controls","requires one fixed-control stage"}};
                    return Offer{};
                },
                [factories](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
                    return compose_strategy(accepted(check_pipeline()),[factories](auto,const StrategyRequest&,const Requirements&) {
                        ++*factories;return std::make_unique<Forward>();
                    });
                }}),"registration failed");
        }
        StrategyConfiguration config{{"inverse"},{},{},{},{},{},{},{},{}};
        FamilyRequest family{"nominal_open_loop",p.identity(),FamilyTarget::candidate_relaxation,
            {1e-8,1e-8},Assurance::numerical,{},{}};
        require(std::holds_alternative<Rejection>(prepare_strategy(p,registry,config,family)),"inverse profile admitted singular dynamics");
        require(*factories==0,"rejection constructed a workspace");
        config.strategy={"forward"};return accepted(prepare_strategy(p,registry,config,family));
    }();
    const auto result=accepted(prepared.preparation().create()->run({}));
    require(*factories==1,"wrong factory count");require(result.incumbents.size()==1,"missing literal witness");
    require(result.incumbents[0].witness.states==std::vector<Vector>{{2},{3}},"retained trajectory differs");
    require(result.incumbents[0].witness.original_objective==3,"original cost differs");
    require(result.outcome.subject==p.identity() && !result.family,"result identity or family claim differs");
    std::cout<<"Installed resolved problem client: literal identity, retained data and actual strategy admission passed\n";
    return 0;
} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
