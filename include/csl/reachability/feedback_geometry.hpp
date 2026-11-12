#pragma once

#include <csl/reachability/nominal_tube.hpp>
#include <csl/sets/generator_sets.hpp>

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

struct FeedbackSet {
    FeedbackFamily family;
    FeedbackScope scope;
    SetRelation relation;
    Assurance assurance;
    FeedbackMembership membership;
    std::vector<SetId> source_sets;
    std::vector<RequestProvenance> providers;
    std::vector<GeometryEvidence> lineage;
};

struct FeedbackGeometryStage {
    StageIndex stage;
    std::vector<std::size_t> coordinates;
    // The source H operands and full-state intersection precede projection.
    OperationResult forward_h, backward_h, intersection_h;
    FeedbackSet forward, backward, intersection;
};

} // namespace csl::reachability
