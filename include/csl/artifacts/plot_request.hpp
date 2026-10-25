#pragma once

#include <csl/artifacts/plot_data.hpp>
#include <csl/geometry/contracts.hpp>
#include <csl/registry/provider.hpp>

#include <array>
#include <chrono>

namespace csl::artifacts {

struct CoordinatePair {
    std::size_t first{}, second{};
};

struct StateRelationCoordinates {
    std::vector<std::vector<std::size_t>> by_stage;
};

struct PlotSourceOwner {
    ProblemId problem;
    std::variant<SetId, FamilyIdentity> identity;
};

struct FamilySourceEvidence {
    FamilyIdentity family;
    CompletenessSupport support;
    bool registry_verified{};
};

class PlotProjectionSource;
using PlotSourceResult = std::variant<std::shared_ptr<const PlotProjectionSource>, Diagnostics>;

PlotSourceResult make_reachable_set_source(
    SetHandle, ProblemId, StateRelationCoordinates);
PlotSourceResult make_optimal_family_source(
    const OptimalFamily&, StateRelationCoordinates);

class PlotProjectionSource {
public:
    const SetHandle& relation() const noexcept { return relation_; }
    const PlotSourceOwner& owner() const noexcept { return owner_; }
    const StateRelationCoordinates& coordinates() const noexcept { return coordinates_; }
    const std::optional<FamilySourceEvidence>& family_evidence() const noexcept { return family_evidence_; }

private:
    PlotProjectionSource(SetHandle, PlotSourceOwner, StateRelationCoordinates,
        std::optional<FamilySourceEvidence>);

    SetHandle relation_;
    PlotSourceOwner owner_;
    StateRelationCoordinates coordinates_;
    std::optional<FamilySourceEvidence> family_evidence_;

    friend PlotSourceResult make_reachable_set_source(
        SetHandle, ProblemId, StateRelationCoordinates);
    friend PlotSourceResult make_optimal_family_source(
        const OptimalFamily&, StateRelationCoordinates);
};

struct TrajectoryPairRequest {
    CoordinatePair coordinates;
};

struct SetProjectionRequest {
    std::shared_ptr<const PlotProjectionSource> source;
    StageIndex stage;
    CoordinatePair coordinates;
    SetRelation required_relation;
    Assurance assurance;
    RequestId request;
    ReferenceId ideal_output;
};

struct PlotRequest {
    std::variant<TrajectoryPairRequest, SetProjectionRequest> source;

    static PlotRequest trajectory_pair(CoordinatePair);
    static PlotRequest set_projection(std::shared_ptr<const PlotProjectionSource>, StageIndex,
        CoordinatePair, SetRelation, Assurance, RequestId, ReferenceId);
};

enum class PlotSampleKind { selected_witnesses, support_samples };

struct PlotTrajectoryPath {
    RunId run;
    std::size_t source_ordinal{};
    ModuleId strategy;
    std::string strategy_version;
    double objective{};
    PlotEvidence evidence;
    std::vector<std::array<double, 2>> points;
};

struct PlotTerminalSample {
    RunId run;
    std::size_t source_ordinal{};
    std::array<double, 2> point;
};

struct PlotTrajectoryPair {
    ProblemId problem;
    PlotAxis state_axis;
    std::array<CoordinateAnnotation, 2> coordinates;
    std::vector<PlotTrajectoryPath> paths;
    std::vector<PlotTerminalSample> terminal_samples;
    PlotSampleKind kind{PlotSampleKind::selected_witnesses};
};

struct PlotQueryCost {
    std::chrono::nanoseconds geometry_operation_elapsed{};
};

struct PlotSetProjection {
    ProblemId problem;
    PlotSourceOwner source;
    StageIndex stage;
    GeometryReference reference;
    SetHandle projected_relation;
    std::array<CoordinateAnnotation, 2> coordinates;
    SetRelation relation;
    EvidenceSupport support;
    std::vector<std::string> assumptions;
    registry::Provenance provider;
    std::optional<FamilySourceEvidence> family_evidence;
    PlotQueryCost cost;
};

struct PlotRequestFailure {
    std::optional<GeometryRequestIdentity> identity;
    std::optional<registry::Provenance> selected_provider;
    std::optional<PlotQueryCost> cost;
    std::variant<registry::Rejection, Unsupported, OperationStopped, ArtifactError> cause;
};

using PlotOutcome = std::variant<PlotTrajectoryPair, PlotSetProjection, PlotRequestFailure>;

PlotOutcome make_plot(const PlotData&, const PlotRequest&);
PlotOutcome make_plot(const PlotData&, const PlotRequest&,
    const registry::PreparedProvider<registry::GeometryPort>&,
    const ExecutionContext& = {});

}
