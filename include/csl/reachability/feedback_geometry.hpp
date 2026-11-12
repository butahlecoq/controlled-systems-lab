#pragma once

#include <csl/reachability/nominal_tube.hpp>
#include <csl/sets/generator_sets.hpp>
#include <csl/registry/provider.hpp>
#include <csl/reachability/bounded_h_support.hpp>

namespace csl::reachability {

enum class FeedbackFamily { polytope, box, zonotope, parallelotope, ellipsoid };
enum class FeedbackScope { forward_relevant_from_observation, global_source_domain };

// H membership includes the actual full-state inequalities and equalities.
// A parallelotope retains its frame even though its solver membership is H.
struct FeedbackHMembership {
    SetHandle set;
    std::optional<Matrix> parallelotope_frame;
};
// x = center + generators * factors, each factor independently in [-1,1].
struct FeedbackZonotopeMembership {
    Vector center;
    Matrix generators;
    std::vector<sets::FactorId> factors;
};
// x = center + factor * z, ||z||_2 <= 1, including singular factors.
struct FeedbackEllipsoidMembership { Vector center; Matrix factor; };
using FeedbackMembership = std::variant<FeedbackHMembership,
    FeedbackZonotopeMembership, FeedbackEllipsoidMembership>;

// A strict source predicate is retained separately from the closed outer set.
// For example, orbit radius > 0 uses coordinate 0 and lower_bound 0.
struct StrictCoordinateLowerBound { std::size_t coordinate; double lower_bound; };

struct FeedbackSet {
    FeedbackFamily family;
    FeedbackScope scope;
    SetRelation relation;
    Assurance assurance;
    FeedbackMembership membership;
    std::vector<StrictCoordinateLowerBound> strict_source_domain;
    std::vector<SetId> source_sets;
    std::vector<GeometryReference> requests;
    std::vector<RequestProvenance> providers;
    std::vector<registry::LPQueryRecord> support_calls;
    std::vector<SupportBoundMethod> support_methods;
    std::vector<SupportBoundCertificate> support_certificates;
    std::vector<std::string> construction;
    std::vector<GeometryEvidence> lineage;
};

struct FeedbackGeometryStage {
    StageIndex stage;
    std::vector<std::size_t> coordinates;
    // The source H operands and full-state intersection precede projection.
    std::optional<OperationResult> forward_h, backward_h, intersection_h;
    std::optional<SetHandle> forward_embedding_h, backward_embedding_h;
    std::optional<FeedbackSet> forward, backward, intersection;
};

struct FeedbackGeometry {
    ProblemId problem;
    RequestId request;
    FeedbackFamily family;
    FeedbackScope backward_scope{FeedbackScope::forward_relevant_from_observation};
    std::vector<FeedbackGeometryStage> stages;
};
enum class FeedbackGeometryPhase { forward, terminal, backward, intersection };
struct FeedbackGeometryFailure {
    FeedbackGeometry prefix;
    StageIndex stage;
    FeedbackGeometryPhase phase;
    std::variant<Unsupported, OperationStopped> cause;
    std::vector<GeometryReference> pending_requests;
    std::vector<RequestProvenance> pending_providers;
    std::vector<GeometryEvidence> pending_lineage;
    std::vector<registry::LPQueryRecord> pending_support_calls;
    std::vector<SupportBoundCertificate> pending_support_certificates;
};
using FeedbackGeometryOutcome = std::variant<FeedbackGeometry, FeedbackGeometryFailure>;
struct FeedbackGeometryDependencies {
    NominalTubeDependencies geometry;
    registry::PreparedProvider<registry::LPPort> support;
    std::size_t max_generators_per_stage;
};

// A deliberately coarse cover for a clipped bounded H intersection. This is
// distinct from correlated native propagation. Polytope requires its original H
// operand and is not constructed by this axis-only helper.
std::variant<FeedbackMembership, Diagnostics> axis_enclosure(FeedbackFamily,
    SetId, const Vector& lower, const Vector& upper,
    const std::vector<std::string>& coordinate_labels);

FeedbackGeometryOutcome feedback_geometry(const problem::ResolvedProblem&, RequestId,
    const SetHandle& terminal_feasibility, FeedbackFamily,
    const std::vector<StrictCoordinateLowerBound>& strict_source_domain,
    const FeedbackGeometryDependencies&, const ExecutionContext&);

} // namespace csl::reachability
