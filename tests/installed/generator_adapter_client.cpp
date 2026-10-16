#include <csl/geometry/generator_adapter.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>
#include <algorithm>
#include <iostream>
#include <set>
#include <stdexcept>

namespace {
template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> result) {
    if(!std::holds_alternative<T>(result)) throw std::runtime_error("generator port client rejected expected result");
    return std::get<T>(std::move(result));
}
template<class Port> csl::registry::PreparedProvider<Port> prepare(
        csl::registry::Registration<Port> registration,csl::RepresentationId representation) {
    csl::registry::Registry<Port> entries;
    const csl::registry::Method method{registration.identity.id,registration.identity.version};
    if(entries.add(std::move(registration))) throw std::runtime_error("generator registration failed");
    csl::registry::Requirements required;
    required.output.representation=representation;
    required.output.relation=csl::SetRelation::equivalent;
    return take(csl::registry::prepare_provider(csl::registry::select_provider(entries,method,required)));
}
}

int main() {
    using namespace csl;
    const auto box=take(sets::make_generator_set({{"box"},{1,2},{2,2,{2,0,0,3}},
        {{"horizontal"},{"vertical"}},{0,2,{}},{},{}}));
    auto geometry=prepare(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    const OperationRequest request{{{"installed-geo07"},{"image"},{"image-out"}},
        {"csl.geometry.generators.operations"},AffineImage{box.as_handle(),{1,2,{1,1}},{4}},
        SetRelation::equivalent,Assurance::numerical};
    auto planned=take(geometry.prepare(request));
    auto [work]=planned.create();
    const auto image_result=take(work->run({{},{},{},{1e-8,1e-8},"installed-geo07"}));
    if(!check_geometry_evidence(image_result.evidence,request).empty()) return 1;
    const auto image=take(sets::from_generator_handle(image_result.output));
    if(image.center()!=Vector{7} || image.generators().values!=Vector{2,3} ||
       image.factor_ids()!=std::vector<sets::FactorId>{{"horizontal"},{"vertical"}}) return 2;
    // Literal physical H oracle: x<=12 and -x<=-2.
    for(double x:Vector{2,7,12}) if(x>12 || -x>-2) return 3;
    for(double x:Vector{1,13}) if(x<=12 && -x<=-2) return 4;
    if(image.center()[0]-image.generators().values[0]-image.generators().values[1]!=2 ||
       image.center()[0]+image.generators().values[0]+image.generators().values[1]!=12) return 5;

    const auto left=take(sets::make_generator_set({{"shared-left"},{0},{1,1,{1}},
        {{"history.0"}},{0,1,{}},{},{}}));
    const auto right=take(sets::make_generator_set({{"shared-right"},{0},{1,1,{-1}},
        {{"history.0"}},{0,1,{}},{},{}}));
    const OperationRequest dependent{{{"installed-geo07"},{"dependent"},{"origin"}},
        {"csl.geometry.generators.operations"},DependentSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    auto dependent_plan=take(geometry.prepare(dependent));
    auto [dependent_work]=dependent_plan.create();
    const auto dependent_result=take(dependent_work->run({{},{},{},{1e-8,1e-8},"installed-geo07"}));
    if(!check_geometry_evidence(dependent_result.evidence,dependent).empty()) return 9;
    const auto cancellation=take(sets::from_generator_handle(dependent_result.output));
    if(cancellation.center()!=Vector{0} || cancellation.generators().values!=Vector{0} ||
        cancellation.factor_ids()!=std::vector<sets::FactorId>{{"history.0"}}) return 10;
    // Literal physical H oracle: x<=0 and -x<=0.
    if(cancellation.center()[0]>0 || -cancellation.center()[0]>0) return 11;
    const OperationRequest independent{{{"installed-geo07"},{"independent"},{"interval"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    if(!std::holds_alternative<registry::Rejection>(geometry.prepare(independent))) return 12;

    auto converter=prepare(geometry::generators::make_v_conversion_registration(4),{"csl.polyhedron.v"});
    const ConversionRequest conversion{{{"installed-geo07"},{"convert"},{"image-v"}},
        image.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    auto converted=take(converter.prepare(conversion));
    auto [conversion_work]=converted.create();
    const auto result=take(conversion_work->run({{},{},{},{1e-8,1e-8},"installed-geo07"}));
    if(!check_geometry_evidence(result.evidence,conversion).empty()) return 6;
    const auto data=take(sets::from_handle(result.output));
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(!v || v->vertices.rows()!=4 || v->rays.rows()!=0) return 7;
    std::set<double> vertices;
    for(std::size_t row=0;row<v->vertices.rows();++row) vertices.insert(v->vertices(row,0));
    if(vertices!=std::set<double>{2,6,8,12}) return 8;
    std::cout << "Installed generator adapter client: image, dependent sum and V conversion passed\n";
    return 0;
}
