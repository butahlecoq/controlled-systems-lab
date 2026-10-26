#pragma once

#include <csl/artifacts/stage_projection_capture.hpp>

namespace csl::artifacts {

struct StageProjectionTrajectorySeries {
    RunId source_run;
    std::array<std::size_t, 2> coordinates;
    std::vector<std::array<double, 2>> points;
    std::string evidence;
};

// Stable identity supplied by the saved run that owns this projection batch.
// Route and coordinate order are explicit because stage marginals cannot be
// reconstructed from a selected trajectory after the run has been saved.
struct StageProjectionBatchIdentity {
    RunId run;
    std::string route;
    std::string source_record_schema;
    std::string source_record_sha256;
    std::vector<CoordinateAnnotation> state_coordinates;
    std::vector<std::array<std::size_t, 2>> requested_coordinate_pairs;
    PlotAxis stage_axis;
    std::vector<StageProjectionTrajectorySeries> trajectory_series;
};

ArtifactResult<std::string> encode_stage_projection_batch_json(
    const StageProjectionBatchIdentity&, const StageProjectionBatchCapture&);

} // namespace csl::artifacts
