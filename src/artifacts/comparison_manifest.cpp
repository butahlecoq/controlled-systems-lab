#include <csl/artifacts/comparison_manifest.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
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
    if(spec.at("input_manifest_source")=="resolved-problem-canonical-bytes")return true;
    const auto expected=spec.at("input_manifest_hash").get<std::string>();
    const auto& attachments=run.at("attachments");
    std::size_t matches=0;
    for(const auto& attachment:attachments)
        if(attachment.at("role")=="certificate"&&
           attachment.at("schema")=="csl.exp05-finite-minimax-case/1"&&
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
};
bool exact_fields(const Json& value, std::initializer_list<std::string_view> fields) {
    if(!value.is_object()||value.size()!=fields.size())return false;
    return std::all_of(fields.begin(),fields.end(),[&](const auto field){return value.contains(field);});
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
    if(!exact_fields(environment,{"schema","build","runtime","execution"})||
        environment.at("schema")!="csl.obs04-environment/1")
        throw std::invalid_argument("Environment manifest schema or fields are invalid");
    const auto& build=environment.at("build");
    if(!exact_fields(build,{"schema","source_revision","source_tree_sha256","source_snapshot_method","source_dirty",
        "compiler_id","compiler_version","generator","architecture","build_type","cxx_standard",
        "c_flags_sha256","cxx_flags_sha256","executable_link_flags_sha256","target_flags_sha256","backends"})||
        build.at("schema")!="csl.obs04-build/1"||!valid_git_revision(build.at("source_revision"))||
        !valid_sha256(build.at("source_tree_sha256"))||
        build.at("source_snapshot_method")!="git-head-tracked-diff-untracked-content-sha256/1"||
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
    if(!exact_fields(backends,{"highs","qhull"}))
        throw std::invalid_argument("Environment backend facts are invalid");
    for(const auto name:{"highs","qhull"}) {
        const auto& backend=backends.at(name);
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
        !positive_small_integer(execution.at("warmup_repetitions"))||execution.at("warmup_repetitions")!=1||
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
         spec.at("input_manifest_source")=="csl.exp05-finite-minimax-case/1");
    const bool record_with_environment=schema=="csl.comparison-spec/3"&&spec.size()==8&&spec.contains("arms")&&
        spec.contains("input_manifest_hash")&&spec.contains("input_manifest_source")&&
        (spec.at("input_manifest_source")=="resolved-problem-canonical-bytes"||
         spec.at("input_manifest_source")=="csl.exp05-finite-minimax-case/1")&&spec.contains("environment");
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
           spec.at("input_manifest_source")!="csl.exp05-finite-minimax-case/1")
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
    return {record||record_with_environment,std::move(configurations),std::move(strategies),std::move(instrumentation),repetitions};
}
bool arm_matches_run(const Json& run,const SpecShape& spec,std::size_t arm) {
    if(spec.strategies.empty())return true;
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
bool measurement_matches_arm(AttemptStatus status,const Json& measurement,const Json& run,
    const SpecShape& spec,std::size_t arm,std::uint32_t repetition) {
    if(!measurement_status_matches(status,measurement))return false;
    if(spec.strategies.empty())return true;
    const auto schema=measurement.value("schema",std::string{});
    if(schema=="csl.exp05-fixed-plan-event/1")
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
            const auto run_bytes=attempt.run.content().bytes();
            if(run_bytes.size()>limits.bytes-payload_bytes)
                return error(ArtifactErrorCode::limit, "attempts", "Attempt payloads exceed byte budget");
            payload_bytes+=run_bytes.size();
            const auto run_text = bytes_to_string(run_bytes);
            auto validated = decode_recorded_run(run_text, validation_limits);
            if (std::holds_alternative<ArtifactError>(validated))
                return error(ArtifactErrorCode::reference, "attempts[" + std::to_string(i) + "].run", "Attempt does not contain a valid recorded run");
            const auto run_json = parse_bounded(run_text, validation_limits);
            if (run_json.at("run").get<std::string>() != attempt.reference.run.value ||
                attempt.run.content().digest() != attempt.reference.content_digest ||
                run_json.at("problem").get<std::string>()!=spec_json.at("problem_id").get<std::string>() ||
                run_json.at("configuration").at("id").get<std::string>()!=
                    spec_shape.configurations.at(attempt.strategy_index) ||
                problem::hex(request_digest(run_json))!=spec_json.at("request_digest").get<std::string>() ||
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
            const auto run_content=decode_recorded_run(run_text,limits);
            if (std::holds_alternative<ArtifactError>(run_content)) return error(ArtifactErrorCode::reference,"comparison.attempts.run","Invalid recorded run");
            const auto run_json=parse_bounded(run_text,limits);
            const auto& content=std::get<RecordedRunArtifact>(run_content).content();
            if (run_json.at("run").get<std::string>()!=item.at("run_id").get<std::string>() ||
                problem::hex(content.digest())!=item.at("run_digest").get<std::string>() ||
                run_json.at("problem").get<std::string>()!=spec.at("problem_id").get<std::string>() ||
                run_json.at("configuration").at("id").get<std::string>()!=
                    spec_shape.configurations.at(key.first) ||
                problem::hex(request_digest(run_json))!=spec.at("request_digest").get<std::string>() ||
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
}
