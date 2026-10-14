#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <memory>
#include <string>
#include <variant>

using namespace csl;

namespace {
std::unique_ptr<LPWorkspace> highs_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"barycentric-test"}, {"seed"}}, {}, 0,
        {0, 0, {0}, {}, {}}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

bool in_reference_triangle(const Vector& point) {
    return point.size() == 2 && point[0] >= 0.0 && point[1] >= 0.0 &&
        point[0] + point[1] <= 1.0;
}

double support(const geometry::PointCloud& cloud, const std::vector<std::size_t>& points,
        const Vector& direction) {
    double result = -std::numeric_limits<double>::infinity();
    for (const auto point : points)
        result = std::max(result, direction[0] * cloud.points[point][0] +
            direction[1] * cloud.points[point][1]);
    return result;
}
}

TEST_CASE("LP barycentric membership agrees with the hand-derived reference triangle") {
    auto workspace = highs_workspace();
    REQUIRE(workspace != nullptr);
    const std::array<Vector, 4> queries{{{0.25, 0.25}, {0.5, 0.5}, {0.0, 1.0}, {1.0, 1.0}}};

    for (std::size_t query = 0; query < queries.size(); ++query) {
        const auto& point = queries[query];
        const geometry::PointCloud cloud{{"reference-triangle-" + std::to_string(query)},
            {point, {0.0, 0.0}, {1.0, 0.0}, {0.0, 1.0}}};
        auto reduced = geometry::reduce_hull(cloud, *workspace, {});
        REQUIRE(std::holds_alternative<geometry::HullReduction>(reduced));
        const auto& result = std::get<geometry::HullReduction>(reduced);
        REQUIRE_FALSE(result.attempts.empty());

        const bool expected_inside = in_reference_triangle(point);
        CHECK((result.attempts.front().outcome == geometry::MembershipOutcome::feasible) == expected_inside);
        CHECK((result.attempts.front().outcome == geometry::MembershipOutcome::infeasible) == !expected_inside);
        if (!expected_inside) continue;

        const auto certificate = std::find_if(result.removed.begin(), result.removed.end(),
            [](const geometry::RemovalCertificate& item) { return item.removed == 0; });
        REQUIRE(certificate != result.removed.end());
        long double weight_sum = 0.0L;
        std::array<long double, 2> reconstructed{};
        for (const auto& term : certificate->combination) {
            REQUIRE(term.point < cloud.points.size());
            CHECK(term.point != 0);
            CHECK(term.weight >= 0.0);
            weight_sum += static_cast<long double>(term.weight);
            reconstructed[0] += static_cast<long double>(term.weight) * cloud.points[term.point][0];
            reconstructed[1] += static_cast<long double>(term.weight) * cloud.points[term.point][1];
        }
        CHECK(std::abs(weight_sum - 1.0L) < 1e-12L);
        CHECK(std::abs(reconstructed[0] - point[0]) < 1e-12L);
        CHECK(std::abs(reconstructed[1] - point[1]) < 1e-12L);
    }
}

TEST_CASE("square hull reduction preserves analytic support and every extreme point") {
    auto workspace = highs_workspace();
    REQUIRE(workspace != nullptr);
    const geometry::PointCloud cloud{{"support-square"}, {
        {0, 0}, {1, 0}, {1, 1}, {0, 1}, {0.5, 0.5}, {0.5, 0.5}
    }};
    auto reduced = geometry::reduce_hull(cloud, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(reduced));
    const auto& result = std::get<geometry::HullReduction>(reduced);
    REQUIRE(result.status == geometry::ReductionStatus::complete);
    for (std::size_t extreme = 0; extreme < 4; ++extreme)
        CHECK(std::find(result.retained.begin(), result.retained.end(), extreme) != result.retained.end());
    CHECK(std::find(result.retained.begin(), result.retained.end(), 4) == result.retained.end());
    CHECK(std::find(result.retained.begin(), result.retained.end(), 5) == result.retained.end());

    const std::array<Vector, 8> directions{{
        {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {-1, 1}, {1, -1}, {-1, -1}
    }};
    const std::vector<std::size_t> all_points{0, 1, 2, 3, 4, 5};
    for (const auto& direction : directions)
        CHECK(support(cloud, result.retained, direction) == doctest::Approx(
            support(cloud, all_points, direction)).epsilon(1e-12));
}
