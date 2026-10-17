#include <csl/geometry/hull_reducer.hpp>
#include "reducer_internal.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace csl::geometry {
namespace {

constexpr std::size_t consecutive_redundant_trigger = 10;
constexpr double group_radius_factor = 0.05;

class GroupedHullReducerWorkspace final : public HullReducerWorkspace {
public:
    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        return reduce_grouped_hull(cloud, lp, context);
    }
};

GroupedReductionMetrics ordered_candidates(const PointCloud& cloud,
        std::vector<double>& widths) {
    GroupedReductionMetrics metrics;
    const auto count = cloud.points.size();
    metrics.ordered_candidates = count;
    auto& order = metrics.processing_order;
    order.resize(count);
    std::iota(order.begin(), order.end(), std::size_t{0});
    const auto dimension = count == 0 ? 0 : cloud.points.front().size();
    if (count < 2 || dimension == 0) {
        metrics.used_identity_fallback = count > 0 && dimension == 0;
        return metrics;
    }
    for (const auto& point : cloud.points)
        if (point.size() != dimension ||
            std::any_of(point.begin(), point.end(), [](double x) { return !std::isfinite(x); })) {
            metrics.used_identity_fallback = true;
            return metrics;
        }

    std::vector<double> midpoints(dimension, 0.0);
    widths.assign(dimension, 0.0);
    for (std::size_t axis = 0; axis < dimension; ++axis) {
        const auto bounds = std::minmax_element(cloud.points.begin(), cloud.points.end(),
            [axis](const Vector& a, const Vector& b) { return a[axis] < b[axis]; });
        const double low = (*bounds.first)[axis];
        const double high = (*bounds.second)[axis];
        widths[axis] = high - low;
        if (widths[axis] == 0.0) {
            ++metrics.zero_width_coordinates;
            metrics.used_identity_fallback = true;
        } else if (!std::isfinite(widths[axis]) || widths[axis] < 0.0) {
            metrics.used_identity_fallback = true;
        }
        midpoints[axis] = std::midpoint(low, high);
    }
    if (metrics.used_identity_fallback) return metrics;

    std::vector<double> scores(count, -std::numeric_limits<double>::infinity());
    for (std::size_t axis = 0; axis < dimension; ++axis) {
        for (std::size_t point = 0; point < count; ++point) {
            const double normalized =
                (cloud.points[point][axis] - midpoints[axis]) / widths[axis];
            if (!std::isfinite(normalized)) {
                metrics.used_identity_fallback = true;
                return metrics;
            }
            scores[point] = std::max(scores[point], std::abs(normalized));
        }
    }
    std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
        return scores[a] > scores[b];
    });
    return metrics;
}

bool close_to_group(const PointCloud& cloud, std::size_t left, std::size_t right,
        const std::vector<double>& widths, double radius) {
    double distance = 0.0;
    for (std::size_t axis = 0; axis < widths.size(); ++axis)
        distance = std::hypot(distance, cloud.points[left][axis] - cloud.points[right][axis]);
    return std::isfinite(distance) && distance <= radius;
}

bool stop_outcome(MembershipOutcome outcome) {
    return outcome == MembershipOutcome::unsupported || outcome == MembershipOutcome::stopped;
}

} // namespace

HullReductionResult reduce_grouped_hull(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context) {
    std::vector<double> widths;
    auto metrics = ordered_candidates(cloud, widths);
    const auto& order = metrics.processing_order;
    // Reuse the shared input/context validator without issuing an LP query.
    auto validation = detail::reduce_hull_in_order(cloud, lp, context, {});
    if (std::holds_alternative<Diagnostics>(validation)) return validation;
    if (order.size() < 2) {
        auto result = detail::reduce_hull_in_order(cloud, lp, context, order);
        if (auto* reduction = std::get_if<HullReduction>(&result)) reduction->grouped = std::move(metrics);
        return result;
    }

    const bool grouping_supported = !metrics.used_identity_fallback &&
        !widths.empty() && *std::min_element(widths.begin(), widths.end()) > 0.0;
    std::vector<std::size_t> retained{order[0], order[1]};
    std::vector<RemovalCertificate> prior_certificates;
    std::vector<MembershipAttempt> stage_attempts;
    std::size_t stage_lp_calls = 0;
    std::size_t position = 2;
    std::size_t redundant_streak = 0;

    for (; position < order.size(); ++position) {
        const auto candidate = order[position];
        auto classified = detail::classify_candidate(cloud, retained, candidate, lp, context);
        ++metrics.streamed_candidates;
        stage_lp_calls += classified.lp_calls;
        stage_attempts.push_back(classified.attempt);
        if (classified.certificate) {
            prior_certificates.push_back(std::move(*classified.certificate));
            ++metrics.certified_stream_removals;
            ++redundant_streak;
        } else {
            retained.push_back(candidate);
            redundant_streak = 0;
        }
        if (stop_outcome(classified.attempt.outcome)) {
            ++position;
            break;
        }
        if (grouping_supported && redundant_streak >= consecutive_redundant_trigger) {
            metrics.grouping_triggered = true;
            // The source includes its tenth redundant point in the grouped remainder.
            if (!prior_certificates.empty() && prior_certificates.back().removed == candidate)
                prior_certificates.pop_back();
            break;
        }
    }

    if (metrics.grouping_triggered) {
        ++metrics.grouping_passes;
        const auto fixed = retained;
        std::vector<std::size_t> outside_group;
        std::vector<std::size_t> nearby;
        const double radius = group_radius_factor * *std::min_element(widths.begin(), widths.end());
        for (; position < order.size(); ++position) {
            const auto candidate = order[position];
            for (const auto previous : outside_group) {
                if (close_to_group(cloud, candidate, previous, widths, radius) &&
                    std::find(nearby.begin(), nearby.end(), previous) == nearby.end()) {
                    nearby.push_back(previous);
                    ++metrics.nearby_supports;
                }
            }
            std::vector<std::size_t> support = fixed;
            support.insert(support.end(), nearby.begin(), nearby.end());
            auto classified = detail::classify_candidate(cloud, support, candidate, lp, context);
            ++metrics.grouped_candidates;
            stage_lp_calls += classified.lp_calls;
            stage_attempts.push_back(classified.attempt);
            if (classified.certificate) prior_certificates.push_back(std::move(*classified.certificate));
            else outside_group.push_back(candidate);
            if (stop_outcome(classified.attempt.outcome)) {
                ++position;
                break;
            }
        }
        if (position < order.size())
            outside_group.insert(outside_group.end(), order.begin() + static_cast<std::ptrdiff_t>(position), order.end());
        retained = fixed;
        retained.insert(retained.end(), outside_group.begin(), outside_group.end());
    } else if (position < order.size()) {
        // A stopped stream leaves the unclassified suffix untouched for the
        // final shared pass; no candidate is discarded on an uncertain result.
        retained.insert(retained.end(), order.begin() + static_cast<std::ptrdiff_t>(position), order.end());
    }

    auto result = detail::reduce_hull_in_order(cloud, lp, context, retained,
        std::move(prior_certificates));
    if (auto* reduction = std::get_if<HullReduction>(&result)) {
        stage_lp_calls += reduction->lp_calls;
        stage_attempts.insert(stage_attempts.end(), reduction->attempts.begin(), reduction->attempts.end());
        reduction->lp_calls = stage_lp_calls;
        reduction->attempts = std::move(stage_attempts);
        reduction->grouped = std::move(metrics);
    }
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
