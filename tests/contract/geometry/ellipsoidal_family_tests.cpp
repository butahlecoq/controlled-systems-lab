#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/approximation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>

using namespace csl;
using namespace csl::geometry::approximation;
using namespace csl::geometry::ellipsoidal;

namespace {
SetHandle square() {
    const auto vertices=numeric::snapshot(Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}});
    const auto rays=numeric::snapshot(Matrix{0,2,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    const auto made=sets::make_v({{"source"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
    REQUIRE(std::holds_alternative<sets::SetData>(made));
    return std::get<sets::SetData>(made).as_handle();
}
}

TEST_CASE("finite outer family is an intersection of independently enclosed ellipsoids") {
    registry::Registry<registry::ApproximationPort> methods;
    const registry::Method axis{{"test.ellipse.axis"},"1"};
    const registry::Method rotated{{"test.ellipse.rotated"},"1"};
    REQUIRE_FALSE(methods.add(make_directional_ellipsoid_registration(axis,{"axis"},
        Matrix{2,2,{1,0,0,1}})).has_value());
    REQUIRE_FALSE(methods.add(make_directional_ellipsoid_registration(rotated,{"rotated"},
        Matrix{2,2,{1,1,1,-1}})).has_value());
    const ApproximationRequest request{{{"app04"},{"family"},{"source"}},square(),
        {"csl.ellipsoid.directional2d"},SetRelation::outer,1,Assurance::numerical};
    const auto result=run_ellipsoid_family(methods,{axis,rotated},request,ExecutionContext{});
    REQUIRE(std::holds_alternative<EllipsoidFamily>(result));
    const auto& family=std::get<EllipsoidFamily>(result);
    CHECK(family.reference_id()==request.input.id);
    CHECK(family.relation()==SetRelation::outer);
    CHECK(family.composition()==FamilyComposition::intersection);
    REQUIRE(family.members().size()==2);
    CHECK(family.members()[0].result.output.id==SetId{"axis"});
    CHECK(family.members()[1].result.output.id==SetId{"rotated"});
    for(const auto& member:family.members()) {
        CHECK(member.basis==StructuralBasis::v_ellipsoid_containment);
        CHECK(member.result.relation==SetRelation::outer);
        CHECK(std::holds_alternative<EllipsoidSet>(
            from_ellipsoid_handle(member.result.output)));
    }
}

TEST_CASE("empty and unsupported inner family refuse") {
    registry::Registry<registry::ApproximationPort> methods;
    const registry::Method axis{{"test.ellipse.axis"},"1"};
    REQUIRE_FALSE(methods.add(make_directional_ellipsoid_registration(axis,{"axis"},
        Matrix{2,2,{1,0,0,1}})).has_value());
    ApproximationRequest request{{{"app04"},{"family"},{"source"}},square(),
        {"csl.ellipsoid.directional2d"},SetRelation::outer,1,Assurance::numerical};
    CHECK(std::holds_alternative<registry::Rejection>(
        run_ellipsoid_family(methods,{},request,ExecutionContext{})));
    request.direction=SetRelation::inner;
    CHECK(std::holds_alternative<registry::Rejection>(
        run_ellipsoid_family(methods,{axis},request,ExecutionContext{})));
}
