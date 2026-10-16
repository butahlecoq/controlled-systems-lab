#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/quickhull_2d.hpp>

#include <algorithm>
#include <memory>
#include <variant>

using namespace csl;

namespace {
std::unique_ptr<LPWorkspace> highs_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"quickhull-oracle"},{"seed"}}, {}, 0,
        {0,0,{0},{},{}}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

std::vector<Vector> ordered_coordinates(const geometry::PointCloud& cloud,
                                        const std::vector<std::size_t>& indices) {
    std::vector<Vector> result;
    for (const auto index : indices) result.push_back(cloud.points[index]);
    std::sort(result.begin(), result.end());
    return result;
}
} // namespace

TEST_CASE("geometric hull equals the independent LP hull on exact analytic clouds") {
    const std::vector<geometry::PointCloud> fixtures{
        {{"square"}, {{0,0}, {2,0}, {2,2}, {0,2}, {1,1}, {1,0}, {0,0}}},
        {{"line"}, {{0,0}, {0,2}, {0,1}, {0,2}, {0,0}}},
        {{"rotated"}, {{-2,0}, {0,-2}, {2,0}, {0,2}, {0,0}}}
    };
    auto lp = highs_workspace();
    REQUIRE(lp != nullptr);
    for (const auto& cloud : fixtures) {
        CAPTURE(cloud.problem.value);
        const auto geometric = geometry::quickhull_2d(cloud.points);
        REQUIRE(std::holds_alternative<geometry::QuickHull2D>(geometric));
        const auto reference = geometry::reduce_hull(cloud, *lp, {});
        REQUIRE(std::holds_alternative<geometry::HullReduction>(reference));
        const auto& lp_hull = std::get<geometry::HullReduction>(reference);
        REQUIRE(lp_hull.status == geometry::ReductionStatus::complete);
        CHECK(ordered_coordinates(cloud, std::get<geometry::QuickHull2D>(geometric).vertex_indices) ==
              ordered_coordinates(cloud, lp_hull.retained));
    }
}
