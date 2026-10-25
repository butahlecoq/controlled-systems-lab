#pragma once

#include <csl/artifacts/plot_data.hpp>

namespace csl::artifacts {

// Encode selected trajectories from validated PlotData for the offline figure
// exporter. source_record_sha256 binds this document to the saved run record.
ArtifactResult<std::string> encode_plot_document_json(const PlotData&,
    std::string_view source_record_schema, std::string_view source_record_sha256);

} // namespace csl::artifacts
