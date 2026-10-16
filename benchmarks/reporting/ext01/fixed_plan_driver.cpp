#include <csl/optimization/worst_case_vertex.hpp>
#include <csl/reachability/fixed_plan_disturbance.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::reachability;
using nlohmann::json;

template<class T> T take(std::variant<T,Diagnostic> result) {
    if(!std::holds_alternative<T>(result))throw std::runtime_error("invalid report fixture");
    return std::get<T>(std::move(result));
}

sets::SetData interval(std::string id,double lo,double hi,std::string label) {
    return take(sets::make_v({{std::move(id)},1,{std::move(label)}},
        {take(numeric::snapshot(Matrix{2,1,{lo,hi}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
}

sets::SetData safe(double lo,double hi) {
    return take(sets::make_h({{"safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{hi,-lo})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
}

FixedPlanRequest integrator(double bound) {
    SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    return {take(model::snapshot(authored,Vector{0,1,2})),
        take(sets::make_singleton({{"x0"},1,{"x"}},
            take(numeric::snapshot_vector(Vector{0})))),
        {{0},{0}}, {interval("w0",-1,1,"w"),interval("w1",-1,1,"w")},
        {safe(-3,3),safe(-bound,bound),safe(-3,3)}, {"ext01-report-integrator"}};
}

json l19() {
    const auto domain=take(sets::make_v({{"l19"},1,{"x"}},
        {take(numeric::snapshot(Matrix{3,1,{0,1,2}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
    auto result=optimization::snapshot(QuadraticTerminal{{1,1,{2}},{-2},1});
    if(!std::holds_alternative<optimization::Objective>(result))
        throw std::runtime_error("L19 objective rejected");
    const auto worst=optimization::worst_case_vertex(domain,
        std::get<optimization::Objective>(result),3);
    if(!std::holds_alternative<optimization::WorstCaseValue>(worst))
        throw std::runtime_error("L19 did not return a value");
    const auto& value=std::get<optimization::WorstCaseValue>(worst);
    if(value.value!=1 || value.maximizer!=Vector{0} || value.evaluated_vertices!=3)
        throw std::runtime_error("L19 literal oracle mismatch");
    return {{"status","numerical_value"},{"worst_value",value.value},
        {"maximizer",value.maximizer},{"evaluated_vertices",value.evaluated_vertices},
        {"stationary_midpoint_value",0}};
}

json integrator_case(bool narrow) {
    const auto result=fixed_plan_disturbance(integrator(narrow?0.5:3),8);
    if(narrow) {
        if(!std::holds_alternative<FixedPlanViolation>(result))
            throw std::runtime_error("integrator violation oracle mismatch");
        const auto& violation=std::get<FixedPlanViolation>(result);
        if(violation.stage!=1 || violation.violating_successor!=Vector{-1})
            throw std::runtime_error("integrator violation coordinates mismatch");
        return {{"status","robust_violation"},{"stage",violation.stage},
            {"violating_successor",violation.violating_successor}};
    }
    if(!std::holds_alternative<FixedPlanReachable>(result))
        throw std::runtime_error("integrator did not return a tube");
    const auto& tube=std::get<FixedPlanReachable>(result);
    if(tube.stages.size()!=3)throw std::runtime_error("integrator stage count mismatch");
    const auto representation=tube.stages.back().representation();
    if(!std::holds_alternative<sets::VRepresentation>(representation))
        throw std::runtime_error("integrator terminal representation mismatch");
    const auto& vertices=std::get<sets::VRepresentation>(representation).vertices;
    if(vertices.rows()!=4 || vertices(0,0)!=-2 || vertices(1,0)!=0 ||
       vertices(2,0)!=0 || vertices(3,0)!=2)
        throw std::runtime_error("integrator terminal vertices mismatch");
    const auto objective=optimization::snapshot(QuadraticTerminal{{1,1,{2}},{0},0});
    if(!std::holds_alternative<optimization::Objective>(objective))
        throw std::runtime_error("integrator objective rejected");
    const auto worst=optimization::worst_case_vertex(tube.stages.back(),
        std::get<optimization::Objective>(objective),8);
    if(!std::holds_alternative<optimization::WorstCaseValue>(worst) ||
       std::get<optimization::WorstCaseValue>(worst).value!=4)
        throw std::runtime_error("integrator worst-case oracle mismatch");
    return {{"status","numerical_reachable"},{"stages",tube.stages.size()},
        {"terminal_candidates",vertices.rows()},{"terminal_worst_value",4}};
}

json b08() {
    SystemModel authored{{{4,1,2},TimeDomain::discrete,
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
    const auto objective=optimization::snapshot(ResidualNormTerminal{
        {4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}},{1200,0,450,0}});
    if(!std::holds_alternative<optimization::Objective>(objective))
        throw std::runtime_error("B08 objective rejected");
    const Vector actions{0.6,0.3,0,-0.3,-0.6};
    double best=std::numeric_limits<double>::infinity();
    std::size_t ties=0,plans=0,histories=0;
    for(const auto u0:actions)for(const auto u1:actions)
      for(const auto u2:actions)for(const auto u3:actions) {
        const FixedPlanRequest plan{system,initial,{{u0},{u1},{u2},{u3}},disturbances,safe_sets,
                                    {"b08-plan-"+std::to_string(plans++)}};
        const auto propagated=fixed_plan_disturbance(plan,256);
        if(!std::holds_alternative<FixedPlanReachable>(propagated))
            throw std::runtime_error("B08 fixed plan did not return a tube");
        const auto& terminal=std::get<FixedPlanReachable>(propagated).stages.back();
        const auto representation=terminal.representation();
        if(!std::holds_alternative<sets::VRepresentation>(representation) ||
           std::get<sets::VRepresentation>(representation).vertices.rows()!=256)
            throw std::runtime_error("B08 history count mismatch");
        histories+=256;
        const auto worst=optimization::worst_case_vertex(terminal,
            std::get<optimization::Objective>(objective),256);
        if(!std::holds_alternative<optimization::WorstCaseValue>(worst))
            throw std::runtime_error("B08 worst case did not return a value");
        const auto value=std::get<optimization::WorstCaseValue>(worst).value;
        if(value<best-1e-8) {best=value;ties=1;}
        else if(std::abs(value-best)<=1e-8)++ties;
    }
    if(plans!=625 || histories!=160000 || std::abs(best-67.150601101407)>1e-8 || ties!=3)
        throw std::runtime_error("B08 independent rounded-reference oracle mismatch");
    return {{"status","numerical_reference"},{"plan_count",plans},
        {"disturbance_histories",histories},{"minimum_worst_value",best},
        {"ties_at_1e-8",ties}};
}

using Case=json (*)();
json feasible() {return integrator_case(false);}
json violating() {return integrator_case(true);}

void emit(std::string_view name,Case run,std::size_t round,bool warmup,std::size_t batch) {
    const auto start=std::chrono::steady_clock::now();
    json result;
    for(std::size_t i=0;i<batch;++i)result=run();
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now()-start).count();
    if(elapsed<=0)throw std::runtime_error("nonpositive clock interval");
    std::cout<<json{{"schema","csl.ext01-raw-trial/1"},{"fixture",name},
        {"round",round},{"warmup",warmup},{"batch",batch},
        {"checked_calls",batch},{"elapsed_ns",elapsed},
        {"result",result}}.dump()<<'\n';
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
            {"l19",l19},{"integrator_feasible",feasible},
            {"integrator_violation",violating},{"b08_rounded",b08}};
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
