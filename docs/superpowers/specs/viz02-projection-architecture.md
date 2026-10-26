# VIZ-02 projection architecture

## Problem

VIZ-01 supplies state histories and typed witness evidence, but those rows are finite selected trajectories. A 2D mathematical state-set projection requires an explicit geometry request against a live relation. The existing geometry registry already owns projection admission and execution, and its result keeps `SetRelation` distinct from `EvidenceSupport`. Current H projection uses binary64 arithmetic and reports `Unestablished` support, so an `equivalent` operation must not be relabelled exact. Family relations are opaque; a plot adapter must not fabricate a `SetHandle` from a family identity or from a decoded claim.

## Usage (caller's view)

Select two coordinates from recorded witness paths without creating or calling a geometry provider:

```cpp
PlotRequest request = PlotRequest::trajectory_pair({1, 3});
auto traces = make_plot(plot_data, request);
```

Project a live relation only after naming its state-coordinate map, source owner, and required relation and assurance:

```cpp
PlotRequest request = PlotRequest::set_projection(
    source, StageIndex{2}, {1, 3}, SetRelation::equivalent,
    Assurance::numerical, {"fuel-stock-request"}, {"projected-fuel-stocks"});
auto projection = make_plot(plot_data, request, geometry_provider, context);
```

If the caller asks for validated arithmetic that no selected provider supports, preparation returns a typed rejection before workspace creation. If a geometry operation runs but stops or returns unsupported, the failure retains the source/request identity, selected provider context, and elapsed operation duration when available.

Finite support samples are a third explicit request path. The caller supplies one or more nonzero 2D directions, each with its own request and reference identity. The adapter embeds each direction into the chosen two coordinates of the source relation and invokes the selected `SupportQuery` provider. Each returned support value, optional maximizing point, support-value evidence, reference and assumptions stay tagged as `support_samples`; they are not returned as a complete set projection. A V-only support provider rejects an H source during admission.

## Shape

Use one tagged `PlotRequest` and a `PlotOutcome` variant while keeping the trajectory, projection, and support-sample paths separate inside the adapter. The trajectory alternative contains only an ordered pair of state-coordinate indices; it extracts the pair at every state point and marks each path's terminal point. The set-projection alternative contains a projectable source, stage, coordinate pair, required `SetRelation`, `Assurance`, `RequestId`, and `ReferenceId`. The support-sample alternative contains a projectable source, stage, coordinate pair, explicit 2D directions and a unique request/reference identity per direction. A projection source owns a live `SetHandle`, the problem and source owner identity, and a complete stage-to-relation coordinate map. The map has one row per state stage and one relation index per state coordinate, so a joint family can select a state marginal without guessing how its stored state and control coordinates are ordered.

`make_plot(plot_data, trajectory_request)` is pure selection of state-coordinate values and terminal samples. It has no provider parameter. `make_plot(plot_data, set_request, prepared_geometry_provider, context)` validates the source map and pair, constructs the existing `OperationRequest{Projection{...}}`, prepares the selected provider, creates a workspace only after admission, and runs it. The result copies the returned `GeometryReference`, relation, support, assumptions and selected actual provider provenance. The support-sample path embeds each 2D direction in the full source dimension, prepares and runs one existing `SupportQuery` per direction, and retains optional projected maximizers and support values separately from set geometry. Both geometry-backed paths record only wall time around operation runs, separate from synthesis and strategy timings. These durations are descriptive, not CPU work or complexity counts.

The source factory for an `OptimalFamily` accepts only a live complete family with registry verification and an available concrete relation representation. It obtains ordinary set data from the family payload, then retains the family identity and completeness support alongside (not inside) the projection evidence. If the payload has no projectable relation view, or the family is partial, candidate-only, or merely decoded, construction returns unsupported. A direct reachable-set source must provide its own live `SetHandle`, source identity and state-coordinate map. The adapter never infers a family handle from a witness, run identity, or coordinate dimension.

`SetRelation::equivalent` and `EvidenceSupport` remain separate in `PlotSetProjection`. For example, `equivalent + Unestablished` means the provider reports an equivalent relation for stored input/output while its arithmetic support remains unestablished. A validated/exact request requires a provider accepted for `Assurance::validated`; it is rejected otherwise. Inner, outer, and heuristic results retain their own relation value. The renderer must not promote an outer approximation, a finite sample, or unestablished arithmetic to exact geometry.

The public interface centralizes source mapping, request identity, provider admission, failure context and cost measurement. The renderer receives a typed result instead of assembling raw geometry operations. The additional source factory exists only because `JointRelationPayload` intentionally does not promise a generic set handle. No new registry, H/V conversion selection, solver call or rendering dependency is introduced.

### Type sketch

```cpp
struct CoordinatePair { std::size_t first, second; };
struct StateRelationCoordinates { std::vector<std::vector<std::size_t>> by_stage; };
struct PlotSourceOwner { ProblemId problem; std::variant<SetId, FamilyIdentity> identity; };
struct FamilySourceEvidence {
    FamilyIdentity family;
    CompletenessSupport support;
    bool registry_verified;
};
class PlotProjectionSource;
using PlotSourceResult = std::variant<std::shared_ptr<const PlotProjectionSource>, Diagnostics>;
PlotSourceResult make_reachable_set_source(
    SetHandle, ProblemId, StateRelationCoordinates);
PlotSourceResult make_optimal_family_source(
    const OptimalFamily&, StateRelationCoordinates);

class PlotProjectionSource {
public:
    const SetHandle& relation() const noexcept;
    const PlotSourceOwner& owner() const noexcept;
    const StateRelationCoordinates& coordinates() const noexcept;
    const std::optional<FamilySourceEvidence>& family_evidence() const noexcept;
private:
    PlotProjectionSource(SetHandle, PlotSourceOwner, StateRelationCoordinates,
        std::optional<FamilySourceEvidence>);
    SetHandle relation_;
    PlotSourceOwner owner_;
    StateRelationCoordinates coordinates_;
    std::optional<FamilySourceEvidence> family_evidence_;
    friend PlotSourceResult make_reachable_set_source(SetHandle, ProblemId,
        StateRelationCoordinates);
    friend PlotSourceResult make_optimal_family_source(const OptimalFamily&,
        StateRelationCoordinates);
};

struct TrajectoryPairRequest { CoordinatePair coordinates; };
struct SetProjectionRequest {
    std::shared_ptr<const PlotProjectionSource> source;
    StageIndex stage;
    CoordinatePair coordinates;
    SetRelation required_relation;
    Assurance assurance;
    RequestId request;
    ReferenceId ideal_output;
};
struct SupportSampleDirection {
    std::array<double, 2> direction;
    RequestId request;
    ReferenceId ideal_output;
};
struct SupportSamplesRequest {
    std::shared_ptr<const PlotProjectionSource> source;
    StageIndex stage;
    CoordinatePair coordinates;
    std::vector<SupportSampleDirection> directions;
    Assurance assurance;
};
struct PlotRequest {
    std::variant<TrajectoryPairRequest, SetProjectionRequest, SupportSamplesRequest> source;
    static PlotRequest trajectory_pair(CoordinatePair);
    static PlotRequest set_projection(std::shared_ptr<const PlotProjectionSource>, StageIndex,
        CoordinatePair, SetRelation, Assurance, RequestId, ReferenceId);
    static PlotRequest support_samples(std::shared_ptr<const PlotProjectionSource>, StageIndex,
        CoordinatePair, std::vector<SupportSampleDirection>, Assurance);
};
enum class PlotSampleKind { selected_witnesses, support_samples };
struct PlotQueryCost { std::chrono::nanoseconds geometry_operation_elapsed{}; };
struct PlotTrajectoryPath {
    RunId run;
    std::size_t source_ordinal;
    ModuleId strategy;
    std::string strategy_version;
    double objective;
    PlotEvidence evidence;
    std::vector<std::array<double, 2>> points;
};
struct PlotTerminalSample {
    RunId run;
    std::size_t source_ordinal;
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
struct PlotRequestFailure {
    std::optional<GeometryRequestIdentity> identity;
    std::optional<registry::Provenance> selected_provider;
    std::optional<PlotQueryCost> cost;
    std::variant<registry::Rejection, Unsupported, OperationStopped, ArtifactError> cause;
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
struct PlotSupportSample {
    std::array<double, 2> direction;
    std::variant<double, EmptySupport, UnboundedSupport> value;
    std::optional<std::array<double, 2>> point;
    GeometryReference reference;
    EvidenceSupport support;
    std::vector<std::string> assumptions;
};
struct PlotSupportSamples {
    ProblemId problem;
    PlotSourceOwner source;
    StageIndex stage;
    std::array<CoordinateAnnotation, 2> coordinates;
    PlotSampleKind kind{PlotSampleKind::support_samples};
    std::vector<PlotSupportSample> samples;
    registry::Provenance provider;
    std::optional<FamilySourceEvidence> family_evidence;
    PlotQueryCost cost;
};
using PlotOutcome = std::variant<PlotTrajectoryPair, PlotSetProjection,
    PlotSupportSamples, PlotRequestFailure>;

PlotOutcome make_plot(const PlotData&, const PlotRequest&);
PlotOutcome make_plot(const PlotData&, const PlotRequest&,
    const registry::PreparedProvider<registry::GeometryPort>&,
    const ExecutionContext& = {});
```

The implementation should use concrete success/failure variants rather than default-constructible placeholder fields; this compact sketch highlights the request boundary and required evidence fields. A projection-source factory must prove the supplied owner and live relation refer to the same source. For family sources it takes the relation from that exact live family payload; it returns unsupported when the payload exposes no relation. Coordinate maps are validated for stage count, state-coordinate count, in-range relation indices, and uniqueness at the boundary.

## Synthesis decision

Use Candidate B's tagged `PlotRequest`/`PlotOutcome` and source-supplied live `SetHandle`. This most directly matches the issue's request object, expresses stage-to-joint-coordinate selection, and refuses to invent an `OptimalFamily` conversion that existing payloads do not promise. Graft Candidate A's separate source-family claim and failure provenance/cost fields so callers can distinguish family completeness from projection evidence and retain context across rejection or stop. The cross-judge also required a bound family-source factory and an unambiguous stage mapping; those are included here. Reject Candidate A's loose `PlotSetSource` construction as too easy to misbind, and reject renderer-managed raw `GeometryOperation` construction because it would duplicate provider policy and evidence labeling.

## Tradeoffs accepted

- We accept a caller-supplied stage-to-relation map in exchange for not assuming a joint relation's internal coordinate order.
- We accept `Assurance::validated` as the request for exact arithmetic evidence; current binary64 projection providers will reject it.
- We accept descriptive operation wall time as the initial query-cost measure because the geometry result exposes no row/vertex work count. It does not imply computational complexity or compare providers.
- We accept that an optimal family remains unprojectable when its live payload does not expose ordinary set data.
- We keep the renderer out of this API. A standalone illustrative fuel projection graphic is included at `docs/examples/fuel-state-projections-illustrative.svg`; #96 can render saved projection results to SVG/PDF plus PNG without duplicating geometry work.

## Alternatives considered

- Separate public trajectory and set-projection request APIs make the no-query property obvious but fail to provide the requested unified `PlotRequest` surface and force consumers to combine two result types. They expose more composition policy to each caller.
- Making each renderer create `GeometryOperation` directly keeps the plot adapter smaller but duplicates source-coordinate mapping, admission, failure binding and guarantee interpretation in each consumer. It hides less capability behind the public plotting boundary.
- Treating `FamilyIdentity` plus an arbitrary `SetHandle` as a sufficient family source is shorter, but it cannot prove those values identify the same relation. A source factory must derive the set from the live family object or reject it.

## Open questions and risks

- Is wall time around the admitted geometry run sufficient for “query cost,” or should a future geometry result expose generated-row/vertex counts? This design records elapsed operation time only.
- Which currently supported optimal-family strategies expose a live ordinary set relation for fuel profiles? The API returns unsupported when the payload does not provide one.
- Historical B04 bounds and a canonical executable source remain unresolved. The VIZ-02 test/example must use a clearly labelled illustrative four-state fixture unless that source is restored independently.

## Implementation and follow-up

The bound projection-source factories and tagged plot request are implemented in `plot_request.hpp` and `plot_request.cpp`. Contract tests prove the no-query witness path and analytic rectangle/line projections. #96 remains responsible for regenerating standalone figures from saved result data, with visual QA and raster previews.

## Stage-resolved extension in #708

This VIZ-02 contract remains a single-pair, single-stage projection API. The
closed #91 scope excluded intermediate all-stage viewers. Issue #708 adds a
separate requirement for ordered coordinate-pair lists and stage-labelled set
marginals R0 through RT, with trajectories stored as distinct series. It does
not change the meaning of `PlotData`, `PlotRequest`, or the `csl.plot-document/1`
format. The [stage-projection architecture note](../../architecture/stage-projection-visualization.md)
records the route capability audit and the additive batch design.

Projection remains an explicit geometry operation through the existing
`GeometryPort`. Capture uses only stage relations exposed by the task run and
records missing or unsupported stages. It does not infer set geometry from a
trajectory or rerun a task to fill missing records. An offline renderer reads
the saved stage batch and performs no geometry or solver operation.
