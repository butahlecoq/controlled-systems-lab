#include <csl/optimization/finite_action_minimax.hpp>
#include "fuel_timing.hpp"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
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
    const auto input=request(c);
    const auto solver_start=std::chrono::steady_clock::now();
    const auto outcome=finite_action_minimax(input,{3125,1024,near_optimal_tolerance});
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
        {"source_commit",CSL_ISSUE6_B07_SOURCE_COMMIT},
        {"driver_sha256",CSL_ISSUE6_B07_DRIVER_SHA256},
        {"scenario_sha256",CSL_ISSUE6_B07_SCENARIO_SHA256},
        {"compiler_id",CSL_ISSUE6_B07_COMPILER_ID},
        {"compiler_version",CSL_ISSUE6_B07_COMPILER_VERSION},
        {"build_type",CSL_ISSUE6_B07_BUILD_TYPE},
        {"executable_sha256",std::getenv("CSL_ISSUE6_B07_EXECUTABLE_SHA256")?
            std::getenv("CSL_ISSUE6_B07_EXECUTABLE_SHA256"):"not-supplied"},
        {"initial_stock_oxidizer_kg",c.stocks?302:305},{"initial_stock_fuel_kg",c.stocks?207:205},
        {"initial_flow_oxidizer_kg_per_second",29.375},{"initial_flow_fuel_kg_per_second",20.4},
        {"terminal_lambda",c.lambda},{"disturbance_coefficients",{c.archive_disturbance?0.06:0.05,c.archive_disturbance?-0.05:-0.04}},
        {"modeled_horizon_seconds",10},{"step_seconds",2},{"status","numerical_optimal"},
        {"plans_total",result.plans.size()},{"plans_feasible",feasible},
        {"near_optimal_tolerance",near_optimal_tolerance},
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"value_squared",result.value},
        {"value_norm",std::sqrt(result.value)},
        {"elapsed_ns",std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count()},
        {"solver_call_wall_ns",std::chrono::duration_cast<std::chrono::nanoseconds>(stop-solver_start).count()},
        {"winner_terminal_vertices_x1_x3_x2_x4",[&](){json a=json::array();for(const auto& p:points(first.terminal))a.push_back({p[0],p[2],p[1],p[3]});return a;}()}};
}

json run(Case c,bool retain_attempt_rows=false) {
    std::vector<json> runs;
    runs.reserve(8);
    for(int i=0;i<8;++i) runs.push_back(run_once(c));
    std::vector<std::int64_t> measured;
    std::vector<std::int64_t> solver_measured;
    for(std::size_t i=1;i<runs.size();++i) {
        measured.push_back(runs[i]["elapsed_ns"].get<std::int64_t>());
        solver_measured.push_back(runs[i]["solver_call_wall_ns"].get<std::int64_t>());
    }
    auto sorted=measured;
    std::sort(sorted.begin(),sorted.end());
    json result=runs.back();
    result["warmup_calls"]=1;
    result["warmup_elapsed_ns"]=runs.front()["elapsed_ns"];
    result["warmup_solver_call_wall_ns"]=runs.front()["solver_call_wall_ns"];
    result["measured_calls"]=measured.size();
    result["measured_elapsed_ns"]=measured;
    result["median_elapsed_ns"]=sorted[3];
    result["min_elapsed_ns"]=sorted.front();
    result["max_elapsed_ns"]=sorted.back();
    std::sort(solver_measured.begin(),solver_measured.end());
    result["median_solver_call_wall_ns"]=solver_measured[3];
    result["measured_solver_call_wall_ns"]=solver_measured;
    if(retain_attempt_rows) {
        json attempt_rows=json::array();
        for(std::size_t index=0;index<runs.size();++index) {
            runs[index]["attempt_index"]=index;
            runs[index]["is_warmup"]=index==0;
            attempt_rows.push_back(std::move(runs[index]));
        }
        result["attempt_rows"]=std::move(attempt_rows);
    }
    result.erase("elapsed_ns");
    return result;
}

json phase_run(Case c) {
    const auto request_started=std::chrono::steady_clock::now();
    const auto input=request(c);
    const auto request_ready=std::chrono::steady_clock::now();
    auto timed=csl::issue6::timing::run_enabled(input,{3125,1024,1e-9},
        "b07-phase-s"+std::to_string(c.stocks)+"-l"+std::to_string(c.lambda)+"-d"+
            std::to_string(c.archive_disturbance),CSL_ISSUE6_B07_SCENARIO_SHA256);
    if(!std::holds_alternative<FiniteMinimaxOptimal>(timed.outcome))
        throw std::runtime_error("B07 instrumented call did not return an optimum");
    const auto& result=std::get<FiniteMinimaxOptimal>(timed.outcome);
    if(result.plans.size()!=3125 || result.minimizing_plan_indices.empty())
        throw std::runtime_error("B07 instrumented plan catalogue mismatch");
    std::size_t feasible=0;
    for(const auto& plan:result.plans)if(std::holds_alternative<FinitePlanFeasible>(plan))++feasible;
    const auto& winner=std::get<FinitePlanFeasible>(result.plans.at(result.minimizing_plan_indices.front()));
    json terminal_points=json::array();
    for(const auto& point:points(winner.terminal))
        terminal_points.push_back({point[0],point[2],point[1],point[3]});
    const auto request_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(request_ready-request_started).count();
    auto phase=csl::issue6::timing::phase_json(timed.report,timed.collector_setup_ns,timed.solver_call_ns);
    phase["request_construction_ns"]=request_ns;
    phase["public_call_wall_ns"]=request_ns+timed.collector_setup_ns+timed.solver_call_ns;
    return {{"case_id","B07-reconstruction-s"+std::to_string(c.stocks)+"-l"+
            std::to_string(c.lambda)+"-d"+std::to_string(c.archive_disturbance)},
        {"source_commit",CSL_ISSUE6_B07_SOURCE_COMMIT},{"driver_sha256",CSL_ISSUE6_B07_DRIVER_SHA256},
        {"scenario_sha256",CSL_ISSUE6_B07_SCENARIO_SHA256},
        {"status","numerical_optimal"},{"plan_count",result.plans.size()},
        {"plans_feasible",feasible},{"minimizing_plan_indices",result.minimizing_plan_indices},
        {"value_squared",result.value},{"winner_terminal_vertices_x1_x3_x2_x4",std::move(terminal_points)},
        {"phase_timing",std::move(phase)}};
}
}

int main(int argc,char** argv) {
    try {
        const bool phase_timing=argc==2 && std::string_view(argv[1])=="--phase-timing";
        if(argc>2 || (argc==2 && !phase_timing))
            throw std::runtime_error("usage: csl_issue6_b07_report [--phase-timing]");
        for(int stocks=0;stocks<2;++stocks)
            for(int lambda=0;lambda<2;++lambda)
                for(int disturbance=0;disturbance<2;++disturbance) {
                    const Case c{stocks,lambda,disturbance};
                    if(!phase_timing)std::cout<<run(c).dump()<<'\n';
                    else {
                        const auto baseline=run(c,true);
                        auto measured=phase_run(c);
                        if(baseline.at("plans_total")!=measured.at("plan_count") ||
                           baseline.at("plans_feasible")!=measured.at("plans_feasible") ||
                           baseline.at("minimizing_plan_indices")!=measured.at("minimizing_plan_indices") ||
                           baseline.at("value_squared")!=measured.at("value_squared"))
                            throw std::runtime_error("B07 instrumentation changed the numerical result");
                        for(const auto& attempt:baseline.at("attempt_rows"))
                            if(attempt.at("plans_total")!=measured.at("plan_count") ||
                               attempt.at("plans_feasible")!=measured.at("plans_feasible") ||
                               attempt.at("minimizing_plan_indices")!=measured.at("minimizing_plan_indices") ||
                               attempt.at("value_squared")!=measured.at("value_squared") ||
                               attempt.at("winner_terminal_vertices_x1_x3_x2_x4")!=
                                   measured.at("winner_terminal_vertices_x1_x3_x2_x4"))
                                throw std::runtime_error("A B07 baseline attempt output differs from the instrumented result");
                        measured["phase_timing"]["outcome_fields_match_exactly"]=true;
                        measured["phase_timing"]["uninstrumented_median_solver_call_wall_ns"]=
                            baseline.at("median_solver_call_wall_ns");
                        measured["phase_timing"]["uninstrumented_median_public_call_wall_ns"]=
                            baseline.at("median_elapsed_ns");
                        measured["phase_timing"]["uninstrumented_warmup_elapsed_ns"]=
                            baseline.at("warmup_elapsed_ns");
                        measured["phase_timing"]["uninstrumented_warmup_solver_call_wall_ns"]=
                            baseline.at("warmup_solver_call_wall_ns");
                        measured["phase_timing"]["uninstrumented_measured_elapsed_ns"]=
                            baseline.at("measured_elapsed_ns");
                        measured["phase_timing"]["uninstrumented_measured_solver_call_wall_ns"]=
                            baseline.at("measured_solver_call_wall_ns");
                        measured["phase_timing"]["uninstrumented_attempt_rows"]=
                            baseline.at("attempt_rows");
                        measured["phase_timing"]["baseline_warmup_repetitions"]=1;
                        measured["phase_timing"]["baseline_measured_repetitions"]=7;
                        measured["phase_timing"]["pair_order"]={"uninstrumented-seven-sample-batch","instrumented-single-call"};
                        const auto serialization_started=std::chrono::steady_clock::now();
                        const auto serialized=measured.dump();
                        measured["phase_timing"]["serialization_ns"]=
                            std::chrono::duration_cast<std::chrono::nanoseconds>(
                                std::chrono::steady_clock::now()-serialization_started).count();
                        measured["phase_timing"]["pre_record_serialized_bytes"]=serialized.size();
                        std::cout<<measured.dump()<<'\n';
                    }
                }
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"B07 reference failed: "<<error.what()<<'\n';
        return 2;
    }
}
