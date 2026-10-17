#pragma once

#include <csl/geometry/hull_reducer.hpp>

namespace csl::geometry::detail {

// Internal order is a permutation of original point IDs. The caller constructs
// it; this function preserves those IDs in LP programs and certificates.
HullReductionResult reduce_hull_in_order(const PointCloud&, LPWorkspace&,
    const ExecutionContext&, const std::vector<std::size_t>& order);

HullReductionResult reduce_hull_in_order(const PointCloud&, LPWorkspace&,
    const ExecutionContext&, const std::vector<std::size_t>& order,
    std::vector<RemovalCertificate> prior_certificates);

struct CandidateClassification {
    MembershipAttempt attempt;
    std::optional<RemovalCertificate> certificate;
    std::size_t lp_calls{};
};

CandidateClassification classify_candidate(const PointCloud&,
    const std::vector<std::size_t>& support, std::size_t candidate,
    LPWorkspace&, const ExecutionContext&);

} // namespace csl::geometry::detail
