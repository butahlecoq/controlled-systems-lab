#include <csl/artifacts/comparison_manifest.hpp>
#include <nlohmann/json.hpp>
#include <stdexcept>

namespace csl::artifacts {
namespace {
using Json = nlohmann::json;
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
std::string bytes_to_string(std::span<const std::byte> bytes) {
    std::string out; out.reserve(bytes.size());
    for (auto b : bytes) out.push_back(static_cast<char>(std::to_integer<unsigned char>(b)));
    return out;
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
        if (attempts.empty()) return error(ArtifactErrorCode::invalid_input, "attempts", "At least one attempt is required");
        if (attempts.size() > limits.bytes / 32) return error(ArtifactErrorCode::limit, "attempts", "Attempt count exceeds byte budget");
        const auto spec_text = bytes_to_string(spec.bytes());
        auto spec_json = Json::parse(spec_text);
        if (spec_json.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "spec", "Spec must be canonical JSON");
        Json records = Json::array();
        std::optional<std::pair<std::uint32_t, std::uint32_t>> previous;
        for (std::size_t i = 0; i < attempts.size(); ++i) {
            const auto& attempt = attempts[i];
            if (status_name(attempt.reported_status).empty())
                return error(ArtifactErrorCode::invalid_input, "attempts[" + std::to_string(i) + "].reported_status", "Unknown attempt status");
            const auto key = std::pair{attempt.strategy_index, attempt.repetition_index};
            if (previous && key <= *previous)
                return error(ArtifactErrorCode::invalid_input, "attempts[" + std::to_string(i) + "]", "Attempts must be uniquely ordered by strategy and repetition");
            previous = key;
            const auto run_text = bytes_to_string(attempt.run.content().bytes());
            auto validated = decode_recorded_run(run_text, DecodeLimits{limits.bytes, 1000000, 64, 1024*1024});
            if (std::holds_alternative<ArtifactError>(validated))
                return error(ArtifactErrorCode::reference, "attempts[" + std::to_string(i) + "].run", "Attempt does not contain a valid recorded run");
            records.push_back({{"strategy_index", attempt.strategy_index}, {"repetition_index", attempt.repetition_index},
                {"reported_status", status_name(attempt.reported_status)}, {"run", run_text}});
        }
        Json wire{{"schema", "csl.comparison/1"}, {"spec", spec_text}, {"spec_digest", problem::hex(spec.digest())}, {"attempts", records}};
        const auto text = wire.dump();
        if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.bytes", "Encoded comparison exceeds byte limit");
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) return RecordedComparisonArtifact(*owned);
        return std::get<ArtifactError>(std::move(content));
    } catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "comparison", "Allocation failed"); }
      catch (const std::exception&) { return error(ArtifactErrorCode::invalid_input, "comparison", "Invalid spec or attempt data"); }
}

ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(std::string_view text, DecodeLimits limits) {
    if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "comparison.bytes", "Comparison exceeds byte limit");
    try {
        auto wire = Json::parse(text);
        if (wire.dump() != text) return error(ArtifactErrorCode::invalid_input, "comparison.canonical", "Comparison is not canonical JSON");
        if (!wire.is_object() || wire.size() != 4 || !wire.contains("schema") || !wire.contains("spec") ||
            !wire.contains("spec_digest") || !wire.contains("attempts"))
            return error(ArtifactErrorCode::invalid_input, "comparison.fields", "Comparison fields do not match schema");
        if (wire.at("schema") != "csl.comparison/1") return error(ArtifactErrorCode::unsupported, "comparison.schema", "Unknown comparison schema");
        const auto spec_text = wire.at("spec").get<std::string>();
        if (spec_text.size() > limits.string_bytes) return error(ArtifactErrorCode::limit, "comparison.spec", "Spec exceeds string capacity");
        auto spec = Json::parse(spec_text);
        if (spec.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "comparison.spec", "Spec is not canonical JSON");
        auto owned_spec = own(spec_text);
        if (std::holds_alternative<ArtifactError>(owned_spec) || problem::hex(std::get<problem::ResolvedContent>(owned_spec).digest()) != wire.at("spec_digest"))
            return error(ArtifactErrorCode::identity, "comparison.spec_digest", "Spec digest mismatch");
        const auto& attempts = wire.at("attempts");
        if (!attempts.is_array() || attempts.empty()) return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "At least one attempt is required");
        if (attempts.size() > limits.nodes || spec_text.size() > limits.string_bytes)
            return error(ArtifactErrorCode::limit, "comparison.capacity", "Comparison exceeds structural capacity");
        std::optional<std::pair<std::uint32_t, std::uint32_t>> previous;
        for (std::size_t i = 0; i < attempts.size(); ++i) {
            const auto& item = attempts[i];
            if (!item.is_object() || item.size() != 4 || !item.contains("strategy_index") ||
                !item.contains("repetition_index") || !item.contains("reported_status") || !item.contains("run"))
                return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "Attempt fields do not match schema");
            auto key = std::pair{item.at("strategy_index").get<std::uint32_t>(), item.at("repetition_index").get<std::uint32_t>()};
            if (previous && key <= *previous) return error(ArtifactErrorCode::invalid_input, "comparison.attempts", "Attempts are duplicated or out of order");
            previous = key; (void)parse_status(item.at("reported_status").get<std::string>());
            const auto run_text = item.at("run").get<std::string>();
            if (run_text.size() > limits.string_bytes) return error(ArtifactErrorCode::limit, "comparison.attempts", "Run record exceeds string capacity");
            if (std::holds_alternative<ArtifactError>(decode_recorded_run(run_text, limits)))
                return error(ArtifactErrorCode::reference, "comparison.attempts[" + std::to_string(i) + "].run", "Invalid recorded run");
        }
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) return RecordedComparisonArtifact(*owned);
        return std::get<ArtifactError>(std::move(content));
    } catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "comparison", "Allocation failed"); }
      catch (const std::exception&) { return error(ArtifactErrorCode::invalid_input, "comparison", "Malformed comparison artifact"); }
}
}
