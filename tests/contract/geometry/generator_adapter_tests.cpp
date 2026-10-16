#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/generator_adapter.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>
#include <algorithm>
#include <set>
#include <utility>

using namespace csl;

namespace {
template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class Port> registry::PreparedProvider<Port> provider(
        registry::Registration<Port> registration, RepresentationId representation) {
    registry::Registry<Port> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation=representation;
    requirements.output.relation=SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)));
}
sets::GeneratorSet generator(std::string id,Vector center,Matrix columns,
        std::vector<sets::FactorId> factors, Matrix equalities,Vector values) {
    return take(sets::make_generator_set({{std::move(id)},std::move(center),std::move(columns),
        std::move(factors),std::move(equalities),std::move(values),{}}));
}
OperationResult run(registry::PreparedProvider<registry::GeometryPort>& selected,
        const OperationRequest& request) {
    auto prepared=take(selected.prepare(request));
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-port"}));
}
OperationResult run(registry::PreparedProvider<registry::ConversionPort>& selected,
        const ConversionRequest& request) {
    auto prepared=take(selected.prepare(request));
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-port"}));
}
bool physical_box_h(double x) { return x<=12 && -x<=-2; }
bool physical_sum_h(double x) { return x<=9 && -x<=-3; }
}

TEST_CASE("prepared generator geometry preserves box factors and independent sum") {
    auto geometry=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    const auto box=generator("box",{1,2},{2,2,{2,0,0,3}},
        {{"horizontal"},{"vertical"}},{0,2,{}},{});
    const OperationRequest image_request{{{"geo07"},{"box-image"},{"image"}},
        {"csl.geometry.generators.operations"},
        AffineImage{box.as_handle(),{1,2,{1,1}},{4}},SetRelation::equivalent,Assurance::numerical};
    const auto image_result=run(geometry,image_request);
    CHECK(image_result.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(image_result.evidence,image_request).empty());
    const auto image=take(sets::from_generator_handle(image_result.output));
    CHECK(image.center()==Vector{7});
    CHECK(image.generators().values==Vector{2,3});
    CHECK(image.factor_ids()==std::vector<sets::FactorId>{{"horizontal"},{"vertical"}});
    for (double x:Vector{2,7,8,12}) CHECK(physical_box_h(x));
    for (double x:Vector{1,13}) CHECK_FALSE(physical_box_h(x));
    CHECK(image.center()[0]-image.generators().values[0]-image.generators().values[1]==2);
    CHECK(image.center()[0]+image.generators().values[0]+image.generators().values[1]==12);

    const auto left=generator("left",{2},{1,1,{1}},{{"a"}},{0,1,{}},{});
    const auto right=generator("right",{4},{1,1,{2}},{{"b"}},{0,1,{}},{});
    const OperationRequest sum_request{{{"geo07"},{"independent-sum"},{"sum"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto sum_result=run(geometry,sum_request);
    CHECK(check_geometry_evidence(sum_result.evidence,sum_request).empty());
    const auto sum=take(sets::from_generator_handle(sum_result.output));
    CHECK(sum.center()==Vector{6});
    CHECK(sum.generators().values==Vector{1,2});
    CHECK(sum.factor_ids()==std::vector<sets::FactorId>{{"a"},{"b"}});
    for (double x:Vector{3,6,9}) CHECK(physical_sum_h(x));
    for (double x:Vector{2,10}) CHECK_FALSE(physical_sum_h(x));
    CHECK(sum.center()[0]-sum.generators().values[0]-sum.generators().values[1]==3);
    CHECK(sum.center()[0]+sum.generators().values[0]+sum.generators().values[1]==9);
}

TEST_CASE("generator geometry keeps equalities and rejects dependent Minkowski aliasing") {
    auto ordinary=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    auto constrained=provider(geometry::generators::make_operation_registration(),{"csl.constrained-zonotope"});
    const auto diagonal=generator("diagonal",{0,0},{2,2,{1,0,0,1}},
        {{"u"},{"v"}},{1,2,{1,-1}},{0});
    const OperationRequest image_request{{{"geo07"},{"diagonal-image"},{"diagonal-out"}},
        {"csl.geometry.generators.operations"},AffineImage{diagonal.as_handle(),{1,2,{1,-1}},{0}},
        SetRelation::equivalent,Assurance::numerical};
    CHECK(std::holds_alternative<registry::Rejection>(ordinary.prepare(image_request)));
    const auto image=take(sets::from_generator_handle(run(constrained,image_request).output));
    CHECK(image.factor_ids()==std::vector<sets::FactorId>{{"u"},{"v"}});
    CHECK(image.equalities().values==Vector{1,-1});
    CHECK(image.equality_values()==Vector{0});

    const auto left=generator("left",{0},{1,1,{1}},{{"history.0"}},{0,1,{}},{});
    const auto right=generator("right",{0},{1,1,{-1}},{{"history.0"}},{0,1,{}},{});
    const OperationRequest alias{{{"geo07"},{"shared"},{"not-independent"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    CHECK(std::holds_alternative<registry::Rejection>(ordinary.prepare(alias)));
    auto intersection=alias;
    intersection.operation=Intersection{left.as_handle(),right.as_handle()};
    CHECK(std::holds_alternative<registry::Rejection>(ordinary.prepare(intersection)));
    auto validated=alias;
    validated.operation=AffineImage{left.as_handle(),{1,1,{1}},{0}};
    validated.assurance=Assurance::validated;
    CHECK(std::holds_alternative<registry::Rejection>(ordinary.prepare(validated)));
}

TEST_CASE("bounded explicit zonotope to V conversion has literal vertices and closure gates") {
    auto converter=provider(geometry::generators::make_v_conversion_registration(4),{"csl.polyhedron.v"});
    const auto segment=generator("image",{7},{1,2,{2,3}},
        {{"horizontal"},{"vertical"}},{0,2,{}},{});
    const ConversionRequest request{{{"geo07"},{"convert"},{"image-v"}},
        segment.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    const auto converted=run(converter,request);
    CHECK(converted.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(converted.evidence,request).empty());
    const auto data=take(sets::from_handle(converted.output));
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    REQUIRE(v);
    CHECK(v->rays.rows()==0);
    CHECK(v->vertices.rows()==4);
    std::set<double> observed;
    for(std::size_t row=0;row<v->vertices.rows();++row) {
        const double x=v->vertices(row,0);
        CHECK(physical_box_h(x));
        observed.insert(x);
    }
    CHECK(observed==std::set<double>{2,6,8,12});
    CHECK_FALSE(physical_box_h(1));
    CHECK_FALSE(physical_box_h(13));

    auto too_small=provider(geometry::generators::make_v_conversion_registration(3),{"csl.polyhedron.v"});
    CHECK(std::holds_alternative<registry::Rejection>(too_small.prepare(request)));
    const auto constrained=generator("constrained",{0},{1,1,{1}},{{"q"}},
        {1,1,{1}},{0});
    auto restricted=request;
    restricted.input=constrained.as_handle();
    CHECK(std::holds_alternative<registry::Rejection>(converter.prepare(restricted)));
    restricted=request;
    restricted.assurance=Assurance::validated;
    CHECK(std::holds_alternative<registry::Rejection>(converter.prepare(restricted)));
    restricted=request;
    restricted.output={"csl.polyhedron.h"};
    CHECK(std::holds_alternative<registry::Rejection>(converter.prepare(restricted)));

    const auto point=generator("point",{3,-1},{2,0,{}},{},{0,0,{}},{});
    restricted=request;
    restricted.input=point.as_handle();
    const auto point_result=run(converter,restricted);
    const auto point_data=take(sets::from_handle(point_result.output));
    const auto point_v=std::get<sets::VRepresentation>(point_data.representation());
    CHECK(point_v.vertices.rows()==1);
    CHECK(point_v.vertices(0,0)==3);
    CHECK(point_v.vertices(0,1)==-1);
}
