#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/sets/data.hpp>

namespace csl::artifacts {

struct HRelationAttachmentLimits {
    std::uint64_t max_bytes;
    std::uint64_t max_dimension;
    std::uint64_t max_rows;
    std::uint64_t max_text_bytes;
};

// Encodes the ordered logical H rows as exact binary64 bit patterns. This is
// representation transport only; it carries no relation-equivalence or proof authority.
ArtifactResult<problem::ResolvedContent> encode_h_relation_attachment(
    const sets::SetData&, HRelationAttachmentLimits);
ArtifactResult<sets::SetData> decode_h_relation_attachment(
    std::span<const std::byte>, HRelationAttachmentLimits,
    std::optional<problem::ContentDigest> expected_digest = {});

} // namespace csl::artifacts
