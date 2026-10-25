#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/validated_finite_action_minimax.hpp>
#include <csl/artifacts/comparison_manifest.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;

template<class T> T take(std::variant<T,Diagnostic> value) {
    if(!std::holds_alternative<T>(value)) throw std::runtime_error("fixture construction failed");
    return std::get<T>(std::move(value));
}
template<class T> T take_artifact(artifacts::ArtifactResult<T> value) {
    if(!std::holds_alternative<T>(value)) {
        const auto& error=std::get<artifacts::ArtifactError>(value);
        throw std::runtime_error(error.path+": "+error.message);
    }
    return std::get<T>(std::move(value));
}

FiniteActionMinimaxRequest make_case() {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1}));
    const auto initial=take(sets::make_singleton({{"x0"},1,{"x"}},
        take(numeric::snapshot_vector(Vector{0}))));
    const auto disturbance=take(sets::make_v({{"w0"},1,{"w"}},
        {take(numeric::snapshot(Matrix{2,1,{0,2}})),take(numeric::snapshot(Matrix{0,1,{}}))}));
    const auto safe=take(sets::make_h({{"safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{10,10})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))}));
    const auto objective=std::get<Objective>(snapshot(ResidualNormTerminal{{1,1,{1}},{1}}));
    return {{"pending-problem-id"},{"issue422-run"},system,initial,
        {1,{{0},{1}}},{disturbance},{safe,safe},objective};
}

ValidatedFiniteActionMinimaxRequest validated(const FiniteActionMinimaxRequest& request) {
    return {request.problem,request.request,request.system,request.initial,request.actions,
        request.disturbances,request.admissible_states,request.objective};
}

Json oracle(const FiniteActionMinimaxRequest& request) {
    const auto dynamics=std::get<model::DynamicsStage>(request.system.stage({0}));
    const auto initial=std::get<sets::SingletonRepresentation>(request.initial.representation()).point;
    const auto& disturbance=std::get<sets::VRepresentation>(request.disturbances[0].representation()).vertices;
    if(initial[0] < -10.0 || initial[0] > 10.0)throw std::runtime_error("oracle found initial-state constraint violation");
    double global=std::numeric_limits<double>::infinity();
    Json plans=Json::array();
    for(std::size_t ai=0;ai<request.actions.catalogue.size();++ai) {
        double worst=-std::numeric_limits<double>::infinity();
        Json histories=Json::array();
        for(std::size_t wi=0;wi<disturbance.rows();++wi) {
            const double x=dynamics.A(0,0)*initial[0]+dynamics.B(0,0)*request.actions.catalogue[ai][0]+
                dynamics.E(0,0)*disturbance(wi,0)+dynamics.offset[0];
            if(x < -10.0 || x > 10.0) throw std::runtime_error("oracle found stage constraint violation");
            const double cost=std::abs(x-1.0);
            worst=std::max(worst,cost);
            histories.push_back({{"disturbance_vertex",wi},{"state",x},{"cost",cost},{"safe",true}});
        }
        global=std::min(global,worst);
        plans.push_back({{"action_index",ai},{"worst_cost",worst},{"histories",std::move(histories)}});
    }
    return {{"status","verified"},{"scope","all 2 fixed plans x 2 disturbance vertices; scalar stage constraint and terminal objective"},
        {"global_minimax_value",global},{"plans",std::move(plans)}};
}

bool fixture_matches_manifest(const FiniteActionMinimaxRequest& request) {
    if(request.system.horizon()!=1||request.system.dimensions()!=Dimensions{1,1,1}||
       request.actions.dimension!=1||request.actions.catalogue!=std::vector<Vector>{{0},{1}}||
       request.disturbances.size()!=1||request.admissible_states.size()!=2)return false;
    const auto dynamics=std::get<model::DynamicsStage>(request.system.stage({0}));
    if(dynamics.A(0,0)!=1||dynamics.B(0,0)!=1||dynamics.E(0,0)!=1||dynamics.offset[0]!=0)return false;
    const auto initial_rep=request.initial.representation();
    const auto disturbance_rep=request.disturbances[0].representation();
    const auto initial=std::get_if<sets::SingletonRepresentation>(&initial_rep);
    const auto disturbances=std::get_if<sets::VRepresentation>(&disturbance_rep);
    if(!initial||initial->point[0]!=0||!disturbances||disturbances->vertices.rows()!=2||
       disturbances->vertices(0,0)!=0||disturbances->vertices(1,0)!=2)return false;
    for(const auto& safe:request.admissible_states) {
        const auto safe_rep=safe.representation();
        const auto h=std::get_if<sets::HRepresentation>(&safe_rep);
        if(!h||h->inequalities.rows()!=2||h->upper_bounds[0]!=10||h->upper_bounds[1]!=10||
           h->inequalities(0,0)!=1||h->inequalities(1,0)!=-1)return false;
    }
    const auto objective=request.objective.coefficients();
    const auto residual=std::get_if<ResidualCoefficients>(&objective);
    return residual&&residual->map.rows()==1&&residual->map(0,0)==1&&residual->target[0]==1;
}

problem::ResolvedContent owned(std::string_view text) {
    return take(problem::snapshot_content(std::as_bytes(std::span<const char>{text.data(),text.size()})));
}

artifacts::ResolvedConfiguration configuration(std::string method,std::string source_sha256,Assurance assurance) {
    namespace ar=artifacts;
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    ar::ConfigurationInput input;
    input.collection={false,ar::CollectionMode::summary,0,0,0,0};
    ar::NamedOption source_pin{"source_sha256",ar::OptionValue{ar::OptionScalar{std::move(source_sha256)}}};
    input.modules={{"strategy",{{method},"1",missing},{std::move(source_pin)}}};
    input.numerical={0,0};input.resources={1,1,1,{}};
    input.output={ar::OutputKind::finite_minimax,assurance,
        FamilyTarget::exact_optimal_relation,{"csl.polyhedron.h"},{0,0,{}, {}}};
    input.selector={{"csl.selector.none"},"1",{}};
    input.strategy={{method},{},{},{},{},{},{},input.selector.id,input.output.representation};
    input.workspace=ar::WorkspacePolicy::fresh;
    return take_artifact(ar::resolve_configuration(std::move(input)));
}

artifacts::RecordedRunArtifact record_attempt(std::string method,std::string run_id,
        Assurance assurance,double lower,double upper,std::string_view manifest,
        const Json& detailed_outcome,const Json& independent_oracle,
        const ProblemId& problem_id,const Dimensions dimensions,std::string source_sha256) {
    namespace ar=artifacts;
    auto config=configuration(method,std::move(source_sha256),assurance);
    const ar::RunId run{run_id};
    const ar::CollectionSettings settings{false,ar::CollectionMode::summary,0,0,0,0};
    const ar::CollectionRecord collection{problem_id,config.identity(),run,settings,{}, {}, {},
        ar::Unavailable{ar::MissingReason::collection_disabled,{}},{},{}};
    const auto stats=take_artifact(ar::publish_collection(collection));
    const ProgramIdentity subject{problem_id,{method}};
    const EvidenceSupport support{Unestablished{}};
    const ProgramBoundEvidence bound_evidence{subject,support,{"Finite-catalog comparison; independent oracle archived separately."}};
    const std::string outcome_text=Json{{"schema","csl.exp05-minimax-outcome/1"},
        {"method",method},{"outcome","optimal"},{"assurance",assurance==Assurance::validated?"validated":"numerical"},
        {"lower",lower},{"upper",upper},{"plans",detailed_outcome},
        {"independent_oracle",independent_oracle}}.dump();
    const auto outcome_content=owned(outcome_text);
    const auto input_content=owned(manifest);
    std::vector<ar::Attachment> attachments{
        {{"finite-minimax-case"},ar::AttachmentRole::certificate,input_content.digest(),input_content.bytes().size(),
            "application/json","csl.exp05-finite-minimax-case/1",{},input_content},
        {{"finite-minimax-outcome"},ar::AttachmentRole::certificate,outcome_content.digest(),outcome_content.bytes().size(),
            "application/json","csl.exp05-minimax-outcome/1",{},outcome_content}};
    const ProgramObjectiveEvidence objective{
        ProgramObjectiveBound{lower,bound_evidence},ProgramObjectiveBound{upper,bound_evidence}};
    ar::RunRecord record{problem_id,dimensions,1,std::move(config),run,
        ar::MinimaxFinal{Termination::completed,MinimaxOutcome::optimal,assurance,subject,objective,
            ar::AttachmentId{"finite-minimax-outcome"}},stats,
        {ar::Unavailable{ar::MissingReason::not_instrumented,{}},ar::Unavailable{ar::MissingReason::not_instrumented,{}},
         ar::Unavailable{ar::MissingReason::not_instrumented,{}},ar::Unavailable{ar::MissingReason::not_instrumented,{}},
         false,ar::MemoryAccounting::unlimited},{},std::move(attachments),ar::ProblemProvenance::identity_recorded,{}};
    return take_artifact(ar::encode_recorded_run(take_artifact(ar::publish_identity_recorded_run(std::move(record)))));
}

Json main_run() {
    auto request=make_case();
    if(!fixture_matches_manifest(request))throw std::runtime_error("finite request does not match canonical case manifest");
    Json manifest;
    manifest["schema"]="csl.exp05-finite-minimax-case/1";
    manifest["request_id"]=request.request.value;
    manifest["semantics"]="exists fixed action, for all disturbance vertices";
    manifest["horizon"]=1;
    manifest["model"]={{"A",{{1}}},{"B",{{1}}},{"E",{{1}}},{"offset",{0}}};
    manifest["initial_vertices"]={{0}};
    manifest["action_catalogue"]={{0},{1}};
    manifest["disturbance_vertices_by_stage"]={{{0},{2}}};
    manifest["safe_state_set_by_stage"]={"-10 <= x <= 10","-10 <= x <= 10"};
    manifest["objective"]="abs(x_terminal - 1)";
    manifest["limits"]={{"max_plans",2},{"max_histories_per_plan",2},{"max_interval_operations",1000}};
    manifest["independent_oracle"]={{"id","csl.exp05.scalar-history-enumerator/1"},
        {"scope","enumerates every listed fixed action and disturbance vertex; evaluates original scalar dynamics, safe set, and terminal cost"}};
    const auto canonical=manifest.dump();
    const auto content=take(problem::snapshot_content(std::as_bytes(std::span<const char>{canonical.data(),canonical.size()})));
    request.problem.value="csl.problem.v1.sha256:"+problem::hex(content.digest());
    const auto truth=oracle(request);

    std::array<std::vector<std::int64_t>,2> timings;
    std::vector<Json> numerical_trials,validated_trials;
    Json last_numerical,last_validated;
    Json numerical_plan_evidence,validated_plan_evidence;
    double numerical_value{},validated_lower{},validated_upper{};
    std::size_t numerical_plan_count{},validated_plan_count{};
    auto run_numerical=[&] {
        const auto start=std::chrono::steady_clock::now();
        const auto outcome=finite_action_minimax(request,{2,2,0});
        const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
        if(!std::holds_alternative<FiniteMinimaxOptimal>(outcome)) throw std::runtime_error("numerical solver did not complete");
        const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
        timings[0].push_back(ns);
        numerical_value=result.value;numerical_plan_count=result.plans.size();
        numerical_plan_evidence=Json::array();
        for(const auto& entry:result.plans) {
            if(const auto* plan=std::get_if<FinitePlanFeasible>(&entry)) {
                const auto& terminal=std::get<sets::VRepresentation>(plan->terminal.representation()).vertices;
                Json vertices=Json::array();
                for(std::size_t row=0;row<terminal.rows();++row)vertices.push_back(terminal(row,0));
                numerical_plan_evidence.push_back({{"status","feasible"},{"action_indices",plan->action_indices},
                    {"worst_value",plan->worst_value},{"maximizer",plan->maximizer},
                    {"evaluated_vertices",plan->evaluated_vertices},{"terminal_vertices",std::move(vertices)}});
            } else {
                const auto& rejected=std::get<FinitePlanRejected>(entry);
                numerical_plan_evidence.push_back({{"status","rejected"},{"action_indices",rejected.action_indices},
                    {"stage",rejected.stage},{"violating_successor",rejected.violating_successor}});
            }
        }
        last_numerical={{"method","csl.finite-action-minimax.numerical/1"},{"termination","completed"},
            {"outcome","optimal"},{"value",result.value},{"elapsed_ns",ns},{"plan_count",result.plans.size()},
            {"plans",numerical_plan_evidence}};
        numerical_trials.push_back(last_numerical);
    };
    auto run_validated=[&] {
        const auto start=std::chrono::steady_clock::now();
        const auto outcome=validated_finite_action_minimax(validated(request),{2,2,1000});
        const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
        if(!std::holds_alternative<ValidatedMinimaxBounds>(outcome)) throw std::runtime_error("validated solver did not produce bounds");
        const auto& result=std::get<ValidatedMinimaxBounds>(outcome);
        timings[1].push_back(ns);
        validated_lower=result.lower();validated_upper=result.upper();validated_plan_count=result.plans().size();
        validated_plan_evidence=Json::array();
        for(const auto& entry:result.plans()) {
            if(const auto* plan=std::get_if<ValidatedPlanFeasible>(&entry)) {
                Json margins=Json::array();
                for(const auto& margin:plan->stage_constraint_margins)
                    margins.push_back({{"stage",margin.stage},{"row",margin.row},
                        {"kind",static_cast<int>(margin.kind)},
                        {"residual_hull",{margin.residual_hull.lower,margin.residual_hull.upper}}});
                validated_plan_evidence.push_back({{"status","feasible"},{"action_indices",plan->action_indices},
                    {"worst_case",{plan->worst_case.lower,plan->worst_case.upper}},
                    {"histories_examined",plan->histories_examined},{"stage_constraint_margins",std::move(margins)}});
            } else if(const auto* plan=std::get_if<ValidatedPlanInfeasible>(&entry)) {
                validated_plan_evidence.push_back({{"status","infeasible"},{"action_indices",plan->action_indices},
                    {"stage",plan->witness.stage},{"row",plan->witness.row},
                    {"residual",{plan->witness.residual.lower,plan->witness.residual.upper}}});
            } else {
                const auto& unresolved=std::get<ValidatedPlanUnresolved>(entry);
                validated_plan_evidence.push_back({{"status","unresolved"},{"action_indices",unresolved.action_indices},
                    {"worst_case",{unresolved.worst_case.lower,unresolved.worst_case.upper}},
                    {"histories_examined",unresolved.histories_examined}});
            }
        }
        last_validated={{"method","csl.finite-action-minimax.validated/1"},{"termination","completed"},
            {"outcome","bounded"},{"lower",result.lower()},{"upper",result.upper()},
            {"elapsed_ns",ns},{"plan_count",result.plans().size()},{"plans",validated_plan_evidence}};
        validated_trials.push_back(last_validated);
    };
    run_numerical();run_validated(); // warm-up
    timings[0].clear();timings[1].clear();
    numerical_trials.clear();validated_trials.clear();
    for(std::size_t repetition=0;repetition<7;++repetition) {
        if(repetition%2==0){run_numerical();run_validated();}
        else {run_validated();run_numerical();}
    }
    auto statistics=[](std::vector<std::int64_t> values) {
        std::sort(values.begin(),values.end());
        return Json{{"samples_ns",values},{"median_ns",values[values.size()/2]},
            {"min_ns",values.front()},{"max_ns",values.back()}};
    };
    const double expected=truth.at("global_minimax_value").get<double>();
    const auto numerical_check=finite_action_minimax(request,{2,2,0});
    const auto validated_check=validated_finite_action_minimax(validated(request),{2,2,1000});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(numerical_check)||
       !std::holds_alternative<ValidatedMinimaxBounds>(validated_check))
        throw std::runtime_error("final comparison replay failed");
    const auto& numerical_plans=std::get<FiniteMinimaxOptimal>(numerical_check).plans;
    const auto& validated_plans=std::get<ValidatedMinimaxBounds>(validated_check).plans();
    const bool complete_numerical=std::all_of(numerical_plans.begin(),numerical_plans.end(),
        [](const auto& plan){return std::holds_alternative<FinitePlanFeasible>(plan);});
    const bool complete_validated=std::all_of(validated_plans.begin(),validated_plans.end(),
        [](const auto& plan){return std::holds_alternative<ValidatedPlanFeasible>(plan);});
    bool per_plan_agreement=complete_numerical&&complete_validated&&
        numerical_plans.size()==truth.at("plans").size()&&validated_plans.size()==truth.at("plans").size();
    for(std::size_t i=0;per_plan_agreement&&i<truth.at("plans").size();++i) {
        const auto& oracle_plan=truth.at("plans")[i];
        const auto& numeric_plan=std::get<FinitePlanFeasible>(numerical_plans[i]);
        const auto& interval_plan=std::get<ValidatedPlanFeasible>(validated_plans[i]);
        const double oracle_cost=oracle_plan.at("worst_cost").get<double>();
        per_plan_agreement=numeric_plan.action_indices==std::vector<std::size_t>{i}&&
            numeric_plan.worst_value==oracle_cost&&
            interval_plan.action_indices==std::vector<std::size_t>{i}&&
            interval_plan.worst_case.lower<=oracle_cost&&oracle_cost<=interval_plan.worst_case.upper;
    }
    const bool claims_agree=per_plan_agreement&&numerical_value==expected&&
        validated_lower<=expected&&expected<=validated_upper&&numerical_plan_count==2&&validated_plan_count==2;
    namespace ar=artifacts;
    const ProblemId problem_id=request.problem;
    const auto numerical_method=std::string{"csl.finite-action-minimax.numerical"};
    const auto validated_method=std::string{"csl.finite-action-minimax.validated"};
    if(numerical_trials.size()!=7||validated_trials.size()!=7)throw std::runtime_error("comparison repetitions incomplete");
    std::vector<ar::RecordedRunArtifact> numerical_runs,validated_runs;
    for(std::size_t repetition=0;repetition<7;++repetition) {
        const auto& ntrial=numerical_trials[repetition];
        numerical_runs.push_back(record_attempt(numerical_method,"issue422-numerical-r"+std::to_string(repetition),
            Assurance::numerical,ntrial.at("value"),ntrial.at("value"),canonical,ntrial.at("plans"),truth,
            problem_id,request.system.dimensions(),CSL_ISSUE422_NUMERICAL_SOURCE_SHA256));
        const auto& vtrial=validated_trials[repetition];
        validated_runs.push_back(record_attempt(validated_method,"issue422-validated-r"+std::to_string(repetition),
            Assurance::validated,vtrial.at("lower"),vtrial.at("upper"),canonical,vtrial.at("plans"),truth,
            problem_id,request.system.dimensions(),CSL_ISSUE422_VALIDATED_SOURCE_SHA256));
    }
    const auto config_n=take_artifact(ar::comparison_configuration_id(numerical_runs.front()));
    const auto config_v=take_artifact(ar::comparison_configuration_id(validated_runs.front()));
    const auto request_n=take_artifact(ar::comparison_request_digest(numerical_runs.front()));
    const auto request_v=take_artifact(ar::comparison_request_digest(validated_runs.front()));
    if(request_n!=request_v)throw std::runtime_error("paired solver requests are not compatible");
    const Json spec_json={{"arms",Json::array({
            {{"configuration_id",config_n.value},{"strategy",numerical_method},{"instrumentation","disabled"}},
            {{"configuration_id",config_v.value},{"strategy",validated_method},{"instrumentation","disabled"}}})},
        {"input_manifest_hash",problem::hex(content.digest())},
        {"input_manifest_source","csl.exp05-finite-minimax-case/1"},
        {"problem_id",problem_id.value},{"repetitions",7},
        {"request_digest",problem::hex(request_n)},{"schema","csl.comparison-spec/2"}};
    const auto spec=owned(spec_json.dump());
    std::vector<ar::ComparisonAttempt> comparison_attempts;
    for(std::size_t repetition=0;repetition<7;++repetition) {
        const auto& trial=numerical_trials[repetition];const auto& run=numerical_runs[repetition];
        const Json event={{"schema","csl.exp05-fixed-plan-event/1"},{"status","passed"},
            {"strategy",numerical_method},{"instrumentation","disabled"},
            {"repetition",repetition},{"elapsed_ns",trial.at("elapsed_ns")},
            {"outcome","optimal"},{"value",trial.at("value")}};
        comparison_attempts.push_back({0,static_cast<std::uint32_t>(repetition),ar::AttemptStatus::completed,
            {ar::RunId{"issue422-numerical-r"+std::to_string(repetition)},run.content().digest()},run,event.dump()});
    }
    for(std::size_t repetition=0;repetition<7;++repetition) {
        const auto& trial=validated_trials[repetition];const auto& run=validated_runs[repetition];
        const Json event={{"schema","csl.exp05-fixed-plan-event/1"},{"status","passed"},
            {"strategy",validated_method},{"instrumentation","disabled"},
            {"repetition",repetition},{"elapsed_ns",trial.at("elapsed_ns")},
            {"outcome","validated_bounds"},{"lower",trial.at("lower")},{"upper",trial.at("upper")}};
        comparison_attempts.push_back({1,static_cast<std::uint32_t>(repetition),ar::AttemptStatus::completed,
            {ar::RunId{"issue422-validated-r"+std::to_string(repetition)},run.content().digest()},run,event.dump()});
    }
    const auto comparison=take_artifact(ar::encode_recorded_comparison(spec,comparison_attempts));
    const auto comparison_text=std::string(reinterpret_cast<const char*>(comparison.content().bytes().data()),comparison.content().bytes().size());
    if(!std::holds_alternative<ar::RecordedComparisonArtifact>(ar::decode_recorded_comparison(comparison_text)))
        throw std::runtime_error("comparison-record failed decode round trip");
    return {{"schema","csl.exp05-fixed-plan-comparison-observation/1"},
        {"source_revision",CSL_ISSUE422_SOURCE_COMMIT},
        {"harness_sha256",CSL_ISSUE422_HARNESS_SHA256},
        {"input_manifest",manifest},{"input_manifest_sha256",problem::hex(content.digest())},
        {"attempts",Json::array({last_numerical,last_validated})},
        {"timing_summary",Json::array({statistics(timings[0]),statistics(timings[1])})},
        {"warmups",1},{"measured_repetitions_per_method",7},
        {"independent_oracle",truth},{"comparison_claim",claims_agree?"supported":"not_established"},
        {"comparison_record",Json::parse(comparison_text)}};
}
}

int main() {
    try { std::cout << main_run().dump(2) << '\n'; return 0; }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
