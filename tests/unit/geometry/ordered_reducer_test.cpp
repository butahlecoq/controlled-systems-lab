#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include "../../../src/geometry/exact_convex_combination.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <memory>
#include <numeric>

using namespace csl;

namespace {
std::unique_ptr<LPWorkspace> highs_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"ordered-hull"},{"seed"}}, {}, 0,
        {0, 0, {0}, {}, {}}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

class StopWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        return ProgramResult{Termination::resource_limit,
            {program.identity(), MathematicalOutcome::undetermined, Unestablished{}, {}},
            {}, {}, "test stop", {}};
    }
};

class UnsupportedWorkspace final : public LPWorkspace {
public:
    std::size_t calls{};
protected:
    ProgramOutcome do_solve(const LinearProgram&, const ExecutionContext&) override {
        ++calls;
        return Unsupported{Diagnostics{}};
    }
};

geometry::HullReduction completed(const geometry::HullReductionResult& result) {
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.status == geometry::ReductionStatus::complete);
    return reduction;
}

double support(const geometry::PointCloud& cloud, const geometry::HullReduction& result,
        const Vector& direction) {
    double maximum = -INFINITY;
    for (const auto id : result.retained) {
        double value = 0.0;
        for (std::size_t coordinate = 0; coordinate < direction.size(); ++coordinate)
            value += direction[coordinate] * cloud.points[id][coordinate];
        maximum = std::max(maximum, value);
    }
    return maximum;
}

void check_exact_removals(const geometry::PointCloud& cloud, const geometry::HullReduction& result) {
    for (const auto& removed : result.removed) {
        CHECK(geometry::detail::exact_convex_combination(cloud, removed.removed, removed.combination));
        CHECK(removed.program.problem == cloud.problem);
        CHECK(removed.program.program.value == "hull-membership-" + std::to_string(removed.removed));
    }
    CHECK(result.retained.size() + result.removed.size() == cloud.points.size());
}
}

TEST_CASE("ordered adapter uses the active Scientific Research score, retaining original IDs") {
    // Bounding box [-1,1]^2: abs(max(x,y)) ranks point 5 ahead of point 4.
    // max(abs(x),abs(y)) would instead rank point 4 ahead of point 5.
    geometry::PointCloud cloud{{"signed-order"},
        {{-1.0, -1.0}, {1.0, 1.0}, {-1.0, 1.0}, {1.0, -1.0}, {-1.0, 0.25}, {0.75, -0.75}}};
    StopWorkspace lp;
    const auto result = geometry::reduce_ordered_hull(cloud, lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    REQUIRE(reduction.ordered.has_value());
    CHECK(reduction.ordered->processing_order == std::vector<std::size_t>{0, 1, 2, 3, 5, 4});
    CHECK(reduction.ordered->ordered_candidates == cloud.points.size());
    CHECK(reduction.ordered->zero_width_coordinates == 0);
    CHECK_FALSE(reduction.ordered->used_identity_fallback);
    CHECK(reduction.lp_calls == 1);
    REQUIRE(reduction.attempts.size() == 1);
    CHECK(reduction.attempts.front().candidate == 0);
}

TEST_CASE("grouped reducer stops after unsupported staging and preserves incomplete status") {
    geometry::PointCloud cloud{{"unsupported-grouped"}, {{0.0, 0.0}, {1.0, 0.0}, {0.5, 0.5}}};
    UnsupportedWorkspace lp;
    const auto result = geometry::reduce_grouped_hull(cloud, lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(lp.calls == 1);
    CHECK(reduction.lp_calls == 1);
    CHECK(reduction.retained.size() == cloud.points.size());
    REQUIRE(reduction.attempts.size() == 1);
    CHECK(reduction.attempts.front().outcome == geometry::MembershipOutcome::unsupported);
}

TEST_CASE("ordered and baseline reducers preserve literal support through permutations and degeneracies") {
    struct Fixture {
        std::vector<Vector> points;
        std::vector<Vector> directions;
        std::vector<double> expected;
    };
    const std::array fixtures{
        Fixture{{{-1.0}, {0.0}, {1.0}, {0.0}}, {{-1.0}, {1.0}}, {1.0, 1.0}},
        Fixture{{{-2.0, 3.0}, {2.0, 3.0}, {0.0, 3.0}, {-2.0, 3.0}},
            {{-1.0, 0.0}, {1.0, 0.0}, {0.0, -1.0}}, {2.0, 2.0, -3.0}},
        Fixture{{{0.0, 0.0}, {2.0, 0.0}, {0.0, 2.0}, {0.5, 0.5}},
            {{1.0, 0.0}, {0.0, 1.0}, {-1.0, -1.0}}, {2.0, 2.0, 0.0}},
        Fixture{{{-1.0, -1.0}, {1.0, -1.0}, {1.0, 1.0}, {-1.0, 1.0}},
            {{1.0, 0.0}, {0.0, -1.0}, {1.0, 1.0}}, {1.0, 1.0, 2.0}}
    };
    for (const auto& fixture : fixtures) {
        std::vector<std::size_t> permutation(fixture.points.size());
        std::iota(permutation.begin(), permutation.end(), 0);
        do {
            geometry::PointCloud cloud{{"permutation"}, {}};
            for (const auto id : permutation) cloud.points.push_back(fixture.points[id]);
            auto ordered_lp = highs_workspace();
            auto baseline_lp = highs_workspace();
            auto ordered = completed(geometry::reduce_ordered_hull(cloud, *ordered_lp, {}));
            auto baseline = completed(geometry::reduce_hull(cloud, *baseline_lp, {}));
            REQUIRE(ordered.ordered.has_value());
            CHECK_FALSE(baseline.ordered.has_value());
            CHECK(ordered.ordered->ordered_candidates == cloud.points.size());
            CHECK(ordered.lp_calls == ordered.attempts.size());
            check_exact_removals(cloud, ordered);
            check_exact_removals(cloud, baseline);
            for (std::size_t i = 0; i < fixture.directions.size(); ++i) {
                CHECK(support(cloud, ordered, fixture.directions[i]) == fixture.expected[i]);
                CHECK(support(cloud, ordered, fixture.directions[i]) ==
                    support(cloud, baseline, fixture.directions[i]));
            }
        } while (std::next_permutation(permutation.begin(), permutation.end()));
    }
}

TEST_CASE("ordered adapter handles empty, singleton, zero dimension, and a late exterior input") {
    StopWorkspace stop;
    for (const auto& points : std::vector<std::vector<Vector>>{{}, {{2.0}}, {{}, {}, {}}}) {
        geometry::PointCloud cloud{{"small"}, points};
        auto result = geometry::reduce_ordered_hull(cloud, stop, {});
        REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
        const auto& reduction = std::get<geometry::HullReduction>(result);
        CHECK(reduction.ordered.has_value());
        CHECK(reduction.lp_calls <= 1);
    }
    geometry::PointCloud cloud{{"late-exterior"}, {{0.0}, {0.5}, {0.25}, {1.0}}};
    auto lp = highs_workspace();
    auto result = completed(geometry::reduce_ordered_hull(cloud, *lp, {}));
    CHECK(result.ordered->processing_order == std::vector<std::size_t>{0, 3, 2, 1});
    CHECK(support(cloud, result, {1.0}) == 1.0);
    CHECK(support(cloud, result, {-1.0}) == 0.0);
}

TEST_CASE("ordered reducer registration exposes order metrics through the shared port") {
    geometry::PointCloud cloud{{"registered-order"}, {{-2.0, 3.0}, {2.0, 3.0}, {0.0, 3.0}}};
    auto registration = geometry::make_ordered_hull_reducer_registration();
    CHECK(registration.identity.id.value == "csl.hull.ordered-membership");
    auto reducer = registration.factory(cloud);
    auto lp = highs_workspace();
    auto result = completed(reducer->reduce(cloud, *lp, {}));
    REQUIRE(result.ordered.has_value());
    CHECK(result.ordered->processing_order == std::vector<std::size_t>{0, 1, 2});
    CHECK(result.ordered->zero_width_coordinates == 1);
    CHECK(result.ordered->ordered_candidates == 3);
    check_exact_removals(cloud, result);
    CHECK(support(cloud, result, {1.0, 0.0}) == 2.0);
    CHECK(support(cloud, result, {-1.0, 0.0}) == 2.0);
}

TEST_CASE("unsafe binary64 range falls back to input order without altering deletion safety") {
    geometry::PointCloud cloud{{"overflow-range"}, {{-1e308}, {1e308}, {0.0}}};
    StopWorkspace stop;
    auto result = geometry::reduce_ordered_hull(cloud, stop, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.ordered.has_value());
    CHECK(reduction.ordered->used_identity_fallback);
    CHECK(reduction.ordered->processing_order == std::vector<std::size_t>{0, 1, 2});
    CHECK(reduction.ordered->ordered_candidates == 3);
    CHECK(reduction.lp_calls == 1);
    CHECK(reduction.attempts.front().candidate == 0);
}

TEST_CASE("grouped reducer clusters nearby points and certifies the same hull for every permutation") {
    const std::vector<Vector> fixture{{0.0, 0.0}, {2.0, 0.0}, {0.0, 2.0},
        {0.5, 0.5}, {0.5, 0.5}};
    std::vector<std::size_t> permutation(fixture.size());
    std::iota(permutation.begin(), permutation.end(), 0);
    do {
        geometry::PointCloud cloud{{"grouped-permutation"}, {}};
        for (auto id : permutation) cloud.points.push_back(fixture[id]);
        auto grouped_lp = highs_workspace();
        auto baseline_lp = highs_workspace();
        auto grouped_result = geometry::reduce_grouped_hull(cloud, *grouped_lp, {});
        auto grouped = completed(grouped_result);
        auto baseline = completed(geometry::reduce_hull(cloud, *baseline_lp, {}));
        REQUIRE(grouped.grouped.has_value());
        CHECK_FALSE(grouped.ordered.has_value());
        CHECK(grouped.grouped->processing_order.size() == cloud.points.size());
        CHECK(grouped.grouped->grouping_passes == 0);
        CHECK(grouped.grouped->grouped_candidates == 0);
        CHECK(grouped.lp_calls == grouped.attempts.size());
        check_exact_removals(cloud, grouped);
        check_exact_removals(cloud, baseline);
        for (const auto direction : std::array<Vector, 4>{{{1.0, 0.0}, {-1.0, 0.0},
                 {0.0, 1.0}, {0.0, -1.0}}})
            CHECK(support(cloud, grouped, direction) == support(cloud, baseline, direction));
    } while (std::next_permutation(permutation.begin(), permutation.end()));
}

TEST_CASE("grouped reducer registration and degenerate coordinates expose honest metrics") {
    geometry::PointCloud cloud{{"grouped-flat"}, {{-1.0, 3.0}, {0.0, 3.0}, {1.0, 3.0}, {0.0, 3.0}}};
    const auto registration = geometry::make_grouped_hull_reducer_registration();
    CHECK(registration.identity.id.value == "csl.hull.grouped-membership");
    auto reducer = registration.factory(cloud);
    auto lp = highs_workspace();
    auto result = completed(reducer->reduce(cloud, *lp, {}));
    REQUIRE(result.grouped.has_value());
    CHECK(result.grouped->zero_width_coordinates == 1);
    CHECK(result.grouped->ordered_candidates == 4);
    CHECK_FALSE(result.grouped->grouping_triggered);
    CHECK(result.grouped->grouped_candidates == 0);
    CHECK(support(cloud, result, {1.0, 0.0}) == 1.0);
    CHECK(support(cloud, result, {-1.0, 0.0}) == 1.0);
    check_exact_removals(cloud, result);
}

TEST_CASE("grouped reducer streams ten certified redundancies then checks the grouped remainder") {
    std::vector<Vector> corners{{0.0, 0.0}, {2.0, 0.0}, {2.0, 2.0}, {0.0, 2.0}};
    std::vector<std::size_t> permutation(corners.size());
    std::iota(permutation.begin(), permutation.end(), 0);
    do {
        geometry::PointCloud cloud{{"grouped-stream"}, {}};
        for (const auto id : permutation) cloud.points.push_back(corners[id]);
        for (int duplicate = 0; duplicate < 10; ++duplicate) cloud.points.push_back({1.0, 1.0});
        auto lp = highs_workspace();
        auto result = completed(geometry::reduce_grouped_hull(cloud, *lp, {}));
        REQUIRE(result.grouped.has_value());
        CHECK(result.grouped->grouping_triggered);
        CHECK(result.grouped->grouping_passes == 1);
        CHECK(result.grouped->streamed_candidates == 12);
        CHECK(result.grouped->grouped_candidates == 1);
        CHECK(result.grouped->certified_stream_removals == 10);
        CHECK(result.lp_calls == result.attempts.size());
        check_exact_removals(cloud, result);
        CHECK(support(cloud, result, {1.0, 0.0}) == 2.0);
        CHECK(support(cloud, result, {-1.0, 0.0}) == 0.0);
        CHECK(support(cloud, result, {0.0, 1.0}) == 2.0);
        CHECK(support(cloud, result, {0.0, -1.0}) == 0.0);
    } while (std::next_permutation(permutation.begin(), permutation.end()));
}

TEST_CASE("grouped remainder adds a nearby outside point as certified support across tied-axis permutations") {
    const std::vector<Vector> axis_extremes{{0.0, 0.5, 0.5}, {1.0, 0.5, 0.5},
        {0.5, 0.0, 0.5}, {0.5, 1.0, 0.5}, {0.5, 0.5, 0.0}, {0.5, 0.5, 1.0}};
    std::vector<std::size_t> permutation(axis_extremes.size());
    std::iota(permutation.begin(), permutation.end(), 0);
    do {
        geometry::PointCloud cloud{{"grouped-nearby-support"}, {}};
        for (const auto id : permutation) cloud.points.push_back(axis_extremes[id]);
        for (int duplicate = 0; duplicate < 10; ++duplicate) cloud.points.push_back({0.9, 0.5, 0.5});
        cloud.points.push_back({0.75, 0.75, 0.75});
        cloud.points.push_back({0.7421875, 0.7421875, 0.7421875});

        auto lp = highs_workspace();
        auto result = completed(geometry::reduce_grouped_hull(cloud, *lp, {}));
        REQUIRE(result.grouped.has_value());
        CHECK(result.grouped->grouping_triggered);
        CHECK(result.grouped->streamed_candidates == 14);
        CHECK(result.grouped->grouped_candidates == 3);
        CHECK(result.grouped->nearby_supports == 1);
        CHECK(result.grouped->certified_stream_removals == 10);
        CHECK(result.lp_calls == result.attempts.size());
        check_exact_removals(cloud, result);
        CHECK(support(cloud, result, {1.0, 0.0, 0.0}) == 1.0);
        CHECK(support(cloud, result, {-1.0, 0.0, 0.0}) == 0.0);
        CHECK(support(cloud, result, {0.0, 1.0, 0.0}) == 1.0);
        CHECK(support(cloud, result, {0.0, 0.0, 1.0}) == 1.0);
        CHECK(support(cloud, result, {1.0, 1.0, 1.0}) == 2.25);
        CHECK(support(cloud, result, {-1.0, -1.0, -1.0}) == -1.0);
    } while (std::next_permutation(permutation.begin(), permutation.end()));
}

TEST_CASE("grouped reducer preserves flat and duplicate hulls across every permutation") {
    const std::vector<Vector> fixture{{-1.0, 3.0}, {0.0, 3.0}, {1.0, 3.0}, {0.0, 3.0}};
    std::vector<std::size_t> permutation(fixture.size());
    std::iota(permutation.begin(), permutation.end(), 0);
    do {
        geometry::PointCloud cloud{{"grouped-flat-permutation"}, {}};
        for (auto id : permutation) cloud.points.push_back(fixture[id]);
        auto grouped_lp = highs_workspace();
        auto baseline_lp = highs_workspace();
        auto grouped = completed(geometry::reduce_grouped_hull(cloud, *grouped_lp, {}));
        auto baseline = completed(geometry::reduce_hull(cloud, *baseline_lp, {}));
        REQUIRE(grouped.grouped.has_value());
        CHECK(grouped.grouped->used_identity_fallback);
        CHECK(grouped.grouped->zero_width_coordinates == 1);
        check_exact_removals(cloud, grouped);
        check_exact_removals(cloud, baseline);
        CHECK(support(cloud, grouped, {1.0, 0.0}) == support(cloud, baseline, {1.0, 0.0}));
        CHECK(support(cloud, grouped, {-1.0, 0.0}) == support(cloud, baseline, {-1.0, 0.0}));
    } while (std::next_permutation(permutation.begin(), permutation.end()));
}

TEST_CASE("grouped ordering falls back to input order when box width overflows") {
    geometry::PointCloud cloud{{"grouped-overflow"}, {{-1e308}, {1e308}, {0.0}}};
    StopWorkspace stop;
    auto result = geometry::reduce_grouped_hull(cloud, stop, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.grouped.has_value());
    CHECK(reduction.grouped->used_identity_fallback);
    CHECK(reduction.grouped->processing_order == std::vector<std::size_t>{0, 1, 2});
    CHECK(reduction.grouped->grouping_passes == 0);
    CHECK(reduction.grouped->grouped_candidates == 0);
    CHECK(reduction.attempts.front().candidate == 2);
}
