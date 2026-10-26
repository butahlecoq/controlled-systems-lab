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
    // The route-wide state schema used to resolve every requested pair once.
    std::vector<CoordinateAnnotation> state_coordinates;
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

struct ValidatedStageProjectionRequest {
    std::vector<ResolvedStageProjectionPair> coordinate_pairs;
};

using StageProjectionRequestValidation = std::variant<ValidatedStageProjectionRequest,
    ArtifactError>;

StageProjectionRequestValidation validate_stage_projection_request(
    const StageProjectionCaptureRequest&);

} // namespace csl::artifacts
