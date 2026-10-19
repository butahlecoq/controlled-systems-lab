#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/approximation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>

#include <chrono>
#include <cmath>
#include <limits>

using namespace csl;
using namespace csl::geometry::approximation;
using namespace csl::geometry::ellipsoidal;

namespace {
sets::SetData take(sets::Result<sets::SetData> result) {
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result));
}
SetHandle polygon(const char* id,Matrix points,Matrix rays={}) {
    if(rays.rows==0)rays.cols=2;
    const auto vertices=numeric::snapshot(points);
    const auto ray_view=numeric::snapshot(rays);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ray_view));
    return take(sets::make_v({{id},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),
         std::get<numeric::MatrixView>(ray_view)})).as_handle();
}
ApproximationRequest outer(SetHandle input,std::size_t budget=1,
                           Assurance assurance=Assurance::numerical) {
    return {{{"app04"},{"directional"},{"source-polytope"}},std::move(input),
        {"csl.ellipsoid.directional2d"},SetRelation::outer,budget,assurance};
}
const registry::Method method{{"csl.approximation.ellipsoid.xy"},"1"};
registry::Registry<registry::ApproximationPort> methods() {
    registry::Registry<registry::ApproximationPort> registry;
    REQUIRE_FALSE(registry.add(make_directional_ellipsoid_registration(method,
        {"outer-ellipse"},Matrix{2,2,{1,0,0,1}})).has_value());
    return registry;
}
}

TEST_CASE("registered planar ellipsoid encloses the complete square") {
    const auto input=polygon("square",Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}});
    const auto registry=methods();
    const auto result=run_registered(registry,method,outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto& admitted=std::get<EnclosedApproximation>(result);
    CHECK(admitted.basis==StructuralBasis::v_ellipsoid_containment);
    const auto imported=from_ellipsoid_handle(admitted.result.output);
    REQUIRE(std::holds_alternative<EllipsoidSet>(imported));
    const auto& ellipse=std::get<EllipsoidSet>(imported);
    CHECK(ellipse.center()==Vector{0,0});
    CHECK(ellipse.projected_bounds()==Vector{1,1});
    CHECK(ellipse.radii()[0]>=std::sqrt(2.0));
    CHECK(ellipse.radii()[1]>=std::sqrt(2.0));
    const auto support=ellipse.support({1,1});
    REQUIRE(std::holds_alternative<double>(support));
    CHECK(std::get<double>(support)>=2.0); // square support is exactly 2
}

TEST_CASE("rotated orientation and degenerate source retain valid outer results") {
    auto input=polygon("rectangle",Matrix{4,2,{-2,-1,2,-1,2,1,-2,1}});
    registry::Registry<registry::ApproximationPort> registry;
    const registry::Method rotated{{"csl.approximation.ellipsoid.diagonal"},"1"};
    REQUIRE_FALSE(registry.add(make_directional_ellipsoid_registration(rotated,
        {"diagonal-ellipse"},Matrix{2,2,{1,1,1,-1}})).has_value());
    auto result=run_registered(registry,rotated,outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    auto ellipse=std::get<EllipsoidSet>(from_ellipsoid_handle(
        std::get<EnclosedApproximation>(result).result.output));
    CHECK(ellipse.orientation().values==Vector{1,1,1,-1});
    CHECK(ellipse.projected_bounds()==Vector{3,3});

    const auto identity=methods();
    input=polygon("line",Matrix{2,2,{-1,0,1,0}});
    result=run_registered(identity,method,outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    ellipse=std::get<EllipsoidSet>(from_ellipsoid_handle(
        std::get<EnclosedApproximation>(result).result.output));
    CHECK(ellipse.radii()[1]==0.0);
    CHECK(ellipse.as_handle().metadata.polyhedral==SetProperty::yes);
    input=polygon("point",Matrix{1,2,{3,-4}});
    result=run_registered(identity,method,outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    ellipse=std::get<EllipsoidSet>(from_ellipsoid_handle(
        std::get<EnclosedApproximation>(result).result.output));
    CHECK(ellipse.center()==Vector{3,-4});
    CHECK(ellipse.radii()==Vector{0,0});
}

TEST_CASE("unsupported source, budget and assurance refuse before output") {
    const auto registry=methods();
    auto input=polygon("square",Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}});
    CHECK(std::holds_alternative<registry::Rejection>(
        run_registered(registry,method,outer(input,0),ExecutionContext{})));
    CHECK(std::holds_alternative<registry::Rejection>(
        run_registered(registry,method,outer(input,1,Assurance::validated),ExecutionContext{})));
    input=polygon("rayed",Matrix{1,2,{0,0}},Matrix{1,2,{1,0}});
    CHECK(std::holds_alternative<registry::Rejection>(
        run_registered(registry,method,outer(input),ExecutionContext{})));
    input=polygon("empty",Matrix{0,2,{}});
    CHECK(std::holds_alternative<registry::Rejection>(
        run_registered(registry,method,outer(input),ExecutionContext{})));
    registry::Registry<registry::ApproximationPort> singular;
    const registry::Method singular_method{{"test.ellipsoid.singular"},"1"};
    REQUIRE_FALSE(singular.add(make_directional_ellipsoid_registration(singular_method,
        {"singular"},Matrix{2,2,{1,1,2,2}})).has_value());
    CHECK(std::holds_alternative<registry::Rejection>(run_registered(singular,
        singular_method,outer(polygon("square2",Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}})),
        ExecutionContext{})));
}

TEST_CASE("unrepresentable radii refuse and tiny nonzero width stays nonzero") {
    const auto registry=methods();
    const double huge=std::numeric_limits<double>::max();
    const auto wide=polygon("wide",Matrix{2,2,{-huge,0,huge,0}});
    CHECK(std::holds_alternative<Unsupported>(
        run_registered(registry,method,outer(wide),ExecutionContext{})));
    const double tiny=std::numeric_limits<double>::denorm_min();
    const auto narrow=polygon("narrow",Matrix{2,2,{-tiny,0,tiny,0}});
    const auto result=run_registered(registry,method,outer(narrow),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto imported=from_ellipsoid_handle(
        std::get<EnclosedApproximation>(result).result.output);
    REQUIRE(std::holds_alternative<EllipsoidSet>(imported));
    CHECK(std::get<EllipsoidSet>(imported).radii()[0]>0);
    CHECK(std::get<EllipsoidSet>(imported).radii()[1]==0);
}

TEST_CASE("directional radius chooses the least sufficient binary64 value") {
    const auto registry=methods();
    constexpr double bound=5.0917663780381025e-12;
    const auto input=polygon("rounding-boundary",Matrix{2,2,{-bound,0,bound,0}});
    const auto result=run_registered(registry,method,outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto imported=from_ellipsoid_handle(
        std::get<EnclosedApproximation>(result).result.output);
    REQUIRE(std::holds_alternative<EllipsoidSet>(imported));
    CHECK(std::get<EllipsoidSet>(imported).radii()[0]==7.200845068256816e-12);
}

TEST_CASE("cancellation and forged provider bounds cannot publish an enclosure") {
    const auto input=polygon("square",Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}});
    const auto registry=methods();
    ExecutionContext cancelled;
    cancelled.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    CHECK(std::holds_alternative<OperationStopped>(
        run_registered(registry,method,outer(input),cancelled)));

    registry::Registry<registry::ApproximationPort> forged;
    const registry::Method liar{{"test.ellipsoid.understated"},"1"};
    auto entry=make_directional_ellipsoid_registration(liar,{"liar"},
        Matrix{2,2,{1,0,0,1}});
    // A provider may return a mathematically valid ellipsoid that does not
    // cover the requested source. Admission must inspect the source vertices.
    entry.factory=[](const ApproximationRequest&) -> std::unique_ptr<SetApproximatorWorkspace> {
        struct Workspace final : SetApproximatorWorkspace {
            SetTransformOutcome approximate(const ApproximationRequest& request,
                                             const ExecutionContext&) override {
                auto ellipse=std::get<EllipsoidSet>(make_ellipsoid({{"liar"},{0,0},
                    {2,2,{1,0,0,1}},{0.5,0.5},{1,1},{"x","y"}}));
                return OperationResult{ellipse.as_handle(),SetRelation::outer,
                    {{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
                     SymbolicArgument{"provider claim","unverified"},{},std::nullopt}};
            }
        };
        return std::make_unique<Workspace>();
    };
    REQUIRE_FALSE(forged.add(std::move(entry)).has_value());
    CHECK(std::holds_alternative<Unsupported>(
        run_registered(forged,liar,outer(input),ExecutionContext{})));
}
