#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/bounded_hull_checker.hpp>

#include <chrono>
#include <limits>
#include <vector>

using csl::Vector;
using namespace csl::geometry;

namespace {
const std::vector<Vector> square{{0,0}, {2,0}, {2,2}, {0,2},
    {1,1}, {1,0}, {2,1}, {1,2}, {0,1}};

SourceIndexHull hull(std::vector<std::size_t> indices) {
    return {std::get<HullInputDigest>(digest_hull_input(square)), std::move(indices)};
}
} // namespace

TEST_CASE("exact source hull accepts all corners and redundant retained points") {
    const auto minimal = check_source_index_hull(square, hull({0,1,2,3}));
    CHECK(minimal.status == HullCheckStatus::verified);
    CHECK_FALSE(minimal.counterexample_index.has_value());
    CHECK(minimal.elapsed >= std::chrono::nanoseconds::zero());
    CHECK(minimal.budget.wall == std::chrono::milliseconds{5000});
    CHECK(minimal.evidence_scope == "exact represented binary64 2D finite hull");
    CHECK(check_source_index_hull(square, hull({0,1,2,3,4,5,6,7,8})).status ==
          HullCheckStatus::verified);
}

TEST_CASE("omitted true corner yields a concrete source point counterexample") {
    const auto result = check_source_index_hull(square, hull({0,1,2,4,5,6,7,8}));
    CHECK(result.status == HullCheckStatus::incorrect);
    REQUIRE(result.counterexample_index.has_value());
    CHECK(*result.counterexample_index == 3);
    CHECK(result.reason == "input point lies outside reported convex hull");
}

TEST_CASE("source indices are unique, in range, and bound to exact ordered bytes") {
    const auto duplicate = check_source_index_hull(square, hull({0,1,2,3,3}));
    CHECK(duplicate.status == HullCheckStatus::incorrect);
    CHECK(duplicate.reason == "duplicate source index");
    const auto out_of_range = check_source_index_hull(square, hull({0,1,2,3,9}));
    CHECK(out_of_range.status == HullCheckStatus::incorrect);
    CHECK(out_of_range.counterexample_index == 9);

    auto changed = square;
    changed[4][0] = 1.25;
    const auto mismatch = check_source_index_hull(changed, hull({0,1,2,3}));
    CHECK(mismatch.status == HullCheckStatus::incorrect);
    CHECK(mismatch.reason == "output input digest does not match the exact ordered input manifest");
    auto reordered = square;
    std::swap(reordered[0], reordered[1]);
    CHECK(check_source_index_hull(reordered, hull({0,1,2,3})).status ==
          HullCheckStatus::incorrect);
}

TEST_CASE("budget and unsupported input preserve inconclusive status") {
    const auto timeout = check_source_index_hull(square, hull({0,1,2,3}),
        {std::chrono::milliseconds{0}, 64});
    CHECK(timeout.status == HullCheckStatus::inconclusive);
    CHECK(timeout.reason == "checker timeout");
    CHECK(timeout.budget.wall == std::chrono::milliseconds{0});
    const auto capacity = check_source_index_hull(square, hull({0,1,2,3}),
        {std::chrono::milliseconds{5000}, 4});
    CHECK(capacity.status == HullCheckStatus::inconclusive);
    CHECK(capacity.reason == "checker point capacity exceeded");
    const std::vector<Vector> three_dimensions{{0,0,0}, {1,0,0}};
    const auto digest = std::get<HullInputDigest>(digest_hull_input(three_dimensions));
    const auto unsupported = check_source_index_hull(three_dimensions, {digest, {0,1}});
    CHECK(unsupported.status == HullCheckStatus::inconclusive);
    CHECK(unsupported.reason == "unsupported dimension");
}

TEST_CASE("modern-only square smoke records algorithm and independent checker") {
    const auto smoke = run_bounded_square_smoke();
    CHECK(smoke.algorithm == "modern QuickHull2D");
    CHECK(smoke.algorithm_status == "completed");
    CHECK(smoke.algorithm_failure.empty());
    CHECK(smoke.checker.status == HullCheckStatus::verified);
    const auto timed_out = run_bounded_square_smoke({std::chrono::milliseconds{0}, 64});
    CHECK(timed_out.algorithm_status == "completed");
    CHECK(timed_out.checker.status == HullCheckStatus::inconclusive);
    const auto failed = record_bounded_hull_attempt(square,
        std::string{"algorithm stopped before output"}, "modern candidate");
    CHECK(failed.algorithm_status == "failed");
    CHECK(failed.algorithm_failure == "algorithm stopped before output");
    CHECK(failed.checker.status == HullCheckStatus::inconclusive);
    CHECK(failed.checker.reason == "algorithm produced no source-index hull");
}
