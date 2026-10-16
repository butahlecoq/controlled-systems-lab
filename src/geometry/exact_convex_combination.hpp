#pragma once

#include <csl/geometry/hull_reducer.hpp>
#include "exact_dyadic.hpp"

#include <cmath>
#include <span>

namespace csl::geometry::detail {

inline bool exact_convex_combination(const PointCloud& cloud, std::size_t removed,
        std::span<const ConvexCombination> terms) noexcept {
    using namespace exact_detail;
    if (removed >= cloud.points.size()) return false;
    const auto& candidate = cloud.points[removed];
    Integer total;
    for (const auto& term : terms) {
        if (term.point >= cloud.points.size() || term.point == removed ||
            !std::isfinite(term.weight) || term.weight < 0.0 ||
            cloud.points[term.point].size() != candidate.size()) return false;
        const auto weight = decode(term.weight);
        if (!add_dyadic(total, weight)) return false;
    }
    Integer one;
    if (!add_dyadic(one, decode(1.0)) || total.negative || compare_magnitude(total, one) != 0)
        return false;

    for (std::size_t coordinate = 0; coordinate < candidate.size(); ++coordinate) {
        const double target_value = candidate[coordinate];
        if (!std::isfinite(target_value)) return false;
        Integer sum;
        for (const auto& term : terms) {
            const double support_value = cloud.points[term.point][coordinate];
            if (!std::isfinite(support_value) ||
                !add_product(sum, decode(term.weight), decode(support_value))) return false;
        }
        Integer expected;
        if (!add_dyadic(expected, decode(target_value)) ||
            sum.negative != expected.negative || compare_magnitude(sum, expected) != 0) return false;
    }
    return true;
}

} // namespace csl::geometry::detail
