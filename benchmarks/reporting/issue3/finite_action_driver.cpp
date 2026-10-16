#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::optimization;
using nlohmann::json;
constexpr std::string_view source_commit="6c1cde0fcaabf40b8fdcb5973f36465cdccdcaf4";

template<class T> T take(std::variant<T,Diagnostic> result) {
    if(!std::holds_alternative<T>(result)) throw std::runtime_error("invalid report fixture");
    return std::get<T>(std::move(result));
}

sets::SetData singleton(std::string id,double value) {
    return take(sets::make_singleton({{std::move(id)},1,{"x"}},
        take(numeric::snapshot_vector(Vector{value}))));
}
sets::SetData interval(std::string id,double lo,double hi) {
    return take(sets::make_v({{std::move(id)},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{lo,hi}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
}
sets::SetData safe(double bound) {
    return take(sets::make_h({{"safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{bound,bound})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
}
FiniteActionMinimaxRequest integrator(double bound) {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    return {{"issue3-integrator"},{"report-integrator"},
        take(model::snapshot(authored,Vector{0,1})),singleton("x0",0),
        {1,{{0},{1}}},{interval("w0",0,2)},{safe(10),safe(bound)},
        std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}},{-2},1}))};
}

json l19() {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    const auto initial=take(sets::make_v({{"l19"},1,{"x"}},
        {take(numeric::snapshot(Matrix{3,1,{0,1,2}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}},{-2},1}));
    Vector values;
    for(const double point:Vector{0,1,2}) {
        const auto result=evaluate(objective,Vector{point});
        if(!std::holds_alternative<double>(result)) throw std::runtime_error("L19 evaluation failed");
        values.push_back(std::get<double>(result));
    }
    if(values!=Vector{1,0,1}) throw std::runtime_error("L19 stationary interior sample mismatch");
    const FiniteActionMinimaxRequest input{{"issue3-l19"},{"report-l19"},
        take(model::snapshot(authored,Vector{0})),initial,{1,{}},{},
        {take(sets::make_universal({{"l19-safe"},1,{"x"}}))},objective};
    const auto outcome=finite_action_minimax(input,{1,3,0});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
        throw std::runtime_error("L19 minimax outcome mismatch");
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    if(result.value!=1 || result.plans.size()!=1 ||
       result.minimizing_plan_indices!=std::vector<std::size_t>{0} ||
       !std::holds_alternative<FinitePlanFeasible>(result.plans[0]) ||
       std::get<FinitePlanFeasible>(result.plans[0]).evaluated_vertices!=3)
        throw std::runtime_error("L19 literal minimax oracle mismatch");
    return {{"status","numerical_optimal"},{"value",result.value},{"plan_count",result.plans.size()},
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"evaluated_vertices",3},
        {"sampled_objective_values",values}};
}

json integrator_case() {
    const auto outcome=finite_action_minimax(integrator(10),{2,2,0});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
        throw std::runtime_error("integrator minimax outcome mismatch");
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    if(result.value!=1 || result.plans.size()!=2 ||
       result.minimizing_plan_indices!=std::vector<std::size_t>{0})
        throw std::runtime_error("integrator literal minimax oracle mismatch");
    Vector values;
    for(const auto& record:result.plans) {
        if(!std::holds_alternative<FinitePlanFeasible>(record) ||
           std::get<FinitePlanFeasible>(record).evaluated_vertices!=2)
            throw std::runtime_error("integrator plan evidence mismatch");
        values.push_back(std::get<FinitePlanFeasible>(record).worst_value);
    }
    if(values!=Vector{1,4}) throw std::runtime_error("integrator worst values mismatch");
    return {{"status","numerical_optimal"},{"value",result.value},{"plan_count",result.plans.size()},
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"worst_values",values}};
}

json infeasible_case() {
    const auto outcome=finite_action_minimax(integrator(0.5),{2,2,0});
    if(!std::holds_alternative<FiniteMinimaxInfeasible>(outcome))
        throw std::runtime_error("all-infeasible outcome mismatch");
    const auto& rejected=std::get<FiniteMinimaxInfeasible>(outcome).rejected_plans;
    if(rejected.size()!=2 || rejected[0].stage!=1 || rejected[1].stage!=1 ||
       rejected[0].violating_successor!=Vector{2} ||
       rejected[1].violating_successor!=Vector{1})
        throw std::runtime_error("all-infeasible literal oracle mismatch");
    return {{"status","infeasible"},{"rejected_plans",rejected.size()},{"violating_stage",1}};
}

json empty_case() {
    auto input=integrator(10);
    input.actions.catalogue.clear();
    if(!std::holds_alternative<FiniteMinimaxEmptyCatalogue>(
           finite_action_minimax(input,{2,2,0})))
        throw std::runtime_error("empty catalogue oracle mismatch");
    return {{"status","empty_catalogue"}};
}

json no_scenarios_case() {
    auto input=integrator(10);
    input.disturbances[0]=take(sets::make_empty({{"empty-w"},1,{"x"}}));
    if(!std::holds_alternative<FiniteMinimaxNoScenarios>(
           finite_action_minimax(input,{2,2,0})))
        throw std::runtime_error("no-scenarios oracle mismatch");
    return {{"status","no_scenarios"}};
}

json cancelled_case() {
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context{};
    context.cancellation=cancellation.get_token();
    const auto outcome=finite_action_minimax(integrator(10),{2,2,0},context);
    if(!std::holds_alternative<OperationStopped>(outcome) ||
       std::get<OperationStopped>(outcome).reason!=StopReason::cancelled)
        throw std::runtime_error("cancelled search oracle mismatch");
    return {{"status","stopped"},{"reason","cancelled"}};
}

json b08() {
    const SystemModel authored{{{4,1,2},TimeDomain::discrete,
        LinearStage{{4,4,{1,0,0,0,-25,1,0,0,0,0,1,0,0,0,-25,1}},
                    {4,1,{20.073,0,-10.473,0}},
                    {4,2,{1,0,0,0,0,-1,0,0}}, {0,0,0,0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1,2,3,4}));
    const auto initial=take(sets::make_singleton({{"b08-x0"},4,{}},
        take(numeric::snapshot_vector(Vector{1182.074,119560,459.832,45260}))));
    std::vector<sets::SetData> disturbances;
    for(std::size_t stage=0;stage<4;++stage) {
        const double a=0.1+0.1*stage,b=0.1+0.3*stage;
        disturbances.push_back(take(sets::make_v({{"b08-w"+std::to_string(stage)},2,{}},
            {take(numeric::snapshot(Matrix{4,2,{-a,-b,-a,b,a,-b,a,b}})),
             take(numeric::snapshot(Matrix{0,2,{}}))})));
    }
    std::vector<sets::SetData> safe_sets;
    for(std::size_t stage=0;stage<5;++stage)
        safe_sets.push_back(take(sets::make_universal({{"b08-safe"+std::to_string(stage)},4,{}})));
    const auto objective=std::get<Objective>(snapshot(ResidualNormTerminal{
        {4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}},{1200,0,450,0}}));
    const FiniteActionMinimaxRequest input{{"b08-displayed-rounded"},{"issue3-report-b08"},
        system,initial,{1,{{0.6},{0.3},{0},{-0.3},{-0.6}}},
        disturbances,safe_sets,objective};
    const auto outcome=finite_action_minimax(input,{625,256,1e-8});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
        throw std::runtime_error("B08 whole-catalogue outcome mismatch");
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    std::size_t evaluated=0;
    for(const auto& record:result.plans) {
        if(!std::holds_alternative<FinitePlanFeasible>(record))
            throw std::runtime_error("B08 plan rejected");
        const auto& plan=std::get<FinitePlanFeasible>(record);
        if(plan.evaluated_vertices!=256)throw std::runtime_error("B08 plan corner count mismatch");
        evaluated+=plan.evaluated_vertices;
    }
    if(result.plans.size()!=625 || evaluated!=160000 ||
       result.minimizing_plan_indices!=std::vector<std::size_t>{17,33,129} ||
       std::abs(result.value-67.150601101407)>1e-8)
        throw std::runtime_error("B08 displayed-reference literal oracle mismatch");
    return {{"status","numerical_optimal"},{"value",result.value},
        {"plan_count",result.plans.size()},{"evaluated_vertices",evaluated},
        {"minimizing_plan_indices",result.minimizing_plan_indices}};
}

using Case=json (*)();
void emit(std::string_view name,Case run,std::size_t round,bool warmup,std::size_t batch) {
    const auto start=std::chrono::steady_clock::now();
    json result;
    for(std::size_t i=0;i<batch;++i) result=run();
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now()-start).count();
    if(elapsed<=0)throw std::runtime_error("nonpositive clock interval");
    std::cout<<json{{"schema","csl.issue3-raw-trial/1"},{"fixture",name},
        {"source_commit",source_commit},{"harness_commit",CSL_ISSUE3_HARNESS_COMMIT},
        {"round",round},{"warmup",warmup},{"batch",batch},
        {"checked_calls",batch},{"elapsed_ns",elapsed},{"result",result}}.dump()<<'\n';
}
} // namespace

int main(int argc,char** argv) {
    try {
        if(argc!=2 && argc!=3)throw std::invalid_argument("usage: driver --smoke | --measure ROUNDS");
        const std::string_view mode(argv[1]);
        std::size_t rounds=1;
        if(mode=="--measure" && argc==3) {
            const std::string digits(argv[2]);
            if(digits.empty() || digits.find_first_not_of("0123456789")!=std::string::npos)
                throw std::invalid_argument("rounds must be a decimal integer");
            rounds=std::stoull(digits);
            if(rounds<7 || rounds>1000)throw std::invalid_argument("rounds outside 7..1000");
        } else if(mode!="--smoke" || argc!=2)
            throw std::invalid_argument("usage: driver --smoke | --measure ROUNDS");
        const std::pair<std::string_view,Case> cases[]{
            {"l19",l19},{"integrator",integrator_case},{"all_infeasible",infeasible_case},
            {"empty_catalogue",empty_case},{"no_scenarios",no_scenarios_case},
            {"cancelled",cancelled_case},
            {"b08_rounded",b08}};
        for(std::size_t round=0;round<rounds+(mode=="--measure");++round) {
            const bool warmup=mode=="--measure" && round==0;
            const auto run_case=[&](std::string_view name,Case run) {
                const std::size_t batch=mode!="--measure" || name=="b08_rounded"?1:
                    name=="l19"?10000:5000;
                emit(name,run,round,warmup,batch);
            };
            if(round%2==0)for(const auto& [name,run]:cases)run_case(name,run);
            else for(auto it=std::rbegin(cases);it!=std::rend(cases);++it)
                run_case(it->first,it->second);
        }
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
