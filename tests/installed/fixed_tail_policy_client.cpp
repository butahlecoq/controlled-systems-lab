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
struct ExampleParameters {
    std::size_t horizon{1};
    Vector observed{0,0};
    std::size_t offset{};
    std::size_t original_horizon{};
    Vector target{1,0};
    double running_coefficient{2};
    double control_lower{-2},control_upper{2};
};
FixedTailModel example(ExampleParameters options={}) {
    const auto horizon=options.horizon;
    const auto original=options.original_horizon?options.original_horizon:options.offset+horizon;
    const Matrix I{2,2,{1,0,0,1}};
    auto system=std::make_shared<const SystemModel>(SystemModel{{{2,2,0},TimeDomain::discrete,LinearStage{I,I,{2,0,{}},{0,0}}},{}});
    Vector times(horizon+1);for(std::size_t k=0;k<=horizon;++k)times[k]=static_cast<double>(options.offset+k);
    Vector linear;double constant=0;
    for(const auto value:options.target) {linear.push_back(-2*value);constant+=value*value;}
    Problem p{{"fixed-tail-native-analytic"},system,times,KnownInitial{options.observed},
        ContinuousDomain{std::vector<AdmissibleSet>(horizon,box(2,options.control_lower,options.control_upper))},
        std::vector<AdmissibleSet>(horizon+1,UniversalSet{2}),{},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{2,2,{2,0,0,2}},linear,constant}};
    auto resolved=take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    optimization::RunningControlCost running{"fixed-tail-native-full-J",original,{}};
    for(std::size_t k=0;k<original;++k)running.stages.push_back({k,{optimization::QuadraticControlPenalty{{0,0},{1,1},{1,1},options.running_coefficient,original}}});
    return take(prepare_fixed_tail(resolved,running,options.offset));
}
FixedTailModel singular_four_state_example() {
    Matrix I{4,4,Vector(16,0)},Q{4,4,Vector(16,0)};
    for(std::size_t j=0;j<4;++j){I.values[j*4+j]=1;Q.values[j*4+j]=2;}
    auto system=std::make_shared<const SystemModel>(SystemModel{{{4,2,0},TimeDomain::discrete,
        LinearStage{I,{4,2,{1,0,0,1,0,0,0,0}},{4,0,{}},Vector(4,0)}},{}});
    Problem p{{"fixed-tail-native-singular-four-state"},system,{0,1},KnownInitial{Vector(4,0)},
        ContinuousDomain{{box(2,-2,2)}},{UniversalSet{4},UniversalSet{4}},{},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{Q,{-2,0,0,0},1}};
    auto source=take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    optimization::RunningControlCost running{"fixed-tail-native-singular-J",1,
        {{0,{optimization::QuadraticControlPenalty{{0,0},{1,1},{1,1},2,1}}}}};
    return take(prepare_fixed_tail(source,running,0));
}
}
int run() {
    registry::Registry<registry::FixedTailOptimizerPort> providers;
    auto registration=adapters::nlp::make_casadi_fixed_tail_registration();
    const registry::Method method{registration.identity.id,registration.identity.version};
    require(!providers.add(std::move(registration)),"native provider registration failed");
    registry::Requirements requirements;requirements.output.representation={"csl.fixed-tail-solve.v1"};
    auto selected=take(registry::prepare_provider(registry::select_provider(providers,method,requirements)));
    {
        const auto model=example();
        const auto count=model.source_cost.quadratic.dimension;
        Matrix I{count,count,Vector(count*count,0)};
        for(std::size_t j=0;j<count;++j)I.values[j*count+j]=1;
        FixedTailSolveRequest malformed{{model.problem,{"malformed-native-admission"}},model.full_history,model.source_cost,
            {model.source_cost.coordinates,I,Vector(count,0)},{},Vector(count,0),true,{}};
        malformed.domain.inequalities.values.clear();
        const auto adapter=adapters::nlp::make_casadi_fixed_tail_registration();
        require(std::holds_alternative<Diagnostics>(adapter.capabilities(malformed,requirements)),
                "native CasADi adapter offered malformed external H storage");
    }
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
    Vector polygon_control,parallelotope_control;
    for(const auto family:{FixedTailFamily::polytope,FixedTailFamily::box,FixedTailFamily::zonotope,FixedTailFamily::parallelotope,FixedTailFamily::ellipsoid}) {
        const auto run_case=[&](FixedTailModel model,const char* label) {
            const auto hint=take(initialize_fixed_tail(model));
            auto outcome=fixed_tail_policy({model,{label},family,hint.history,{}},selected,context);
            if(const auto* f=std::get_if<FixedTailPolicyFailure>(&outcome))throw std::runtime_error(std::string(label)+": "+f->phase+": "+f->cause.explanation);
            if(const auto* stop=std::get_if<OperationStopped>(&outcome))throw std::runtime_error(std::string(label)+": "+stop->diagnostics);
            return std::get<FixedTailPolicyResult>(std::move(outcome));
        };
        const auto two=run_case(example({.horizon=2}),"two-stage distinct rollout");
        require(two.regions.size()==3,"two-stage rollout lost a selected physical family");
        require(std::abs(two.control[0]-.5)<1e-5 && std::abs(two.cost.total-.5)<1e-6,
            "fixed-tail rollout was replaced by full-history MPC (which chooses u0=u1=1/3)");
        const auto corner=run_case(example({.target={1.8,1.3},.running_coefficient=.02}),"family affects action");
        if(family==FixedTailFamily::polytope)polygon_control=corner.control;
        if(family==FixedTailFamily::parallelotope)parallelotope_control=corner.control;
        const auto four=run_case(singular_four_state_example(),"four-state singular carrier");
        require(std::abs(four.control[0]-1.0/3)<1e-5,"unused state coordinates changed the mathematical optimum");
        require(four.regions[1].carrier_lower[2]==0 && four.regions[1].carrier_upper[2]==0,
            "exact zero carrier widths were inflated");
        const auto point=run_case(example({.control_lower=0,.control_upper=0}),"zero-input point region");
        require(std::abs(point.control[0])<1e-7 && std::abs(point.control[1])<1e-7,
            "zero-control source did not recover its single admissible action");
        if(family!=FixedTailFamily::polytope)require(point.regions[1].inner->point,"zero-radius family was not retained as a point");
    }
    require(polygon_control[0]>parallelotope_control[0]+.1,"selected family memberships did not affect the source-cost argmin");
    auto model=example({.horizon=2});
    Vector anchor{0,0,.5,0,.75,0,.5,0,.25,0};
    auto lift=take(fixed_control_tail_lift(model,anchor));
    const auto history=take(recover_fixed_tail_history(lift,Vector{1,0}));
    require(history==Vector({0,0,1,0,1.25,0,1,0,.25,0}),"native history lift did not freeze future controls");
    const auto first=take(initialize_fixed_tail(model));
    require(first.history==Vector(10,0),"native initial zero-control rollout differs");
    auto next=example({.observed={1.1,0},.offset=1,.original_horizon=2});
    const FixedTailWarmHistory previous{model.source_cost.coordinates,0,model.source_cost.running_source.objective_id,2,history};
    const auto shifted=take(initialize_fixed_tail(next,previous));
    require(shifted.history==Vector({1.1,0,1.25,0,.25,0}),"native shift repeated terminal stage or lost observation");
    auto invalid_previous=previous;invalid_previous.absolute_stage=3;
    require(std::holds_alternative<Diagnostic>(initialize_fixed_tail(next,invalid_previous)),"native shift accepted a nonconsecutive stage");
    const auto tail=take(fixed_tail_state_lift(model,anchor,{1}));
    require(tail.maps.size()==2 && tail.offsets[1]==Vector({.25,0}),"tail-state lift lost control offset");
    auto positive_model=example({.horizon=2,.observed={.1,0},.target={1.1,0}});
    const auto positive_initial=take(initialize_fixed_tail(positive_model));
    auto positive_outcome=fixed_tail_policy({positive_model,{"strict-positive-readback"},FixedTailFamily::box,
        positive_initial.history,{0}},selected,context);
    if(const auto* failure=std::get_if<FixedTailPolicyFailure>(&positive_outcome))
        throw std::runtime_error(failure->phase+": "+failure->cause.explanation);
    const auto& positive=std::get<FixedTailPolicyResult>(positive_outcome);
    require(positive.feasibility.supplied_initial_primary==positive_initial.history,
        "positive-state solver did not retain literal requested initialization");
    require(positive.feasibility.provider_initial_primary_readback[0]==.1,
        "known observed initial state was unnecessarily log/exp encoded");
    for(std::size_t k=0;k<=2;++k)require(positive.history[k*2]>0,
        "strict-positive native history lost its source domain");
    std::cout<<"Native fixed-tail policy: all five physical families, all stages, full source J and frozen-tail recovery passed\n";
    return 0;
}
int main() {
    try { return run(); }
    catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
