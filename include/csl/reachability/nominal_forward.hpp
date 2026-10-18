#pragma once

#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/problem/resolved_problem.hpp>

namespace csl::reachability {
// Lossless metadata bridge: native numeric buffers keep their ordered columns;
// source and target labels/IDs differ, and coordinates maps target to source.
struct CoordinateRelabeling {
    SetHandle source, target;
    std::vector<std::size_t> coordinates;
};

// A marginal and its recovery factor, never an optimal-history family.
// Initial joint coordinates are [x_0]; later factors are [x_t,u_t,x_(t+1)].
struct ForwardStage {
    StageIndex stage;
    OperationResult marginal;
    SetHandle joint_factor;
    GeometryEvidence recovery_evidence; // authored joint relation unestablished
    SetHandle propagation_factor; // provider sum intersect next constraints
    std::vector<SetId> source_factors;
    std::vector<std::size_t> state_coordinates, control_coordinates, next_coordinates;
    std::vector<GeometryEvidence> operation_lineage;
    std::vector<RequestProvenance> providers;
    std::vector<CoordinateRelabeling> coordinate_lineage;
};
struct ForwardTube {
    ProblemId problem;
    RequestId request;
    std::vector<ForwardStage> stages;
};
// A stage marginal already computed when a later operation stops. Its
// evidence remains scoped to this marginal and never certifies tube completion.
struct ForwardPartialRelation {
    StageIndex stage;
    OperationResult marginal;
    SetHandle projection_source;
    std::vector<std::size_t> source_coordinates;
};
// The prefix includes the empty marginal. No later stages were executed.
struct EmptyForwardStage { ForwardTube prefix; StageIndex stage; GeometryEvidence evidence; };
struct ForwardFailure {
    ForwardTube prefix;
    StageIndex stage;
    std::optional<ForwardPartialRelation> partial_relation;
    std::optional<GeometryReference> active_request;
    std::vector<GeometryEvidence> completed_lineage;
    std::vector<RequestProvenance> providers;
    std::vector<CoordinateRelabeling> coordinate_lineage;
    std::variant<Unsupported,OperationStopped> cause;
};
using NominalForwardOutcome = std::variant<ForwardTube,EmptyForwardStage,ForwardFailure>;
struct ForwardDependencies {
    registry::PreparedProvider<registry::GeometryPort> projection;
    registry::PreparedProvider<registry::GeometryPort> affine_sum;
    registry::PreparedProvider<registry::ConversionPort> to_h;
};

// First profile: discrete nominal open loop, known initial point, no external
// port or temporal coupling, continuous native H/singleton/empty/universal sets.
// Selected providers materialize equivalent native H projections, V affine
// images/sums, and V-to-H conversion. Affine/conversion requests use unnamed
// positional coordinates; lossless metadata maps restore authored state labels.
// Provider limitations (including boundedness/capacity) remain typed rejections.
// Each generated request is admitted before creating its exclusive workspace.
NominalForwardOutcome nominal_forward(const problem::ResolvedProblem&, RequestId,
    const ForwardDependencies&, const ExecutionContext&);

} // namespace csl::reachability
