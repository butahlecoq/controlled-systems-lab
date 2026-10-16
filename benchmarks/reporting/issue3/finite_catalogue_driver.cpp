#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <iostream>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::optimization;
using nlohmann::json;
constexpr std::string_view source_commit="994f3ee4310b4087d289e2eb02adbdb9dfd97827";

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
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}},{-2},1}));
    Vector values;
    for(const double point:Vector{0,1,2}) {
        const auto result=evaluate(objective,Vector{point});
        if(!std::holds_alternative<double>(result)) throw std::runtime_error("L19 evaluation failed");
        values.push_back(std::get<double>(result));
    }
    if(values!=Vector{1,0,1}) throw std::runtime_error("L19 stationary interior sample mismatch");
    const FiniteActionMinimaxRequest input{{"issue3-l19"},{"report-l19"},
        take(model::snapshot(authored,Vector{0,1})),singleton("l19-x0",0),
        {1,{{0},{1}}},{interval("l19-w0",0,1)},
        {safe(10),safe(10)},objective};
    const auto outcome=finite_action_minimax(input,{2,2,0});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
        throw std::runtime_error("L19 minimax outcome mismatch");
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    if(result.value!=1 || result.plans.size()!=2 ||
       result.minimizing_plan_indices!=std::vector<std::size_t>{0,1} ||
       !std::holds_alternative<FinitePlanFeasible>(result.plans[0]) ||
       !std::holds_alternative<FinitePlanFeasible>(result.plans[1]))
        throw std::runtime_error("L19 literal minimax oracle mismatch");
    const auto& first=std::get<FinitePlanFeasible>(result.plans[0]);
    const auto& second=std::get<FinitePlanFeasible>(result.plans[1]);
    if(first.worst_value!=1 || second.worst_value!=1 ||
       first.evaluated_vertices!=2 || second.evaluated_vertices!=2 ||
       first.maximizer!=Vector{0} || second.maximizer!=Vector{2})
        throw std::runtime_error("L19 action endpoint evidence mismatch");
    return {{"status","numerical_optimal"},{"value",result.value},{"plan_count",result.plans.size()},
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"evaluated_vertices",4},
        {"worst_values",Vector{first.worst_value,second.worst_value}},
        {"maximizers",std::vector<Vector>{first.maximizer,second.maximizer}},
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
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"worst_values",values},
        {"evaluated_vertices",4}};
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
    return {{"status","infeasible"},{"rejected_plans",json::array({
        {{"action_indices",rejected[0].action_indices},{"stage",rejected[0].stage},
         {"violating_successor",rejected[0].violating_successor}},
        {{"action_indices",rejected[1].action_indices},{"stage",rejected[1].stage},
         {"violating_successor",rejected[1].violating_successor}}})}};
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

json unsupported_case() {
    const auto outcome=finite_action_minimax(integrator(10),{1,2,0});
    if(!std::holds_alternative<Unsupported>(outcome) ||
       std::get<Unsupported>(outcome).diagnostics.size()!=1 ||
       std::get<Unsupported>(outcome).diagnostics[0].field!="finite_minimax.capacity")
        throw std::runtime_error("unsupported capacity oracle mismatch");
    return {{"status","unsupported"},{"field","finite_minimax.capacity"}};
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

FiniteActionMinimaxRequest b08_request() {
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
    return {{"b08-displayed-rounded"},{"issue3-report-b08"},
        system,initial,{1,{{0.6},{0.3},{0},{-0.3},{-0.6}}},
        disturbances,safe_sets,objective};
}

json b08() {
    const auto input=b08_request();
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
json details(std::string_view name) {
    const json base_model={{"A",{{1}}},{"B",{{1}}},{"D",{{1}}},
        {"initial",{0}},{"horizon",1}};
    const json quadratic={{"type","quadratic_terminal"},{"Q",{{2}}},{"q",{-2}},
        {"c",1},{"convention","0.5*x'Q*x+q'x+c"}};
    if(name=="l19") return {
        {"problem_id","issue3-l19"},{"request_id","report-l19"},
        {"limits",{{"max_plans",2},{"max_points_per_stage",2},{"near_optimal_tolerance",0}}},
        {"objective_convention","0.5*x'Q*x+q'x+c"},{"assurance","numerical"},
        {"input",{{"model",base_model},{"actions",{{0},{1}}},
            {"disturbance_vertices",{{0},{1}}},{"safe_bound",10},{"objective",quadratic}}},
        {"expected",{{"status","numerical_optimal"},{"value",1},{"plan_count",2},
            {"minimizing_plan_indices",{0,1}},{"evaluated_vertices",4},
            {"worst_values",{1,1}},{"maximizers",{{0},{2}}},
            {"sampled_objective_values",{1,0,1}}}}};
    if(name=="integrator" || name=="all_infeasible" || name=="empty_catalogue" ||
       name=="no_scenarios" || name=="unsupported" || name=="cancelled") {
        const bool narrow=name=="all_infeasible";
        json actions=json::array({json::array({0}),json::array({1})});
        if(name=="empty_catalogue") actions=json::array();
        json disturbance=json::array({json::array({0}),json::array({2})});
        if(name=="no_scenarios") disturbance=json::array();
        const std::size_t max_plans=name=="unsupported"?1:2;
        json expected;
        if(name=="integrator") expected={{"status","numerical_optimal"},{"value",1},
            {"plan_count",2},{"minimizing_plan_indices",{0}},{"worst_values",{1,4}},
            {"evaluated_vertices",4}};
        else if(narrow) expected={{"status","infeasible"},{"rejected_plans",json::array({
            {{"action_indices",{0}},{"stage",1},{"violating_successor",{2}}},
            {{"action_indices",{1}},{"stage",1},{"violating_successor",{1}}}})}};
        else if(name=="empty_catalogue") expected={{"status","empty_catalogue"}};
        else if(name=="no_scenarios") expected={{"status","no_scenarios"}};
        else if(name=="unsupported") expected={{"status","unsupported"},
            {"field","finite_minimax.capacity"}};
        else expected={{"status","stopped"},{"reason","cancelled"}};
        return {{"problem_id","issue3-integrator"},{"request_id","report-integrator"},
            {"limits",{{"max_plans",max_plans},{"max_points_per_stage",2},
                       {"near_optimal_tolerance",0}}},
            {"objective_convention","0.5*x'Q*x+q'x+c"},
            {"assurance",name=="integrator" || narrow?json("numerical"):json(nullptr)},
            {"input",{{"model",base_model},{"actions",actions},
                {"disturbance_vertices",disturbance},{"safe_bound",narrow?0.5:10.0},
                {"objective",quadratic},{"pre_cancelled",name=="cancelled"}}},
            {"expected",expected}};
    }
    if(name=="b08_rounded") {
        const auto input=b08_request();
        json vertices=json::array();
        for(const auto& disturbance:input.disturbances) {
            const auto representation=disturbance.representation();
            if(!std::holds_alternative<sets::VRepresentation>(representation))
                throw std::runtime_error("B08 input description lost V representation");
            const auto& matrix=std::get<sets::VRepresentation>(representation).vertices;
            json stage=json::array();
            for(std::size_t row=0;row<matrix.rows();++row) {
                json coordinate=json::array();
                for(std::size_t column=0;column<matrix.cols();++column) {
                    std::ostringstream stream;
                    stream<<std::hexfloat<<matrix(row,column);
                    coordinate.push_back(stream.str());
                }
                stage.push_back(std::move(coordinate));
            }
            vertices.push_back(std::move(stage));
        }
        return {
        {"problem_id","b08-displayed-rounded"},{"request_id","issue3-report-b08"},
        {"limits",{{"max_plans",625},{"max_points_per_stage",256},
                   {"near_optimal_tolerance",1e-8}}},
        {"objective_convention","Euclidean terminal residual norm"},
        {"assurance","numerical"},
        {"input",{{"model",{{"A",{{1,0,0,0},{-25,1,0,0},{0,0,1,0},{0,0,-25,1}}},
                              {"B",{{20.073},{0},{-10.473},{0}}},
                              {"D",{{1,0},{0,0},{0,-1},{0,0}}},
                              {"initial",{1182.074,119560,459.832,45260}},
                              {"horizon",4}}},
            {"actions",{{0.6},{0.3},{0},{-0.3},{-0.6}}},
            {"authored_disturbance_halfwidths",{{0.1,0.1},{0.2,0.4},{0.3,0.7},{0.4,1.0}}},
            {"disturbance_vertices_binary64_hex",vertices},
            {"safe","universal"},{"objective",{{"type","residual_norm_terminal"},
                {"C",{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1}}},
                {"target",{1200,0,450,0}}}}}},
        {"expected",{{"status","numerical_optimal"},{"value",67.150601101407},
            {"plan_count",625},{"evaluated_vertices",160000},
            {"minimizing_plan_indices",{17,33,129}}}}};
    }
    throw std::runtime_error("unknown fixture metadata");
}

bool matches(json observed,json expected,std::string_view name) {
    if(name=="b08_rounded") {
        if(!observed.contains("value") || !observed["value"].is_number()) return false;
        const auto value=observed["value"].get<double>();
        if(std::abs(value-67.150601101407)>1e-8) return false;
        observed["value"]=expected["value"];
    }
    return observed==expected;
}

// Source-bound, untimed audit output. The immutable published collection used
// --smoke/--measure; this mode exposes every public per-plan outcome so an
// independent exact-dyadic checker can replay the frozen B08 input.
json b08_audit() {
    const auto metadata=details("b08_rounded");
    const auto input_canonical=metadata["input"].dump();
    const auto bytes=std::as_bytes(std::span<const char>{input_canonical.data(),input_canonical.size()});
    const auto input_hash=problem::hex(take(problem::snapshot_content(bytes)).digest());
    const auto outcome=finite_action_minimax(b08_request(),{625,256,1e-8});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
        throw std::runtime_error("B08 audit requires completed public optimal outcome");
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    json plans=json::array();
    for(const auto& record:result.plans) {
        if(const auto* feasible=std::get_if<FinitePlanFeasible>(&record))
            plans.push_back({{"status","feasible"},{"action_indices",feasible->action_indices},
                {"worst_value",feasible->worst_value},
                {"evaluated_vertices",feasible->evaluated_vertices}});
        else {
            const auto& rejected=std::get<FinitePlanRejected>(record);
            plans.push_back({{"status","rejected"},{"action_indices",rejected.action_indices},
                {"stage",rejected.stage},{"violating_successor",rejected.violating_successor}});
        }
    }
    return {{"schema","csl.issue3-b08-per-plan-audit/1"},{"source_commit",source_commit},
        {"fixture_sha256",CSL_ISSUE3_FIXTURE_SHA256},
        {"input_canonical",input_canonical},{"input_sha256",input_hash},
        {"status","numerical_optimal"},{"value",result.value},
        {"minimizing_plan_indices",result.minimizing_plan_indices},{"plans",std::move(plans)}};
}

void emit(std::string_view name,Case run,std::size_t round,bool warmup,std::size_t batch) {
    const auto metadata=details(name);
    const auto input_canonical=metadata["input"].dump();
    const auto bytes=std::as_bytes(std::span<const char>{input_canonical.data(),input_canonical.size()});
    const auto input_hash=problem::hex(take(problem::snapshot_content(bytes)).digest());
    const auto start=std::chrono::steady_clock::now();
    json result;
    for(std::size_t i=0;i<batch;++i) {
        result=run();
        if(!matches(result,metadata["expected"],name))
            throw std::runtime_error("observed result differs from independent fixture expectation");
    }
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now()-start).count();
    if(elapsed<=0)throw std::runtime_error("nonpositive clock interval");
    json plan_count=nullptr;
    if(result.contains("plan_count")) plan_count=result["plan_count"];
    else if(result.contains("rejected_plans")) plan_count=result["rejected_plans"].size();
    else if(result["status"]=="empty_catalogue") plan_count=0;
    json row_count=nullptr;
    if(result.contains("evaluated_vertices")) row_count=result["evaluated_vertices"];
    else if(result["status"]=="infeasible" || result["status"]=="empty_catalogue") row_count=0;
    std::cout<<json{{"schema","csl.issue3-raw-trial/1"},{"fixture",name},
        {"source_commit",source_commit},{"harness_commit",CSL_ISSUE3_HARNESS_COMMIT},
        {"fixture_sha256",CSL_ISSUE3_FIXTURE_SHA256},
        {"input_canonical",input_canonical},{"input_sha256",input_hash},
        {"problem_id",metadata["problem_id"]},{"request_id",metadata["request_id"]},
        {"limits",metadata["limits"]},{"objective_convention",metadata["objective_convention"]},
        {"assurance",metadata["assurance"]},
        {"plan_count",plan_count},{"evaluated_terminal_rows",row_count},
        {"round",round},{"warmup",warmup},{"batch",batch},
        {"checked_calls",batch},{"elapsed_ns",elapsed},{"result",result},
        {"checks",{{"expected",metadata["expected"]},{"observed",result},
                   {"absolute_tolerance",name=="b08_rounded"?1e-8:0.0},
                   {"passed",true}}}}.dump()<<'\n';
}
} // namespace

int main(int argc,char** argv) {
    try {
        if(argc==2 && std::string_view(argv[1])=="--audit-b08") {
            std::cout<<b08_audit().dump()<<'\n';
            return 0;
        }
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
            {"unsupported",unsupported_case},
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
