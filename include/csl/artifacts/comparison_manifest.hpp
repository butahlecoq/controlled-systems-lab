#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace csl::artifacts {

enum class AttemptStatus { completed, failed, refused, unsupported, timed_out, cancelled, resource_limited, incomplete };
struct ComparisonSpecId { problem::ContentDigest digest; };
struct ComparisonRunId { problem::ContentDigest digest; };
struct RunRecordRef { RunId run; problem::ContentDigest content_digest; };

struct ExternalMethodSource { std::string path; std::string sha256; };
struct ExternalMethodRuntime {
    std::string language;
    std::string implementation;
    std::string version;
    std::string executable_sha256;
    std::string os;
    std::string architecture;
    std::string compiler;
    std::string compiler_version;
    std::string build_type;
};
struct ExternalMethodRunInput {
    RunId run;
    ProblemId problem;
    ConfigId configuration;
    problem::ContentDigest request_digest;
    std::string input_manifest_schema;
    std::vector<std::byte> input_manifest;
    std::string method_id;
    std::string method_version;
    std::vector<ExternalMethodSource> sources;
    std::optional<std::string> deviations_sha256;
    ExternalMethodRuntime runtime;
    AttemptStatus status{};
    // Canonical method-specific JSON. The comparison codec retains it but does
    // not interpret algorithm outputs or checker evidence.
    std::string result_payload;
};

class RecordedExternalMethodRunArtifact {
public:
    RecordedExternalMethodRunArtifact(const RecordedExternalMethodRunArtifact&) = default;
    RecordedExternalMethodRunArtifact& operator=(const RecordedExternalMethodRunArtifact&) = default;
    const problem::ResolvedContent& content() const noexcept { return content_; }
    const RunId& run_id() const noexcept { return run_id_; }
    const ProblemId& problem_id() const noexcept { return problem_id_; }
    const ConfigId& configuration_id() const noexcept { return configuration_id_; }
    AttemptStatus status() const noexcept { return status_; }
private:
    RecordedExternalMethodRunArtifact(problem::ResolvedContent content, RunId run,
        ProblemId problem, ConfigId configuration, AttemptStatus status)
        : content_(std::move(content)), run_id_(std::move(run)), problem_id_(std::move(problem)),
          configuration_id_(std::move(configuration)), status_(status) {}
    problem::ResolvedContent content_;
    RunId run_id_;
    ProblemId problem_id_;
    ConfigId configuration_id_;
    AttemptStatus status_;
    friend ArtifactResult<RecordedExternalMethodRunArtifact> encode_external_method_run(
        const ExternalMethodRunInput&, EncodeLimits);
    friend ArtifactResult<RecordedExternalMethodRunArtifact> decode_external_method_run(
        std::string_view, DecodeLimits);
};

class ComparisonRunArtifact {
public:
    using Value = std::variant<RecordedRunArtifact, RecordedExternalMethodRunArtifact>;
    ComparisonRunArtifact(RecordedRunArtifact run) : value_(std::move(run)) {}
    ComparisonRunArtifact(RecordedExternalMethodRunArtifact run) : value_(std::move(run)) {}
    const problem::ResolvedContent& content() const noexcept {
        return std::visit([](const auto& run) -> const problem::ResolvedContent& {
            return run.content();
        }, value_);
    }
    const Value& value() const noexcept { return value_; }
private:
    Value value_;
};

ArtifactResult<RecordedExternalMethodRunArtifact> encode_external_method_run(
    const ExternalMethodRunInput&, EncodeLimits limits = {});
ArtifactResult<RecordedExternalMethodRunArtifact> decode_external_method_run(
    std::string_view, DecodeLimits limits = {});

struct ComparisonAttempt {
    // The zero-based arm in the canonical spec. OBS-04 specs may define an
    // arm as one strategy/configuration/mode combination.
    std::uint32_t strategy_index{};
    std::uint32_t repetition_index{};
    AttemptStatus reported_status{};
    RunRecordRef reference;
    ComparisonRunArtifact run;
    // Exact JSON measurement event for csl.comparison-record/1. It is kept as
    // supplied and included in the comparison content digest.
    std::string measurement_payload;
};

// An inert, self-contained comparison archive. The spec and each run remain
// opaque canonical records; importing this type grants no execution authority.
class RecordedComparisonArtifact {
public:
    RecordedComparisonArtifact(const RecordedComparisonArtifact&) = default;
    RecordedComparisonArtifact& operator=(const RecordedComparisonArtifact&) = default;
    const problem::ResolvedContent& content() const noexcept { return content_; }
    ComparisonSpecId spec_id() const noexcept { return spec_id_; }
    ComparisonRunId identity() const noexcept { return run_id_; }
private:
    explicit RecordedComparisonArtifact(problem::ResolvedContent content, ComparisonSpecId spec_id,
        ComparisonRunId run_id)
        : content_(std::move(content)), spec_id_(spec_id), run_id_(run_id) {}
    problem::ResolvedContent content_;
    ComparisonSpecId spec_id_;
    ComparisonRunId run_id_;
    friend ArtifactResult<RecordedComparisonArtifact> encode_recorded_comparison(
        const problem::ResolvedContent&, const std::vector<ComparisonAttempt>&, EncodeLimits);
    friend ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(std::string_view, DecodeLimits);
};

ArtifactResult<RecordedComparisonArtifact> encode_recorded_comparison(
    const problem::ResolvedContent& canonical_spec, const std::vector<ComparisonAttempt>& ordered_attempts,
    EncodeLimits limits = {});
ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(
    std::string_view, DecodeLimits limits = {});
// Hashes the common request portion of one recorded run's resolved configuration,
// excluding implementation modules, adapter identities and collection mode.
ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const RecordedRunArtifact&, DecodeLimits limits = {});
ArtifactResult<ConfigId> comparison_configuration_id(
    const RecordedRunArtifact&, DecodeLimits limits = {});
ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const RecordedExternalMethodRunArtifact&, DecodeLimits limits = {});
ArtifactResult<ConfigId> comparison_configuration_id(
    const RecordedExternalMethodRunArtifact&, DecodeLimits limits = {});
ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const ComparisonRunArtifact&, DecodeLimits limits = {});
ArtifactResult<ConfigId> comparison_configuration_id(
    const ComparisonRunArtifact&, DecodeLimits limits = {});

} // namespace csl::artifacts
