#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/phase_one.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
namespace po = csl::optimization::phase_one;
using json = nlohmann::json;
using Clock = std::chrono::steady_clock;
using Ns = std::chrono::nanoseconds;

struct Fixture {
    const char* id;
    std::size_t rows, columns;
    std::vector<double> dense, rhs, expected;
    const char* outcome;
    double auxiliary;
};
const std::vector<Fixture> fixtures{
    {"triangle",3,3,{0,1,0, 0,0,1, 1,1,1},{.25,.25,1},{.5,.25,.25},"optimal",0},
    {"signed_triangle",3,3,{-1,1,-1, -1,-1,1, 1,1,1},{-.5,-.5,1},{.5,.25,.25},"optimal",0},
    {"edge",3,3,{0,1,0, 0,0,1, 1,1,1},{.5,0,1},{.5,.5,0},"optimal",0},
    {"duplicate_tie",2,2,{1,1,1,1},{1,1},{1,0},"optimal",0},
    {"contradictory_rows",2,1,{1,1},{0,1},{0},"infeasible",1}
};
constexpr double abs_tol=1e-8, rel_tol=0.0;
long long ns(Clock::time_point a, Clock::time_point b) { return std::chrono::duration_cast<Ns>(b-a).count(); }
const char* status(MathematicalOutcome x) {
    switch(x) { case MathematicalOutcome::optimal:return "optimal"; case MathematicalOutcome::infeasible:return "infeasible";
    case MathematicalOutcome::unbounded:return "unbounded"; case MathematicalOutcome::infimum_not_attained:return "infimum_not_attained"; default:return "undetermined"; }
}
const char* termination(Termination x) {
    switch(x) { case Termination::completed:return "completed"; case Termination::cancelled:return "cancelled";
    case Termination::resource_limit:return "resource_limit"; case Termination::numerical_failure:return "numerical_failure";
    case Termination::operation_rejected:return "operation_rejected"; default:return "contract_rejected"; }
}
SparseMatrix matrix(const Fixture& f) {
    SparseMatrix a; a.rows=f.rows; a.cols=f.columns; a.row_offsets.push_back(0);
    for(std::size_t i=0;i<f.rows;++i) { for(std::size_t j=0;j<f.columns;++j) if(f.dense[i*f.columns+j]!=0) { a.column_indices.push_back(j); a.values.push_back(f.dense[i*f.columns+j]); } a.row_offsets.push_back(a.values.size()); }
    return a;
}
LinearProgram make_program(const Fixture& f) {
    auto made=po::make_program({{"opt04-report"},{f.id}},matrix(f),f.rhs);
    if(!std::holds_alternative<LinearProgram>(made)) throw std::runtime_error("fixture program rejected");
    return std::get<LinearProgram>(std::move(made));
}
template<class T,class... R> T take(std::variant<T,R...> v) {
    if(!std::holds_alternative<T>(v)) throw std::runtime_error("registry/preparation rejected fixture");
    return std::get<T>(std::move(v));
}
json vec(const std::optional<Vector>& v) { return v?json(*v):json(nullptr); }
double max_abs_row_violation(const Fixture& f,const Vector& x) {
    double result=0; for(std::size_t i=0;i<f.rows;++i) { double v=-f.rhs[i]; for(std::size_t j=0;j<f.columns;++j) v+=f.dense[i*f.columns+j]*x[j]; result=std::max(result,std::abs(v)); } return result;
}
double max_nonnegative_violation(const Vector& x) { double r=0; for(double v:x) r=std::max(r,std::max(0.0,-v)); return r; }
struct SideResult { json detail; bool passed{false}; };
SideResult run_side(const Fixture& f,const std::string& side) {
    const auto all_start=Clock::now();
    json out;
    std::unique_ptr<BoundWorkspace<LPPort>> bound;
    const auto setup_start=Clock::now();
    LinearProgram p=make_program(f);
    Registry<LPPort> registry;
    if(side=="phase-one-bland") {
        auto registration=take(po::make_registration());
        if(registry.add(std::move(registration))) throw std::runtime_error("phase-one registration conflict");
    } else {
        auto registration=take(adapters::lp::make_highs_registration());
        if(registry.add(std::move(registration))) throw std::runtime_error("HiGHS registration conflict");
    }
    Requirements req; req.output.representation={"csl.program-result.v1"}; req.output.assurance=Assurance::numerical;
    req.basis_diagnostics=side=="phase-one-bland";
    auto prepared=take(prepare_pipeline(select(registry,{{side=="phase-one-bland"?"phase-one-bland":"csl.lp.highs"},{}},p,req)));
    auto [workspace]=prepared.create(); bound=std::move(workspace);
    const auto setup_end=Clock::now();
    const auto run_start=Clock::now();
    auto resources=std::make_shared<ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto outcome=bound->run({std::move(resources), {}, {}, {abs_tol,rel_tol}, std::string("opt04-")+f.id});
    const auto run_end=Clock::now();
    if(!std::holds_alternative<ProgramResult>(outcome)) throw std::runtime_error("registered adapter rejected run");
    const auto& result=std::get<ProgramResult>(outcome);
    const auto verify_start=Clock::now();
    const auto observed=status(result.outcome.value);
    const bool status_ok=observed==std::string(f.outcome);
    double rows=0, nonnegative=0, objective=0;
    json primal=nullptr;
    if(result.primal) {
        primal=*result.primal; rows=max_abs_row_violation(f,*result.primal); nonnegative=max_nonnegative_violation(*result.primal);
        auto eval=evaluate_primal(p,*result.primal,{abs_tol,rel_tol},{{"opt04-independent-oracle"},"1"});
        if(!std::holds_alternative<PrimalEvaluation>(eval)) throw std::runtime_error("independent primal evaluation failed");
        objective=std::get<PrimalEvaluation>(eval).objective;
    }
    json checks=json::array();
    checks.push_back({{"name","expected_status"},{"passed",status_ok}});
    bool candidate_ok=true;
    if(std::string(f.outcome)=="optimal") {
        candidate_ok=result.primal.has_value()&&result.primal->size()==f.expected.size();
        if(candidate_ok && side=="phase-one-bland") for(std::size_t i=0;i<f.expected.size();++i) candidate_ok=candidate_ok&&std::abs((*result.primal)[i]-f.expected[i])<=abs_tol;
        if(side=="highs-reference") candidate_ok=candidate_ok&&rows<=abs_tol&&nonnegative<=abs_tol&&std::abs(objective)<=abs_tol;
        checks.push_back({{"name",side=="phase-one-bland"?"literal_expected_candidate":"independent_feasible_witness"},{"passed",candidate_ok}});
        checks.push_back({{"name","original_equalities"},{"passed",rows<=abs_tol}});
        checks.push_back({{"name","nonnegative_variables"},{"passed",nonnegative<=abs_tol}});
        checks.push_back({{"name","zero_original_objective"},{"passed",std::abs(objective)<=abs_tol}});
    }
    double auxiliary=-1, auxiliary_residual=-1; std::uint64_t pivots=0,degenerate=0,factorizations=0;
    std::string term=termination(result.termination);
    if(side=="phase-one-bland") {
        const auto* diagnostics=dynamic_cast<const po::DiagnosticsView*>(bound->basis());
        if(!diagnostics) throw std::runtime_error("phase-one diagnostics unavailable");
        auto snap=diagnostics->phase_one_snapshot();
        if(!std::holds_alternative<po::Snapshot>(snap)) throw std::runtime_error("phase-one snapshot unavailable");
        const auto& s=std::get<po::Snapshot>(snap); auxiliary=s.auxiliary?s.auxiliary->value:-1;
        auxiliary_residual=s.auxiliary?s.auxiliary->equations.violation:-1;
        pivots=s.pivots;degenerate=s.degenerate_pivots;factorizations=s.factorizations;
        checks.push_back({{"name","literal_auxiliary_value"},{"passed",std::abs(auxiliary-f.auxiliary)<=abs_tol}});
    }
    const bool passed=status_ok&&candidate_ok&&std::all_of(checks.begin(),checks.end(),[](const json& c){return c["passed"].get<bool>();});
    const auto verify_end=Clock::now();
    out={{"status",passed?"passed":"failed"},{"error",passed?json(nullptr):json("independent oracle mismatch")},
         {"observed_status",observed},{"termination",term},{"primal",primal},{"oracle_match",passed},{"oracle_checks",checks},
         {"original_rows_max_violation",side=="phase-one-bland"?json(rows):json(nullptr)},
         {"nonnegative_max_violation",side=="phase-one-bland"?json(nonnegative):json(nullptr)},
         {"objective_value",side=="phase-one-bland"?json(objective):json(nullptr)},
         {"auxiliary_residual",side=="phase-one-bland"?json(auxiliary_residual):json(nullptr)},
         {"auxiliary_value",side=="phase-one-bland"?json(auxiliary):json(nullptr)},
         {"result",{{"termination",term},{"outcome",observed},{"primal",primal},{"auxiliary",side=="phase-one-bland"?json(auxiliary):json(nullptr)},
                     {"pivots",side=="phase-one-bland"?json(pivots):json(nullptr)},{"degenerate_pivots",side=="phase-one-bland"?json(degenerate):json(nullptr)},{"factorizations",side=="phase-one-bland"?json(factorizations):json(nullptr)}}},
         {"durations_ns",{{"setup",ns(setup_start,setup_end)},{"public_run",ns(run_start,run_end)},{"verification",ns(verify_start,verify_end)},{"end_to_end",ns(all_start,verify_end)}}},
         {"work_observed",true}};
    return {std::move(out),passed};
}
SideResult failed_side(const std::string& error, long long elapsed) {
    return {json{{"status","failed"},{"error",error},{"observed_status","undetermined"},{"termination","exception"},
        {"primal",nullptr},{"oracle_match",false},{"oracle_checks",json::array({json{{"name","run_completed"},{"passed",false}}})},
        {"original_rows_max_violation",nullptr},{"nonnegative_max_violation",nullptr},{"objective_value",nullptr},
        {"auxiliary_residual",nullptr},{"auxiliary_value",nullptr},
        {"result",{{"termination","exception"},{"outcome","undetermined"},{"primal",nullptr},{"auxiliary",nullptr},
                    {"pivots",nullptr},{"degenerate_pivots",nullptr},{"factorizations",nullptr}}},
        {"durations_ns",{{"setup",nullptr},{"public_run",nullptr},{"verification",nullptr},{"end_to_end",elapsed}}},
        {"work_observed",false}},false};
}
int main(int argc,char** argv) {
    try {
        bool smoke=false;
        if(argc==2&&std::string(argv[1])=="--smoke") smoke=true;
        else if(argc!=1) throw std::runtime_error("usage: csl_opt04_phase_one_report [--smoke]");
        std::size_t sequence=0; bool any_failed=false;
        // Normal execution emits a single balanced block, one excluded warmup
        // followed by seven measured rounds; --smoke is one functional round.
        const std::size_t warmups=smoke?0:1, reps=smoke?1:7;
        for(std::size_t warm=0;warm<warmups;++warm) for(const auto& f:fixtures) for(const auto* side:{"phase-one-bland","highs-reference"}) {
            const auto started=Clock::now();
            SideResult r;
            try { r=run_side(f,side); }
            catch(const std::exception& e) { r=failed_side(e.what(),ns(started,Clock::now())); }
            any_failed=any_failed||!r.passed;
            json trial={{"fixture",f.id},{"side",side},{"repetition",warm},{"sequence",sequence++},{"pair_id",std::string(f.id)+"-warmup-"+std::to_string(warm)},
                {"warmup",true},{"status",r.detail["status"]},{"error",r.detail["error"]},{"expected_status",f.outcome},{"observed_status",r.detail["observed_status"]},
                {"reference_status",nullptr},{"oracle_match",r.detail["oracle_match"]},{"oracle_checks",r.detail["oracle_checks"]},{"work_observed",true},
                {"tolerances",{{"absolute",abs_tol},{"relative",rel_tol}}},{"original_rows_max_violation",r.detail["original_rows_max_violation"]},
                {"nonnegative_max_violation",r.detail["nonnegative_max_violation"]},{"objective_value",r.detail["objective_value"]},
                {"auxiliary_residual",r.detail["auxiliary_residual"]},{"auxiliary_value",r.detail["auxiliary_value"]},{"durations_ns",r.detail["durations_ns"]},{"result",r.detail["result"]}};
            std::cout<<trial.dump()<<'\n';
        }
        for(std::size_t rep=0;rep<reps;++rep) for(std::size_t fi=0;fi<fixtures.size();++fi) {
            const auto index=rep%2?fixtures.size()-1-fi:fi; const auto& f=fixtures[index];
            const bool reverse=((rep+index)%2)!=0;
            const std::string first=reverse?"highs-reference":"phase-one-bland";
            const std::string second=reverse?"phase-one-bland":"highs-reference";
            for(const auto& side:{first,second}) {
                const auto started=Clock::now();
                SideResult r;
                try { r=run_side(f,side); }
                catch(const std::exception& e) { r=failed_side(e.what(),ns(started,Clock::now())); }
                any_failed=any_failed||!r.passed;
                json trial={{"fixture",f.id},{"side",side},{"repetition",rep},{"sequence",sequence++},{"pair_id",std::string(f.id)+"-"+std::to_string(rep)},
                    {"warmup",false},{"status",r.detail["status"]},{"error",r.detail["error"]},{"expected_status",f.outcome},{"observed_status",r.detail["observed_status"]},
                    {"reference_status",nullptr},{"oracle_match",r.detail["oracle_match"]},{"oracle_checks",r.detail["oracle_checks"]},{"work_observed",true},
                    {"tolerances",{{"absolute",abs_tol},{"relative",rel_tol}}},{"original_rows_max_violation",r.detail["original_rows_max_violation"]},
                    {"nonnegative_max_violation",r.detail["nonnegative_max_violation"]},{"objective_value",r.detail["objective_value"]},
                    {"auxiliary_residual",r.detail["auxiliary_residual"]},{"auxiliary_value",r.detail["auxiliary_value"]},{"durations_ns",r.detail["durations_ns"]},{"result",r.detail["result"]}};
                std::cout<<trial.dump()<<'\n';
                if(!r.passed) std::cerr<<"trial_failed="<<f.id<<","<<side<<","<<rep<<'\n';
            }
        }
        return any_failed?1:0;
    } catch(const std::exception& e) { std::cerr<<"opt04_report_error="<<e.what()<<'\n'; return 2; }
}
