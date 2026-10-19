#include <csl/geometry/reachable_plan.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <bit>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iostream>
#include <memory>
#include <iomanip>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::geometry::approximation;
using verification::CheckStatus;

std::uint64_t count(const char* argument) {
    const std::string value(argument);
    if(value.empty() || value.find_first_not_of("0123456789")!=std::string::npos)
        throw std::invalid_argument("positive decimal count required");
    const auto parsed=std::stoull(value);
    if(parsed==0 || parsed>1000000)throw std::invalid_argument("count outside 1..1000000");
    return parsed;
}

template<class T,class... Others> T take(std::variant<T,Others...> outcome) {
    if(!std::holds_alternative<T>(outcome))throw std::runtime_error("fixture construction failed");
    return std::get<T>(std::move(outcome));
}

problem::ResolvedProblem original() {
    Problem authored{{"app01-plan-report"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},
        TimeDomain::discrete,LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),
        {0,1},KnownInitial{{2}},ContinuousDomain{{Singleton{{3}}}},
        {UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,
        LinearTerminal{{1},0}};
    return take(problem::resolve(authored,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}

SetHandle interval() {
    return take(sets::make_h({{"app01-stage-reference"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{4,-2})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))})).as_handle();
}

SetHandle singleton() {
    return take(sets::make_singleton({{"app01-inner-point"},1,{"x"}},
        take(numeric::snapshot_vector(Vector{3})))).as_handle();
}

SetHandle empty_v() {
    return take(sets::make_v({{"app01-empty-v"},1,{"x"}},
        {take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))})).as_handle();
}

class Workspace final : public SetApproximatorWorkspace {
    OperationResult result_;
public:
    explicit Workspace(OperationResult result):result_(std::move(result)){}
    SetTransformOutcome approximate(const ApproximationRequest&,const ExecutionContext&) override {return result_;}
};

registry::Registry<registry::ApproximationPort> provider(const ApproximationRequest& query,SetHandle output) {
    registry::Registry<registry::ApproximationPort> methods;
    OperationResult result{output,SetRelation::inner,
        {{query.identity,{query.input.id}},GeometryClaimScope::set_relation,Unestablished{},{},{}}};
    const auto error=methods.add({{{"app01.literal-provider"},"1"},
        [](const ApproximationRequest& request,const registry::Requirements&) -> registry::Capability {
            registry::Output offer;offer.representation=request.output;offer.relation=SetRelation::inner;
            return registry::Offer{offer};
        },
        [result](const ApproximationRequest&) {return std::make_unique<Workspace>(result);}});
    if(error)throw std::runtime_error("fixture provider registration failed");
    return methods;
}

struct Fixture {
    std::string_view name;
    StageSetReference stage;
    ApproximationRequest request;
    registry::Registry<registry::ApproximationPort> methods;
    Witness witness;
};

Fixture fixture(const problem::ResolvedProblem& problem,std::string_view name,const SetHandle& reference,
                const SetHandle& point,const SetHandle& empty) {
    const auto output=name=="empty_inner"?empty:point;
    ApproximationRequest request{{problem.identity(),{"app01-stage-check"},{"app01-declared-stage1"}},
        reference,output.metadata.representation,SetRelation::inner,2,Assurance::numerical};
    Witness witness{problem.identity(),{{2},{3}},{{name=="invalid_plan"?5.0:3.0}},3};
    return {name,{problem.identity(),StageIndex{1},reference,{0},{"app01-declared-stage1"}},
        request,provider(request,output),witness};
}

const char* status(CheckStatus value) {
    switch(value) {
    case CheckStatus::not_checked:return "not_checked";
    case CheckStatus::numerical_pass:return "numerical_pass";
    case CheckStatus::violation:return "violation";
    case CheckStatus::invalid_input:return "invalid_input";
    case CheckStatus::unsupported:return "unsupported";
    }
    throw std::logic_error("unknown status");
}

const char* termination(Termination value) {
    switch(value) {
    case Termination::completed:return "completed";
    case Termination::cancelled:return "cancelled";
    case Termination::resource_limit:return "resource_limit";
    case Termination::numerical_failure:return "numerical_failure";
    case Termination::operation_rejected:return "operation_rejected";
    case Termination::contract_rejected:return "contract_rejected";
    }
    throw std::logic_error("unknown termination");
}

const char* outcome(const PlanCheck& report) {
    if(!report.approximation)return "none";
    if(std::holds_alternative<EnclosedApproximation>(*report.approximation))return "enclosed";
    if(std::holds_alternative<HeuristicApproximation>(*report.approximation))return "heuristic";
    if(std::holds_alternative<registry::Rejection>(*report.approximation))return "rejection";
    if(std::holds_alternative<OperationStopped>(*report.approximation))return "stopped";
    if(std::holds_alternative<Unsupported>(*report.approximation))return "unsupported";
    throw std::logic_error("unknown approximation outcome");
}

const char* basis(const PlanCheck& report) {
    if(!report.approximation)return "none";
    const auto* enclosed=std::get_if<EnclosedApproximation>(&*report.approximation);
    if(!enclosed)return "none";
    switch(enclosed->basis) {
    case StructuralBasis::identical_set:return "identical_set";
    case StructuralBasis::empty_subset:return "empty_subset";
    case StructuralBasis::universal_superset:return "universal_superset";
    case StructuralBasis::h_constraint_containment:return "h_constraint_containment";
    case StructuralBasis::h_point_containment:return "h_point_containment";
    case StructuralBasis::v_h_containment:return "v_h_containment";
    case StructuralBasis::h_v_containment:return "h_v_containment";
    case StructuralBasis::generator_axis_cover:return "generator_axis_cover";
    }
    throw std::logic_error("unknown basis");
}

bool expected(const PlanCheck& report,std::string_view name) {
    if(report.termination!=Termination::completed || report.diagnostics.size()>(name=="empty_inner"?1u:0u))return false;
    if(std::string_view(outcome(report))!="enclosed")return false;
    if(name=="empty_inner")return std::string_view(basis(report))=="empty_subset" &&
        report.membership==CheckStatus::violation && !report.trajectory &&
        !report.numerical_achievable_value;
    if(std::string_view(basis(report))!="h_point_containment" ||
       report.membership!=CheckStatus::numerical_pass || !report.trajectory ||
       report.trajectory->bindings!=CheckStatus::numerical_pass ||
       report.trajectory->objective!=CheckStatus::numerical_pass ||
       report.trajectory->termination!=Termination::completed ||
       report.trajectory->recomputed_objective!=3.0 ||
       report.trajectory->optimality!=CheckStatus::unsupported ||
       report.trajectory->completeness!=CheckStatus::unsupported ||
       report.trajectory->validated!=CheckStatus::unsupported)return false;
    const auto& residuals=report.trajectory->residuals;
    if(residuals.size()!=4)return false;
    const bool invalid=name=="invalid_plan";
    const std::string_view fields[]={"initial[0]","controls[0].singleton[0]","dynamics[0][0]","objective"};
    const double violations[]={0,invalid?2.0:0.0,invalid?2.0:0.0,0};
    const double scales[]={2,invalid?5.0:3.0,invalid?5.0:3.0,3};
    for(std::size_t i=0;i<residuals.size();++i)
        if(residuals[i].field!=fields[i] || residuals[i].measure.violation!=violations[i] ||
           residuals[i].measure.scale!=scales[i] ||
           residuals[i].tolerance!=1e-8+1e-8*scales[i] ||
           residuals[i].satisfied!=(violations[i]<=1e-8+1e-8*scales[i]))return false;
    if(name=="valid_plan")return report.trajectory->feasibility==CheckStatus::numerical_pass &&
        report.numerical_achievable_value==3.0;
    return report.trajectory->feasibility==CheckStatus::violation && !report.numerical_achievable_value;
}

std::uint64_t observe(const PlanCheck& report) {
    std::uint64_t token=static_cast<std::uint64_t>(report.membership)*0x9e3779b97f4a7c15ULL;
    token^=static_cast<std::uint64_t>(report.termination)<<24;
    if(report.numerical_achievable_value)token^=std::bit_cast<std::uint64_t>(*report.numerical_achievable_value);
    if(report.trajectory) {
        token^=static_cast<std::uint64_t>(report.trajectory->feasibility)<<16;
        token^=static_cast<std::uint64_t>(report.trajectory->objective)<<32;
        token^=report.trajectory->residuals.size();
    }
    return token;
}

bool run(const problem::ResolvedProblem& problem,const Fixture& input,
         std::uint64_t batch,std::uint64_t warmups,std::uint64_t repetitions) {
    for(std::uint64_t round=0;round<warmups+repetitions;++round) {
        const auto begin=std::chrono::steady_clock::now();
        std::uint64_t checked=0,failures=0,token=0;
        PlanCheck last;
        for(std::uint64_t iteration=0;iteration<batch;++iteration) {
            last=check_inner_state_plan(problem,input.stage,input.methods,
                {{"app01.literal-provider"},std::nullopt},input.request,input.witness);
            ++checked;
            token^=observe(last)+(iteration*0x9e3779b97f4a7c15ULL);
            if(!expected(last,input.name))++failures;
        }
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now()-begin).count();
        const auto* trajectory=last.trajectory?&*last.trajectory:nullptr;
        std::cout<<"{\"event\":\"trial\",\"fixture\":\""<<input.name
            <<"\",\"round\":"<<round<<",\"warmup\":"<<(round<warmups?"true":"false")
            <<",\"batch\":"<<batch<<",\"elapsed_ns\":"<<elapsed
            <<",\"checked_calls\":"<<checked<<",\"failures\":"<<failures
            <<",\"termination\":\""<<termination(last.termination)
            <<"\",\"approximation_outcome\":\""<<outcome(last)
            <<"\",\"basis\":\""<<basis(last)<<"\",\"membership\":\""<<status(last.membership)
            <<"\",\"bindings\":\""<<(trajectory?status(trajectory->bindings):"not_checked")
            <<"\",\"feasibility\":\""<<(trajectory?status(trajectory->feasibility):"not_checked")
            <<"\",\"objective\":\""<<(trajectory?status(trajectory->objective):"not_checked")
            <<"\",\"optimality\":\""<<(trajectory?status(trajectory->optimality):"not_checked")
            <<"\",\"completeness\":\""<<(trajectory?status(trajectory->completeness):"not_checked")
            <<"\",\"validated\":\""<<(trajectory?status(trajectory->validated):"not_checked")
            <<"\",\"trajectory_termination\":";
        if(trajectory)std::cout<<'"'<<termination(trajectory->termination)<<'"';
        else std::cout<<"null";
        std::cout<<",\"recomputed_objective\":";
        if(trajectory && trajectory->recomputed_objective)std::cout<<*trajectory->recomputed_objective;
        else std::cout<<"null";
        std::cout<<",\"numerical_achievable_value\":";
        if(last.numerical_achievable_value)std::cout<<*last.numerical_achievable_value;
        else std::cout<<"null";
        std::cout<<",\"residual_count\":"<<(trajectory?trajectory->residuals.size():0)
            <<",\"residuals\":[";
        if(trajectory) {
            bool first=true;
            for(const auto& residual:trajectory->residuals) {
                if(!first)std::cout<<',';
                first=false;
                std::cout<<"{\"field\":"<<std::quoted(residual.field)
                    <<",\"violation\":"<<residual.measure.violation
                    <<",\"scale\":"<<residual.measure.scale
                    <<",\"tolerance\":"<<residual.tolerance
                    <<",\"satisfied\":"<<(residual.satisfied?"true":"false")<<'}';
            }
        }
        std::cout<<"],\"observation_token\":"<<token<<"}\n";
        std::cout.flush();
        if(failures || checked!=batch || elapsed<=0)return false;
    }
    return true;
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=4)throw std::invalid_argument("usage: csl_app01_plan_report BATCH WARMUPS REPETITIONS");
        const auto batch=count(argv[1]),warmups=count(argv[2]),repetitions=count(argv[3]);
        const auto problem=original();
        const auto reference=interval(),point=singleton(),empty=empty_v();
        std::cout.precision(17);
        std::cout<<"{\"event\":\"header\",\"schema\":\"csl.app01-plan-raw/2\",\"provider_id\":\"app01.literal-provider\",\"provider_version\":\"1\",\"batch\":"<<batch
            <<",\"warmups\":"<<warmups<<",\"repetitions\":"<<repetitions<<"}\n";
        for(const auto name:{"valid_plan","invalid_plan","empty_inner"})
            if(!run(problem,fixture(problem,name,reference,point,empty),batch,warmups,repetitions))return 2;
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
