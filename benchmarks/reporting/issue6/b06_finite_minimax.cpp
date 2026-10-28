#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>
#include "issue6_b06_scenario.hpp"

#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <string_view>
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

double scalar(const json& value,const std::string& path) {
    const auto text=value.is_string()?value.get<std::string>():value.dump();
    const auto slash=text.find('/');
    try {
        double result{};
        const auto parse=[](const std::string& part) {
            std::size_t consumed{};
            const auto number=std::stod(part,&consumed);
            if(consumed!=part.size())throw std::invalid_argument("trailing characters");
            return number;
        };
        if(slash==std::string::npos)result=parse(text);
        else {
            const auto numerator=parse(text.substr(0,slash));
            const auto denominator=parse(text.substr(slash+1));
            if(denominator==0.0)throw std::invalid_argument("zero denominator");
            result=numerator/denominator;
        }
        if(!std::isfinite(result))throw std::invalid_argument("nonfinite scalar");
        return result;
    } catch(const std::exception&) {
        throw std::runtime_error(path+" must be a finite numeric scalar");
    }
}

Vector vector(const json& values,std::size_t size,const std::string& path) {
    if(!values.is_array()||values.size()!=size)throw std::runtime_error(path+" has an invalid dimension");
    Vector result;result.reserve(size);
    for(std::size_t i=0;i<size;++i)result.push_back(scalar(values[i],path+"["+std::to_string(i)+"]"));
    return result;
}

Matrix matrix(const json& values,std::size_t rows,std::size_t cols,const std::string& path) {
    return {rows,cols,vector(values,rows*cols,path)};
}

FiniteActionMinimaxRequest b06_request(const json& scenario) {
    if(scenario.at("schema_version")!=1||scenario.at("id")!="b06-owner-confirmed-disturbance-v1")
        throw std::runtime_error("scenario schema or identity mismatch");
    const auto& spec=scenario.at("model");
    if(spec.at("time_domain")!="discrete"||spec.at("state_constraints")!="none; this is the unconstrained B06/L09 formulation")
        throw std::runtime_error("unsupported B06 time domain or state-constraint profile");
    const auto n=spec.at("state_dimension").get<std::size_t>();
    const auto m=spec.at("control_dimension").get<std::size_t>();
    const auto d=spec.at("disturbance_dimension").get<std::size_t>();
    const auto horizon=spec.at("horizon").get<std::size_t>();
    if(n==0||m==0||d==0||horizon==0)throw std::runtime_error("scenario dimensions and horizon must be positive");
    auto authored_a=matrix(spec.at("A_row_major"),n,n,"model.A_row_major");
    auto authored_b=matrix(spec.at("B"),n,m,"model.B");
    auto authored_d=matrix(spec.at("D_row_major"),n,d,"model.D_row_major");
    auto offset=vector(spec.at("offset"),n,"model.offset");
    const auto system=take(model::snapshot(SystemModel{{{n,m,d},TimeDomain::discrete,
        LinearStage{std::move(authored_a),std::move(authored_b),std::move(authored_d),std::move(offset)}},{}},
        [&](){Vector times(horizon+1);for(std::size_t i=0;i<=horizon;++i)times[i]=static_cast<double>(i);return times;}()));
    std::vector<std::string> state_coordinates;for(std::size_t j=0;j<n;++j)state_coordinates.push_back("x"+std::to_string(j+1));
    const auto initial=take(sets::make_singleton({{"b06-x0"},n,state_coordinates},
        take(numeric::snapshot_vector(vector(spec.at("initial_state"),n,"model.initial_state")))));
    const auto& disturbance_spec=spec.at("disturbance_box_per_stage");
    if(disturbance_spec.at("kind")!="box"||!disturbance_spec.at("independent_choices_across_stages").get<bool>())
        throw std::runtime_error("disturbance domain must be an independently chosen box at every stage");
    const auto lower=vector(disturbance_spec.at("lower"),d,"model.disturbance_box_per_stage.lower");
    const auto upper=vector(disturbance_spec.at("upper"),d,"model.disturbance_box_per_stage.upper");
    for(std::size_t j=0;j<d;++j)if(!(lower[j]<upper[j]))
        throw std::runtime_error("disturbance box lower bounds must be below upper bounds");
    json vertex_rows=json::array();
    if(d>=sizeof(std::size_t)*8)throw std::runtime_error("disturbance dimension is too large to enumerate box corners");
    for(std::size_t mask=0;mask<(std::size_t{1}<<d);++mask) {
        json row=json::array();
        for(std::size_t j=0;j<d;++j)row.push_back((mask&(std::size_t{1}<<j))?upper[j]:lower[j]);
        vertex_rows.push_back(std::move(row));
    }
    Vector disturbance_values;disturbance_values.reserve(vertex_rows.size()*d);
    for(const auto& row:vertex_rows)for(std::size_t j=0;j<d;++j)disturbance_values.push_back(row[j].get<double>());
    std::vector<std::string> disturbance_coordinates;for(std::size_t j=0;j<d;++j)disturbance_coordinates.push_back("w"+std::to_string(j+1));
    const auto disturbance=take(sets::make_v({{"b06-w"},d,std::move(disturbance_coordinates)},
        {take(numeric::snapshot(Matrix{vertex_rows.size(),d,std::move(disturbance_values)})),
         take(numeric::snapshot(Matrix{0,d,{}}))}));
    std::vector<sets::SetData> disturbances(horizon,disturbance);
    std::vector<sets::SetData> safe_sets;
    safe_sets.reserve(horizon+1);
    for(std::size_t stage=0;stage<=horizon;++stage)
        safe_sets.push_back(take(sets::make_universal({{"b06-unconstrained-"+std::to_string(stage)},n,state_coordinates})));
    std::vector<Vector> catalogue;
    for(const auto& row:spec.at("control_catalogue_rows"))catalogue.push_back(vector(row,m,"model.control_catalogue_rows"));
    if(catalogue.empty())throw std::runtime_error("control catalogue must not be empty");
    if(m==1) {
        const auto legacy=vector(spec.at("control_catalogue_ordered"),catalogue.size(),"model.control_catalogue_ordered");
        for(std::size_t i=0;i<catalogue.size();++i)if(catalogue[i][0]!=legacy[i])
            throw std::runtime_error("structured and legacy control catalogues disagree");
    }
    const auto& quadratic=scenario.at("objective").at("quadratic_terminal");
    if(quadratic.at("convention")!="one_half_x_transpose_Q_x_plus_linear_transpose_x_plus_constant")
        throw std::runtime_error("unsupported terminal quadratic convention");
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{
        matrix(quadratic.at("Q_row_major"),n,n,"objective.quadratic_terminal.Q_row_major"),
        vector(quadratic.at("linear"),n,"objective.quadratic_terminal.linear"),
        scalar(quadratic.at("constant"),"objective.quadratic_terminal.constant")}));
    return {{scenario.at("id").get<std::string>()},{"b06-finite-action-reference"},
        system,initial,{m,std::move(catalogue)},
        std::move(disturbances),std::move(safe_sets),objective};
}

json load_scenario(const std::string& path="benchmarks/scenarios/b06-owner-confirmed-disturbance-v1.json") {
    std::ifstream stream(path,std::ios::binary);
    if(!stream)throw std::runtime_error("cannot open scenario: "+path);
    const std::string bytes{std::istreambuf_iterator<char>(stream),std::istreambuf_iterator<char>()};
    if(bytes!=csl::issue6::configured_b06_scenario)
        throw std::runtime_error("scenario bytes differ from the configured canonical fixture; reconfigure and rebuild before execution");
    return json::parse(bytes);
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

json run_once(std::size_t batch,const json& scenario,bool include_geometry=false) {
    const auto started=std::chrono::steady_clock::now();
    const auto result=finite_action_minimax(b06_request(scenario),{3125,1024,0.0});
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
        const bool validate_only=argc>=2 && std::string_view(argv[1])=="--validate-only";
        if(validate_only && argc>3)throw std::runtime_error("usage: b06_finite_minimax --validate-only [SCENARIO.json]");
        const auto scenario=validate_only&&argc==3?load_scenario(argv[2]):load_scenario();
        if(validate_only) {
            (void)b06_request(scenario);
            std::cout<<json{{"status","scenario_validated"},{"scenario_id",scenario.at("id")},
                {"source_commit",CSL_ISSUE6_SOURCE_COMMIT},{"fixture_sha256",CSL_ISSUE6_FIXTURE_SHA256}}.dump()<<'\n';
            return 0;
        }
        std::size_t batches=1;
        bool geometry=false;
        if(argc==3 && std::string_view(argv[1])=="--measure") batches=std::stoul(argv[2]);
        else if(argc==2 && std::string_view(argv[1])=="--geometry") geometry=true;
        else if(argc!=1) throw std::runtime_error("usage: b06_finite_minimax [--measure batches|--geometry|--validate-only]");
        if(batches==0 || batches>25) throw std::runtime_error("batch count must be 1..25");
        if(geometry) std::cout<<run_once(0,scenario,true).dump()<<'\n';
        else for(std::size_t batch=0;batch<=batches;++batch)
            std::cout<<run_once(batch,scenario).dump()<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"B06 run rejected: "<<error.what()<<'\n';
        return 2;
    }
}
