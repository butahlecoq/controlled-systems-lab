#include <csl/artifacts/comparison_manifest.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cctype>
#include <limits>
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
    case AttemptStatus::unsupported: return "unsupported";
    case AttemptStatus::cancelled: return "cancelled";
    case AttemptStatus::resource_limited: return "resource_limited";
    case AttemptStatus::incomplete: return "incomplete";
    }
    return {};
}
AttemptStatus parse_status(const std::string& value) {
    if (value == "completed") return AttemptStatus::completed;
    if (value == "failed") return AttemptStatus::failed;
    if (value == "unsupported") return AttemptStatus::unsupported;
    if (value == "cancelled") return AttemptStatus::cancelled;
    if (value == "resource_limited") return AttemptStatus::resource_limited;
    if (value == "incomplete") return AttemptStatus::incomplete;
    throw std::invalid_argument("Unknown attempt status");
}
bool status_matches(AttemptStatus status, const Json& run) {
    const auto& final=run.at("final");
    const auto kind=final.at("kind").get<std::string>();
    if(kind=="synthesis"||kind=="program") {
        const auto& result=kind=="synthesis"?final.at("value"):final.at("value").at("result");
        const auto termination=result.at("termination").get<std::string>();
        if(termination=="completed")return status==AttemptStatus::completed;
        if(termination=="cancelled")return status==AttemptStatus::cancelled;
        if(termination=="resource_limit")return status==AttemptStatus::resource_limited;
        if(termination=="operation_rejected"||termination=="contract_rejected")return status==AttemptStatus::unsupported;
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
Json common_request(const Json& run) {
    auto request=run.at("configuration").at("value");
    request.erase("modules");
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
std::pair<std::uint32_t,std::uint32_t> validate_spec(const Json& spec) {
    if (!spec.is_object() || spec.size()!=5 || spec.value("schema",std::string{})!="csl.comparison-spec/1" ||
        !spec.contains("problem_id") || !spec.contains("request_digest") ||
        !spec.contains("strategies") || !spec.contains("repetitions"))
        throw std::invalid_argument("Comparison spec fields do not match schema");
    const auto valid_digest=[](const Json& value){return value.is_string()&&value.get<std::string>().size()==64&&
        std::all_of(value.get<std::string>().begin(),value.get<std::string>().end(),[](unsigned char c){return std::isxdigit(c)!=0&&!(c>='A'&&c<='F');});};
    if(!spec.at("problem_id").is_string()||spec.at("problem_id").get<std::string>().empty()||!valid_digest(spec.at("request_digest")))
        throw std::invalid_argument("Comparison spec digest is malformed");
    const auto& strategies=spec.at("strategies");
    if(!strategies.is_array()||strategies.empty()||strategies.size()>std::numeric_limits<std::uint32_t>::max())
        throw std::invalid_argument("Comparison spec strategy list is invalid");
    for(const auto& strategy:strategies)if(!valid_digest(strategy))throw std::invalid_argument("Strategy configuration identity is malformed");
    const auto repetitions=spec.at("repetitions").get<std::uint32_t>();
    if(repetitions==0)throw std::invalid_argument("Repetition count must be positive");
    return {static_cast<std::uint32_t>(strategies.size()),repetitions};
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
        const auto [strategy_count,repetition_count]=validate_spec(spec_json);
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
                    spec_json.at("strategies").at(attempt.strategy_index).get<std::string>() ||
                problem::hex(request_digest(run_json))!=spec_json.at("request_digest").get<std::string>() ||
                !status_matches(attempt.reported_status,run_json))
                return error(ArtifactErrorCode::identity, "attempts[" + std::to_string(i) + "].reference", "Run reference identity or content digest mismatch");
            records.push_back({{"strategy_index", attempt.strategy_index}, {"repetition_index", attempt.repetition_index},
                {"reported_status", status_name(attempt.reported_status)}, {"run_id", attempt.reference.run.value},
                {"run_digest", problem::hex(attempt.reference.content_digest)}, {"run", run_text}});
        }
        Json wire{{"schema", "csl.comparison/1"}, {"spec", spec_text}, {"spec_digest", problem::hex(spec.digest())}, {"attempts", records}};
        const auto text = wire.dump();
        if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.bytes", "Encoded comparison exceeds byte limit");
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) return RecordedComparisonArtifact(*owned,{spec.digest()});
        return std::get<ArtifactError>(std::move(content));
    } catch (const ArtifactError& failure) { return failure; }
      catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "comparison", "Allocation failed"); }
      catch (const std::exception&) { return error(ArtifactErrorCode::invalid_input, "comparison", "Invalid spec or attempt data"); }
}

ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(std::string_view text, DecodeLimits limits) {
    if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.bytes", "Comparison exceeds byte limit");
    try {
        auto outer_limits=limits; outer_limits.string_bytes=limits.bytes;
        auto wire = parse_bounded(text,outer_limits);
        if (wire.dump() != text) return error(ArtifactErrorCode::invalid_input, "comparison.canonical", "Comparison is not canonical JSON");
        if (!wire.is_object() || wire.size() != 4 || !wire.contains("schema") || !wire.contains("spec") ||
            !wire.contains("spec_digest") || !wire.contains("attempts"))
            return error(ArtifactErrorCode::invalid_input, "comparison.fields", "Comparison fields do not match schema");
        if (wire.at("schema") != "csl.comparison/1") return error(ArtifactErrorCode::unsupported, "comparison.schema", "Unknown comparison schema");
        const auto spec_text = wire.at("spec").get<std::string>();
        if (spec_text.size() > limits.string_bytes) return error(ArtifactErrorCode::limit, "comparison.spec", "Spec exceeds string capacity");
        auto spec = parse_bounded(spec_text,limits);
        if (spec.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "comparison.spec", "Spec is not canonical JSON");
        const auto [strategy_count,repetition_count]=validate_spec(spec);
        auto owned_spec = own(spec_text);
        if (std::holds_alternative<ArtifactError>(owned_spec) || problem::hex(std::get<problem::ResolvedContent>(owned_spec).digest()) != wire.at("spec_digest").get<std::string>())
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
            if (!item.is_object() || item.size() != 6 || !item.contains("strategy_index") ||
                !item.contains("repetition_index") || !item.contains("reported_status") ||
                !item.contains("run_id") || !item.contains("run_digest") || !item.contains("run"))
                return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "Attempt fields do not match schema");
            auto key = std::pair{item.at("strategy_index").get<std::uint32_t>(), item.at("repetition_index").get<std::uint32_t>()};
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
                    spec.at("strategies").at(key.first).get<std::string>() ||
                problem::hex(request_digest(run_json))!=spec.at("request_digest").get<std::string>() ||
                !status_matches(parse_status(item.at("reported_status").get<std::string>()),run_json))
                return error(ArtifactErrorCode::identity,"comparison.attempts.reference","Run reference identity or digest mismatch");
        }
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) return RecordedComparisonArtifact(*owned,{std::get<problem::ResolvedContent>(owned_spec).digest()});
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
