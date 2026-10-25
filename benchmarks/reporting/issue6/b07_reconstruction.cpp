#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using nlohmann::json;

template<class T> T take(std::variant<T,Diagnostic> result) {
    if(const auto* error=std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field+": "+error->explanation);
    return std::get<T>(std::move(result));
}

struct Case { int stocks; int lambda; int archive_disturbance; };

FiniteActionMinimaxRequest request(Case c) {
    const double a=c.archive_disturbance ? 0.06 : 0.05;
    const double b=c.archive_disturbance ? -0.05 : -0.04;
    const SystemModel authored{{{4,1,2},TimeDomain::discrete,
        LinearStage{{4,4,{1,0,0,0,-2,1,0,0,0,0,1,0,0,0,-2,1}},
            {4,1,{0.7,0,-1.0/3.0,0}},
            {4,2,{a,0,0,0,0,b,0,0}}, {0,0,0,0}}}, {}};
    const auto system=take(model::snapshot(authored,Vector{0,1,2,3,4,5}));
    const auto initial=take(sets::make_singleton({{"b07-x0"},4,{"x1","x2","x3","x4"}},
        take(numeric::snapshot_vector(Vector{29.375,c.stocks?302.0:305.0,20.4,c.stocks?207.0:205.0}))));
    const auto disturbance=take(sets::make_v({{"b07-w"},2,{"w_oxidizer","w_fuel"}},
        {take(numeric::snapshot(Matrix{4,2,{-1,-1,-1,1,1,-1,1,1}})),
         take(numeric::snapshot(Matrix{0,2,{}}))}));
    std::vector<sets::SetData> disturbances(5,disturbance);
    std::vector<sets::SetData> safe;
    safe.push_back(take(sets::make_universal({{"b07-stage-0"},4,{"x1","x2","x3","x4"}})));
    const Matrix H{6,4,{1,0,0,0,-1,0,0,0,0,0,1,0,0,0,-1,0,0,-1,0,0,0,0,0,-1}};
    for(std::size_t stage=1;stage<=5;++stage)
        safe.push_back(take(sets::make_h({{"b07-stage-"+std::to_string(stage)},4,{"x1","x2","x3","x4"}},
            {take(numeric::snapshot(H)),take(numeric::snapshot_vector(Vector{31,-29,20.5,-19.5,0,0})),
             take(numeric::snapshot(Matrix{0,4,{}})),take(numeric::snapshot_vector(Vector{}))})));
    const double lambda=static_cast<double>(c.lambda);
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{
        {4,4,{2,0,0,0,0,2+2*lambda,0,-3*lambda,0,0,4.5,0,0,-3*lambda,0,4.5+4.5*lambda}},
        {-60,0,-90,0},1800}));
    return {{"b07-reconstruction-s"+std::to_string(c.stocks)+"-l"+std::to_string(c.lambda)+"-d"+std::to_string(c.archive_disturbance)},
        {"b07-finite-action-reference"},system,initial,
        {1,{{1},{0.3},{0},{-0.3},{-1}}},std::move(disturbances),std::move(safe),objective};
}

json points(const sets::SetData& set) {
    const auto repr=set.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&repr);
    if(!v || v->rays.rows()!=0) throw std::runtime_error("terminal result is not bounded V");
    json out=json::array();
    for(std::size_t i=0;i<v->vertices.rows();++i) {
        json row=json::array();
        for(std::size_t j=0;j<v->vertices.cols();++j) row.push_back(v->vertices(i,j));
        out.push_back(std::move(row));
    }
    return out;
}

json run_once(Case c) {
    const auto start=std::chrono::steady_clock::now();
    constexpr double near_optimal_tolerance=1e-9;
    const auto outcome=finite_action_minimax(request(c),{3125,1024,near_optimal_tolerance});
    const auto stop=std::chrono::steady_clock::now();
    if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome)) {
        if(const auto* rejected=std::get_if<FiniteMinimaxInfeasible>(&outcome))
            throw std::runtime_error("B07 infeasible plan set: "+std::to_string(rejected->rejected_plans.size())+
                " rejected; first rejection stage="+(rejected->rejected_plans.empty()?"none":std::to_string(rejected->rejected_plans.front().stage)));
        if(const auto* unsupported=std::get_if<Unsupported>(&outcome))
            throw std::runtime_error("B07 unsupported: "+(unsupported->diagnostics.empty()?std::string("no diagnostic"):unsupported->diagnostics.front().explanation));
        if(std::holds_alternative<FiniteMinimaxNoScenarios>(outcome)) throw std::runtime_error("B07 has no scenarios");
        if(std::holds_alternative<FiniteMinimaxEmptyCatalogue>(outcome)) throw std::runtime_error("B07 has empty catalogue");
        throw std::runtime_error("B07 operation stopped");
    }
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    if(result.plans.size()!=3125 || result.minimizing_plan_indices.empty())
        throw std::runtime_error("B07 plan catalogue mismatch");
    const auto& first=std::get<FinitePlanFeasible>(result.plans.at(result.minimizing_plan_indices.front()));
    std::size_t feasible=0;
    for(const auto& p:result.plans) if(std::holds_alternative<FinitePlanFeasible>(p)) ++feasible;
    return {{"case_id","B07-reconstruction-s"+std::to_string(c.stocks)+"-l"+std::to_string(c.lambda)+"-d"+std::to_string(c.archive_disturbance)},
        {"initial_stock_oxidizer_kg",c.stocks?302:305},{"initial_stock_fuel_kg",c.stocks?207:205},
        {"terminal_lambda",c.lambda},{"disturbance_coefficients",{c.archive_disturbance?0.06:0.05,c.archive_disturbance?-0.05:-0.04}},
        {"modeled_horizon_seconds",10},{"step_seconds",2},{"status","numerical_optimal"},
        {"plans_total",result.plans.size()},{"plans_feasible",feasible},
        {"near_optimal_tolerance",near_optimal_tolerance},
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"value_squared",result.value},
        {"value_norm",std::sqrt(result.value)},
        {"elapsed_ns",std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count()},
        {"winner_terminal_vertices_x1_x3_x2_x4",[&](){json a=json::array();for(const auto& p:points(first.terminal))a.push_back({p[0],p[2],p[1],p[3]});return a;}()}};
}

json run(Case c) {
    std::vector<json> runs;
    runs.reserve(8);
    for(int i=0;i<8;++i) runs.push_back(run_once(c));
    std::vector<std::int64_t> measured;
    for(std::size_t i=1;i<runs.size();++i) measured.push_back(runs[i]["elapsed_ns"].get<std::int64_t>());
    auto sorted=measured;
    std::sort(sorted.begin(),sorted.end());
    json result=runs.back();
    result["warmup_calls"]=1;
    result["measured_calls"]=measured.size();
    result["measured_elapsed_ns"]=measured;
    result["median_elapsed_ns"]=sorted[3];
    result["min_elapsed_ns"]=sorted.front();
    result["max_elapsed_ns"]=sorted.back();
    result.erase("elapsed_ns");
    return result;
}
}

int main() {
    try {
        for(int stocks=0;stocks<2;++stocks)
            for(int lambda=0;lambda<2;++lambda)
                for(int disturbance=0;disturbance<2;++disturbance)
                    std::cout<<run({stocks,lambda,disturbance}).dump()<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"B07 reference failed: "<<error.what()<<'\n';
        return 2;
    }
}
