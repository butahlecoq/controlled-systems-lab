#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace csl::artifacts {

enum class AttemptStatus { completed, failed, unsupported, cancelled, resource_limited, incomplete };

struct ComparisonAttempt {
    std::uint32_t strategy_index{};
    std::uint32_t repetition_index{};
    AttemptStatus reported_status{};
    RecordedRunArtifact run;
};

// An inert, self-contained comparison archive. The spec and each run remain
// opaque canonical records; importing this type grants no execution authority.
class RecordedComparisonArtifact {
public:
    RecordedComparisonArtifact(const RecordedComparisonArtifact&) = default;
    RecordedComparisonArtifact& operator=(const RecordedComparisonArtifact&) = default;
    const problem::ResolvedContent& content() const noexcept { return content_; }
private:
    explicit RecordedComparisonArtifact(problem::ResolvedContent content) : content_(std::move(content)) {}
    problem::ResolvedContent content_;
    friend ArtifactResult<RecordedComparisonArtifact> encode_recorded_comparison(
        const problem::ResolvedContent&, const std::vector<ComparisonAttempt>&, EncodeLimits);
    friend ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(std::string_view, DecodeLimits);
};

ArtifactResult<RecordedComparisonArtifact> encode_recorded_comparison(
    const problem::ResolvedContent& canonical_spec, const std::vector<ComparisonAttempt>& ordered_attempts,
    EncodeLimits limits = {});
ArtifactResult<RecordedComparisonArtifact> decode_recorded_comparison(
    std::string_view, DecodeLimits limits = {});

} // namespace csl::artifacts
