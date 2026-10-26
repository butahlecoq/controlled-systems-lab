#pragma once

#include <csl/artifacts/plot_request.hpp>

#include <variant>

namespace csl::artifacts {

struct CoordinateOrdinal { std::size_t value{}; };
struct CoordinateName { std::string value; };
using StateCoordinate = std::variant<CoordinateOrdinal, CoordinateName>;

struct StageCoordinatePair {
    StateCoordinate first;
    StateCoordinate second;
};

struct StageProjectionSet {
    SetHandle relation;
    PlotSourceOwner owner;
    std::vector<CoordinateAnnotation> state_coordinates;
    // Maps each state coordinate to its coordinate in `relation`.
    std::vector<std::size_t> relation_coordinates;
    SetRelation relation_claim{SetRelation::equivalent};
    Assurance assurance{Assurance::numerical};
};

struct StageProjectionGap {
    enum class Kind { missing, unsupported, stopped } kind{Kind::missing};
    std::string explanation;
    std::optional<OperationStopped> stop;
};

struct StageProjectionInput {
    StageIndex stage;
    std::optional<double> physical_time;
    std::variant<StageProjectionSet, StageProjectionGap> source;
};

struct StageProjectionCaptureRequest {
    ProblemId problem;
    RequestId request;
    std::vector<StageCoordinatePair> coordinate_pairs;
    std::vector<StageProjectionInput> stages;
    SetRelation required_relation{SetRelation::equivalent};
    Assurance assurance{Assurance::numerical};
};

struct ResolvedStageProjectionPair {
    std::size_t first{};
    std::size_t second{};
    std::array<CoordinateAnnotation, 2> coordinates;
};

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

using StageProjectionOutcome = std::variant<PlotSetProjection, StageProjectionUnavailable,
    StageProjectionFailure>;

struct StageProjectionRecord {
    StageIndex stage;
    std::optional<double> physical_time;
    ResolvedStageProjectionPair pair;
    std::optional<Assurance> source_assurance;
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
