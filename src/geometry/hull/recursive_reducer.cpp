#include <csl/geometry/hull_reducer.hpp>
#include "../hull/reducer_internal.hpp"

#include <algorithm>
#include <chrono>
#include <future>
#include <numeric>
#include <string>

namespace csl::geometry {
namespace {

constexpr std::size_t leaf_limit = 16;

Diagnostics invalid(std::string field, std::string explanation) {
    return {{DiagnosticCode::invalid_input, std::move(field), std::move(explanation)}};
}

bool point_less(const PointCloud& cloud, std::size_t left, std::size_t right) {
    const auto& a = cloud.points[left];
    const auto& b = cloud.points[right];
    if (std::lexicographical_compare(a.begin(), a.end(), b.begin(), b.end())) return true;
    if (std::lexicographical_compare(b.begin(), b.end(), a.begin(), a.end())) return false;
    return left < right;
}

using ChildWorkspace = registry::BoundWorkspace<registry::LPPort>;

std::variant<registry::PreparedPipeline<registry::LPPort>, Diagnostics> prepare_lp_provider(
        const registry::Registration<registry::LPPort>& provider, const PointCloud& cloud) {
    auto seed_result = optimization::make_linear_program({
        {cloud.problem, {"recursive-hull-workspace-seed"}}, {}, 0.0,
        {0, 0, {0}, {}, {}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed_result))
        return invalid("recursive.lp_provider", "Could not create the LP workspace seed request");

    registry::Registry<registry::LPPort> providers;
    if (auto rejection = providers.add(provider)) return rejection->diagnostics;
    registry::Requirements requirements;
    requirements.output = {{{"csl.program-result.v1"}}, Assurance::numerical, {}, {}, {}};
    auto prepared = registry::prepare_pipeline(registry::select(providers,
        registry::Method{provider.identity.id, provider.identity.version},
        std::get<LinearProgram>(seed_result), requirements));
    if (auto* rejection = std::get_if<registry::Rejection>(&prepared)) return rejection->diagnostics;
    return std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(prepared));
}

struct NodeStats {
    RecursiveReductionMetrics metrics;
};

struct NodeResult {
    HullReduction reduction;
    NodeStats stats;
};

using NodeOutcome = std::variant<NodeResult, Diagnostics>;

NodeOutcome merge_nodes(const PointCloud& cloud, NodeResult left, NodeResult right,
        LPWorkspace& lp, const ExecutionContext& context, const std::string& path) {
    std::vector<std::size_t> merge_ids = left.reduction.retained;
    merge_ids.insert(merge_ids.end(), right.reduction.retained.begin(), right.reduction.retained.end());
    std::sort(merge_ids.begin(), merge_ids.end(), [&](std::size_t a, std::size_t b) {
        return point_less(cloud, a, b);
    });

    std::vector<RemovalCertificate> certificates = std::move(left.reduction.removed);
    certificates.insert(certificates.end(),
        std::make_move_iterator(right.reduction.removed.begin()),
        std::make_move_iterator(right.reduction.removed.end()));
    auto merged_result = detail::reduce_hull_in_order(cloud, lp, context, merge_ids,
        std::move(certificates), path);
    if (auto* diagnostics = std::get_if<Diagnostics>(&merged_result)) return *diagnostics;
    auto merged = std::get<HullReduction>(std::move(merged_result));
    merged.attempts.insert(merged.attempts.begin(),
        left.reduction.attempts.begin(), left.reduction.attempts.end());
    merged.attempts.insert(merged.attempts.begin() + static_cast<std::ptrdiff_t>(left.reduction.attempts.size()),
        right.reduction.attempts.begin(), right.reduction.attempts.end());
    merged.lp_calls += left.reduction.lp_calls + right.reduction.lp_calls;
    if (left.reduction.status == ReductionStatus::incomplete ||
        right.reduction.status == ReductionStatus::incomplete)
        merged.status = ReductionStatus::incomplete;

    NodeStats stats;
    stats.metrics.leaf_nodes = left.stats.metrics.leaf_nodes + right.stats.metrics.leaf_nodes;
    stats.metrics.merge_nodes = left.stats.metrics.merge_nodes + right.stats.metrics.merge_nodes + 1;
    stats.metrics.leaf_lp_calls = left.stats.metrics.leaf_lp_calls + right.stats.metrics.leaf_lp_calls;
    stats.metrics.merge_lp_calls = left.stats.metrics.merge_lp_calls + right.stats.metrics.merge_lp_calls +
        (merged.lp_calls - left.reduction.lp_calls - right.reduction.lp_calls);
    stats.metrics.peak_merge_points = std::max({left.stats.metrics.peak_merge_points,
        right.stats.metrics.peak_merge_points, merge_ids.size()});
    return NodeResult{std::move(merged), std::move(stats)};
}

NodeOutcome reduce_node(const PointCloud& cloud, std::vector<std::size_t> ids,
        LPWorkspace& lp, const ExecutionContext& context, std::string path) {
    if (ids.size() <= leaf_limit) {
        auto result = detail::reduce_hull_in_order(cloud, lp, context, ids, {}, path);
        if (auto* diagnostics = std::get_if<Diagnostics>(&result)) return *diagnostics;
        auto reduction = std::get<HullReduction>(std::move(result));
        NodeStats stats;
        stats.metrics.leaf_nodes = 1;
        stats.metrics.leaf_lp_calls = reduction.lp_calls;
        return NodeResult{std::move(reduction), std::move(stats)};
    }

    std::sort(ids.begin(), ids.end(), [&](std::size_t a, std::size_t b) {
        return point_less(cloud, a, b);
    });
    const auto middle = ids.size() / 2;
    std::vector<std::size_t> left_ids(ids.begin(), ids.begin() + static_cast<std::ptrdiff_t>(middle));
    std::vector<std::size_t> right_ids(ids.begin() + static_cast<std::ptrdiff_t>(middle), ids.end());

    // A subtree is sequential internally. Only the caller may run the root's
    // left and right subtrees concurrently, bounding active workers at two.
    auto left_outcome = reduce_node(cloud, std::move(left_ids), lp, context, path + "0");
    if (auto* diagnostics = std::get_if<Diagnostics>(&left_outcome)) return *diagnostics;
    auto right_outcome = reduce_node(cloud, std::move(right_ids), lp, context, path + "1");
    if (auto* diagnostics = std::get_if<Diagnostics>(&right_outcome)) return *diagnostics;

    auto left = std::get<NodeResult>(std::move(left_outcome));
    auto right = std::get<NodeResult>(std::move(right_outcome));
    return merge_nodes(cloud, std::move(left), std::move(right), lp, context, path + "m");
}

class RecursiveHullReducerWorkspace final : public HullReducerWorkspace {
public:
    explicit RecursiveHullReducerWorkspace(registry::Registration<registry::LPPort> provider)
        : provider_(std::move(provider)) {}

    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& supplied_lp,
            const ExecutionContext& context) override {
        static_cast<void>(supplied_lp);
        if (cloud.problem.value.empty()) return invalid("point_cloud.problem", "Problem identity is required");
        if (!std::isfinite(context.numerical.absolute_tolerance) || context.numerical.absolute_tolerance < 0.0 ||
            !std::isfinite(context.numerical.relative_tolerance) || context.numerical.relative_tolerance < 0.0 ||
            !std::isfinite(context.numerical.absolute_tolerance + context.numerical.relative_tolerance))
            return invalid("numerical", "Finite nonnegative tolerances are required");
        if (context.resources) {
            auto resource_diagnostics = check_resources(*context.resources);
            if (!resource_diagnostics.empty()) return resource_diagnostics;
        }
        if (!cloud.points.empty()) {
            const auto dimension = cloud.points.front().size();
            for (const auto& point : cloud.points) {
                if (point.size() != dimension) return invalid("point_cloud.points", "All points must have equal dimension");
                if (std::any_of(point.begin(), point.end(), [](double value) { return !std::isfinite(value); }))
                    return invalid("point_cloud.points", "Coordinates must be finite");
            }
        }

        std::vector<std::size_t> ids(cloud.points.size());
        std::iota(ids.begin(), ids.end(), std::size_t{0});
        auto prepared_result = prepare_lp_provider(provider_, cloud);
        if (auto* diagnostics = std::get_if<Diagnostics>(&prepared_result)) return *diagnostics;
        auto prepared = std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(prepared_result));
        auto create_child = [&]() -> std::unique_ptr<ChildWorkspace> {
            auto workspaces = prepared.create();
            return std::move(std::get<0>(workspaces));
        };

        auto first = create_child();
        if (ids.size() <= leaf_limit) {
            registry::LPWorkspaceView lp(*first);
            auto result = reduce_node(cloud, std::move(ids), lp, context, "r");
            if (auto* diagnostics = std::get_if<Diagnostics>(&result)) return *diagnostics;
            auto node = std::get<NodeResult>(std::move(result));
            node.reduction.recursive = node.stats.metrics;
            return node.reduction;
        }

        auto second = create_child();
        registry::LPWorkspaceView first_lp(*first);
        registry::LPWorkspaceView second_lp(*second);
        const bool parallel = context.resources && context.resources->outer_workers >= 2 &&
            context.resources->threads_per_worker > 0 &&
            context.resources->total_threads / context.resources->threads_per_worker >= 2;
        NodeOutcome left_outcome = Diagnostics{};
        NodeOutcome right_outcome = Diagnostics{};
        std::chrono::steady_clock::duration left_time{};
        std::chrono::steady_clock::duration right_time{};
        auto split_ids = ids;
        std::sort(split_ids.begin(), split_ids.end(), [&](std::size_t a, std::size_t b) {
            return point_less(cloud, a, b);
        });
        const auto middle = split_ids.size() / 2;
        std::vector<std::size_t> left_ids(split_ids.begin(), split_ids.begin() + static_cast<std::ptrdiff_t>(middle));
        std::vector<std::size_t> right_ids(split_ids.begin() + static_cast<std::ptrdiff_t>(middle), split_ids.end());
        const auto root_started = std::chrono::steady_clock::now();
        if (parallel) {
            auto left_future = std::async(std::launch::async, [&] {
                const auto started = std::chrono::steady_clock::now();
                auto outcome = reduce_node(cloud, std::move(left_ids), first_lp, context, "r0");
                return std::pair{std::move(outcome), std::chrono::steady_clock::now() - started};
            });
            auto right_future = std::async(std::launch::async, [&] {
                const auto started = std::chrono::steady_clock::now();
                auto outcome = reduce_node(cloud, std::move(right_ids), second_lp, context, "r1");
                return std::pair{std::move(outcome), std::chrono::steady_clock::now() - started};
            });
            auto left = left_future.get();
            auto right = right_future.get();
            left_outcome = std::move(left.first);
            left_time = left.second;
            right_outcome = std::move(right.first);
            right_time = right.second;
        } else {
            auto started = std::chrono::steady_clock::now();
            left_outcome = reduce_node(cloud, std::move(left_ids), first_lp, context, "r0");
            left_time = std::chrono::steady_clock::now() - started;
            started = std::chrono::steady_clock::now();
            right_outcome = reduce_node(cloud, std::move(right_ids), second_lp, context, "r1");
            right_time = std::chrono::steady_clock::now() - started;
        }
        if (auto* diagnostics = std::get_if<Diagnostics>(&left_outcome)) return *diagnostics;
        if (auto* diagnostics = std::get_if<Diagnostics>(&right_outcome)) return *diagnostics;
        auto left = std::get<NodeResult>(std::move(left_outcome));
        auto right = std::get<NodeResult>(std::move(right_outcome));
        auto merged_outcome = merge_nodes(cloud, std::move(left), std::move(right),
            first_lp, context, "rm");
        if (auto* diagnostics = std::get_if<Diagnostics>(&merged_outcome)) return *diagnostics;
        auto merged_node = std::get<NodeResult>(std::move(merged_outcome));
        auto& merged = merged_node.reduction;
        auto metrics = merged_node.stats.metrics;
        metrics.concurrent_child_subtrees = parallel ? 2 : 0;
        if (parallel) {
            const auto elapsed = std::chrono::steady_clock::now() - root_started;
            const auto longer_child = std::max(left_time, right_time);
            if (elapsed > longer_child)
                metrics.parallel_overhead_microseconds = static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::microseconds>(elapsed - longer_child).count());
        }
        merged.recursive = metrics;
        return merged;
    }

private:
    registry::Registration<registry::LPPort> provider_;
};

} // namespace

registry::Registration<registry::HullReducerPort> make_recursive_hull_reducer_registration(
        registry::Registration<registry::LPPort> lp_provider) {
    return {{{"csl.hull.recursive-split-merge"}, "1.0.0"},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [provider = std::move(lp_provider)](const PointCloud&) {
            return std::make_unique<RecursiveHullReducerWorkspace>(provider);
        }};
}

} // namespace csl::geometry
