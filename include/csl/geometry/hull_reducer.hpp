#pragma once

#include <csl/optimization/lp_backend.hpp>

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

// Uses independent zero-objective barycentric feasibility programs. Only a
// feasible primal point that passes fresh residual and nonnegativity checks can
// remove a candidate. All other outcomes conservatively retain it.
HullReductionResult reduce_hull(const PointCloud&, LPWorkspace&,
                                const ExecutionContext&);

} // namespace csl::geometry
