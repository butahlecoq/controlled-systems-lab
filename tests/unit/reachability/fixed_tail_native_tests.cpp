#include <csl/reachability/fixed_tail_policy.hpp>
#include <csl/adapters/nlp/casadi_fixed_tail.hpp>
#include <csl/sets/data.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace csl;
using namespace csl::reachability;
namespace {
template<class T,class... E>T take(std::variant<T,E...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("native fixed-tail fixture preparation failed");
    return std::get<T>(std::move(value));
}
void require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
SetHandle box(std::size_t n,double lower,double upper) {
    Matrix A{2*n,n,Vector(2*n*n,0)};Vector b(2*n);
    for(std::size_t i=0;i<n;++i){A.values[2*i*n+i]=1;A.values[(2*i+1)*n+i]=-1;b[2*i]=upper;b[2*i+1]=-lower;}
    return take(sets::make_h({{"test-control"},n,{}},{take(numeric::snapshot(A)),take(numeric::snapshot_vector(b)),take(numeric::snapshot(Matrix{0,n,{}})),take(numeric::snapshot_vector({}))})).as_handle();
}
FixedTailModel example(std::size_t horizon=1) {
    const Matrix I{2,2,{1,0,0,1}};
    auto system=std::make_shared<const SystemModel>(SystemModel{{{2,2,0},TimeDomain::discrete,LinearStage{I,I,{2,0,{}},{0,0}}},{}});
    Vector times(horizon+1);for(std::size_t k=0;k<=horizon;++k)times[k]=static_cast<double>(k);
    Problem p{{"fixed-tail-native-analytic"},system,times,KnownInitial{{0,0}},ContinuousDomain{std::vector<AdmissibleSet>(horizon,box(2,-2,2))},
        std::vector<AdmissibleSet>(horizon+1,UniversalSet{2}),{},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{2,2,{2,0,0,2}},{-2,0},1}};
    auto resolved=take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    optimization::RunningControlCost running{"fixed-tail-native-full-J",horizon,{}};
    for(std::size_t k=0;k<horizon;++k)running.stages.push_back({k,{optimization::QuadraticControlPenalty{{0,0},{1,1},{1,1},2,horizon}}});
    return take(prepare_fixed_tail(resolved,running,0));
}
}
int main() {
    registry::Registry<registry::FixedTailOptimizerPort> providers;
    auto registration=adapters::nlp::make_casadi_fixed_tail_registration();
    const registry::Method method{registration.identity.id,registration.identity.version};
    require(!providers.add(std::move(registration)),"native provider registration failed");
    registry::Requirements requirements;requirements.output.representation={"csl.fixed-tail-solve.v1"};
    auto selected=take(registry::prepare_provider(registry::select_provider(providers,method,requirements)));
    const ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-7,1e-8},"fixed-tail-native-test"};
    for(const auto family:{FixedTailFamily::polytope,FixedTailFamily::box,FixedTailFamily::zonotope,FixedTailFamily::parallelotope,FixedTailFamily::ellipsoid}) {
        auto model=example();
        auto result=fixed_tail_policy({model,{"all-five"},family,Vector(6,0),{}},selected,context);
        if(const auto* failure=std::get_if<FixedTailPolicyFailure>(&result))throw std::runtime_error(failure->phase+": "+failure->cause.explanation);
        if(const auto* stop=std::get_if<OperationStopped>(&result))throw std::runtime_error(stop->diagnostics);
        const auto& answer=std::get<FixedTailPolicyResult>(result);
        require(answer.regions.size()==2,"all-stage physical inner regions missing");
        require(answer.providers.size()==2,"both actual native solver phases must be retained");
        require(std::abs(answer.control[0]-1.0/3)<1e-5,"full source cost did not select u=1/3");
        require(std::abs(answer.cost.total-2.0/3)<1e-6,"source running cost was dropped");
        require(answer.feasibility.supplied_initial_primary==Vector(6,0),"original warm input not submitted");
        require(answer.reduced_argmin.primary.size()==2,"final policy freed future history coordinates");
    }
    auto model=example(2);
    Vector anchor{0,0,.5,0,.75,0,.5,0,.25,0};
    auto lift=take(fixed_control_tail_lift(model,anchor));
    const auto history=take(recover_fixed_tail_history(lift,Vector{1,0}));
    require(history==Vector({0,0,1,0,1.25,0,1,0,.25,0}),"native history lift did not freeze future controls");
    const auto tail=take(fixed_tail_state_lift(model,anchor,{1}));
    require(tail.maps.size()==2 && tail.offsets[1]==Vector({.25,0}),"tail-state lift lost control offset");
    std::cout<<"Native fixed-tail policy: all five physical families, all stages, full source J and frozen-tail recovery passed\n";
}
