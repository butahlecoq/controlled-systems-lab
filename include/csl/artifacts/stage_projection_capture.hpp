#pragma once

#include <csl/artifacts/stage_projection_request.hpp>

namespace csl::artifacts {

struct StageProjectionUnavailable {
    StageProjectionGap::Kind kind;
    std::string explanation;
    std::optional<OperationStopped> stop;
};

struct StageProjectionFailure {
    GeometryRequestIdentity identity;
    std::optional<registry::Provenance> selected_provider;
    std::optional<PlotQueryCost> cost;
    std::variant<registry::Rejection, Unsupported, OperationStopped, ArtifactError> cause;
};

struct StageProjectionSuccess {
    PlotSetProjection projection;
    std::optional<GeometryErrorBound> error_bound;
    std::vector<SetHandle> additional_components;
    struct Materialization {
        SetHandle relation;
        GeometryEvidence evidence;
        registry::Provenance provider;
        SetRelation relation_claim{SetRelation::equivalent};
    };
    struct MaterializationFailure {
        std::string kind;
        std::string explanation;
        std::optional<registry::Provenance> provider;
    };
    // Optional equivalent finite-point representation used by saved figures.
    // The projection itself remains the original 2D relation and evidence.
    std::optional<Materialization> materialization;
    // A failed optional figure conversion does not invalidate the projection.
    std::optional<MaterializationFailure> materialization_failure;
};

using StageProjectionOutcome = std::variant<StageProjectionSuccess, StageProjectionUnavailable,
    StageProjectionFailure>;

struct StageProjectionRecord {
    StageIndex stage;
    std::optional<double> physical_time;
    ResolvedStageProjectionPair pair;
    std::optional<Assurance> source_assurance;
    std::vector<StageProjectionSourceEvidence> source_evidence;
    StageProjectionOutcome outcome;
};

struct StageProjectionBatchCapture {
    ProblemId problem;
    RequestId request;
    SetRelation required_relation;
    Assurance requested_assurance;
    std::vector<StageProjectionRecord> records;
};

using StageProjectionCaptureOutcome = std::variant<StageProjectionBatchCapture,
    Unsupported, ArtifactError>;

StageProjectionCaptureOutcome capture_stage_projections(
    const StageProjectionCaptureRequest&,
    const registry::PreparedProvider<registry::GeometryPort>&,
    const ExecutionContext& = {});

} // namespace csl::artifacts
