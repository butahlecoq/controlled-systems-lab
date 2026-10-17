#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace csl::artifacts {

enum class AttemptStatus { completed, failed, unsupported, cancelled, resource_limited, incomplete };
struct ComparisonSpecId { problem::ContentDigest digest; };
struct ComparisonRunId { problem::ContentDigest digest; };
struct RunRecordRef { RunId run; problem::ContentDigest content_digest; };

struct ComparisonAttempt {
    std::uint32_t strategy_index{};
    std::uint32_t repetition_index{};
    AttemptStatus reported_status{};
    RunRecordRef reference;
    RecordedRunArtifact run;
};

// An inert, self-contained comparison archive. The spec and each run remain
// opaque canonical records; importing this type grants no execution authority.
class RecordedComparisonArtifact {
public:
    RecordedComparisonArtifact(const RecordedComparisonArtifact&) = default;
    RecordedComparisonArtifact& operator=(const RecordedComparisonArtifact&) = default;
    const problem::ResolvedContent& content() const noexcept { return content_; }
    ComparisonSpecId spec_id() const noexcept { return spec_id_; }
    ComparisonRunId identity() const noexcept { return {content_.digest()}; }
private:
    explicit RecordedComparisonArtifact(problem::ResolvedContent content, ComparisonSpecId spec_id)
        : content_(std::move(content)), spec_id_(spec_id) {}
    problem::ResolvedContent content_;
    ComparisonSpecId spec_id_;
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
// excluding implementation modules and strategy-specific adapter identities.
ArtifactResult<problem::ContentDigest> comparison_request_digest(
    const RecordedRunArtifact&, DecodeLimits limits = {});

} // namespace csl::artifacts
