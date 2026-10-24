#pragma once

#include <csl/geometry/hull_reducer.hpp>
#include <string_view>

namespace csl::geometry::detail {

// Internal order is a permutation of original point IDs. The caller constructs
// it; this function preserves those IDs in LP programs and certificates.
HullReductionResult reduce_hull_in_order(const PointCloud&, LPWorkspace&,
    const ExecutionContext&, const std::vector<std::size_t>& order);

HullReductionResult reduce_hull_in_order(const PointCloud&, LPWorkspace&,
    const ExecutionContext&, const std::vector<std::size_t>& order,
    std::vector<RemovalCertificate> prior_certificates,
    std::string_view query_namespace = {});

HullReductionResult finish_grouped_hull(const PointCloud&, LPWorkspace&,
    const ExecutionContext&, const std::vector<std::size_t>& retained,
    std::vector<RemovalCertificate> prior_certificates,
    std::vector<MembershipAttempt> attempts, std::size_t lp_calls,
    bool staged_incomplete, bool stop_after_staging);

struct CandidateClassification {
    MembershipAttempt attempt;
    std::optional<RemovalCertificate> certificate;
    std::size_t lp_calls{};
};

CandidateClassification classify_candidate(const PointCloud&,
    const std::vector<std::size_t>& support, std::size_t candidate,
    LPWorkspace&, const ExecutionContext&, std::string_view query_namespace = {});

} // namespace csl::geometry::detail
