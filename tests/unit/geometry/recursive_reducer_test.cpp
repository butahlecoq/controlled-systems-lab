#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include "../../../src/geometry/exact_convex_combination.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <numeric>
#include <sstream>
#include <mutex>
#include <thread>
#include <unordered_set>

using namespace csl;

namespace {

struct WorkspaceTracker {
    std::mutex mutex;
    std::unordered_set<std::size_t> active;
    std::size_t next_id{};
    std::size_t created{};
    std::size_t peak_active{};
    bool same_workspace_overlap{};
};

class TrackedLPWorkspace final : public LPWorkspace {
public:
    TrackedLPWorkspace(std::unique_ptr<LPWorkspace> inner,
            std::shared_ptr<WorkspaceTracker> tracker, std::size_t id)
        : inner_(std::move(inner)), tracker_(std::move(tracker)), id_(id) {}
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext& context) override {
        {
            std::lock_guard lock(tracker_->mutex);
            if (!tracker_->active.insert(id_).second) tracker_->same_workspace_overlap = true;
            tracker_->peak_active = std::max(tracker_->peak_active, tracker_->active.size());
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        auto result = inner_->solve(program, context);
        {
            std::lock_guard lock(tracker_->mutex);
            tracker_->active.erase(id_);
        }
        return result;
    }
private:
    std::unique_ptr<LPWorkspace> inner_;
    std::shared_ptr<WorkspaceTracker> tracker_;
    std::size_t id_;
};

registry::Registration<registry::LPPort> highs_provider() {
    auto result = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(result));
    return std::get<registry::Registration<registry::LPPort>>(std::move(result));
}

registry::Registration<registry::LPPort> tracked_highs_provider(
        const std::shared_ptr<WorkspaceTracker>& tracker) {
    auto underlying = highs_provider();
    auto factory = underlying.factory;
    return {{{"csl.test.tracked-highs"}, underlying.identity.version},
        underlying.capabilities,
        [factory = std::move(factory), tracker](const LinearProgram& request) {
            auto workspace = factory(request);
            std::size_t id;
            {
                std::lock_guard lock(tracker->mutex);
                id = tracker->next_id++;
                ++tracker->created;
            }
            return std::make_unique<TrackedLPWorkspace>(std::move(workspace), tracker, id);
        }, {}};
}

std::unique_ptr<LPWorkspace> highs_workspace(const registry::Registration<registry::LPPort>& provider) {
    auto seed = optimization::make_linear_program({{{"recursive-test"},{"seed"}}, {}, 0.0,
        {0, 0, {0}, {}, {}}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return provider.factory(std::get<LinearProgram>(seed));
}

bool independent_membership(LPWorkspace& lp, const geometry::PointCloud& cloud,
        const std::vector<std::size_t>& support, std::size_t candidate) {
    static std::atomic<std::size_t> query_serial{};
    if (std::any_of(support.begin(), support.end(), [&](std::size_t point) {
            return cloud.points[point] == cloud.points[candidate];
        })) return true;
    const auto dimension = cloud.points[candidate].size();
    SparseMatrix matrix{dimension + 1, support.size(), {0}, {}, {}};
    for (std::size_t row = 0; row <= dimension; ++row) {
        for (std::size_t column = 0; column < support.size(); ++column) {
            matrix.column_indices.push_back(column);
            matrix.values.push_back(row == dimension ? 1.0 : cloud.points[support[column]][row]);
        }
        matrix.row_offsets.push_back(matrix.values.size());
    }
    Vector rhs = cloud.points[candidate];
    rhs.push_back(1.0);
    std::vector<Interval> rows;
    for (double value : rhs) rows.push_back({value, value});
    auto result = optimization::make_linear_program({
        {cloud.problem, {"recursive-test-independent-" + std::to_string(candidate) + "-" +
            std::to_string(query_serial.fetch_add(1))}},
        Vector(support.size(), 0.0), 0.0, std::move(matrix),
        std::vector<Interval>(support.size(), {0.0, std::nullopt}), std::move(rows)});
    if (!std::holds_alternative<LinearProgram>(result)) return false;
    auto outcome = lp.solve(std::get<LinearProgram>(result), {});
    if (!std::holds_alternative<ProgramResult>(outcome)) return false;
    const auto& solved = std::get<ProgramResult>(outcome);
    if (solved.termination != Termination::completed || solved.outcome.value != MathematicalOutcome::optimal ||
        !solved.primal || solved.primal->size() != support.size()) return false;
    double weight_sum = 0.0;
    Vector reconstructed(dimension, 0.0);
    for (std::size_t i = 0; i < support.size(); ++i) {
        if ((*solved.primal)[i] < 0.0) return false;
        weight_sum += (*solved.primal)[i];
        for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate)
            reconstructed[coordinate] += (*solved.primal)[i] * cloud.points[support[i]][coordinate];
    }
    if (std::abs(weight_sum - 1.0) > 1e-8) return false;
    for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate)
        if (std::abs(reconstructed[coordinate] - cloud.points[candidate][coordinate]) > 1e-8) return false;
    return true;
}

geometry::PointCloud fixture(std::string name, int kind) {
    geometry::PointCloud cloud{{std::move(name)}, {}};
    for (int i = -12; i <= 12; ++i) {
        if (kind == 0) {
            cloud.points.push_back({static_cast<double>(i), static_cast<double>((i * 7) % 11)});
            cloud.points.push_back({static_cast<double>(i), static_cast<double>((i * 7) % 11)});
        } else if (kind == 1) {
            cloud.points.push_back({static_cast<double>(i), static_cast<double>(2 * i - 3)});
        } else {
            cloud.points.push_back({static_cast<double>(i), static_cast<double>((i * i) % 17 - 8)});
        }
    }
    if (kind == 0) {
        cloud.points.insert(cloud.points.end(), {{-20.0, -20.0}, {-20.0, 20.0}, {20.0, -20.0}, {20.0, 20.0}});
    }
    return cloud;
}

std::vector<std::size_t> permuted_ids(std::size_t count, int permutation) {
    std::vector<std::size_t> ids(count);
    std::iota(ids.begin(), ids.end(), std::size_t{0});
    if (permutation == 1) std::reverse(ids.begin(), ids.end());
    if (permutation == 2) std::rotate(ids.begin(), ids.begin() + static_cast<std::ptrdiff_t>(count / 3), ids.end());
    return ids;
}

geometry::HullReduction run_recursive(const geometry::PointCloud& cloud,
        const registry::Registration<registry::LPPort>& provider, ExecutionContext context,
        LPWorkspace& injected_lp) {
    registry::Registry<registry::HullReducerPort> reducers;
    REQUIRE_FALSE(reducers.add(geometry::make_recursive_hull_reducer_registration(provider)));
    auto prepared = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.recursive-split-merge"}, "1.0.0"}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(prepared));
    auto workspaces = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(prepared)).create();
    auto result = std::get<0>(workspaces)->run_with(context, injected_lp);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&result)) {
        for (const auto& diagnostic : *diagnostics)
            INFO(diagnostic.field << ": " << diagnostic.explanation);
    }
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    return std::get<geometry::HullReduction>(std::move(result));
}

void check_hull_equivalent(const geometry::PointCloud& cloud,
        const geometry::HullReduction& a, const geometry::HullReduction& b,
        LPWorkspace& oracle) {
    auto support_description = [&](const std::vector<std::size_t>& ids) {
        std::ostringstream out;
        for (const auto id : ids) {
            out << id << ':';
            for (const auto coordinate : cloud.points[id]) out << coordinate << ',';
            out << ' ';
        }
        return out.str();
    };
    for (const auto point : a.retained)
        CHECK_MESSAGE(independent_membership(oracle, cloud, b.retained, point),
            cloud.problem.value << " baseline point " << point << " absent from recursive hull; recursive=" <<
                support_description(b.retained));
    for (const auto point : b.retained)
        CHECK_MESSAGE(independent_membership(oracle, cloud, a.retained, point),
            cloud.problem.value << " recursive point " << point << " absent from baseline hull; baseline=" <<
                support_description(a.retained));
    for (const auto& certificate : a.removed) {
        CHECK(geometry::detail::exact_convex_combination(cloud, certificate.removed, certificate.combination));
        CHECK(independent_membership(oracle, cloud, b.retained, certificate.removed));
    }
    for (const auto& certificate : b.removed) {
        CHECK(geometry::detail::exact_convex_combination(cloud, certificate.removed, certificate.combination));
        CHECK(independent_membership(oracle, cloud, a.retained, certificate.removed));
    }
}

TEST_CASE("recursive split-and-merge preserves certified hulls across signed, duplicate and degenerate inputs") {
    const auto provider = highs_provider();
    for (int kind = 0; kind < 3; ++kind) {
        for (int permutation = 0; permutation < 3; ++permutation) {
            auto cloud = fixture("recursive-fixture-" + std::to_string(kind) + "-" +
                std::to_string(permutation), kind);
            const auto ids = permuted_ids(cloud.points.size(), permutation);
            geometry::PointCloud permuted{cloud.problem, {}};
            for (const auto id : ids) permuted.points.push_back(cloud.points[id]);

            auto baseline_lp = highs_workspace(provider);
            auto baseline_result = geometry::reduce_hull(permuted, *baseline_lp, {});
            REQUIRE(std::holds_alternative<geometry::HullReduction>(baseline_result));
            const auto baseline = std::get<geometry::HullReduction>(std::move(baseline_result));

            auto recursive_lp = highs_workspace(provider);
            ExecutionContext sequential;
            sequential.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
            const auto recursive = run_recursive(permuted, provider, sequential, *recursive_lp);
            REQUIRE(recursive.recursive.has_value());
            CHECK(recursive.recursive->leaf_nodes > 1);
            CHECK(recursive.recursive->merge_nodes > 0);
            CHECK(recursive.recursive->leaf_lp_calls + recursive.recursive->merge_lp_calls == recursive.lp_calls);

            auto oracle = highs_workspace(provider);
            check_hull_equivalent(permuted, baseline, recursive, *oracle);
        }
    }
}

TEST_CASE("recursive root uses two isolated subtrees under the common resource policy") {
    const auto tracker = std::make_shared<WorkspaceTracker>();
    const auto provider = tracked_highs_provider(tracker);
    auto cloud = fixture("recursive-parallel", 2);
    auto serial_lp = highs_workspace(provider);
    ExecutionContext serial_context;
    serial_context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    const auto serial = run_recursive(cloud, provider, serial_context, *serial_lp);

    auto parallel_lp = highs_workspace(provider);
    ExecutionContext parallel_context;
    parallel_context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{2, 2, 1, {}});
    const auto parallel = run_recursive(cloud, provider, parallel_context, *parallel_lp);
    REQUIRE(serial.recursive.has_value());
    REQUIRE(parallel.recursive.has_value());
    CHECK(serial.recursive->concurrent_child_subtrees == 0);
    CHECK(parallel.recursive->concurrent_child_subtrees == 2);
    CHECK(parallel.recursive->peak_merge_points > 0);
    CHECK(tracker->created >= 4);
    CHECK(tracker->peak_active >= 2);
    CHECK_FALSE(tracker->same_workspace_overlap);
    auto oracle = highs_workspace(provider);
    check_hull_equivalent(cloud, serial, parallel, *oracle);
}

} // namespace
