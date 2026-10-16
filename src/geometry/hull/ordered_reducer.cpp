#include <csl/geometry/hull_reducer.hpp>
#include "reducer_internal.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace csl::geometry {
namespace {

class OrderedHullReducerWorkspace final : public HullReducerWorkspace {
public:
    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        return reduce_ordered_hull(cloud, lp, context);
    }
};

} // namespace

HullReductionResult reduce_ordered_hull(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context) {
    std::vector<std::size_t> order(cloud.points.size());
    std::iota(order.begin(), order.end(), std::size_t{0});

    // Let the shared reducer return its established diagnostics for malformed
    // input; no comparator may see mismatched dimensions or nonfinite values.
    const auto dimension = cloud.points.empty() ? 0 : cloud.points.front().size();
    for (const auto& point : cloud.points)
        if (point.size() != dimension ||
            std::any_of(point.begin(), point.end(), [](double x) { return !std::isfinite(x); }))
            return detail::reduce_hull_in_order(cloud, lp, context, order);

    OrderedReductionMetrics metrics;
    metrics.ordered_candidates = cloud.points.size();
    if (!cloud.points.empty() && dimension != 0) {
        std::vector<double> ranges(dimension, 0.0);
        std::vector<double> midpoints(dimension, 0.0);
        for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
            auto [minimum, maximum] = std::minmax_element(cloud.points.begin(), cloud.points.end(),
                [coordinate](const Vector& left, const Vector& right) {
                    return left[coordinate] < right[coordinate];
                });
            const double low = (*minimum)[coordinate];
            const double high = (*maximum)[coordinate];
            if (low == high) {
                ++metrics.zero_width_coordinates;
                continue;
            }
            ranges[coordinate] = high - low;
            if (!std::isfinite(ranges[coordinate]) || ranges[coordinate] <= 0.0) {
                metrics.used_identity_fallback = true;
                continue;
            }
            midpoints[coordinate] = std::midpoint(low, high);
        }
        if (!metrics.used_identity_fallback) {
            std::vector<double> score(cloud.points.size(), -std::numeric_limits<double>::infinity());
            for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
                if (ranges[coordinate] == 0.0) continue;
                for (std::size_t point = 0; point < cloud.points.size(); ++point) {
                    const double normalized =
                        (cloud.points[point][coordinate] - midpoints[coordinate]) / ranges[coordinate];
                    if (!std::isfinite(normalized)) {
                        metrics.used_identity_fallback = true;
                        break;
                    }
                    score[point] = std::max(score[point], normalized);
                }
                if (metrics.used_identity_fallback) break;
            }
            if (!metrics.used_identity_fallback) {
                for (auto& value : score)
                    value = std::isinf(value) ? 0.0 : std::abs(value);
                std::stable_sort(order.begin(), order.end(), [&](std::size_t left, std::size_t right) {
                    return score[left] > score[right];
                });
            }
        }
    }
    metrics.processing_order = order;
    auto reduced = detail::reduce_hull_in_order(cloud, lp, context, order);
    if (auto* result = std::get_if<HullReduction>(&reduced))
        result->ordered = std::move(metrics);
    return reduced;
}

registry::Registration<registry::HullReducerPort> make_ordered_hull_reducer_registration() {
    return {{{"csl.hull.ordered-membership"}, "1.0.0"},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [](const PointCloud&) { return std::make_unique<OrderedHullReducerWorkspace>(); }};
}

} // namespace csl::geometry
