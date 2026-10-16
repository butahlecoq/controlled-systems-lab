#pragma once

#include <csl/geometry/hull_reducer.hpp>

namespace csl::geometry::detail {

// Internal order is a permutation of original point IDs. The caller constructs
// it; this function preserves those IDs in LP programs and certificates.
HullReductionResult reduce_hull_in_order(const PointCloud&, LPWorkspace&,
    const ExecutionContext&, const std::vector<std::size_t>& order);

} // namespace csl::geometry::detail
