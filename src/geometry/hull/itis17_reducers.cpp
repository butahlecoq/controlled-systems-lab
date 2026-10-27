#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include "reducer_internal.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <string>

namespace csl::geometry {
namespace {

class A43Workspace final : public HullReducerWorkspace {
public:
    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        auto basis_result = reduce_hull_basis_reuse(cloud, lp, context);
        if (!std::holds_alternative<HullReduction>(basis_result)) return basis_result;
        auto basis_reduction = std::get<HullReduction>(std::move(basis_result));

        auto final_result = detail::reduce_hull_in_order(cloud, lp, context,
            basis_reduction.retained, std::move(basis_reduction.removed),
            "itis17-a43-final-recheck");
        if (!std::holds_alternative<HullReduction>(final_result)) return final_result;

        auto reduction = std::get<HullReduction>(std::move(final_result));
        const auto final_recheck_calls = reduction.lp_calls;
        reduction.lp_calls += basis_reduction.lp_calls;
        reduction.attempts.insert(reduction.attempts.begin(),
            basis_reduction.attempts.begin(), basis_reduction.attempts.end());
        if (basis_reduction.status == ReductionStatus::incomplete)
            reduction.status = ReductionStatus::incomplete;
        reduction.basis_reuse = std::move(basis_reduction.basis_reuse);
        reduction.itis17_a43 = A43ReductionMetrics{final_recheck_calls, false};
        return reduction;
    }
};

class A44Workspace final : public HullReducerWorkspace {
public:
    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        std::vector<std::size_t> order(cloud.points.size());
        std::iota(order.begin(), order.end(), std::size_t{0});

        const auto dimension = cloud.points.empty() ? 0 : cloud.points.front().size();
        for (const auto& point : cloud.points) {
            if (point.size() != dimension || std::any_of(point.begin(), point.end(),
                    [](double value) { return !std::isfinite(value); }))
                return detail::reduce_hull_in_order(cloud, lp, context, order);
        }

        A44ReductionMetrics metrics;
        metrics.processing_order = order;
        if (dimension > 0 && !cloud.points.empty()) {
            std::vector<long double> low(dimension), high(dimension), center(dimension);
            for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
                const auto [minimum, maximum] = std::minmax_element(cloud.points.begin(),
                    cloud.points.end(), [coordinate](const Vector& left, const Vector& right) {
                        return left[coordinate] < right[coordinate];
                    });
                low[coordinate] = (*minimum)[coordinate];
                high[coordinate] = (*maximum)[coordinate];
                center[coordinate] = low[coordinate] + (high[coordinate] - low[coordinate]) / 2.0L;
                if (low[coordinate] == high[coordinate]) ++metrics.zero_width_coordinates;
            }

            std::vector<long double> score(cloud.points.size(), 0.0L);
            for (std::size_t point = 0; point < cloud.points.size(); ++point) {
                for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
                    const auto width = high[coordinate] - low[coordinate];
                    if (width == 0.0L) continue;
                    const auto normalized =
                        (static_cast<long double>(cloud.points[point][coordinate]) - center[coordinate]) /
                        width;
                    if (!std::isfinite(normalized)) {
                        metrics.used_identity_fallback = true;
                        break;
                    }
                    score[point] += normalized * normalized;
                }
                if (metrics.used_identity_fallback) break;
            }
            if (!metrics.used_identity_fallback) {
                std::stable_sort(order.begin(), order.end(), [&](std::size_t left, std::size_t right) {
                    if (score[left] != score[right]) return score[left] > score[right];
                    return left < right;
                });
                metrics.processing_order = order;
            }
        }

        // The paper seeds X_pr with the first k+1 points, described as the
        // points farthest from the box center, then classifies the remainder.
        // Its earlier "increasing distance" sentence conflicts with that
        // description; this implementation records the farthest-first reading.
        const auto seed_count = std::min(order.size(), dimension + 1);
        std::vector<std::size_t> retained(order.begin(),
            order.begin() + static_cast<std::ptrdiff_t>(seed_count));
        std::vector<RemovalCertificate> removed;
        std::vector<MembershipAttempt> attempts;
        ReductionStatus stage_status = ReductionStatus::complete;
        std::size_t incremental_calls = 0;
        for (std::size_t position = seed_count; position < order.size(); ++position) {
            const auto candidate = order[position];
            auto classified = detail::classify_candidate(cloud, retained, candidate,
                lp, context, "itis17-a44-incremental");
            incremental_calls += classified.lp_calls;
            attempts.push_back(classified.attempt);
            if (classified.attempt.outcome == MembershipOutcome::feasible &&
                classified.certificate) {
                removed.push_back(std::move(*classified.certificate));
                continue;
            }
            retained.push_back(candidate);
            if (classified.attempt.outcome != MembershipOutcome::infeasible) {
                stage_status = ReductionStatus::incomplete;
                if (classified.attempt.outcome == MembershipOutcome::stopped) {
                    retained.insert(retained.end(), order.begin() +
                        static_cast<std::ptrdiff_t>(position + 1), order.end());
                    break;
                }
            }
        }

        auto final_result = detail::reduce_hull_in_order(cloud, lp, context, retained,
            std::move(removed), "itis17-a44-final-recheck");
        if (!std::holds_alternative<HullReduction>(final_result)) return final_result;
        auto reduction = std::get<HullReduction>(std::move(final_result));
        metrics.incremental_membership_calls = incremental_calls;
        metrics.seeded_candidates = seed_count;
        metrics.final_recheck_calls = reduction.lp_calls;
        reduction.lp_calls += incremental_calls;
        reduction.attempts.insert(reduction.attempts.begin(), attempts.begin(), attempts.end());
        if (stage_status == ReductionStatus::incomplete)
            reduction.status = ReductionStatus::incomplete;
        reduction.itis17_a44 = std::move(metrics);
        return reduction;
    }
};

} // namespace

HullReductionResult reduce_itis17_a43_hull(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context) {
    A43Workspace workspace;
    return workspace.reduce(cloud, lp, context);
}

HullReductionResult reduce_itis17_a44_hull(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context) {
    A44Workspace workspace;
    return workspace.reduce(cloud, lp, context);
}

registry::Registration<registry::HullReducerPort> make_itis17_a43_hull_reducer_registration() {
    return {{{"csl.hull.itis17.a43-certified-basis-reuse"}, "1.0.0"},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [](const PointCloud&) { return std::make_unique<A43Workspace>(); }};
}

registry::Registration<registry::HullReducerPort> make_itis17_a44_hull_reducer_registration() {
    return {{{"csl.hull.itis17.a44-incremental-lp"}, "2.0.0"},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [](const PointCloud&) { return std::make_unique<A44Workspace>(); }};
}

} // namespace csl::geometry
