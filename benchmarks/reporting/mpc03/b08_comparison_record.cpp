#include <csl/artifacts/comparison_manifest.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>

namespace {
using Json=nlohmann::json;
namespace ar=csl::artifacts;
using namespace csl;

template<class T> T take(ar::ArtifactResult<T> result) {
    if(!std::holds_alternative<T>(result)) {
        const auto& error=std::get<ar::ArtifactError>(result);
        throw std::runtime_error(error.path+": "+error.message);
    }
    return std::get<T>(std::move(result));
}
problem::ResolvedContent content(std::string_view bytes) {
    auto result=problem::snapshot_content(std::as_bytes(std::span<const char>{bytes.data(),bytes.size()}));
    if(!std::holds_alternative<problem::ResolvedContent>(result))
        throw std::runtime_error("could not hash saved B08 evidence");
    return std::get<problem::ResolvedContent>(std::move(result));
}
std::string read(const std::filesystem::path& path) {
    std::ifstream input(path,std::ios::binary);
    if(!input)throw std::runtime_error("cannot read "+path.string());
    std::string bytes{std::istreambuf_iterator<char>{input},std::istreambuf_iterator<char>{}};
    if(input.bad())throw std::runtime_error("failed reading "+path.string());
    return bytes;
}
std::string digest_hex(const problem::ContentDigest& digest) { return problem::hex(digest); }
ar::ResolvedConfiguration configuration(std::string method,std::string version,std::string driver_hash) {
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    ar::ConfigurationInput input;
    input.collection={false,ar::CollectionMode::summary,0,0,0,0};
    input.modules={{"strategy",{{method},std::move(version),missing},{{"source_sha256",ar::OptionValue{ar::OptionScalar{driver_hash}}}}}};
    input.numerical={0,0};input.resources={1,1,1,{}};
    input.output={ar::OutputKind::program,Assurance::numerical,
        FamilyTarget::exact_optimal_relation,{"csl.polyhedron.h"},{0,0,{}, {}}};
    input.selector={{"csl.selector.none"},"1",{}};
    input.strategy={{method},{},{},{},{},{},{},input.selector.id,input.output.representation};
    input.workspace=ar::WorkspacePolicy::fresh;
    return take(ar::resolve_configuration(std::move(input)));
}
ar::Attachment attachment(std::string id,std::string schema,std::string media,std::string_view bytes) {
    auto value=content(bytes);
    return {{std::move(id)},ar::AttachmentRole::certificate,value.digest(),value.bytes().size(),
        std::move(media),std::move(schema),{},value};
}
ar::RecordedRunArtifact make_run(std::string method,std::string run_id,const Json& evidence,
        const std::string& manifest,const std::string& solver,const std::string& oracle,
        const std::string& svg,const ProblemId& problem_id,double lower,double upper,
        std::string mathematical_outcome) {
    const auto& solver_capture=evidence.at("solver");
    auto config=configuration(method,"PySCIPOpt/"+solver_capture.at("pyscipopt_version").get<std::string>()+
        ";SCIP/"+solver_capture.at("scip_version").get<std::string>(),
        evidence.at("driver_sha256").get<std::string>());
    const ar::RunId run{run_id};
    const ar::CollectionSettings settings{false,ar::CollectionMode::summary,0,0,0,0};
    const ar::CollectionRecord collection{problem_id,config.identity(),run,settings,{}, {}, {},
        ar::Unavailable{ar::MissingReason::collection_disabled,{}},{},{}};
    auto statistics=take(ar::publish_collection(collection));
    const ProgramIdentity subject{problem_id,{method}};
    const ProgramBoundEvidence bound_evidence{subject,Unestablished{},
        {"External SCIP capture; see attached immutable solver output and exact displayed-data oracle."}};
    std::optional<ProgramObjectiveBound> lo,hi;
    if(std::isfinite(lower))lo=ProgramObjectiveBound{lower,bound_evidence};
    if(std::isfinite(upper))hi=ProgramObjectiveBound{upper,bound_evidence};
    Json outcome={{"schema","csl.mpc03-b08-comparison-outcome/1"},
        {"method",method},{"mathematical_outcome",mathematical_outcome},
        {"solver_termination",evidence.at("solver").at("status")},
        {"solver_result",evidence.at("solver")},
        {"independent_exact_reference",evidence.at("oracle")},
        {"scope","L04 displayed rounded data; four-step open-loop case"},
        {"claim_limits",Json::array({"one exploratory capture; no timing ranking; printed decimals treated as exact by the rational oracle"})}};
    const auto outcome_text=outcome.dump();
    std::vector<ar::Attachment> attachments{
        attachment("b08-case","csl.mpc03-b08-case/1","application/json",manifest),
        attachment("b08-solver-output","csl.mpc03-b08-solver-output/1","application/json",solver),
        attachment("b08-independent-oracle","csl.mpc03-b08-exact-oracle/1","application/json",oracle),
        attachment("b08-disturbance-tube","image/svg+xml","image/svg+xml",svg),
        attachment("b08-comparison-outcome","csl.mpc03-b08-comparison-outcome/1","application/json",outcome_text)};
    const ProgramResult result{Termination::completed,
        {subject,mathematical_outcome=="optimal"?MathematicalOutcome::optimal:MathematicalOutcome::undetermined,
         Unestablished{}, {"See attached scoped exact-oracle evidence and solver-output evidence."}},
        {},{std::move(lo),std::move(hi)},"External SCIP result retained without native-run interpretation.",{}};
    ar::RunRecord record{problem_id,{4,1,2},4,std::move(config),run,
        ar::ProgramFinal{result,{}},statistics,
        {ar::Unavailable{ar::MissingReason::not_instrumented,{}},ar::Unavailable{ar::MissingReason::not_instrumented,{}},
         ar::Unavailable{ar::MissingReason::not_instrumented,{}},ar::Unavailable{ar::MissingReason::not_instrumented,{}},
         false,ar::MemoryAccounting::unlimited},{},std::move(attachments),ar::ProblemProvenance::identity_recorded,{}};
    return take(ar::encode_recorded_run(take(ar::publish_identity_recorded_run(std::move(record)))));
}
std::string artifact_text(const problem::ResolvedContent& value) {
    return {reinterpret_cast<const char*>(value.bytes().data()),value.bytes().size()};
}
void write_exclusive(const std::filesystem::path& path,std::string_view bytes) {
    if(std::filesystem::exists(path))throw std::runtime_error("refusing to overwrite "+path.string());
    std::ofstream output(path,std::ios::binary|std::ios::out);
    if(!output)throw std::runtime_error("cannot create "+path.string());
    output.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));
    if(!output)throw std::runtime_error("cannot write "+path.string());
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=3)throw std::runtime_error("usage: csl_mpc03_b08_comparison_record <saved-b08-bundle-dir> <new-output-file>");
        const std::filesystem::path bundle=argv[1],output=argv[2];
        const auto record_text=read(bundle/"record.json"),solver_text=read(bundle/"solver-output.json"),
            oracle_text=read(bundle/"independent-oracle.json"),svg_text=read(bundle/"disturbance-tube.svg");
        const auto record=Json::parse(record_text),solver=Json::parse(solver_text),oracle=Json::parse(oracle_text);
        if(record.at("schema")!="csl.mpc03-b08-miQCP-record/1"||
           solver.at("schema")!="csl.mpc03-b08-solver-output/1")throw std::runtime_error("unsupported B08 bundle schemas");
        const auto manifest=record.at("scenario").dump();
        const auto manifest_content=content(manifest);
        if(digest_hex(manifest_content.digest())!=record.at("scenario_sha256").get<std::string>()||
           digest_hex(content(solver_text).digest())!=record.at("solver_output_sha256").get<std::string>()||
           digest_hex(content(oracle_text).digest())!=record.at("oracle_sha256").get<std::string>())
            throw std::runtime_error("frozen B08 input hashes do not match record.json");
        if(record.at("source_commit")!=solver.at("source_commit")||
           record.at("scenario_sha256")!=solver.at("scenario_sha256")||
           record.at("result").at("finite")!=solver.at("finite_miqcp")||
           record.at("result").at("relaxation")!=solver.at("convex_control_qcp")||
           record.at("result").at("exact_reference")!=oracle)
            throw std::runtime_error("B08 record, solver output, and exact oracle disagree");
        if(solver.at("warmups")!=0||solver.at("attempt_count_per_formulation")!=1||
           solver.at("timing_scope")!="one exploratory solve per formulation; no performance comparison")
            throw std::runtime_error("B08 capture no longer matches the declared one-shot scope");
        if(solver.at("disturbance_history_count")!=256)
            throw std::runtime_error("B08 capture must retain all 256 disturbance histories");
        const std::array<std::uint64_t,5> expected_stage_counts{1,4,16,64,256};
        const auto& tube=record.at("result").at("projected_tube");
        if(tube.size()!=expected_stage_counts.size())throw std::runtime_error("B08 projected tube is incomplete");
        for(std::size_t index=0;index<expected_stage_counts.size();++index)
            if(tube.at(index).at("corner_history_count")!=expected_stage_counts[index])
                throw std::runtime_error("B08 projected tube omits stage disturbance histories");
        const auto finite=solver.at("finite_miqcp"),relaxed=solver.at("convex_control_qcp");
        if(finite.at("formulation")!="finite-miQCP"||relaxed.at("formulation")!="convex-control-QCP")
            throw std::runtime_error("B08 formulation identities changed");
        const auto upper=record.at("result").at("bounds_squared").at("upper").get<double>();
        const auto lower=record.at("result").at("bounds_squared").at("lower").get<double>();
        if(finite.at("status")!="optimal"||relaxed.at("status")!="optimal"||
           !finite.at("objective_squared").is_number()||!relaxed.at("global_dual_bound_squared").is_number())
            throw std::runtime_error("B08 saved solver statuses do not support the completed-capture adapter");
        bool exact_plan=false;
        for(const auto& indices:record.at("result").at("exact_minimizing_action_indices"))
            if(indices==finite.at("action_indices"))exact_plan=true;
        if(!exact_plan||std::abs(finite.at("objective_squared").get<double>()-upper)>1.0e-6||
           lower>upper+1.0e-6)
            throw std::runtime_error("B08 solver outcomes disagree with the exact finite optimum or bound direction");
        const auto problem_id=ProblemId{"csl.problem.v1.sha256:"+digest_hex(manifest_content.digest())};
        const auto finite_run=make_run("external.pyscipopt.finite-action-miqcp","mpc03-b08-finite-miQCP",
            {{"record",record},{"oracle",oracle},{"solver",finite},{"driver_sha256",solver.at("driver_sha256")}},manifest,solver_text,oracle_text,svg_text,
            problem_id,upper,upper,"optimal");
        const auto relaxed_run=make_run("external.pyscipopt.convex-control-qcp","mpc03-b08-convex-control-qcp",
            {{"record",record},{"oracle",oracle},{"solver",relaxed},{"driver_sha256",solver.at("driver_sha256")}},manifest,solver_text,oracle_text,svg_text,
            problem_id,lower,std::numeric_limits<double>::infinity(),"undetermined");
        const auto request_a=take(ar::comparison_request_digest(finite_run));
        const auto request_b=take(ar::comparison_request_digest(relaxed_run));
        if(request_a!=request_b)throw std::runtime_error("B08 arms do not share the same requested problem/profile identity");
        const auto config_a=take(ar::comparison_configuration_id(finite_run));
        const auto config_b=take(ar::comparison_configuration_id(relaxed_run));
        Json spec={{"schema","csl.comparison-spec/2"},{"problem_id",problem_id.value},
            {"request_digest",digest_hex(request_a)},{"arms",Json::array({
                {{"configuration_id",config_a.value},{"strategy","external.pyscipopt.finite-action-miqcp"},{"instrumentation","disabled"}},
                {{"configuration_id",config_b.value},{"strategy","external.pyscipopt.convex-control-qcp"},{"instrumentation","disabled"}}})},
            {"repetitions",1},{"input_manifest_hash",digest_hex(manifest_content.digest())},
            {"input_manifest_source","csl.mpc03-b08-case/1"}};
        const auto spec_text=spec.dump();
        auto spec_content=content(spec_text);
        const auto event_a=Json{{"schema","csl.mpc03-b08-comparison-event/1"},{"repetition",0},
            {"status","passed"},{"strategy","external.pyscipopt.finite-action-miqcp"},{"instrumentation","disabled"},
            {"formulation","finite-action MIQCP"},{"solver_termination",finite.at("status")},
            {"elapsed_ns_single_capture",finite.at("elapsed_ns_single_capture")},{"mathematical_outcome","optimal"},
            {"objective_squared",finite.at("objective_squared")},{"exact_upper_bound",upper},
            {"projection","disturbance-tube.svg"},{"no_speed_claim",true}}.dump();
        const auto event_b=Json{{"schema","csl.mpc03-b08-comparison-event/1"},{"repetition",0},
            {"status","passed"},{"strategy","external.pyscipopt.convex-control-qcp"},{"instrumentation","disabled"},
            {"formulation","continuous-control QCP relaxation"},{"solver_termination",relaxed.at("status")},
            {"elapsed_ns_single_capture",relaxed.at("elapsed_ns_single_capture")},{"mathematical_outcome","undetermined"},
            {"relaxation_lower_bound",lower},{"finite_feasible_upper_bound",upper},
            {"projection","disturbance-tube.svg"},{"no_speed_claim",true}}.dump();
        std::vector<ar::ComparisonAttempt> attempts{
            {0,0,ar::AttemptStatus::completed,{ar::RunId{"mpc03-b08-finite-miQCP"},finite_run.content().digest()},finite_run,event_a},
            {1,0,ar::AttemptStatus::completed,{ar::RunId{"mpc03-b08-convex-control-qcp"},relaxed_run.content().digest()},relaxed_run,event_b}};
        auto archived=take(ar::encode_recorded_comparison(spec_content,attempts));
        auto decoded=take(ar::decode_recorded_comparison(artifact_text(archived.content())));
        write_exclusive(output,artifact_text(decoded.content()));
        std::cout<<"comparison_spec_id="<<digest_hex(decoded.spec_id().digest)<<"\ncomparison_run_id="
            <<digest_hex(decoded.identity().digest)<<"\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
