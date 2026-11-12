#pragma once

#include <csl/reachability/nominal_forward.hpp>

namespace csl::reachability {

enum class NominalTubePhase { forward, terminal, backward, intersection };

// Each present set is a full-state H relation at this local task stage.
// coordinates maps these ordered state coordinates to the source state vector.
struct NominalTubeStage {
    StageIndex stage;
    std::vector<std::size_t> coordinates;
    std::vector<std::string> coordinate_labels;
    std::optional<OperationResult> forward;
    std::optional<OperationResult> backward;
    std::optional<OperationResult> intersection;
    std::vector<SetId> source_sets;
    std::vector<RequestProvenance> providers;
    std::vector<GeometryEvidence> lineage;
};

struct NominalTube {
    ProblemId problem;
    RequestId request;
    std::vector<NominalTubeStage> stages;
};

struct NominalTubeFailure {
    NominalTube prefix;
    StageIndex stage;
    NominalTubePhase phase;
    std::optional<GeometryRequestIdentity> active_request;
    std::variant<Unsupported, OperationStopped> cause;
};

// Forward propagation may establish an empty stage before the horizon. Keep
// the actual prefix and its emptiness evidence distinct from provider failure.
struct NominalTubeEmptyForward {
    NominalTube prefix;
    StageIndex first_empty_stage;
    GeometryEvidence evidence;
};

using NominalTubeOutcome = std::variant<NominalTube, NominalTubeEmptyForward, NominalTubeFailure>;

struct NominalTubeDependencies {
    ForwardDependencies forward;
    registry::PreparedProvider<registry::GeometryPort> intersection;
};

// Computes full-state F_k, B_k and F_k ∩ B_k for one closed-H continuous
// nominal affine profile. No objective optimization or nonlinear claim is made.
NominalTubeOutcome nominal_tube(const problem::ResolvedProblem&, RequestId,
    const SetHandle& terminal_feasibility, const NominalTubeDependencies&,
    const ExecutionContext&);

} // namespace csl::reachability
