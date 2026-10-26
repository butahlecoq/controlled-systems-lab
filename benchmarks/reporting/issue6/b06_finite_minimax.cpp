#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>
#if defined(__linux__)
#include <sys/resource.h>
#endif

namespace {
using namespace csl;
using namespace csl::optimization;
using nlohmann::json;

template<class T> T take(std::variant<T,Diagnostic> result) {
    if(const auto* error=std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field+": "+error->explanation);
    return std::get<T>(std::move(result));
}

FiniteActionMinimaxRequest b06_request() {
    const SystemModel authored{{{4,1,2},TimeDomain::discrete,
        LinearStage{
            {4,4,{1,0,0,0,-2,1,0,0,0,0,1,0,0,0,-2,1}},
            {4,1,{0.7,0,-1.0/3.0,0}},
            {4,2,{0.05,0,0,0,0,-0.04,0,0}},
            {0,0,0,0}}}, {}};
    const auto system=take(model::snapshot(authored,Vector{0,1,2,3,4,5}));
    const auto initial=take(sets::make_singleton({{"b06-x0"},4,{"x1","x2","x3","x4"}},
        take(numeric::snapshot_vector(Vector{29.31,302,20.354,207}))));
    const auto disturbance=take(sets::make_v({{"b06-w"},2,{"w1","w2"}},
        {take(numeric::snapshot(Matrix{4,2,{-1,-1,-1,1,1,-1,1,1}})),
         take(numeric::snapshot(Matrix{0,2,{}}))}));
    std::vector<sets::SetData> disturbances(5,disturbance);
    std::vector<sets::SetData> safe_sets;
    safe_sets.reserve(6);
    for(std::size_t stage=0;stage<6;++stage)
        safe_sets.push_back(take(sets::make_universal({{"b06-unconstrained-"+std::to_string(stage)},4,{"x1","x2","x3","x4"}})));
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{
        {4,4,{2,0,0,0,0,4,0,-3,0,0,4.5,0,0,-3,0,9}},
        {-60,0,-90,0},1800}));
    return {{"b06-owner-confirmed-disturbance-v1"},{"b06-finite-action-reference"},
        system,initial,{1,{{1},{0.3},{0},{-0.3},{-1}}},
        std::move(disturbances),std::move(safe_sets),objective};
}

json terminal_vertices(const sets::SetData& set) {
    const auto representation=set.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(!v || v->rays.rows()!=0) throw std::runtime_error("terminal result is not a bounded V set");
    json result=json::array();
    for(std::size_t row=0;row<v->vertices.rows();++row) {
        json point=json::array();
        for(std::size_t column=0;column<v->vertices.cols();++column)
            point.push_back(v->vertices(row,column));
        result.push_back(std::move(point));
    }
    return result;
}

json run_once(std::size_t batch,bool include_geometry=false) {
    const auto started=std::chrono::steady_clock::now();
    const auto result=finite_action_minimax(b06_request(),{3125,1024,0.0});
    const auto stopped=std::chrono::steady_clock::now();
    if(!std::holds_alternative<FiniteMinimaxOptimal>(result))
        throw std::runtime_error("B06 reference did not return a numerical optimum");
    const auto& optimum=std::get<FiniteMinimaxOptimal>(result);
    if(optimum.plans.size()!=3125 || optimum.minimizing_plan_indices.empty())
        throw std::runtime_error("B06 plan catalogue count mismatch");
    const std::vector<std::size_t> reported_plan{3,0,2,2,1};
    std::size_t reported_index=0;
    for(const auto digit:reported_plan) reported_index=reported_index*5+digit;
    const auto& record=optimum.plans.at(reported_index);
    if(!std::holds_alternative<FinitePlanFeasible>(record))
        throw std::runtime_error("Printed L09 plan was rejected");
    const auto& printed=std::get<FinitePlanFeasible>(record);
    std::size_t checked_vertices=0;
    for(const auto& plan:optimum.plans) {
        if(!std::holds_alternative<FinitePlanFeasible>(plan))
            throw std::runtime_error("Unconstrained B06 unexpectedly rejected a plan");
        checked_vertices+=std::get<FinitePlanFeasible>(plan).evaluated_vertices;
    }
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(stopped-started).count();
    json row={{"schema","csl.issue6-b06-run/1"},{"batch",batch},
        {"source_commit",CSL_ISSUE6_SOURCE_COMMIT},
        {"fixture_sha256",CSL_ISSUE6_FIXTURE_SHA256},
        {"driver_sha256",CSL_ISSUE6_DRIVER_SHA256},
        {"status","numerical_optimal"},{"assurance","numerical"},
        {"elapsed_ns",elapsed},{"plan_count",optimum.plans.size()},
        {"evaluated_terminal_vertices",checked_vertices},
        {"minimizing_plan_indices",optimum.minimizing_plan_indices},
        {"objective_squared",optimum.value},{"objective_norm",std::sqrt(optimum.value)},
        {"printed_plan_index",reported_index},{"printed_plan_worst_squared",printed.worst_value},
        {"printed_plan_worst_norm",std::sqrt(printed.worst_value)},
        {"printed_plan_maximizer",printed.maximizer}};
#if defined(__linux__)
    rusage usage{};
    if(getrusage(RUSAGE_SELF,&usage)==0) row["process_peak_rss_kib"]=usage.ru_maxrss;
#else
    row["process_peak_rss_kib"]=nullptr;
#endif
    if(include_geometry) {
        const auto& best=std::get<FinitePlanFeasible>(optimum.plans.at(optimum.minimizing_plan_indices.front()));
        row["winner_terminal_vertices"]=terminal_vertices(best.terminal);
        row["printed_terminal_vertices"]=terminal_vertices(printed.terminal);
    }
    return row;
}
}

int main(int argc,char** argv) {
    try {
        std::size_t batches=1;
        bool geometry=false;
        if(argc==3 && std::string_view(argv[1])=="--measure") batches=std::stoul(argv[2]);
        else if(argc==2 && std::string_view(argv[1])=="--geometry") geometry=true;
        else if(argc!=1) throw std::runtime_error("usage: b06_finite_minimax [--measure batches]");
        if(batches==0 || batches>25) throw std::runtime_error("batch count must be 1..25");
        if(geometry) std::cout<<run_once(0,true).dump()<<'\n';
        else for(std::size_t batch=0;batch<=batches;++batch)
            std::cout<<run_once(batch).dump()<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"B06 run rejected: "<<error.what()<<'\n';
        return 2;
    }
}
