#include <csl/artifacts/comparison_manifest.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cctype>
#include <cmath>
#include <initializer_list>
#include <limits>
#include <optional>
#include <set>
#include <stdexcept>

namespace csl::artifacts {
namespace {
using Json = nlohmann::json;
void preflight(std::string_view text, const DecodeLimits& limits) {
    if (text.size() > limits.bytes) throw ArtifactError{ArtifactErrorCode::limit, "comparison.bytes", "Input byte capacity exceeded"};
    std::uint64_t depth=0, nodes=0;
    const auto node=[&] { if (++nodes > limits.nodes) throw ArtifactError{ArtifactErrorCode::limit,"comparison.nodes","Node capacity exceeded"}; };
    for (std::size_t i=0;i<text.size();++i) {
        const char c=text[i];
        if (c=='"') { node(); std::uint64_t length=0; bool closed=false;
            for (++i;i<text.size();++i) { const char ch=text[i]; if(ch=='"'){closed=true;break;}
                if(ch=='\\'&&i+1<text.size()){++i;if(text[i]=='u')i=std::min(i+4,text.size()-1);++length;} else ++length;
                if(length>limits.string_bytes)throw ArtifactError{ArtifactErrorCode::limit,"comparison.string","String capacity exceeded"};
            }
            if(!closed)throw ArtifactError{ArtifactErrorCode::invalid_input,"comparison.syntax","Unterminated string"};
        } else if(c=='{'||c=='['){node();if(++depth>limits.depth)throw ArtifactError{ArtifactErrorCode::limit,"comparison.depth","Depth capacity exceeded"};}
        else if(c=='}'||c==']'){if(depth==0)throw ArtifactError{ArtifactErrorCode::invalid_input,"comparison.syntax","Unexpected close"};--depth;}
        else if(c=='t'||c=='f'||c=='n'||c=='-'||(c>='0'&&c<='9')){node();while(i+1<text.size()&&text[i+1]!=','&&text[i+1]!=']'&&text[i+1]!='}'&&text[i+1]!=' '&&text[i+1]!='\n'&&text[i+1]!='\r'&&text[i+1]!='\t')++i;}
    }
}
Json parse_bounded(std::string_view text, const DecodeLimits& limits) {
    preflight(text,limits); std::vector<std::set<std::string>> keys;
    return Json::parse(text.begin(),text.end(),[&](int,Json::parse_event_t event,Json& parsed){
        if(event==Json::parse_event_t::object_start)keys.emplace_back();
        else if(event==Json::parse_event_t::key){if(keys.empty()||!keys.back().insert(parsed.get<std::string>()).second)throw ArtifactError{ArtifactErrorCode::invalid_input,"comparison.duplicate_key","Duplicate object key"};}
        else if(event==Json::parse_event_t::object_end) keys.pop_back();
        return true;
    });
}
ArtifactError error(ArtifactErrorCode code, std::string path, std::string message) {
    return {code, std::move(path), std::move(message)};
}
std::string status_name(AttemptStatus status) {
    switch (status) {
    case AttemptStatus::completed: return "completed";
    case AttemptStatus::failed: return "failed";
    case AttemptStatus::refused: return "refused";
    case AttemptStatus::unsupported: return "unsupported";
    case AttemptStatus::timed_out: return "timed_out";
    case AttemptStatus::cancelled: return "cancelled";
    case AttemptStatus::resource_limited: return "resource_limited";
    case AttemptStatus::incomplete: return "incomplete";
    }
    return {};
}
AttemptStatus parse_status(const std::string& value) {
    if (value == "completed") return AttemptStatus::completed;
    if (value == "failed") return AttemptStatus::failed;
    if (value == "refused") return AttemptStatus::refused;
    if (value == "unsupported") return AttemptStatus::unsupported;
    if (value == "timed_out") return AttemptStatus::timed_out;
    if (value == "cancelled") return AttemptStatus::cancelled;
    if (value == "resource_limited") return AttemptStatus::resource_limited;
    if (value == "incomplete") return AttemptStatus::incomplete;
    throw std::invalid_argument("Unknown attempt status");
}
bool measurement_status_matches(AttemptStatus status, const Json& measurement) {
    if (!measurement.is_object() || !measurement.contains("status") || !measurement.at("status").is_string())
        return false;
    const auto value=measurement.at("status").get<std::string>();
    if(value=="passed")return status==AttemptStatus::completed;
    if(value=="failed")return status==AttemptStatus::failed;
    if(value=="refused")return status==AttemptStatus::refused;
    if(value=="unsupported")return status==AttemptStatus::unsupported;
    if(value=="timed_out")return status==AttemptStatus::timed_out;
    if(value=="cancelled")return status==AttemptStatus::cancelled;
    if(value=="resource_limited")return status==AttemptStatus::resource_limited;
    return value=="incomplete"&&status==AttemptStatus::incomplete;
}
bool status_matches(AttemptStatus status, const Json& run) {
    if(run.value("schema",std::string{})=="csl.external-method-run/1")
        return run.at("status")==status_name(status);
    const auto& final=run.at("final");
    const auto kind=final.at("kind").get<std::string>();
    if(kind=="synthesis"||kind=="program"||kind=="finite_minimax") {
        const auto& result=kind=="synthesis"||kind=="finite_minimax"?final.at("value"):final.at("value").at("result");
        const auto termination=result.at("termination").get<std::string>();
        if(termination=="completed")return status==AttemptStatus::completed;
        if(termination=="cancelled")return status==AttemptStatus::cancelled;
        if(termination=="deadline_expired")return status==AttemptStatus::timed_out;
        if(termination=="resource_limit")return status==AttemptStatus::resource_limited;
        if(termination=="operation_rejected")return status==
            (kind=="synthesis"?AttemptStatus::unsupported:AttemptStatus::refused);
        if(termination=="contract_rejected")return status==AttemptStatus::failed;
        return termination=="numerical_failure"&&status==AttemptStatus::failed;
    }
    if(kind=="unsupported")return status==AttemptStatus::unsupported;
    if(kind=="failed")return status==AttemptStatus::failed;
    if(kind!="skipped")return false;
    const auto reason=final.at("value").at("reason").get<std::string>();
    if(reason=="cancelled")return status==AttemptStatus::cancelled;
    if(reason=="deadline"||reason=="task_limit"||reason=="reservation_exceeds_budget")
        return status==AttemptStatus::resource_limited;
    return reason=="batch_failed"&&status==AttemptStatus::incomplete;
}
std::string bytes_to_string(std::span<const std::byte> bytes) {
    std::string out; out.reserve(bytes.size());
    for (auto b : bytes) out.push_back(static_cast<char>(std::to_integer<unsigned char>(b)));
    return out;
}
ArtifactResult<problem::ResolvedContent> own(std::string_view text);
bool input_manifest_attached(const Json& run,const Json& spec) {
    if(spec.value("schema",std::string{})=="csl.comparison-spec/1")return true;
    if(spec.at("input_manifest_source")=="resolved-problem-canonical-bytes")return true;
    const auto expected=spec.at("input_manifest_hash").get<std::string>();
    if(run.value("schema",std::string{})=="csl.external-method-run/1") {
        const auto& manifest=run.at("input_manifest");
        return manifest.at("schema")==spec.at("input_manifest_source")&&
            manifest.at("sha256")==expected;
    }
    const auto source=spec.at("input_manifest_source").get<std::string>();
    const auto expected_role=source=="csl.mpc01-canonical-input/1"?"diagnostics":"certificate";
    const auto& attachments=run.at("attachments");
    std::size_t matches=0;
    for(const auto& attachment:attachments)
        if(attachment.at("role")==expected_role&&
           attachment.at("schema")==source&&
           attachment.at("digest")==expected&&!attachment.at("content").is_null())++matches;
    return matches==1;
}
Json common_request(const Json& run) {
    auto request=run.at("configuration").at("value");
    request.erase("modules");
    request.at("collection").erase("enabled");
    const auto strategy=request.at("strategy");
    request["strategy"]={{"selector",strategy.at("selector")},{"representation",strategy.at("representation")}};
    return request;
}
problem::ContentDigest request_digest(const Json& run) {
    const auto text=common_request(run).dump();
    auto content=own(text);
    if(const auto* value=std::get_if<problem::ResolvedContent>(&content))return value->digest();
    throw std::bad_alloc();
}
struct SpecShape {
    bool record_v1{};
    std::vector<std::string> configurations;
    std::vector<std::string> strategies;
    std::vector<std::string> instrumentation;
    std::uint32_t repetitions{};
    Json environment{nullptr};
};
bool exact_fields(const Json& value, std::initializer_list<std::string_view> fields) {
    if(!value.is_object()||value.size()!=fields.size())return false;
    return std::all_of(fields.begin(),fields.end(),[&](const auto field){return value.contains(field);});
}
bool nonnegative_integer(const Json& value) {
    if(value.is_number_unsigned())return true;
    return value.is_number_integer()&&value.get<std::int64_t>()>=0;
}
bool optional_nonnegative_integer(const Json& value) {
    return value.is_null()||nonnegative_integer(value);
}
bool nonempty_string(const Json& value) {
    return value.is_string()&&!value.get_ref<const std::string&>().empty();
}
bool valid_counterexample(const Json& witness,std::string_view relation,
    const Json& input_set,const Json& output_set) {
    if(!exact_fields(witness,{"kind","point","contained_in","excluded_from"})||
        witness.at("kind")!="point_membership"||!witness.at("point").is_array()||
        witness.at("point").empty())return false;
    for(const auto& coordinate:witness.at("point"))
        if(!coordinate.is_number()||!std::isfinite(coordinate.get<double>()))return false;
    const auto& contained=relation=="outer"?input_set:output_set;
    const auto& excluded=relation=="outer"?output_set:input_set;
    return witness.at("contained_in")==contained&&witness.at("excluded_from")==excluded;
}
bool known_structural_basis(const Json& value) {
    if(!value.is_string())return false;
    static constexpr std::array<std::string_view,9> bases{
        "identical_set","empty_subset","universal_superset","h_constraint_containment",
        "h_point_containment","v_h_containment","h_v_containment","generator_axis_cover",
        "v_ellipsoid_containment"};
    const auto& basis=value.get_ref<const std::string&>();
    return std::find(bases.begin(),bases.end(),basis)!=bases.end();
}
bool complete_inclusion_oracle_kind(const Json& value) {
    return value=="exact_dyadic_all_vertices";
}
bool valid_checker_resource(const Json& resource) {
    if(!exact_fields(resource,{"requested","enforced","observed","mechanism","scope","unavailable_reason"})||
        !optional_nonnegative_integer(resource.at("requested"))||
        !optional_nonnegative_integer(resource.at("enforced"))||
        !optional_nonnegative_integer(resource.at("observed")))return false;
    const auto& mechanism=resource.at("mechanism");
    const auto& scope=resource.at("scope");
    const auto& unavailable=resource.at("unavailable_reason");
    if((!mechanism.is_null()&&!nonempty_string(mechanism))||
        (!scope.is_null()&&!nonempty_string(scope))||
        (!unavailable.is_null()&&!nonempty_string(unavailable)))return false;
    if(!resource.at("enforced").is_null()&&(!nonempty_string(mechanism)||!nonempty_string(scope)))return false;
    if(resource.at("observed").is_null()!=nonempty_string(unavailable))return false;
    if(resource.at("requested").is_null()&&!resource.at("enforced").is_null())return false;
    return true;
}
bool approximation_check_event_matches(const Json& measurement,const Json& run,
    const SpecShape& spec,std::size_t arm,std::uint32_t repetition) {
    if(!exact_fields(measurement,{"schema","status","strategy","instrumentation","repetition","warmup",
        "problem_id","input_set_id","output_set_id","request_id","relation","structural_basis",
        "algorithm","checker"})||
        measurement.at("schema")!="csl.approximation-check-event/1"||
        measurement.at("strategy")!=spec.strategies.at(arm)||
        measurement.at("instrumentation")!=spec.instrumentation.at(arm)||
        measurement.at("repetition")!=repetition||measurement.at("warmup")!=(repetition==0)||
        !nonempty_string(measurement.at("problem_id"))||
        measurement.at("problem_id")!=run.at("problem")||
        !nonempty_string(measurement.at("input_set_id"))||
        !nonempty_string(measurement.at("output_set_id"))||
        !nonempty_string(measurement.at("request_id"))||
        !known_structural_basis(measurement.at("structural_basis"))||
        !run.at("result").is_object()||
        !run.at("result").contains("input_set_id")||
        run.at("result").at("input_set_id")!=measurement.at("input_set_id")||
        !run.at("result").contains("output_set_id")||
        run.at("result").at("output_set_id")!=measurement.at("output_set_id")||
        !run.at("result").contains("request_id")||
        run.at("result").at("request_id")!=measurement.at("request_id")||
        (measurement.at("relation")!="inner"&&measurement.at("relation")!="outer"))return false;

    const auto& algorithm=measurement.at("algorithm");
    if(!exact_fields(algorithm,{"status","elapsed_ns"})||
        !nonempty_string(algorithm.at("status"))||
        algorithm.at("status")!=status_name(parse_status(algorithm.at("status").get<std::string>()))||
        algorithm.at("status")!=(measurement.at("status")=="passed"?"completed":measurement.at("status"))||
        !optional_nonnegative_integer(algorithm.at("elapsed_ns")))return false;
    const auto& checker=measurement.at("checker");
    if(!exact_fields(checker,{"profile","status","outcome","elapsed_ns","budget","resources","oracle"})||
        (checker.at("profile")!="comparison"&&checker.at("profile")!="local_exploration")||
        !optional_nonnegative_integer(checker.at("elapsed_ns")))return false;
    const auto expected_default=checker.at("profile")=="comparison"?5'000'000'000ULL:30'000'000'000ULL;
    const auto& budget=checker.at("budget");
    if(!exact_fields(budget,{"default_wall_time_ns","wall_time_ns"})||
        !nonnegative_integer(budget.at("wall_time_ns"))||
        budget.at("default_wall_time_ns")!=expected_default)return false;
    const auto& resources=checker.at("resources");
    if(!exact_fields(resources,{"wall_time","memory_bytes"})||
        !valid_checker_resource(resources.at("wall_time"))||
        !valid_checker_resource(resources.at("memory_bytes")))return false;
    const auto& wall_time=resources.at("wall_time");
    if(wall_time.at("requested")!=budget.at("wall_time_ns")||
        (!checker.at("elapsed_ns").is_null()&&!wall_time.at("observed").is_null()&&
            checker.at("elapsed_ns")!=wall_time.at("observed")))return false;

    const auto& oracle=checker.at("oracle");
    if(!exact_fields(oracle,{"kind","scope","claim","independent","complete","sound","counterexample"})||
        !nonempty_string(oracle.at("kind"))||oracle.at("scope")!="inclusion"||
        oracle.at("claim")!=measurement.at("relation")||
        !oracle.at("independent").is_boolean()||!oracle.at("complete").is_boolean()||
        !oracle.at("sound").is_boolean())return false;
    const auto checker_status=checker.at("status").get<std::string>();
    const auto outcome=checker.at("outcome").get<std::string>();
    const bool completed=outcome=="completed";
    const bool algorithm_completed=algorithm.at("status")=="completed";
    const auto& counterexample=oracle.at("counterexample");
    if(checker_status=="verified")
        return algorithm_completed&&completed&&complete_inclusion_oracle_kind(oracle.at("kind"))&&
            oracle.at("independent").get<bool>()&&oracle.at("complete").get<bool>()&&
            oracle.at("sound").get<bool>()&&
            counterexample.is_null();
    if(checker_status=="incorrect")
        return algorithm_completed&&completed&&complete_inclusion_oracle_kind(oracle.at("kind"))&&
            oracle.at("independent").get<bool>()&&oracle.at("sound").get<bool>()&&
            valid_counterexample(counterexample,measurement.at("relation").get<std::string>(),
                measurement.at("input_set_id"),measurement.at("output_set_id"));
    if(checker_status!="inconclusive")return false;
    return counterexample.is_null()&&(outcome=="completed"||outcome=="refused"||outcome=="unsupported"||
        outcome=="timed_out"||outcome=="cancelled"||outcome=="resource_limited"||outcome=="incomplete");
}

bool valid_sha256(const Json& value) {
    if(!value.is_string())return false;
    const auto& text=value.get_ref<const std::string&>();
    return text.size()==64&&std::all_of(text.begin(),text.end(),
        [](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
bool valid_git_revision(const Json& value) {
    if(!value.is_string())return false;
    const auto& text=value.get_ref<const std::string&>();
    return text.size()==40&&std::all_of(text.begin(),text.end(),
        [](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
bool positive_small_integer(const Json& value) {
    if(!value.is_number_integer())return false;
    if(value.is_number_unsigned()) {
        const auto integer=value.get<std::uint64_t>();
        return integer>0&&integer<=std::numeric_limits<std::uint32_t>::max();
    }
    const auto integer=value.get<std::int64_t>();
    return integer>0&&integer<=std::numeric_limits<std::uint32_t>::max();
}
void validate_fact(const Json& fact, bool numeric, std::string_view path) {
    if(!fact.is_object()||!fact.contains("status")||!fact.at("status").is_string())
        throw std::invalid_argument(std::string(path)+" has no valid status");
    const auto status=fact.at("status").get<std::string>();
    if(status=="available") {
        if(fact.size()!=2||!fact.contains("value")||
            (numeric?!fact.at("value").is_number_unsigned()&&!fact.at("value").is_number_integer():!fact.at("value").is_string()))
            throw std::invalid_argument(std::string(path)+" available value has the wrong shape");
        if(numeric) {
            if(!positive_small_integer(fact.at("value")))
                throw std::invalid_argument(std::string(path)+" value must be a positive integer");
        } else if(fact.at("value").get_ref<const std::string&>().empty())
            throw std::invalid_argument(std::string(path)+" value must not be empty");
    } else if(status=="unavailable") {
        if(fact.size()!=2||!fact.contains("reason")||!fact.at("reason").is_string()||
            fact.at("reason").get_ref<const std::string&>().empty())
            throw std::invalid_argument(std::string(path)+" unavailable fact requires a reason");
    } else throw std::invalid_argument(std::string(path)+" has an unknown status");
}
void validate_environment(const Json& environment) {
    const bool mpc=environment.value("schema",std::string{})=="csl.mpc01-environment/1";
    if(!exact_fields(environment,{"schema","build","runtime","execution"})||
        (environment.at("schema")!="csl.obs04-environment/1"&&!mpc))
        throw std::invalid_argument("Environment manifest schema or fields are invalid");
    const auto& build=environment.at("build");
    if(!exact_fields(build,{"schema","source_revision","source_tree_sha256","source_snapshot_method","source_dirty",
        "compiler_id","compiler_version","generator","architecture","build_type","cxx_standard",
        "c_flags_sha256","cxx_flags_sha256","executable_link_flags_sha256","target_flags_sha256","backends"})||
        build.at("schema")!=(mpc?"csl.mpc01-build/1":"csl.obs04-build/1")||!valid_git_revision(build.at("source_revision"))||
        !valid_sha256(build.at("source_tree_sha256"))||
        (build.at("source_snapshot_method")!="git-head-tracked-diff-untracked-content-sha256/1"&&
         build.at("source_snapshot_method")!="git-head-tracked-diff-untracked-content-excluding-run-output-sha256/2")||
        !build.at("source_dirty").is_boolean()||
        !build.at("compiler_id").is_string()||build.at("compiler_id").get_ref<const std::string&>().empty()||
        !build.at("compiler_version").is_string()||build.at("compiler_version").get_ref<const std::string&>().empty()||
        !build.at("generator").is_string()||build.at("generator").get_ref<const std::string&>().empty()||
        !build.at("architecture").is_string()||build.at("architecture").get_ref<const std::string&>().empty()||
        build.at("build_type")!="Release"||build.at("cxx_standard")!="20"||
        !valid_sha256(build.at("c_flags_sha256"))||!valid_sha256(build.at("cxx_flags_sha256"))||
        !valid_sha256(build.at("executable_link_flags_sha256"))||
        !valid_sha256(build.at("target_flags_sha256")))
        throw std::invalid_argument("Environment build facts are invalid");
    const auto& backends=build.at("backends");
    if(mpc?!exact_fields(backends,{"osqp","hpipm","blasfeo"}):!exact_fields(backends,{"highs","qhull"}))
        throw std::invalid_argument("Environment backend facts are invalid");
    for(const auto& [name,backend]:backends.items()) {
        if(!exact_fields(backend,{"version","archive_sha256"})||
            !backend.at("version").is_string()||backend.at("version").get_ref<const std::string&>().empty()||
            !valid_sha256(backend.at("archive_sha256")))
            throw std::invalid_argument(std::string("Environment backend fact is invalid: ")+name);
    }
    const auto& runtime=environment.at("runtime");
    if(!exact_fields(runtime,{"schema","binary_sha256","os_family","os_version","kernel",
        "architecture","cpu_model","logical_cpus"})||runtime.at("schema")!="csl.obs04-runtime/1"||
        !runtime.at("os_family").is_string()||runtime.at("os_family").get_ref<const std::string&>().empty()||
        !runtime.at("architecture").is_string()||runtime.at("architecture").get_ref<const std::string&>().empty())
        throw std::invalid_argument("Environment runtime facts are invalid");
    validate_fact(runtime.at("binary_sha256"),false,"runtime.binary_sha256");
    if(runtime.at("binary_sha256").at("status")=="available"&&
        !valid_sha256(runtime.at("binary_sha256").at("value")))
        throw std::invalid_argument("runtime.binary_sha256 value is malformed");
    validate_fact(runtime.at("os_version"),false,"runtime.os_version");
    validate_fact(runtime.at("kernel"),false,"runtime.kernel");
    validate_fact(runtime.at("cpu_model"),false,"runtime.cpu_model");
    validate_fact(runtime.at("logical_cpus"),true,"runtime.logical_cpus");
    const auto& execution=environment.at("execution");
    if(!exact_fields(execution,{"requested_workers","observed_driver_workers","requested_backend_threads",
        "observed_backend_threads","workspace_policy","cache_policy","warmup_repetitions","seed_policy","tolerances"})||
        !positive_small_integer(execution.at("requested_workers"))||
        execution.at("observed_driver_workers")!=1||execution.at("requested_backend_threads")!=1||
        !execution.at("workspace_policy").is_string()||execution.at("workspace_policy")!="fresh-workspace-per-attempt"||
        !execution.at("cache_policy").is_string()||execution.at("cache_policy").get_ref<const std::string&>().empty()||
        execution.at("warmup_repetitions")!=(mpc?0:1)||
        !positive_small_integer(execution.at("requested_backend_threads"))||
        !positive_small_integer(execution.at("observed_driver_workers")))
        throw std::invalid_argument("Environment execution facts are invalid");
    validate_fact(execution.at("observed_backend_threads"),true,"execution.observed_backend_threads");
    const auto& seed=execution.at("seed_policy");
    if(!exact_fields(seed,{"kind","reason"})||seed.at("kind")!="not_applicable"||
        !seed.at("reason").is_string()||seed.at("reason").get_ref<const std::string&>().empty())
        throw std::invalid_argument("Environment seed policy is invalid");
    const auto& tolerances=execution.at("tolerances");
    if(!exact_fields(tolerances,{"absolute","relative"})||!tolerances.at("absolute").is_number()||
        !tolerances.at("relative").is_number()||!std::isfinite(tolerances.at("absolute").get<double>())||
        !std::isfinite(tolerances.at("relative").get<double>())||tolerances.at("absolute").get<double>()<0||
        tolerances.at("relative").get<double>()<0)
        throw std::invalid_argument("Environment numerical tolerances are invalid");
}
SpecShape validate_spec(const Json& spec) {
    if (!spec.is_object() || !spec.contains("problem_id") || !spec.contains("request_digest") ||
        !spec.contains("repetitions"))
        throw std::invalid_argument("Comparison spec fields do not match schema");
    const auto schema=spec.value("schema",std::string{});
    const bool legacy=schema=="csl.comparison-spec/1"&&spec.size()==5&&spec.contains("strategies");
    const bool record=schema=="csl.comparison-spec/2"&&spec.size()==7&&spec.contains("arms")&&
        spec.contains("input_manifest_hash")&&spec.contains("input_manifest_source")&&
        (spec.at("input_manifest_source")=="resolved-problem-canonical-bytes"||
         spec.at("input_manifest_source")=="csl.exp05-finite-minimax-case/1"||
         spec.at("input_manifest_source")=="csl.geometry-hull-input/1"||
         spec.at("input_manifest_source")=="csl.mpc03-b08-case/1"||
         spec.at("input_manifest_source")=="csl.mpc01-canonical-input/1");
    const bool record_with_environment=schema=="csl.comparison-spec/3"&&spec.size()==8&&spec.contains("arms")&&
        spec.contains("input_manifest_hash")&&spec.contains("input_manifest_source")&&
        (spec.at("input_manifest_source")=="resolved-problem-canonical-bytes"||
         spec.at("input_manifest_source")=="csl.exp05-finite-minimax-case/1"||
         spec.at("input_manifest_source")=="csl.geometry-hull-input/1"||
         spec.at("input_manifest_source")=="csl.mpc01-canonical-input/1"||
         spec.at("input_manifest_source")=="csl.mpc03-b08-case/1")&&spec.contains("environment");
    if(!legacy&&!record&&!record_with_environment)throw std::invalid_argument("Comparison spec fields do not match supported schema");
    if(record_with_environment)validate_environment(spec.at("environment"));
    const auto valid_digest=[](const Json& value){
        if(!value.is_string())return false;
        const auto& text=value.get_ref<const std::string&>();
        return text.size()==64&&std::all_of(text.begin(),text.end(),
            [](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
    };
    const auto valid_config_id=[](const Json& value){
        constexpr std::string_view prefix="csl.config.v1.sha256:";
        if(!value.is_string())return false;
        const auto& text=value.get_ref<const std::string&>();
        return text.starts_with(prefix)&&text.size()==prefix.size()+64&&
            std::all_of(text.begin()+static_cast<std::ptrdiff_t>(prefix.size()),text.end(),
                [](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
    };
    if(!spec.at("problem_id").is_string()||spec.at("problem_id").get<std::string>().empty()||!valid_digest(spec.at("request_digest"))||
        ((record||record_with_environment)&&!valid_digest(spec.at("input_manifest_hash"))))
        throw std::invalid_argument("Comparison spec digest is malformed");
    if(record||record_with_environment) {
        if(spec.at("input_manifest_source")!="resolved-problem-canonical-bytes"&&
           spec.at("input_manifest_source")!="csl.exp05-finite-minimax-case/1"&&
           spec.at("input_manifest_source")!="csl.geometry-hull-input/1"&&
           spec.at("input_manifest_source")!="csl.mpc01-canonical-input/1"&&
           spec.at("input_manifest_source")!="csl.mpc03-b08-case/1")
            throw std::invalid_argument("Comparison input manifest source is unsupported");
        constexpr std::string_view prefix="csl.problem.v1.sha256:";
        const auto& problem_id=spec.at("problem_id").get_ref<const std::string&>();
        if(!problem_id.starts_with(prefix)||problem_id.substr(prefix.size())!=
            spec.at("input_manifest_hash").get<std::string>())
            throw std::invalid_argument("Comparison input manifest hash does not match the problem identity");
    }
    const auto& arms=spec.at(legacy?"strategies":"arms");
    if(!arms.is_array()||arms.empty()||arms.size()>std::numeric_limits<std::uint32_t>::max())
        throw std::invalid_argument("Comparison spec arm list is invalid");
    std::vector<std::string> configurations;
    std::vector<std::string> strategies;
    std::vector<std::string> instrumentation;
    for(const auto& arm:arms) {
        const Json* config=nullptr;
        if(legacy) config=&arm;
        else {
            if(!arm.is_object()||arm.size()!=3||!arm.contains("configuration_id")||
                !arm.contains("strategy")||!arm.contains("instrumentation")||
                !arm.at("strategy").is_string()||arm.at("strategy").get<std::string>().empty()||
                !arm.at("instrumentation").is_string()||
                (arm.at("instrumentation")!="enabled"&&arm.at("instrumentation")!="disabled"))
                throw std::invalid_argument("Comparison spec arm fields are invalid");
            config=&arm.at("configuration_id");
            strategies.push_back(arm.at("strategy").get<std::string>());
            instrumentation.push_back(arm.at("instrumentation").get<std::string>());
        }
        if(!valid_config_id(*config))throw std::invalid_argument("Strategy configuration identity is malformed");
        configurations.push_back(config->get<std::string>());
    }
    const auto repetitions=spec.at("repetitions").get<std::uint32_t>();
    if(repetitions==0)throw std::invalid_argument("Repetition count must be positive");
    return {record||record_with_environment,std::move(configurations),std::move(strategies),
        std::move(instrumentation),repetitions,
        record_with_environment?spec.at("environment"):Json{nullptr}};
}
bool arm_matches_run(const Json& run,const SpecShape& spec,std::size_t arm) {
    if(spec.strategies.empty())return true;
    if(run.value("schema",std::string{})=="csl.external-method-run/1")
        return run.at("method").at("id")==spec.strategies.at(arm);
    const auto& config=run.at("configuration").at("value");
    return config.at("strategy").at("strategy")==spec.strategies.at(arm) &&
        config.at("collection").at("enabled").get<bool>()==(spec.instrumentation.at(arm)=="enabled");
}
std::size_t saved_distinct_witness_count(const Json& batch) {
    const auto& witnesses=batch.at("witnesses");
    const auto tolerance=batch.at("distinctness_tolerance").get<double>();
    std::vector<std::size_t> representatives;
    const auto histories_close=[&](const Json& left,const Json& right) {
        if(left.size()!=right.size())return false;
        for(std::size_t time=0;time<left.size();++time) {
            if(left.at(time).size()!=right.at(time).size())return false;
            for(std::size_t coordinate=0;coordinate<left.at(time).size();++coordinate)
                if(!(std::abs(left.at(time).at(coordinate).get<double>()-
                    right.at(time).at(coordinate).get<double>())<=tolerance))return false;
        }
        return true;
    };
    for(std::size_t index=0;index<witnesses.size();++index) {
        bool duplicate=false;
        for(const auto representative:representatives) {
            const auto& candidate=witnesses.at(index);
            const auto& existing=witnesses.at(representative);
            if(histories_close(candidate.at("states"),existing.at("states"))&&
                histories_close(candidate.at("controls"),existing.at("controls"))) {
                duplicate=true;
                break;
            }
        }
        if(!duplicate)representatives.push_back(index);
    }
    return representatives.size();
}
std::string binary64_hex(double value) {
    constexpr char digits[]="0123456789abcdef";
    const auto bits=std::bit_cast<std::uint64_t>(value);
    std::string encoded(16,'0');
    for(std::size_t index=0;index<16;++index)
        encoded[15-index]=digits[(bits>>(index*4))&15];
    return encoded;
}
bool measurement_matches_arm(AttemptStatus status,const Json& measurement,const Json& run,
    const SpecShape& spec,std::size_t arm,std::uint32_t repetition) {
    if(!measurement_status_matches(status,measurement))return false;
    if(spec.strategies.empty())return true;
    const auto schema=measurement.value("schema",std::string{});
    if(schema=="csl.approximation-check-event/1")
        return run.value("schema",std::string{})=="csl.external-method-run/1"&&
            approximation_check_event_matches(measurement,run,spec,arm,repetition);
    if(schema=="csl.mpc01-comparison-event/1") {
        const auto json_string_matches=[](const Json& value,std::string_view expected) {
            return value.is_string()&&std::string_view(value.get_ref<const std::string&>())==expected;
        };
        if(!exact_fields(measurement,{"schema","strategy","instrumentation","repetition","status","attempt"})||
            !json_string_matches(measurement.at("strategy"),spec.strategies.at(arm))||
            !json_string_matches(measurement.at("instrumentation"),spec.instrumentation.at(arm))||
            measurement.at("repetition")!=repetition)return false;
        const auto& native=measurement.at("attempt");
        if(!native.is_object()||native.value("schema",std::string{})!="csl.mpc01-native-attempt/1")return false;
        const auto termination=native.value("termination",std::string{});
        const auto iterations=native.find("solver_iterations");
        if(termination=="completed"&&(iterations==native.end()||!iterations->is_number_unsigned()))return false;
        if(!json_string_matches(measurement.at("status"),termination=="completed"?"passed":termination))return false;
        const auto method=native.value("method",std::string{});
        const auto backend=method=="osqp-sparse-qp"?"csl.external.osqp.sparse-qp":
            method=="hpipm-structured-ocp-qp"?"csl.external.hpipm.structured-ocp-qp":"";
        const auto expected_problem="csl.problem.v1.sha256:"+native.value("input_sha256",std::string{});
        if(std::string(backend).empty()||spec.environment.is_null()||
            spec.strategies.at(arm)!=backend||
            !json_string_matches(run.at("problem"),expected_problem))return false;
        const auto& backends=spec.environment.at("build").at("backends");
        const auto backend_key=method=="osqp-sparse-qp"?"osqp":"hpipm";
        const auto& pinned=backends.at(backend_key);
        bool matched_start_mode=false;
        for(const auto& module:run.at("configuration").at("value").at("modules")) {
            if(!json_string_matches(module.at("role"),"strategy")||
                !json_string_matches(module.at("id"),backend))continue;
            if(module.at("version")!=pinned.at("version")||
                !json_string_matches(module.at("pin").at("state"),"available")||
                !json_string_matches(module.at("pin").at("value").at("scope"),"source_archive")||
                module.at("pin").at("value").at("sha256")!=pinned.at("archive_sha256"))return false;
            const auto option_matches=[&](std::string_view name,const Json& expected) {
                for(const auto& option:module.at("options"))
                    if(json_string_matches(option.at("name"),name)&&option.at("value")==expected)return true;
                return false;
            };
            const auto string_option=[](std::string value) {
                return Json{{"type","string"},{"value",std::move(value)}};
            };
            const auto bool_option=[](bool value) {return Json{{"type","boolean"},{"value",value}};};
            const auto integer_option=[](std::int64_t value) {
                return Json{{"type","signed64"},{"value",std::to_string(value)}};
            };
            const auto number_option=[](double value) {
                return Json{{"type","binary64_bits"},{"value",binary64_hex(value)}};
            };
            for(const auto& option:module.at("options"))
                if(json_string_matches(option.at("name"),"start_mode")&&
                    json_string_matches(option.at("value").at("type"),"string")&&
                    json_string_matches(option.at("value").at("value"),native.value("start_mode",std::string{})))
                    matched_start_mode=true;
            const bool osqp=method=="osqp-sparse-qp";
            if(!option_matches("native_defaults",string_option(osqp?"osqp_set_default_settings":"d_ocp_qp_ipm_arg_set_default_BALANCE"))||
                !option_matches("iteration_limit",integer_option(osqp?200000:1000))||
                !option_matches("warm_start_enabled",bool_option(osqp||native.value("start_mode",std::string{})=="warm_if_available")))return false;
            if(osqp) {
                if(!option_matches("eps_abs",number_option(1e-7))||
                    !option_matches("eps_rel",number_option(1e-7)))return false;
            } else if(!option_matches("mode",string_option("BALANCE"))||
                !option_matches("tol_stat",number_option(1e-8))||
                !option_matches("tol_eq",number_option(1e-8))||
                !option_matches("tol_ineq",number_option(1e-8))||
                !option_matches("tol_comp",number_option(1e-8)))return false;
        }
        if(!matched_start_mode)return false;
        const auto settings=native.find("solver_settings");
        if(settings==native.end()||!settings->is_object())return false;
        if(method=="osqp-sparse-qp") {
            if(settings->value("max_iter",std::int64_t{})!=200000||
                settings->value("eps_abs",-1.0)!=1e-7||settings->value("eps_rel",-1.0)!=1e-7||
                settings->value("warm_starting",false)!=true||
                native.value("warm_start_requested",false)!=(native.value("start_mode",std::string{})=="warm_if_available")||
                (native.value("warm_start_seed_applied",false)&&!native.value("warm_start_requested",false)))return false;
        } else if(settings->value("max_iter",std::int64_t{})!=1000||
            settings->value("mode",std::string{})!="BALANCE"||
            settings->value("tol_stat",-1.0)!=1e-8||settings->value("tol_eq",-1.0)!=1e-8||
            settings->value("tol_ineq",-1.0)!=1e-8||settings->value("tol_comp",-1.0)!=1e-8||
            settings->value("warm_start",false)!=(native.value("start_mode",std::string{})=="warm_if_available")||
            native.value("warm_start_requested",false)!=(native.value("start_mode",std::string{})=="warm_if_available")||
            (native.value("warm_start_seed_applied",false)&&!native.value("warm_start_requested",false)))return false;
        const auto payload=native.dump();
        constexpr char digits[]="0123456789abcdef";
        std::string encoded;encoded.reserve(payload.size()*2);
        for(const unsigned char byte:payload) {
            encoded.push_back(digits[byte>>4]);encoded.push_back(digits[byte&15]);
        }
        std::size_t matches=0;
        for(const auto& attachment:run.at("attachments"))
            if(attachment.at("id")=="native-attempt"&&attachment.at("role")=="diagnostics"&&
                attachment.at("schema")=="csl.mpc01-native-attempt/1"&&attachment.at("content")==encoded)++matches;
        return matches==1;
    }
    if(schema=="csl.external-method-event/1")
        return run.value("schema",std::string{})=="csl.external-method-run/1"&&
            measurement.contains("method_id")&&measurement.at("method_id")==spec.strategies.at(arm)&&
            measurement.contains("instrumentation")&&measurement.at("instrumentation")==spec.instrumentation.at(arm)&&
            measurement.contains("repetition")&&measurement.at("repetition").get<std::uint32_t>()==repetition&&
            measurement.contains("warmup")&&measurement.at("warmup").get<bool>()==(repetition==0);
    if(schema=="csl.exp05-fixed-plan-event/1")
        return measurement.contains("strategy")&&measurement.at("strategy")==spec.strategies.at(arm)&&
            measurement.contains("instrumentation")&&measurement.at("instrumentation")==spec.instrumentation.at(arm)&&
            measurement.contains("repetition")&&measurement.at("repetition").get<std::uint32_t>()==repetition;
    if(schema=="csl.mpc03-b08-comparison-event/1")
        return measurement.contains("strategy")&&measurement.at("strategy")==spec.strategies.at(arm)&&
            measurement.contains("instrumentation")&&measurement.at("instrumentation")==spec.instrumentation.at(arm)&&
            measurement.contains("repetition")&&measurement.at("repetition").get<std::uint32_t>()==repetition;
    if(schema!="csl.obs04-instrumentation-comparison-event/2" &&
        schema!="csl.obs04-instrumentation-comparison-event/3" &&
        schema!="csl.obs04-instrumentation-comparison-event/4" &&
        schema!="csl.obs04-instrumentation-comparison-event/5" &&
        schema!="csl.obs04-instrumentation-comparison-event/6" &&
        schema!="csl.obs04-instrumentation-comparison-event/7" &&
        schema!="csl.obs04-instrumentation-comparison-event/8" &&
        schema!="csl.obs04-instrumentation-comparison-event/9")return false;
    if(measurement.at("strategy")!=spec.strategies.at(arm) ||
        measurement.at("instrumentation")!=spec.instrumentation.at(arm) ||
        measurement.at("repetition").get<std::uint32_t>()!=repetition ||
        measurement.at("warmup").get<bool>()!=(repetition==0))return false;
    if(schema=="csl.obs04-instrumentation-comparison-event/2")return true;
    const auto nonnegative_integer=[](const Json& value) {
        if(value.is_number_unsigned())return true;
        return value.is_number_integer()&&value.get<std::int64_t>()>=0;
    };
    const auto canonical_count=[](const Json& value) {
        if(!value.is_string())return std::optional<std::uint64_t>{};
        const auto& text=value.get_ref<const std::string&>();
        std::uint64_t count{};
        const auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),count);
        if(error!=std::errc{}||end!=text.data()+text.size())return std::optional<std::uint64_t>{};
        return std::optional<std::uint64_t>{count};
    };
    for(const auto* field:{"selection_setup_ns","selection_run_ns","verification_ns"})
        if(!measurement.contains(field)||(!measurement.at(field).is_null()&&
            !nonnegative_integer(measurement.at(field))))return false;
    if(schema=="csl.obs04-instrumentation-comparison-event/4") {
        for(const auto* field:{"family_construction_ns","end_to_end_ns",
                "first_witness_query_ns","additional_witness_query_ns"})
            if(!measurement.contains(field)||(!measurement.at(field).is_null()&&
                !nonnegative_integer(measurement.at(field))))return false;
        if(status==AttemptStatus::completed &&
            (measurement.at("family_construction_ns").is_null()||measurement.at("end_to_end_ns").is_null()||
             !measurement.contains("strategy_run_ns")||measurement.at("strategy_run_ns").is_null()||
             measurement.at("family_construction_ns")!=measurement.at("strategy_run_ns")))return false;
    }
    if((schema=="csl.obs04-instrumentation-comparison-event/7"||
        schema=="csl.obs04-instrumentation-comparison-event/8"||
        schema=="csl.obs04-instrumentation-comparison-event/9")&&
        (!measurement.contains("family_construction_ns")||
         (!measurement.at("family_construction_ns").is_null()&&
          !nonnegative_integer(measurement.at("family_construction_ns")))))return false;
    if((schema=="csl.obs04-instrumentation-comparison-event/7"||
        schema=="csl.obs04-instrumentation-comparison-event/8"||
        schema=="csl.obs04-instrumentation-comparison-event/9")&&
        ((measurement.at("instrumentation")=="disabled"&&
          !measurement.at("family_construction_ns").is_null())||
         (status==AttemptStatus::completed&&measurement.at("instrumentation")=="enabled"&&
          measurement.at("family_construction_ns").is_null())))return false;
    if((schema=="csl.obs04-instrumentation-comparison-event/6"||
        schema=="csl.obs04-instrumentation-comparison-event/7"||
        schema=="csl.obs04-instrumentation-comparison-event/8"||
        schema=="csl.obs04-instrumentation-comparison-event/9") &&
        (!measurement.contains("phase_status")||!measurement.at("phase_status").is_string()||
         (measurement.at("phase_status")!="passed"&&measurement.at("phase_status")!="failed")))return false;
    if(schema=="csl.obs04-instrumentation-comparison-event/5"||
        schema=="csl.obs04-instrumentation-comparison-event/6"||
        schema=="csl.obs04-instrumentation-comparison-event/7"||
        schema=="csl.obs04-instrumentation-comparison-event/8"||
        schema=="csl.obs04-instrumentation-comparison-event/9") {
        for(const auto* field:{"setup_ns","strategy_run_ns"})
            if(!measurement.contains(field)||(!measurement.at(field).is_null()&&
                !nonnegative_integer(measurement.at(field))))return false;
        if(schema!="csl.obs04-instrumentation-comparison-event/7"&&
            schema!="csl.obs04-instrumentation-comparison-event/8"&&
            schema!="csl.obs04-instrumentation-comparison-event/9"&&
            !measurement.at("family_construction_ns").is_null())return false;
        if((schema=="csl.obs04-instrumentation-comparison-event/7"||
            schema=="csl.obs04-instrumentation-comparison-event/8"||
            schema=="csl.obs04-instrumentation-comparison-event/9")&&
            !measurement.at("family_construction_ns").is_null()&&
            !nonnegative_integer(measurement.at("family_construction_ns")))return false;
        if(status==AttemptStatus::completed &&
            (measurement.at("setup_ns").is_null()||measurement.at("strategy_run_ns").is_null()||
             measurement.at("end_to_end_ns").is_null()))return false;
        const auto add_duration=[](std::uint64_t& total,const Json& value) {
            if(value.is_null())return true;
            const auto duration=value.get<std::uint64_t>();
            if(duration>std::numeric_limits<std::uint64_t>::max()-total)return false;
            total+=duration;
            return true;
        };
        std::uint64_t query_total=0;
        if(!add_duration(query_total,measurement.at("first_witness_query_ns"))||
            !add_duration(query_total,measurement.at("additional_witness_query_ns")))return false;
        const bool any_query=!measurement.at("first_witness_query_ns").is_null()||
            !measurement.at("additional_witness_query_ns").is_null();
        if(any_query && (measurement.at("selection_run_ns").is_null()||
            measurement.at("selection_run_ns").get<std::uint64_t>()<query_total))return false;
        if(!measurement.at("end_to_end_ns").is_null()) {
            std::uint64_t phase_total=0;
            for(const auto* field:{"setup_ns","strategy_run_ns","selection_setup_ns",
                    "selection_run_ns","verification_ns"})
                if(!add_duration(phase_total,measurement.at(field)))return false;
            if(measurement.at("end_to_end_ns").get<std::uint64_t>()<phase_total)return false;
        }
    }
    if(schema=="csl.obs04-instrumentation-comparison-event/8"||
        schema=="csl.obs04-instrumentation-comparison-event/9") {
        for(const auto* field:{"strategy_run_cpu_ns","observed_backend_scheduler_width"})
            if(!measurement.contains(field)||(!measurement.at(field).is_null()&&
                !nonnegative_integer(measurement.at(field))))return false;
        const auto& width=measurement.at("observed_backend_scheduler_width");
        if(!width.is_null()&&width.get<std::uint64_t>()==0)return false;
    }
    if(schema=="csl.obs04-instrumentation-comparison-event/9") {
        if(!measurement.contains("strategy_run_peak_rss")||
            !measurement.at("strategy_run_peak_rss").is_object())return false;
        const auto& rss=measurement.at("strategy_run_peak_rss");
        for(const auto* field:{"status","metric","scope","value_bytes","reason"})
            if(!rss.contains(field))return false;
        if(!rss.at("status").is_string()||
            (rss.at("status")!="available"&&rss.at("status")!="unavailable"&&
             rss.at("status")!="not_measured")||
            rss.at("metric")!="process_peak_rss_bytes"||
            rss.at("scope")!="process_vm_hwm_reset_before_and_read_after_strategy_run")return false;
        const auto& value=rss.at("value_bytes");
        const auto& reason=rss.at("reason");
        if(!value.is_null()&&!nonnegative_integer(value))return false;
        if(!reason.is_null()&&!reason.is_string())return false;
        if(rss.at("status")=="available") {
            if(value.is_null()||!reason.is_null())return false;
        } else if(!value.is_null()||!reason.is_string()||reason.get_ref<const std::string&>().empty())return false;
    }
    for(const auto* field:{"requested_witness_count","returned_witness_count","distinct_witness_count"})
        if(!measurement.contains(field)||(!measurement.at(field).is_null()&&
            !nonnegative_integer(measurement.at(field))))return false;
    const auto& configuration=run.at("configuration").at("value");
    const auto configured_count=canonical_count(configuration.at("output").at("witness_count"));
    if(!configured_count||measurement.at("requested_witness_count").get<std::uint64_t>()!=*configured_count)return false;
    const auto& selection=run.at("selection");
    if(selection.is_null()) {
        if(schema=="csl.obs04-instrumentation-comparison-event/4" &&
            (!measurement.at("first_witness_query_ns").is_null() ||
             !measurement.at("additional_witness_query_ns").is_null()))return false;
        return measurement.at("returned_witness_count").is_null()&&
            measurement.at("distinct_witness_count").is_null();
    }
    for(const auto* field:{"selection_setup_ns","selection_run_ns","verification_ns"})
        if(measurement.at(field).is_null())return false;
    if((schema=="csl.obs04-instrumentation-comparison-event/4"||
        schema=="csl.obs04-instrumentation-comparison-event/5"||
        schema=="csl.obs04-instrumentation-comparison-event/6"||
        schema=="csl.obs04-instrumentation-comparison-event/7"||
        schema=="csl.obs04-instrumentation-comparison-event/8"||
        schema=="csl.obs04-instrumentation-comparison-event/9") &&
        (measurement.at("first_witness_query_ns").is_null() ||
         measurement.at("additional_witness_query_ns").is_null()))return false;
    const auto& batch=selection.at("batch");
    const auto returned=batch.at("witnesses").size();
    const auto batch_requested=canonical_count(batch.at("requested"));
    const auto distinct=saved_distinct_witness_count(batch);
    return batch_requested&&measurement.at("requested_witness_count").get<std::uint64_t>()==
            *batch_requested &&
        measurement.at("returned_witness_count").get<std::uint64_t>()==returned &&
        measurement.at("distinct_witness_count").get<std::uint64_t>()==distinct && distinct<=returned;
}
ArtifactResult<problem::ResolvedContent> own(std::string_view text) {
    std::vector<std::byte> bytes; bytes.reserve(text.size());
    for (unsigned char c : text) bytes.push_back(static_cast<std::byte>(c));
    auto result = problem::snapshot_content(bytes);
    if (auto* content = std::get_if<problem::ResolvedContent>(&result)) return *content;
    return error(ArtifactErrorCode::allocation, "comparison.content", "Could not own comparison bytes");
}
}

ArtifactResult<RecordedExternalMethodRunArtifact> encode_external_method_run(
    const ExternalMethodRunInput& input, EncodeLimits limits) {
    try {
        if(input.run.value.empty()||input.problem.value.empty()||input.configuration.value.empty()||
            input.method_id.empty()||input.method_version.empty()||input.input_manifest_schema.empty()||
            input.input_manifest.empty()||input.sources.empty()||status_name(input.status).empty())
            return error(ArtifactErrorCode::invalid_input,"external_run","Required method-run identity is empty");
        auto manifest=problem::snapshot_content(std::span<const std::byte>(input.input_manifest));
        if(const auto* failure=std::get_if<Diagnostic>(&manifest))
            return error(ArtifactErrorCode::invalid_input,"external_run.input_manifest",failure->explanation);
        const auto manifest_digest=std::get<problem::ResolvedContent>(manifest).digest();
        const auto expected_problem="csl.problem.v1.sha256:"+problem::hex(manifest_digest);
        if(input.problem.value!=expected_problem)
            return error(ArtifactErrorCode::identity,"external_run.problem","Problem identity must hash the attached input manifest");
        const auto config_prefix=std::string_view{"csl.config.v1.sha256:"};
        if(!input.configuration.value.starts_with(config_prefix)||input.configuration.value.size()!=config_prefix.size()+64||
            !std::all_of(input.configuration.value.begin()+static_cast<std::ptrdiff_t>(config_prefix.size()),
                input.configuration.value.end(),[](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))
            return error(ArtifactErrorCode::invalid_input,"external_run.configuration","Configuration identity is malformed");
        if(input.sources.size()>64||input.input_manifest.size()>limits.bytes||input.result_payload.size()>limits.bytes)
            return error(ArtifactErrorCode::limit,"external_run","Method-run payload exceeds capacity");
        const auto result_json=parse_bounded(input.result_payload,{limits.bytes,1000000,64,std::min<std::uint64_t>(limits.bytes,1024*1024)});
        if(!result_json.is_object()||result_json.dump()!=input.result_payload)
            return error(ArtifactErrorCode::invalid_input,"external_run.result_payload","Result payload must be a canonical JSON object");
        const auto digest_text=[](const problem::ContentDigest& digest){return problem::hex(digest);};
        auto valid_hash=[](std::string_view value){return value.size()==64&&std::all_of(value.begin(),value.end(),
            [](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});};
        Json sources=Json::array();
        std::set<std::string> source_paths;
        for(const auto& source:input.sources) {
            if(source.path.empty()||!valid_hash(source.sha256)||!source_paths.insert(source.path).second)
                return error(ArtifactErrorCode::invalid_input,"external_run.method.sources","Source paths must be unique and source hashes valid");
            sources.push_back({{"path",source.path},{"sha256",source.sha256}});
        }
        if(input.deviations_sha256&&!valid_hash(*input.deviations_sha256))
            return error(ArtifactErrorCode::invalid_input,"external_run.method.deviations_sha256","Deviation hash is malformed");
        const auto& runtime=input.runtime;
        if(runtime.language.empty()||runtime.implementation.empty()||runtime.version.empty()||runtime.os.empty()||
            runtime.architecture.empty()||runtime.compiler.empty()||runtime.compiler_version.empty()||runtime.build_type.empty()||
            !valid_hash(runtime.executable_sha256))
            return error(ArtifactErrorCode::invalid_input,"external_run.method.runtime","Runtime identity is incomplete or malformed");
        std::string manifest_hex;
        manifest_hex.reserve(input.input_manifest.size()*2);
        constexpr char digits[]="0123456789abcdef";
        for(const auto byte:input.input_manifest) {
            const auto value=std::to_integer<unsigned char>(byte);
            manifest_hex.push_back(digits[value>>4]);
            manifest_hex.push_back(digits[value&15]);
        }
        Json runtime_json{{"language",runtime.language},{"implementation",runtime.implementation},
            {"version",runtime.version},{"executable_sha256",runtime.executable_sha256},
            {"os",runtime.os},{"architecture",runtime.architecture},{"compiler",runtime.compiler},
            {"compiler_version",runtime.compiler_version},{"build_type",runtime.build_type}};
        Json method_json{{"id",input.method_id},{"version",input.method_version},{"sources",sources},
            {"deviations_sha256",input.deviations_sha256?Json(*input.deviations_sha256):Json(nullptr)},
            {"runtime",std::move(runtime_json)}};
        Json manifest_json{{"schema",input.input_manifest_schema},
            {"sha256",problem::hex(manifest_digest)},{"content_hex",manifest_hex}};
        Json wire{{"schema","csl.external-method-run/1"},
            {"problem",input.problem.value},
            {"configuration",{{"id",input.configuration.value}}},
            {"request_digest",digest_text(input.request_digest)},
            {"run",input.run.value},
            {"status",status_name(input.status)},
            {"method",std::move(method_json)},
            {"input_manifest",std::move(manifest_json)},
            {"result",result_json},
            {"recorded_state","unverified_recorded_data"}};
        const auto text=wire.dump();
        if(text.size()>limits.bytes)return error(ArtifactErrorCode::limit,"external_run.bytes","Encoded method run exceeds byte limit");
        auto content=own(text);
        if(const auto* failure=std::get_if<ArtifactError>(&content))return *failure;
        return decode_external_method_run(text,{limits.bytes,1000000,64,std::min<std::uint64_t>(limits.bytes,1024*1024)});
    } catch(const ArtifactError& failure){return failure;}
      catch(const std::bad_alloc&){return error(ArtifactErrorCode::allocation,"external_run","Allocation failed");}
      catch(const std::exception& failure){return error(ArtifactErrorCode::invalid_input,"external_run",failure.what());}
}

ArtifactResult<RecordedExternalMethodRunArtifact> decode_external_method_run(
    std::string_view text, DecodeLimits limits) {
    try {
        const auto wire=parse_bounded(text,limits);
        if(!exact_fields(wire,{"schema","problem","configuration","request_digest","run","status",
            "method","input_manifest","result","recorded_state"})||wire.at("schema")!="csl.external-method-run/1"||
            wire.dump()!=text||wire.at("recorded_state")!="unverified_recorded_data")
            return error(ArtifactErrorCode::invalid_input,"external_run","Method-run schema, identity or canonical bytes are invalid");
        const auto& problem_id=wire.at("problem");
        const auto& configuration=wire.at("configuration");
        const auto& request_digest=wire.at("request_digest");
        const auto& run=wire.at("run");
        if(!problem_id.is_string()||!configuration.is_object()||!exact_fields(configuration,{"id"})||
            !configuration.at("id").is_string()||!request_digest.is_string()||!run.is_string()||run.get_ref<const std::string&>().empty())
            return error(ArtifactErrorCode::invalid_input,"external_run.identity","Method-run identity fields are invalid");
        auto hash_text=[](const Json& value){
            if(!value.is_string())return false;
            const auto& text=value.get_ref<const std::string&>();
            return text.size()==64&&std::all_of(text.begin(),text.end(),[](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
        };
        if(!hash_text(request_digest))return error(ArtifactErrorCode::invalid_input,"external_run.request_digest","Request digest is malformed");
        const auto& config_id=configuration.at("id").get_ref<const std::string&>();
        constexpr std::string_view config_prefix="csl.config.v1.sha256:";
        if(!config_id.starts_with(config_prefix)||config_id.size()!=config_prefix.size()+64||
            !std::all_of(config_id.begin()+static_cast<std::ptrdiff_t>(config_prefix.size()),config_id.end(),
                [](unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))
            return error(ArtifactErrorCode::invalid_input,"external_run.configuration.id","Configuration identity is malformed");
        const auto parsed_status=parse_status(wire.at("status").get<std::string>());
        const auto& method=wire.at("method");
        if(!exact_fields(method,{"id","version","sources","deviations_sha256","runtime"})||
            !method.at("id").is_string()||method.at("id").get_ref<const std::string&>().empty()||
            !method.at("version").is_string()||method.at("version").get_ref<const std::string&>().empty()||
            !method.at("sources").is_array()||method.at("sources").empty()||method.at("sources").size()>64)
            return error(ArtifactErrorCode::invalid_input,"external_run.method","Method identity is malformed");
        if(!method.at("deviations_sha256").is_null()&&!hash_text(method.at("deviations_sha256")))
            return error(ArtifactErrorCode::invalid_input,"external_run.method.deviations_sha256","Deviation hash is malformed");
        std::set<std::string> source_paths;
        for(const auto& source:method.at("sources"))
            if(!exact_fields(source,{"path","sha256"})||!source.at("path").is_string()||
                source.at("path").get_ref<const std::string&>().empty()||!source_paths.insert(source.at("path").get<std::string>()).second||
                !hash_text(source.at("sha256")))
                return error(ArtifactErrorCode::invalid_input,"external_run.method.sources","Source identity is malformed or duplicated");
        const auto& runtime=method.at("runtime");
        if(!exact_fields(runtime,{"language","implementation","version","executable_sha256","os","architecture","compiler","compiler_version","build_type"}))
            return error(ArtifactErrorCode::invalid_input,"external_run.method.runtime","Runtime fields are invalid");
        for(const auto* field:{"language","implementation","version","os","architecture","compiler","compiler_version","build_type"})
            if(!runtime.at(field).is_string()||runtime.at(field).get_ref<const std::string&>().empty())
                return error(ArtifactErrorCode::invalid_input,"external_run.method.runtime","Runtime identity fields must be nonempty strings");
        if(!hash_text(runtime.at("executable_sha256")))
            return error(ArtifactErrorCode::invalid_input,"external_run.method.runtime.executable_sha256","Executable hash is malformed");
        const auto& manifest=wire.at("input_manifest");
        if(!exact_fields(manifest,{"schema","sha256","content_hex"})||!manifest.at("schema").is_string()||
            manifest.at("schema").get_ref<const std::string&>().empty()||!hash_text(manifest.at("sha256"))||
            !manifest.at("content_hex").is_string())
            return error(ArtifactErrorCode::invalid_input,"external_run.input_manifest","Input manifest fields are invalid");
        const auto& encoded=manifest.at("content_hex").get_ref<const std::string&>();
        if(encoded.empty()||encoded.size()%2!=0||encoded.size()/2>limits.bytes)
            return error(ArtifactErrorCode::limit,"external_run.input_manifest.content_hex","Input manifest content is empty or over capacity");
        std::vector<std::byte> bytes;
        bytes.reserve(encoded.size()/2);
        const auto nibble=[](char c)->int {if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;return -1;};
        for(std::size_t i=0;i<encoded.size();i+=2) {
            const int high=nibble(encoded[i]),low=nibble(encoded[i+1]);
            if(high<0||low<0)return error(ArtifactErrorCode::invalid_input,"external_run.input_manifest.content_hex","Input manifest content is not lowercase hexadecimal");
            bytes.push_back(static_cast<std::byte>((high<<4)|low));
        }
        auto manifest_content=problem::snapshot_content(std::span<const std::byte>(bytes));
        if(const auto* failure=std::get_if<Diagnostic>(&manifest_content))
            return error(ArtifactErrorCode::invalid_input,"external_run.input_manifest",failure->explanation);
        const auto manifest_digest=std::get<problem::ResolvedContent>(manifest_content).digest();
        if(problem::hex(manifest_digest)!=manifest.at("sha256").get<std::string>()||
            problem_id.get<std::string>()!="csl.problem.v1.sha256:"+problem::hex(manifest_digest))
            return error(ArtifactErrorCode::identity,"external_run.input_manifest","Problem or input digest does not match manifest bytes");
        if(!wire.at("result").is_object())return error(ArtifactErrorCode::invalid_input,"external_run.result","Result must be an object");
        auto content=own(text);
        if(const auto* failure=std::get_if<ArtifactError>(&content))return *failure;
        auto& owned=std::get<problem::ResolvedContent>(content);
        return RecordedExternalMethodRunArtifact(owned,{run.get<std::string>()},{problem_id.get<std::string>()},
            {config_id},parsed_status);
    } catch(const ArtifactError& failure){return failure;}
      catch(const std::bad_alloc&){return error(ArtifactErrorCode::allocation,"external_run","Allocation failed");}
      catch(const std::exception& failure){return error(ArtifactErrorCode::invalid_input,"external_run",failure.what());}
}

ArtifactResult<RecordedComparisonArtifact> encode_recorded_comparison(
    const problem::ResolvedContent& spec, const std::vector<ComparisonAttempt>& attempts, EncodeLimits limits) {
    try {
        const DecodeLimits validation_limits{limits.bytes, 1000000, 64, std::min<std::uint64_t>(limits.bytes, 1024*1024)};
        if (attempts.empty()) return error(ArtifactErrorCode::invalid_input, "attempts", "At least one attempt is required");
        if (attempts.size() > limits.bytes / 32) return error(ArtifactErrorCode::limit, "attempts", "Attempt count exceeds byte budget");
        if (spec.bytes().size() > limits.bytes) return error(ArtifactErrorCode::limit, "spec", "Spec exceeds byte budget");
        const auto spec_text = bytes_to_string(spec.bytes());
        std::uint64_t payload_bytes=spec.bytes().size();
        auto spec_json = parse_bounded(spec_text, validation_limits);
        if (spec_json.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "spec", "Spec must be canonical JSON");
        const auto spec_shape=validate_spec(spec_json);
        const auto strategy_count=static_cast<std::uint32_t>(spec_shape.configurations.size());
        const auto repetition_count=spec_shape.repetitions;
        if (attempts.size()!=static_cast<std::uint64_t>(strategy_count)*repetition_count)
            return error(ArtifactErrorCode::invalid_input,"attempts","Attempt set is incomplete for the declared strategy and repetition counts");
        Json records = Json::array();
        std::optional<std::pair<std::uint32_t, std::uint32_t>> previous;
        for (std::size_t i = 0; i < attempts.size(); ++i) {
            const auto& attempt = attempts[i];
            if (status_name(attempt.reported_status).empty())
                return error(ArtifactErrorCode::invalid_input, "attempts[" + std::to_string(i) + "].reported_status", "Unknown attempt status");
            const auto key = std::pair{attempt.strategy_index, attempt.repetition_index};
            if(attempt.strategy_index>=strategy_count||attempt.repetition_index>=repetition_count||
                key!=std::pair{static_cast<std::uint32_t>(i/repetition_count),static_cast<std::uint32_t>(i%repetition_count)})
                return error(ArtifactErrorCode::invalid_input,"attempts["+std::to_string(i)+"]","Attempt indices do not cover the complete ordered spec");
            if (previous && key <= *previous)
                return error(ArtifactErrorCode::invalid_input, "attempts[" + std::to_string(i) + "]", "Attempts must be uniquely ordered by strategy and repetition");
            previous = key;
            const auto run_bytes=std::visit([](const auto& run){return run.content().bytes();},attempt.run.value());
            if(run_bytes.size()>limits.bytes-payload_bytes)
                return error(ArtifactErrorCode::limit, "attempts", "Attempt payloads exceed byte budget");
            payload_bytes+=run_bytes.size();
            const auto run_text = bytes_to_string(run_bytes);
            const bool external=std::holds_alternative<RecordedExternalMethodRunArtifact>(attempt.run.value());
            if(external) {
                const auto validated=decode_external_method_run(run_text,validation_limits);
                if(std::holds_alternative<ArtifactError>(validated))
                    return error(ArtifactErrorCode::reference, "attempts[" + std::to_string(i) + "].run", "Attempt does not contain a valid external method run");
            } else {
                const auto validated=decode_recorded_run(run_text,validation_limits);
                if(std::holds_alternative<ArtifactError>(validated))
                    return error(ArtifactErrorCode::reference, "attempts[" + std::to_string(i) + "].run", "Attempt does not contain a valid recorded run");
            }
            /*
             * Both run families share the same outer reference fields. The
             * external form adds source/runtime identity and an input-manifest
             * payload without claiming to be a controlled-system execution.
             */
            const auto run_json = parse_bounded(run_text, validation_limits);
            const auto run_content_digest=std::visit([](const auto& run){return run.content().digest();},attempt.run.value());
            const auto run_request_digest=external?run_json.at("request_digest").get<std::string>():
                problem::hex(request_digest(run_json));
            if (run_json.at("run").get<std::string>() != attempt.reference.run.value ||
                run_content_digest != attempt.reference.content_digest ||
                run_json.at("problem").get<std::string>()!=spec_json.at("problem_id").get<std::string>() ||
                run_json.at("configuration").at("id").get<std::string>()!=
                    spec_shape.configurations.at(attempt.strategy_index) ||
                run_request_digest!=spec_json.at("request_digest").get<std::string>() ||
                !input_manifest_attached(run_json,spec_json) ||
                !arm_matches_run(run_json,spec_shape,attempt.strategy_index) ||
                !status_matches(attempt.reported_status,run_json))
                return error(ArtifactErrorCode::identity, "attempts[" + std::to_string(i) + "].reference", "Run reference identity or content digest mismatch");
            if(spec_shape.record_v1) {
                if(attempt.measurement_payload.empty())
                    return error(ArtifactErrorCode::invalid_input,"attempts["+std::to_string(i)+"].measurement_payload","A measurement payload is required by comparison-record/1");
                if(attempt.measurement_payload.size()>limits.bytes-payload_bytes)
                    return error(ArtifactErrorCode::limit,"attempts","Measurement payloads exceed byte budget");
                payload_bytes+=attempt.measurement_payload.size();
                const auto measurement=parse_bounded(attempt.measurement_payload,validation_limits);
                if(!measurement_matches_arm(attempt.reported_status,measurement,run_json,spec_shape,
                    attempt.strategy_index,attempt.repetition_index))
                    return error(ArtifactErrorCode::identity,"attempts["+std::to_string(i)+"].measurement_payload.status","Measurement status disagrees with the run record");
                records.push_back({{"arm_index", attempt.strategy_index}, {"repetition_index", attempt.repetition_index},
                    {"reported_status", status_name(attempt.reported_status)}, {"run_id", attempt.reference.run.value},
                    {"run_digest", problem::hex(attempt.reference.content_digest)}, {"run", run_text},
                    {"measurement_payload",attempt.measurement_payload}});
            } else {
                if(!attempt.measurement_payload.empty())
                    return error(ArtifactErrorCode::invalid_input,"attempts["+std::to_string(i)+"].measurement_payload","Legacy comparison artifacts cannot carry measurement payloads");
                records.push_back({{"strategy_index", attempt.strategy_index}, {"repetition_index", attempt.repetition_index},
                    {"reported_status", status_name(attempt.reported_status)}, {"run_id", attempt.reference.run.value},
                    {"run_digest", problem::hex(attempt.reference.content_digest)}, {"run", run_text}});
            }
        }
        problem::ContentDigest run_digest{};
        Json wire;
        if(spec_shape.record_v1) {
            const auto spec_id=problem::hex(spec.digest());
            const Json identity_material{{"attempts",records},{"comparison_spec_id",spec_id},
                {"schema","csl.comparison-record/1"}};
            const auto material=own(identity_material.dump());
            if(const auto* failure=std::get_if<ArtifactError>(&material))return *failure;
            run_digest=std::get<problem::ResolvedContent>(material).digest();
            wire={{"schema","csl.comparison-record/1"},{"comparison_spec_id",spec_id},
                {"comparison_run_id",problem::hex(run_digest)},{"spec",spec_text},{"attempts",records}};
            wire["track"]="new-comparison";
        } else {
            wire={{"schema","csl.comparison/1"},{"spec",spec_text},
                {"spec_digest",problem::hex(spec.digest())},{"attempts",records}};
        }
        const auto text = wire.dump();
        if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.bytes", "Encoded comparison exceeds byte limit");
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) {
            if(!spec_shape.record_v1)run_digest=owned->digest();
            return RecordedComparisonArtifact(*owned,{spec.digest()},{run_digest});
        }
        return std::get<ArtifactError>(std::move(content));
    } catch (const ArtifactError& failure) { return failure; }
      catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "comparison", "Allocation failed"); }
      catch (const std::exception& failure) { return error(ArtifactErrorCode::invalid_input, "comparison", std::string("Invalid spec or attempt data: ") + failure.what()); }
}

ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(std::string_view text, DecodeLimits limits) {
    if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.bytes", "Comparison exceeds byte limit");
    try {
        auto outer_limits=limits; outer_limits.string_bytes=limits.bytes;
        auto wire = parse_bounded(text,outer_limits);
        if (wire.dump() != text) return error(ArtifactErrorCode::invalid_input, "comparison.canonical", "Comparison is not canonical JSON");
        if (!wire.is_object() || !wire.contains("schema") || !wire.contains("spec") ||
            !wire.contains("attempts"))
            return error(ArtifactErrorCode::invalid_input, "comparison.fields", "Comparison fields do not match schema");
        const auto outer_schema=wire.at("schema").get<std::string>();
        const bool record_v1=outer_schema=="csl.comparison-record/1";
        if (!record_v1&&outer_schema!="csl.comparison/1") return error(ArtifactErrorCode::unsupported, "comparison.schema", "Unknown comparison schema");
        if((record_v1&&(wire.size()!=6||!wire.contains("comparison_spec_id")||!wire.contains("comparison_run_id")||
                !wire.contains("track")||wire.at("track")!="new-comparison"))||
            (!record_v1&&(wire.size()!=4||!wire.contains("spec_digest"))))
            return error(ArtifactErrorCode::invalid_input,"comparison.fields","Comparison identity fields do not match schema");
        const auto spec_text = wire.at("spec").get<std::string>();
        if (spec_text.size() > limits.string_bytes) return error(ArtifactErrorCode::limit, "comparison.spec", "Spec exceeds string capacity");
        auto spec = parse_bounded(spec_text,limits);
        if (spec.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "comparison.spec", "Spec is not canonical JSON");
        const auto spec_shape=validate_spec(spec);
        if(record_v1!=spec_shape.record_v1)return error(ArtifactErrorCode::identity,"comparison.schema","Comparison and spec schemas disagree");
        const auto strategy_count=static_cast<std::uint32_t>(spec_shape.configurations.size());
        const auto repetition_count=spec_shape.repetitions;
        auto owned_spec = own(spec_text);
        const auto spec_digest_field=record_v1?"comparison_spec_id":"spec_digest";
        if (std::holds_alternative<ArtifactError>(owned_spec) || problem::hex(std::get<problem::ResolvedContent>(owned_spec).digest()) != wire.at(spec_digest_field).get<std::string>())
            return error(ArtifactErrorCode::identity, "comparison.spec_digest", "Spec digest mismatch");
        const auto& attempts = wire.at("attempts");
        if (!attempts.is_array() || attempts.empty()) return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "At least one attempt is required");
        if(attempts.size()!=static_cast<std::uint64_t>(strategy_count)*repetition_count)
            return error(ArtifactErrorCode::invalid_input,"comparison.attempts","Attempt set is incomplete for the declared spec");
        if (attempts.size() > limits.nodes || spec_text.size() > limits.bytes)
            return error(ArtifactErrorCode::limit, "comparison.capacity", "Comparison exceeds structural capacity");
        std::optional<std::pair<std::uint32_t, std::uint32_t>> previous;
        for (std::size_t i = 0; i < attempts.size(); ++i) {
            const auto& item = attempts[i];
            if (!item.is_object() || item.size() != (record_v1?7:6) ||
                !(record_v1?item.contains("arm_index"):item.contains("strategy_index")) ||
                !item.contains("repetition_index") || !item.contains("reported_status") ||
                !item.contains("run_id") || !item.contains("run_digest") || !item.contains("run"))
                return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "Attempt fields do not match schema");
            if(record_v1&&!item.contains("measurement_payload"))
                return error(ArtifactErrorCode::invalid_input,"comparison.attempts","Comparison record attempt lacks measurement payload");
            auto key = std::pair{item.at(record_v1?"arm_index":"strategy_index").get<std::uint32_t>(), item.at("repetition_index").get<std::uint32_t>()};
            if(key!=std::pair{static_cast<std::uint32_t>(i/repetition_count),static_cast<std::uint32_t>(i%repetition_count)})
                return error(ArtifactErrorCode::invalid_input,"comparison.attempts","Attempts do not cover the complete ordered spec");
            if (previous && key <= *previous) return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "Attempts are duplicated or out of order");
            previous = key; (void)parse_status(item.at("reported_status").get<std::string>());
            const auto run_text = item.at("run").get<std::string>();
            if (run_text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.attempts", "Run record exceeds byte capacity");
            const auto run_header=parse_bounded(run_text,limits);
            const bool external=run_header.value("schema",std::string{})=="csl.external-method-run/1";
            problem::ContentDigest run_content_digest{};
            if(external) {
                const auto run_content=decode_external_method_run(run_text,limits);
                if(std::holds_alternative<ArtifactError>(run_content))return error(ArtifactErrorCode::reference,"comparison.attempts.run","Invalid external method run");
                run_content_digest=std::get<RecordedExternalMethodRunArtifact>(run_content).content().digest();
            } else {
                const auto run_content=decode_recorded_run(run_text,limits);
                if(std::holds_alternative<ArtifactError>(run_content))return error(ArtifactErrorCode::reference,"comparison.attempts.run","Invalid recorded run");
                run_content_digest=std::get<RecordedRunArtifact>(run_content).content().digest();
            }
            const auto run_json=parse_bounded(run_text,limits);
            const auto run_request_digest=external?run_json.at("request_digest").get<std::string>():
                problem::hex(request_digest(run_json));
            if (run_json.at("run").get<std::string>()!=item.at("run_id").get<std::string>() ||
                problem::hex(run_content_digest)!=item.at("run_digest").get<std::string>() ||
                run_json.at("problem").get<std::string>()!=spec.at("problem_id").get<std::string>() ||
                run_json.at("configuration").at("id").get<std::string>()!=
                    spec_shape.configurations.at(key.first) ||
                run_request_digest!=spec.at("request_digest").get<std::string>() ||
                !input_manifest_attached(run_json,spec) ||
                !arm_matches_run(run_json,spec_shape,key.first) ||
                !status_matches(parse_status(item.at("reported_status").get<std::string>()),run_json))
                return error(ArtifactErrorCode::identity,"comparison.attempts.reference","Run reference identity or digest mismatch");
            if(record_v1) {
                const auto measurement_text=item.at("measurement_payload").get<std::string>();
                if(measurement_text.size()>limits.bytes||
                    !measurement_matches_arm(parse_status(item.at("reported_status").get<std::string>()),
                        parse_bounded(measurement_text,limits),run_json,spec_shape,key.first,key.second))
                    return error(ArtifactErrorCode::identity,"comparison.attempts.measurement_payload","Measurement status disagrees with the run record");
            }
        }
        problem::ContentDigest run_digest{};
        if(record_v1) {
            const Json identity_material{{"attempts",attempts},
                {"comparison_spec_id",problem::hex(std::get<problem::ResolvedContent>(owned_spec).digest())},
                {"schema","csl.comparison-record/1"}};
            const auto material=own(identity_material.dump());
            if(const auto* failure=std::get_if<ArtifactError>(&material))return *failure;
            run_digest=std::get<problem::ResolvedContent>(material).digest();
            if(problem::hex(run_digest)!=wire.at("comparison_run_id").get<std::string>())
                return error(ArtifactErrorCode::identity,"comparison.comparison_run_id","Comparison run identity mismatch");
        }
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) {
            if(!record_v1)run_digest=owned->digest();
            return RecordedComparisonArtifact(*owned,{std::get<problem::ResolvedContent>(owned_spec).digest()},{run_digest});
        }
        return std::get<ArtifactError>(std::move(content));
    } catch (const ArtifactError& failure) { return failure; }
      catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "comparison", "Allocation failed"); }
      catch (const std::exception&) { return error(ArtifactErrorCode::invalid_input, "comparison", "Malformed comparison artifact"); }
}

ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const RecordedRunArtifact& run, DecodeLimits limits) {
    try {
        const auto text=bytes_to_string(run.content().bytes());
        auto decoded=decode_recorded_run(text,limits);
        if(std::holds_alternative<ArtifactError>(decoded))return std::get<ArtifactError>(decoded);
        auto json=parse_bounded(text,limits);
        return request_digest(json);
    } catch(const ArtifactError& failure){return failure;}
      catch(const std::bad_alloc&){return error(ArtifactErrorCode::allocation,"comparison.request_digest","Allocation failed");}
      catch(const std::exception&){return error(ArtifactErrorCode::invalid_input,"comparison.request_digest","Invalid run configuration");}
}
ArtifactResult<ConfigId> comparison_configuration_id(const RecordedRunArtifact& run, DecodeLimits limits) {
    try {
        const auto text=bytes_to_string(run.content().bytes());
        auto decoded=decode_recorded_run(text,limits);
        if(std::holds_alternative<ArtifactError>(decoded))return std::get<ArtifactError>(decoded);
        const auto json=parse_bounded(text,limits);
        return ConfigId{json.at("configuration").at("id").get<std::string>()};
    } catch(const ArtifactError& failure){return failure;}
      catch(const std::bad_alloc&){return error(ArtifactErrorCode::allocation,"comparison.configuration_id","Allocation failed");}
      catch(const std::exception&){return error(ArtifactErrorCode::invalid_input,"comparison.configuration_id","Invalid run configuration");}
}
ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const RecordedExternalMethodRunArtifact& run, DecodeLimits limits) {
    try {
        const auto text=bytes_to_string(run.content().bytes());
        const auto decoded=decode_external_method_run(text,limits);
        if(const auto* failure=std::get_if<ArtifactError>(&decoded))return *failure;
        const auto json=parse_bounded(text,limits);
        const auto& value=json.at("request_digest").get_ref<const std::string&>();
        problem::ContentDigest digest{};
        for(std::size_t i=0;i<digest.bytes.size();++i) {
            const auto digit=[](char c)->unsigned char {return static_cast<unsigned char>(c<='9'?c-'0':c-'a'+10);};
            digest.bytes[i]=static_cast<std::byte>((digit(value[i*2])<<4)|digit(value[i*2+1]));
        }
        return digest;
    } catch(const ArtifactError& failure){return failure;}
      catch(const std::bad_alloc&){return error(ArtifactErrorCode::allocation,"comparison.request_digest","Allocation failed");}
      catch(const std::exception&){return error(ArtifactErrorCode::invalid_input,"comparison.request_digest","Invalid external method run");}
}
ArtifactResult<ConfigId> comparison_configuration_id(const RecordedExternalMethodRunArtifact& run, DecodeLimits limits) {
    try {
        const auto text=bytes_to_string(run.content().bytes());
        const auto decoded=decode_external_method_run(text,limits);
        if(const auto* failure=std::get_if<ArtifactError>(&decoded))return *failure;
        return std::get<RecordedExternalMethodRunArtifact>(decoded).configuration_id();
    } catch(const ArtifactError& failure){return failure;}
      catch(const std::bad_alloc&){return error(ArtifactErrorCode::allocation,"comparison.configuration_id","Allocation failed");}
      catch(const std::exception&){return error(ArtifactErrorCode::invalid_input,"comparison.configuration_id","Invalid external method run");}
}
ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const ComparisonRunArtifact& run, DecodeLimits limits) {
    return std::visit([&](const auto& value){return comparison_request_digest(value,limits);},run.value());
}
ArtifactResult<ConfigId> comparison_configuration_id(
    const ComparisonRunArtifact& run, DecodeLimits limits) {
    return std::visit([&](const auto& value){return comparison_configuration_id(value,limits);},run.value());
}
}
