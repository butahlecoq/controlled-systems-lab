#pragma once

#include <csl/geometry/contracts.hpp>

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

struct BasisReuseMetrics {
    std::size_t basis_solves{};
    // Original PointCloud indices of structural columns in the validated basis;
    // auxiliary phase-I columns are excluded.
    std::vector<std::size_t> structural_basis_points;
    std::uint64_t pivots{};
    std::uint64_t degenerate_pivots{};
    std::size_t bulk_candidates{};
    std::size_t bulk_removals{};
    bool fell_back_to_lp_baseline{};
};

struct OrderedReductionMetrics {
    // Original PointCloud indices before any LP call. Ties keep input order.
    std::vector<std::size_t> processing_order;
    std::size_t ordered_candidates{};
    std::size_t zero_width_coordinates{};
    // True when finite input has a range or score unsafe for binary64 sorting.
    // In that case processing_order is the original input order.
    bool used_identity_fallback{};
};

struct GroupedReductionMetrics {
    // Original PointCloud IDs after deterministic outer-box ordering.
    std::vector<std::size_t> processing_order;
    std::size_t ordered_candidates{};
    std::size_t streamed_candidates{};
    // Candidates retested in the grouped remainder, including the trigger point.
    std::size_t grouping_passes{};
    std::size_t grouped_candidates{};
    std::size_t nearby_supports{};
    std::size_t certified_stream_removals{};
    bool grouping_triggered{};
    std::size_t zero_width_coordinates{};
    bool used_identity_fallback{};
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
    // Present only for a reducer that performs within-solve basis reuse.
    std::optional<BasisReuseMetrics> basis_reuse{};
    // Present only for a reducer that sorts candidates before certified LP reduction.
    std::optional<OrderedReductionMetrics> ordered{};
    // Present only for the grouped hull-level strategy. Grouping changes LP
    // query order; exact membership certificates remain the removal authority.
    std::optional<GroupedReductionMetrics> grouped{};
};

using HullReductionResult = std::variant<HullReduction, Diagnostics>;

class HullReducerWorkspace : public ExclusiveWorkspace {
public:
    virtual HullReductionResult reduce(const PointCloud&, LPWorkspace&,
                                       const ExecutionContext&) = 0;
};

// Uses independent zero-objective barycentric feasibility programs. Solver
// residuals propose witnesses only; exact dyadic verification of nonnegative
// weights, unit sum, and coordinate reconstruction authorizes removal.
// All other outcomes conservatively retain the candidate.
HullReductionResult reduce_hull(const PointCloud&, LPWorkspace&,
                                const ExecutionContext&);

// Applies the archived Scientific Research bounding-box score as a deterministic
// candidate order, then runs the same certified LP reduction over original IDs.
HullReductionResult reduce_ordered_hull(const PointCloud&, LPWorkspace&,
                                        const ExecutionContext&);

// Streams candidates in the archived Constrained QLPHULL signed max-absolute
// box order; after ten certified redundant outcomes, filters the remainder
// against a fixed retained group plus nearby candidates, then certifies its hull.
HullReductionResult reduce_grouped_hull(const PointCloud&, LPWorkspace&,
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
registry::Registration<registry::HullReducerPort> make_ordered_hull_reducer_registration();
registry::Registration<registry::HullReducerPort> make_grouped_hull_reducer_registration();
} // namespace csl::geometry
