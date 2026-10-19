#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/ellipsoidal.hpp>

#include <cmath>

using namespace csl;
using namespace csl::geometry::ellipsoidal;

namespace {
constexpr double root_two_up = 1.4142135623730951;
EllipsoidInput square() {
    return {{"square-outer"},{0,0},{2,2,{1,0,0,1}},{1,1},
        {root_two_up,root_two_up},{"x","y"}};
}
}

TEST_CASE("a planar outer ellipsoid has immutable PSD geometry and finite support") {
    const auto built=make_ellipsoid(square());
    REQUIRE(std::holds_alternative<EllipsoidSet>(built));
    const auto set=std::get<EllipsoidSet>(built);
    CHECK(set.id()==SetId{"square-outer"});
    CHECK(set.center()==Vector{0,0});
    CHECK(set.orientation().values==Vector{1,0,0,1});
    CHECK(set.projected_bounds()==Vector{1,1});
    CHECK(set.radii()==Vector{root_two_up,root_two_up});
    const auto handle=set.as_handle();
    CHECK(handle.metadata.representation==RepresentationId{"csl.ellipsoid.directional2d"});
    CHECK(handle.metadata.convex==SetProperty::yes);
    CHECK(handle.metadata.bounded==SetProperty::yes);
    const auto imported=from_ellipsoid_handle(handle);
    REQUIRE(std::holds_alternative<EllipsoidSet>(imported));
    const auto support=set.support({1,1});
    REQUIRE(std::holds_alternative<double>(support));
    CHECK(std::get<double>(support)==doctest::Approx(2.0));
}

TEST_CASE("rank-one and point ellipsoids preserve zero-width coordinates") {
    auto line=square();
    line.projected_bounds={1,0};
    line.radii={root_two_up,0};
    const auto built=make_ellipsoid(line);
    REQUIRE(std::holds_alternative<EllipsoidSet>(built));
    const auto& set=std::get<EllipsoidSet>(built);
    CHECK(set.as_handle().metadata.polyhedral==SetProperty::yes);
    const auto vertical=set.support({0,1});
    REQUIRE(std::holds_alternative<double>(vertical));
    CHECK(std::get<double>(vertical)==0.0);
    line.projected_bounds={0,0};
    line.radii={0,0};
    CHECK(std::holds_alternative<EllipsoidSet>(make_ellipsoid(line)));
}

TEST_CASE("malformed shape and forged handle refuse import") {
    auto input=square();
    input.radii={1,1};
    CHECK(std::holds_alternative<Diagnostics>(make_ellipsoid(input)));
    input=square();
    input.orientation={2,2,{1,1,2,2}};
    CHECK(std::holds_alternative<Diagnostics>(make_ellipsoid(input)));
    input=square();
    input.coordinate_labels={"x","x"};
    CHECK(std::holds_alternative<Diagnostics>(make_ellipsoid(input)));
    auto handle=std::get<EllipsoidSet>(make_ellipsoid(square())).as_handle();
    handle.metadata.representation={"csl.polyhedron.h"};
    CHECK(std::holds_alternative<Diagnostics>(from_ellipsoid_handle(handle)));
}
