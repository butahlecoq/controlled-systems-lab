#pragma once

#include <csl/artifacts/plot_request.hpp>

namespace csl::artifacts {

// Encode selected trajectories from validated PlotData for the offline figure
// exporter. source_record_sha256 binds this document to the saved run record.
ArtifactResult<std::string> encode_plot_document_json(const PlotData&,
    std::string_view source_record_schema, std::string_view source_record_sha256);
// Persist already-computed finite 2D projection and directional support-sample
// outcomes alongside selected witness data. Unsupported representations fail
// explicitly. This overload never invokes the geometry provider.
ArtifactResult<std::string> encode_plot_document_json(const PlotData&, const PlotOutcome&,
    std::string_view source_record_schema, std::string_view source_record_sha256);

} // namespace csl::artifacts
