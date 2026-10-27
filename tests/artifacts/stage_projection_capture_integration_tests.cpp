#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/stage_projection_capture.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <array>
#include <vector>

namespace {
using namespace csl;
namespace ar = csl::artifacts;
namespace geo = csl::geometry::polyhedral;
namespace reg = csl::registry;

template<class T, class... Rest>
T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

using Point = std::array<double, 2>;

double cross(const Point& origin, const Point& first, const Point& second) {
    return (first[0] - origin[0]) * (second[1] - origin[1]) -
        (first[1] - origin[1]) * (second[0] - origin[0]);
}

std::vector<Point> hull(std::vector<Point> points) {
    std::sort(points.begin(), points.end());
    points.erase(std::unique(points.begin(), points.end()), points.end());
    if (points.size() < 3) return points;

    std::vector<Point> result;
    for (const auto& point : points) {
        while (result.size() >= 2 && cross(result[result.size() - 2], result.back(), point) <= 0.0)
            result.pop_back();
        result.push_back(point);
    }
    const auto lower_size = result.size();
    for (auto point = points.rbegin() + 1; point != points.rend(); ++point) {
        while (result.size() > lower_size &&
            cross(result[result.size() - 2], result.back(), *point) <= 0.0)
            result.pop_back();
        result.push_back(*point);
    }
    result.pop_back();
    return result;
}

sets::SetData correlated_simplex() {
    // Relation storage is deliberately ordered x2, x0, x3, x1.
    Matrix vertices{6, 4, {
        0, 0, 0, 0,
        1, 0, 0, 0,
        0, 2, 0, 0,
        0, 0, 3, 0,
        0, 0, 0, 4,
        1, 1, 1, 1}};
    Matrix rays{0, 4, {}};
    return take(sets::make_v({{"correlated-simplex"}, 4, {"x2", "x0", "x3", "x1"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

reg::PreparedProvider<reg::GeometryPort> projection_provider() {
    reg::Registry<reg::GeometryPort> registry;
    auto entry = geo::make_projection_registration({geo::ProjectionOutput::v, 64});
    const auto method = reg::Method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    reg::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    return take(reg::prepare_provider(reg::select_provider(registry, method, requirements)));
}

ar::StageProjectionCaptureRequest request(const sets::SetData& source) {
    std::vector<ar::StageCoordinatePair> pairs;
    for (std::size_t first = 0; first < 4; ++first) {
        for (std::size_t second = 0; second < 4; ++second) {
            if (first != second)
                pairs.push_back({ar::CoordinateOrdinal{first}, ar::CoordinateOrdinal{second}});
        }
    }
    ar::StageProjectionSet relation;
    relation.relation = source.as_handle();
    relation.owner = {{"projection-integration"}, source.metadata()->id};
    relation.relation_coordinates = {1, 3, 0, 2};
    std::vector<ar::CoordinateAnnotation> coordinates{
        {"oxidizer flow", "kg/s", {}, {}}, {"oxidizer stock", "kg", {}, {}},
        {"fuel flow", "kg/s", {}, {}}, {"fuel stock", "kg", {}, {}}};
    return {{"projection-integration"}, {"all-pairs"}, std::move(coordinates), std::move(pairs),
        {{{0}, 0.0, std::move(relation)}}, SetRelation::equivalent, Assurance::numerical};
}

std::vector<Point> projected_vertices(const SetHandle& handle) {
    const auto converted = sets::from_handle(handle);
    REQUIRE(std::holds_alternative<sets::SetData>(converted));
    const auto representation = std::get<sets::SetData>(converted).representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(representation));
    const auto& vertices = std::get<sets::VRepresentation>(representation).vertices;
    std::vector<Point> result;
    for (std::size_t row = 0; row < vertices.rows(); ++row)
        result.push_back({vertices(row, 0), vertices(row, 1)});
    return result;
}
}

TEST_CASE("four-state correlated geometry matches an independent oracle in all ordered projections") {
    const auto source = correlated_simplex();
    const auto input = request(source);
    const auto captured = ar::capture_stage_projections(input, projection_provider());
    REQUIRE(std::holds_alternative<ar::StageProjectionBatchCapture>(captured));
    const auto& batch = std::get<ar::StageProjectionBatchCapture>(captured);
    REQUIRE(batch.records.size() == 12);

    constexpr std::array<std::array<double, 4>, 6> states{{
        {{0, 0, 0, 0}}, {{0, 0, 1, 0}}, {{2, 0, 0, 0}},
        {{0, 0, 0, 3}}, {{0, 4, 0, 0}}, {{1, 1, 1, 1}}}};
    for (std::size_t pair = 0; pair < input.coordinate_pairs.size(); ++pair) {
        const auto first = pair / 3;
        const auto second = pair % 3;
        const auto adjusted_second = second >= first ? second + 1 : second;
        const auto& row = batch.records[pair];
        REQUIRE(row.stage.value == 0);
        REQUIRE(row.physical_time.has_value());
        CHECK(*row.physical_time == doctest::Approx(0.0));
        REQUIRE(row.pair.first == first);
        REQUIRE(row.pair.second == adjusted_second);
        REQUIRE(std::holds_alternative<ar::StageProjectionSuccess>(row.outcome));
        const auto& projection = std::get<ar::StageProjectionSuccess>(row.outcome).projection;
        CHECK(projection.coordinates[0].label == input.state_coordinates[first].label);
        CHECK(projection.coordinates[1].label == input.state_coordinates[adjusted_second].label);
        CHECK(projection.reference.identity.request.value ==
            "all-pairs/pair/" + std::to_string(pair) + "/stage/0");

        std::vector<Point> expected;
        for (const auto& state : states)
            expected.push_back({state[first], state[adjusted_second]});
        CHECK(hull(projected_vertices(projection.projected_relation)) == hull(std::move(expected)));
    }
}
