#include <csl/geometry/hull_reducer.hpp>
#include "reducer_internal.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace csl::geometry {
namespace {

constexpr double grouping_radius = 0.05;

class GroupedHullReducerWorkspace final : public HullReducerWorkspace {
public:
    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        return reduce_grouped_hull(cloud, lp, context);
    }
};

GroupedReductionMetrics group_candidates(const PointCloud& cloud) {
    GroupedReductionMetrics metrics;
    const auto count = cloud.points.size();
    metrics.ordered_candidates = count;
    std::vector<std::size_t> ordered(count);
    std::iota(ordered.begin(), ordered.end(), std::size_t{0});
    const auto dimension = count == 0 ? 0 : cloud.points.front().size();
    for (const auto& point : cloud.points)
        if (point.size() != dimension ||
            std::any_of(point.begin(), point.end(), [](double x) { return !std::isfinite(x); })) {
            metrics.processing_order = std::move(ordered);
            metrics.used_identity_fallback = true;
            return metrics;
        }

    if (count == 0 || dimension == 0) {
        metrics.processing_order = std::move(ordered);
        return metrics;
    }

    std::vector<double> low(dimension), high(dimension), width(dimension), midpoint(dimension);
    for (std::size_t axis = 0; axis < dimension; ++axis) {
        auto bounds = std::minmax_element(cloud.points.begin(), cloud.points.end(),
            [axis](const Vector& a, const Vector& b) { return a[axis] < b[axis]; });
        low[axis] = (*bounds.first)[axis];
        high[axis] = (*bounds.second)[axis];
        width[axis] = high[axis] - low[axis];
        if (width[axis] == 0.0) ++metrics.zero_width_coordinates;
        else if (!std::isfinite(width[axis]) || width[axis] < 0.0) metrics.used_identity_fallback = true;
        midpoint[axis] = std::midpoint(low[axis], high[axis]);
    }
    std::vector<double> scores(count, -std::numeric_limits<double>::infinity());
    if (!metrics.used_identity_fallback) {
        for (std::size_t axis = 0; axis < dimension; ++axis) {
            if (width[axis] == 0.0) continue;
            for (std::size_t i = 0; i < count; ++i) {
                const auto value = (cloud.points[i][axis] - midpoint[axis]) / width[axis];
                if (!std::isfinite(value)) { metrics.used_identity_fallback = true; break; }
                scores[i] = std::max(scores[i], std::abs(value));
            }
            if (metrics.used_identity_fallback) break;
        }
    }
    if (!metrics.used_identity_fallback) {
        std::stable_sort(ordered.begin(), ordered.end(), [&](std::size_t a, std::size_t b) {
            return scores[a] > scores[b];
        });
    }
    if (metrics.used_identity_fallback) {
        metrics.processing_order = std::move(ordered);
        metrics.groups = count;
        return metrics;
    }

    // Each first unassigned point is a fixed group center. Candidates within
    // 5% of the bounding-box width on every varying coordinate join that
    // center's group. Zero-width coordinates carry no distance information.
    std::vector<bool> assigned(count, false);
    std::vector<std::size_t> grouped;
    grouped.reserve(count);
    for (std::size_t position = 0; position < count; ++position) {
        const auto center = ordered[position];
        if (assigned[center]) continue;
        assigned[center] = true;
        std::vector<std::size_t> nearby;
        for (std::size_t next = position + 1; next < count; ++next) {
            const auto candidate = ordered[next];
            if (assigned[candidate]) continue;
            bool close = true;
            for (std::size_t axis = 0; axis < dimension; ++axis) {
                if (width[axis] == 0.0) continue;
                const double delta = std::abs(cloud.points[candidate][axis] - cloud.points[center][axis]) / width[axis];
                if (!std::isfinite(delta) || delta > grouping_radius) { close = false; break; }
            }
            if (close) {
                assigned[candidate] = true;
                nearby.push_back(candidate);
            }
        }
        ++metrics.groups;
        metrics.grouped_candidates += nearby.size();
        grouped.push_back(center);
        grouped.insert(grouped.end(), nearby.begin(), nearby.end());
    }
    metrics.processing_order = std::move(grouped);
    return metrics;
}

} // namespace

HullReductionResult reduce_grouped_hull(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context) {
    auto metrics = group_candidates(cloud);
    auto result = detail::reduce_hull_in_order(cloud, lp, context, metrics.processing_order);
    if (auto* reduction = std::get_if<HullReduction>(&result))
        reduction->grouped = std::move(metrics);
    return result;
}

registry::Registration<registry::HullReducerPort> make_grouped_hull_reducer_registration() {
    return {{{"csl.hull.grouped-membership"}, "1.0.0"},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [](const PointCloud&) { return std::make_unique<GroupedHullReducerWorkspace>(); }};
}

} // namespace csl::geometry
