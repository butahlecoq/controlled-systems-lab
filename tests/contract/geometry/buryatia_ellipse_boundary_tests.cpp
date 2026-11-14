#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "ellipse_boundary.hpp"

#include <doctest/doctest.h>

#include <array>
#include <cmath>
#include <limits>

namespace {
using csl::Matrix;
using csl::Vector;
using csl::geometry::ellipsoidal::FactorEllipsoid;
using csl::geometry::ellipsoidal::make_factor_ellipsoid;
using csl::benchmarks::buryatia::factor_ellipsoid_boundary_2d;

double support(const FactorEllipsoid &ellipsoid, const std::array<double, 2> &direction) {
    double square = 0.0;
    for (std::size_t column = 0; column < ellipsoid.factor.cols; ++column) {
        const auto projection =
            direction[0] * ellipsoid.factor.values[column] +
            direction[1] * ellipsoid.factor.values[ellipsoid.factor.cols + column];
        square += projection * projection;
    }
    return direction[0] * ellipsoid.center[0] + direction[1] * ellipsoid.center[1] +
           std::sqrt(square);
}

void check_samples_are_inside(const FactorEllipsoid &ellipsoid,
                              const std::vector<std::array<double, 2>> &points) {
    double q00 = 0.0, q01 = 0.0, q11 = 0.0;
    for (std::size_t column = 0; column < ellipsoid.factor.cols; ++column) {
        const double x = ellipsoid.factor.values[column];
        const double y = ellipsoid.factor.values[ellipsoid.factor.cols + column];
        q00 += x * x;
        q01 += x * y;
        q11 += y * y;
    }
    const double spread = std::hypot(q00 - q11, 2 * q01);
    const double major2 = std::max(0.0, (q00 + q11 + spread) / 2);
    const double minor2 = std::max(0.0, (q00 + q11 - spread) / 2);
    const double angle = 0.5 * std::atan2(2 * q01, q00 - q11);
    const double c = std::cos(angle), s = std::sin(angle);
    const double tolerance = 1e-10 * std::max(1.0, std::sqrt(major2));
    for (const auto &point : points) {
        const auto dx = point[0] - ellipsoid.center[0];
        const auto dy = point[1] - ellipsoid.center[1];
        const auto x = dx * c + dy * s;
        const auto y = -dx * s + dy * c;
        if (minor2 <= tolerance * tolerance) {
            CHECK(std::abs(y) <= tolerance);
            CHECK(x * x <= major2 + tolerance * tolerance);
        } else {
            CHECK(x * x / major2 + y * y / minor2 <= 1 + 1e-10);
        }
    }
}
}

TEST_CASE("ellipse boundary samples follow the rotated factor shape") {
    const auto made = make_factor_ellipsoid({1.0, -2.0}, Matrix{2, 2, {2.0, 1.0, 1.0, 1.0}});
    REQUIRE(std::holds_alternative<FactorEllipsoid>(made));
    const auto &ellipsoid = std::get<FactorEllipsoid>(made);
    const auto points = factor_ellipsoid_boundary_2d(ellipsoid);
    check_samples_are_inside(ellipsoid, points);
    const std::array<std::array<double, 2>, 4> directions{{{1, 0}, {0, 1}, {1, 1}, {-1, 1}}};
    for (const auto direction : directions) {
        double sampled = -std::numeric_limits<double>::infinity();
        for (const auto &point : points)
            sampled = std::max(sampled, direction[0] * point[0] + direction[1] * point[1]);
        const auto exact = support(ellipsoid, direction);
        CHECK(sampled <= exact + 1e-10);
        CHECK(exact - sampled <= 0.01 * std::max(1.0, std::abs(exact)));
    }
}

TEST_CASE("ellipse boundary samples handle a rank-one factor") {
    const auto made = make_factor_ellipsoid({-0.5, 0.25}, Matrix{2, 2, {1.0, 2.0, 2.0, 4.0}});
    REQUIRE(std::holds_alternative<FactorEllipsoid>(made));
    const auto &ellipsoid = std::get<FactorEllipsoid>(made);
    const auto points = factor_ellipsoid_boundary_2d(ellipsoid);
    check_samples_are_inside(ellipsoid, points);
}
