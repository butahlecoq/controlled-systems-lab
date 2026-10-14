#pragma once

#include <csl/geometry/contracts.hpp>

#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

namespace csl::geometry::polyhedral {

enum class ProjectionOutput { lazy, h, v };
struct ProjectionOptions {
    ProjectionOutput output{ProjectionOutput::h};
    // Caller admission limit on intermediate H rows; absent means no policy
    // limit. Fourier--Motzkin row growth and host allocation still apply.
    std::optional<std::size_t> max_rows;
};

struct LazyProjectionDescription {
    SetHandle source;
    std::vector<std::size_t> coordinates;
    std::vector<std::string> coordinate_labels;
    GeometryEvidence creation_evidence;
    // Earlier immutable projection claims, in operation order. Coordinates
    // above map directly to source even when lazy selections are composed.
    std::vector<GeometryEvidence> lineage;
};
std::variant<LazyProjectionDescription, Diagnostics> inspect_lazy_projection(const SetHandle&);

struct ProjectionMaterializationResult {
    OperationResult result;
    RequestProvenance provider;
    std::vector<GeometryEvidence> completed_lineage;
    std::vector<std::size_t> source_coordinates;
};
struct ProjectionMaterializationFailure {
    GeometryReference reference;
    RequestProvenance provider;
    std::vector<GeometryEvidence> completed_lineage;
    std::vector<std::size_t> source_coordinates;
    std::variant<Unsupported, OperationStopped> cause;
};
using ProjectionMaterializationOutcome =
    std::variant<ProjectionMaterializationResult, ProjectionMaterializationFailure>;
// Retains source/coordinate lineage and selected provenance around the existing
// ConversionPort, including pre-admission rejection and late stops/rejection.
ProjectionMaterializationOutcome materialize_lazy_projection(
    const ConversionRequest&, const registry::PreparedProvider<registry::ConversionPort>&,
    const ExecutionContext&);

registry::Registration<registry::GeometryPort> make_projection_registration(
    ProjectionOptions = {});
// Materializes this module's immutable lazy projection payloads, using the
// requested native H or V representation. It never selects an H/V converter.
registry::Registration<registry::ConversionPort> make_projection_materializer(
    std::optional<std::size_t> max_rows = {});

} // namespace csl::geometry::polyhedral
