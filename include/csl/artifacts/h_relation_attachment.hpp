#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/sets/data.hpp>
#include <cstdint>
#include <span>

namespace csl::artifacts {

struct HRelationAttachmentLimits {
    std::uint64_t max_bytes;
    std::uint64_t max_dimension;
    std::uint64_t max_rows;
    std::uint64_t max_text_bytes;
};

struct RecordedNumericalCheck { double absolute_tolerance, relative_tolerance, max_residual; ModuleId verifier; };
struct RecordedSymbolicArgument { std::string reference, assumptions; };
struct RecordedCertificateReference { std::string artifact, verifier; };
struct RecordedExactFarkasEvidence { LinearInfeasibilityCertificate certificate; };
using RecordedEvidenceSupport=std::variant<Unestablished,RecordedNumericalCheck,RecordedSymbolicArgument,
    RecordedCertificateReference,RecordedExactFarkasEvidence>;
struct RecordedAffineDimensionClaim { sets::AffineDimension value; sets::DimensionOrigin origin; RecordedEvidenceSupport support; };
struct RecordedHRelation {
    SetId id;
    SetMetadata metadata;
    std::vector<std::string> coordinate_labels;
    std::optional<RecordedAffineDimensionClaim> affine_dimension;
    sets::HRepresentation representation;
};

// Encodes ordered logical H rows as exact binary64 bit patterns. Import creates
// only an inert RecordedHRelation, never SetData or verifier-authorized evidence.
ArtifactResult<problem::ResolvedContent> encode_h_relation_attachment(
    const sets::SetData&, HRelationAttachmentLimits);
ArtifactResult<RecordedHRelation> decode_h_relation_attachment(
    std::span<const std::byte>, HRelationAttachmentLimits,
    std::optional<problem::ContentDigest> expected_digest = {});

} // namespace csl::artifacts
