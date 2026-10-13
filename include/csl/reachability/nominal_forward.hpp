#pragma once

#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/problem/resolved_problem.hpp>

namespace csl::reachability {

// A marginal and its recovery factor, never an optimal-history family.
// Initial joint coordinates are [x_0]; later factors are [x_t,u_t,x_(t+1)].
struct ForwardStage {
    StageIndex stage;
    OperationResult marginal;
    SetHandle joint_factor;
    std::vector<SetId> source_factors;
    std::vector<std::size_t> state_coordinates, control_coordinates, next_coordinates;
    std::vector<GeometryEvidence> operation_lineage;
    std::vector<RequestProvenance> providers;
};
struct ForwardTube {
    ProblemId problem;
    RequestId request;
    std::vector<ForwardStage> stages;
};
// The prefix includes the empty marginal. No later stages were executed.
struct EmptyForwardStage { ForwardTube prefix; StageIndex stage; GeometryEvidence evidence; };
struct ForwardFailure {
    ForwardTube prefix;
    StageIndex stage;
    std::optional<GeometryReference> active_request;
    std::vector<GeometryEvidence> completed_lineage;
    std::vector<RequestProvenance> providers;
    std::variant<Unsupported,OperationStopped> cause;
};
using NominalForwardOutcome = std::variant<ForwardTube,EmptyForwardStage,ForwardFailure>;

// First profile: discrete nominal open loop, known initial point, no external
// port or temporal coupling, continuous native H/singleton/empty/universal sets.
// The selected provider must materialize equivalent native H projections.
// Each generated request is admitted before creating its exclusive workspace.
NominalForwardOutcome nominal_forward(const problem::ResolvedProblem&, RequestId,
    const registry::PreparedProvider<registry::GeometryPort>&, const ExecutionContext&);

} // namespace csl::reachability
