#include <csl/geometry/affine_sum.hpp>
#include <csl/sets/data.hpp>

#include <iostream>
#include <stdexcept>

namespace {
template<class T,class... R> T take(std::variant<T,R...> result) {
    if(!std::holds_alternative<T>(result))
        throw std::runtime_error("installed source-index affine-sum client failed");
    return std::get<T>(std::move(result));
}

template<class Port> csl::registry::PreparedProvider<Port> prepare(
        csl::registry::Registration<Port> registration) {
    const csl::registry::Method method{registration.identity.id,registration.identity.version};
    csl::registry::Registry<Port> registry;
    if(registry.add(std::move(registration))) throw std::runtime_error("provider registration rejected");
    return take(csl::registry::prepare_provider(csl::registry::select_provider(registry,method,{})));
}
}

int main() {
    using namespace csl;
    const auto vertices=take(numeric::snapshot(Matrix{5,2,{0,0, 1,0, 1,1, 0,1, .25,.25}}));
    const auto rays=take(numeric::snapshot(Matrix{0,2,{}}));
    const auto input=take(sets::make_v({{"installed-source-index-cloud"},2,{"x","y"}},
        {vertices,rays})).as_handle();
    auto selected_hull=prepare(geometry::make_quickhull_source_index_registration());
    geometry::SourceIndexAffineSumDependencies dependencies{std::move(selected_hull),{}, {}};
    registry::Registry<registry::GeometryPort> operations;
    auto registration=geometry::make_affine_sum_registration(std::move(dependencies));
    if(operations.add(registration)) return 1;
    const OperationRequest request{{{"installed-source-index"},{"affine"},{"verified-square"}},
        {"csl.geometry.affine-sum.source-index"},
        AffineImage{input,{2,2,{1,0,0,1}},{0,0}},SetRelation::equivalent,Assurance::numerical};
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.relation=SetRelation::equivalent;
    auto pipeline=take(registry::prepare_pipeline(registry::select(operations,
        {{"csl.geometry.affine-sum.source-index"},{}},request,requirements)));
    auto [workspace]=pipeline.create();
    const auto outcome=workspace->run({{},{},{},{1e-8,1e-8},"installed-source-index"});
    if(!std::holds_alternative<OperationResult>(outcome)) return 2;
    const auto& result=std::get<OperationResult>(outcome);
    if(!check_geometry_evidence(result.evidence,request).empty()) return 3;
    const auto data=take(sets::from_handle(result.output));
    const auto representation=data.representation();
    const auto* output=std::get_if<sets::VRepresentation>(&representation);
    if(!output || output->vertices.rows()!=4 || output->vertices.cols()!=2) return 4;
    bool input_manifest=false, verified=false;
    for(const auto& item:result.evidence.assumptions) {
        input_manifest |= item.starts_with("source-index generated ordered cloud: digest=") &&
            item.find("; rows=")!=std::string::npos;
        verified |= item.starts_with("checker invocation:") && item.find("status=verified")!=std::string::npos;
    }
    if(!input_manifest || !verified) return 5;
    std::cout << "Installed source-index affine-sum client: selected QuickHull and exact all-input checker passed\n";
    return 0;
}
