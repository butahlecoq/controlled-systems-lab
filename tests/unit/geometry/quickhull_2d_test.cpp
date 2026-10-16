#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/quickhull_2d.hpp>

#include <cmath>
#include <limits>
#include <vector>

using csl::Vector;
using csl::geometry::QuickHull2D;
using csl::geometry::quickhull_2d;

TEST_CASE("QuickHull keeps original identities in counterclockwise order") {
    const std::vector<Vector> points{{1,1}, {2,2}, {0,2}, {2,0}, {0,0},
                                     {0,0}, {1,0}, {1,2}, {1,1}};
    const auto output = quickhull_2d(points);
    REQUIRE(std::holds_alternative<QuickHull2D>(output));
    CHECK(std::get<QuickHull2D>(output).vertex_indices ==
          std::vector<std::size_t>{4,3,1,2});
}

TEST_CASE("QuickHull handles empty, coincident, and collinear clouds") {
    const std::vector<Vector> empty;
    const auto empty_hull = quickhull_2d(empty);
    REQUIRE(std::holds_alternative<QuickHull2D>(empty_hull));
    CHECK(std::get<QuickHull2D>(empty_hull).vertex_indices.empty());

    const std::vector<Vector> coincident{{3,-2}, {3,-2}, {3,-2}};
    const auto point_hull = quickhull_2d(coincident);
    REQUIRE(std::holds_alternative<QuickHull2D>(point_hull));
    CHECK(std::get<QuickHull2D>(point_hull).vertex_indices == std::vector<std::size_t>{0});

    const std::vector<Vector> vertical{{1,3}, {1,-2}, {1,0}, {1,3}, {1,-2}};
    const auto line_hull = quickhull_2d(vertical);
    REQUIRE(std::holds_alternative<QuickHull2D>(line_hull));
    CHECK(std::get<QuickHull2D>(line_hull).vertex_indices ==
          std::vector<std::size_t>{1,0});
}

TEST_CASE("QuickHull selects deterministic orientation and farthest-point ties") {
    const std::vector<Vector> diamond{{0,2}, {-2,0}, {0,-2}, {2,0}, {0,0}};
    const auto rotated = quickhull_2d(diamond);
    REQUIRE(std::holds_alternative<QuickHull2D>(rotated));
    CHECK(std::get<QuickHull2D>(rotated).vertex_indices ==
          std::vector<std::size_t>{1,2,3,0});

    const std::vector<Vector> tied{{0,2}, {1,2}, {2,2}, {2,0}, {0,0}};
    const auto tied_hull = quickhull_2d(tied);
    REQUIRE(std::holds_alternative<QuickHull2D>(tied_hull));
    CHECK(std::get<QuickHull2D>(tied_hull).vertex_indices ==
          std::vector<std::size_t>{4,3,2,0});

    const std::vector<Vector> nearly_collinear{{0,0}, {1,1},
        {2,std::nextafter(2.0, 3.0)}};
    const auto tiny_turn = quickhull_2d(nearly_collinear);
    REQUIRE(std::holds_alternative<QuickHull2D>(tiny_turn));
    CHECK(std::get<QuickHull2D>(tiny_turn).vertex_indices ==
          std::vector<std::size_t>{0,1,2});
}

TEST_CASE("QuickHull orientation does not overflow at finite binary64 extremes") {
    const std::vector<Vector> points{{1e308,0}, {-1e308,0}, {0,1e308},
                                     {0,-1e308}, {0,0}};
    const auto output = quickhull_2d(points);
    REQUIRE(std::holds_alternative<QuickHull2D>(output));
    CHECK(std::get<QuickHull2D>(output).vertex_indices ==
          std::vector<std::size_t>{1,3,0,2});
}

TEST_CASE("QuickHull rejects dimensions and nonfinite coordinates") {
    const std::vector<Vector> three_dimensional{{0,0,7}, {1,0,9}};
    const auto dimension = quickhull_2d(three_dimensional);
    REQUIRE(std::holds_alternative<csl::Diagnostics>(dimension));
    CHECK(std::get<csl::Diagnostics>(dimension).front().code ==
          csl::DiagnosticCode::invalid_input);
    CHECK(std::get<csl::Diagnostics>(dimension).front().field == "points");

    const std::vector<Vector> one_dimensional{{0}, {1}};
    CHECK(std::holds_alternative<csl::Diagnostics>(quickhull_2d(one_dimensional)));

    const std::vector<Vector> nonfinite{{0,0}, {std::numeric_limits<double>::infinity(),1}};
    const auto invalid = quickhull_2d(nonfinite);
    REQUIRE(std::holds_alternative<csl::Diagnostics>(invalid));
    CHECK(std::get<csl::Diagnostics>(invalid).front().code ==
          csl::DiagnosticCode::invalid_input);
}
