#pragma once

#include <csl/optimization/lp_backend.hpp>
#include <csl/registry/registry.hpp>

namespace csl::geometry {

struct PointCloud {
    ProblemId problem;
    // Each point has the same ambient dimension. Its position in this vector is
    // its stable identity in the reduction result and certificates.
    std::vector<Vector> points;
};

enum class MembershipOutcome {
    feasible,
    infeasible,
    unsupported,
    stopped,
    numerical_failure,
    malformed_result
};

enum class ReductionStatus { complete, incomplete };

struct MembershipAttempt {
    std::size_t candidate;
    MembershipOutcome outcome;
};

struct ConvexCombination {
    std::size_t point;
    double weight;
};

struct RemovalCertificate {
    std::size_t removed;
    // Certificates are in removal order. A term may refer to a point removed
    // later in this vector; substitute that later certificate to reach the
    // final retained cloud.
    std::vector<ConvexCombination> combination;
    ProgramIdentity program;
    // NumericalCheck records solver diagnostics only. A consumer may authorize
    // removal only after independently proving, over the exact dyadic values
    // represented by these binary64 coordinates and weights, that weights are
    // nonnegative, sum exactly to one, and reconstruct the removed point.
    NumericalCheck evidence;
};

struct HullReduction {
    ReductionStatus status;
    std::vector<std::size_t> retained;
    std::vector<RemovalCertificate> removed;
    std::size_t lp_calls;
    std::vector<MembershipAttempt> attempts;
};

using HullReductionResult = std::variant<HullReduction, Diagnostics>;

class HullReducerWorkspace : public ExclusiveWorkspace {
public:
    virtual HullReductionResult reduce(const PointCloud&, LPWorkspace&,
                                       const ExecutionContext&) = 0;
};

// Uses independent zero-objective barycentric feasibility programs. Only a
// feasible primal point that passes fresh residual and nonnegativity checks can
// remove a candidate. All other outcomes conservatively retain it.
HullReductionResult reduce_hull(const PointCloud&, LPWorkspace&,
                                const ExecutionContext&);

} // namespace csl::geometry

namespace csl::registry {
struct HullReducerPort {
    using Request = geometry::PointCloud;
    using Workspace = geometry::HullReducerWorkspace;
    static constexpr const char* name = "hull-reducer";
    static Request snapshot(const Request& request) { return request; }
    static geometry::HullReductionResult run(Workspace& workspace, const Request& request,
            const ExecutionContext& context, LPWorkspace& lp) {
        return workspace.reduce(request, lp, context);
    }
};
} // namespace csl::registry

namespace csl::geometry {
// Registers the LP-backed membership reducer as one replaceable implementation
// behind HullReducerPort. The LP workspace remains a separate dependency.
registry::Registration<registry::HullReducerPort> make_lp_hull_reducer_registration();
} // namespace csl::geometry
