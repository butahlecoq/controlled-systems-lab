#include <csl/geometry/affine_sum.hpp>
#include <csl/sets/data.hpp>

#include <chrono>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>

namespace {
using namespace csl;
using namespace csl::registry;

template<class T,class... E> T take(std::variant<T,E...> value,const char* where) {
    if(!std::holds_alternative<T>(value)) throw std::runtime_error(std::string(where)+" was rejected");
    return std::get<T>(std::move(value));
}

template<class Port> PreparedProvider<Port> select(Registration<Port> registration) {
    const Method method{registration.identity.id,registration.identity.version};
    Registry<Port> registry;
    if(registry.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    return take(prepare_provider(select_provider(registry,method,{})),"provider selection");
}

SetHandle vertices(std::string id,Matrix matrix) {
    const auto dimension=matrix.cols;
    auto vertices=numeric::snapshot(std::move(matrix));
    auto rays=numeric::snapshot(Matrix{0,dimension,{}});
    if(!std::holds_alternative<numeric::MatrixView>(vertices) ||
       !std::holds_alternative<numeric::MatrixView>(rays)) throw std::runtime_error("V snapshot failed");
    return take(sets::make_v({{std::move(id)},dimension,{"x","y"}},
        {std::get<numeric::MatrixView>(std::move(vertices)),
         std::get<numeric::MatrixView>(std::move(rays))}),"V set").as_handle();
}

std::string quote(std::string_view value) {
    std::string result="\"";
    for(const char ch:value) {
        if(ch=='\\'||ch=='\"') result+='\\';
        if(ch=='\n') result+="\\n";
        else result+=ch;
    }
    return result+'\"';
}

void emit_result(std::string_view operation,const OperationRequest& request,
        const OperationResult& result,std::string_view provider) {
    const auto data=take(sets::from_handle(result.output),"operation output import");
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(!v) throw std::runtime_error("operation did not return V data");
    if(!check_geometry_evidence(result.evidence,request).empty())
        throw std::runtime_error("operation evidence rejected");
    std::cout<<"{\"operation\":"<<quote(operation)<<",\"method\":"<<quote(provider)
        <<",\"status\":\"completed\",\"vertices\":[";
    for(std::size_t row=0;row<v->vertices.rows();++row) {
        if(row) std::cout<<',';
        std::cout<<'['<<std::setprecision(17)<<v->vertices(row,0)<<','<<v->vertices(row,1)<<']';
    }
    std::cout<<"],\"evidence\":[";
    for(std::size_t i=0;i<result.evidence.assumptions.size();++i) {
        if(i) std::cout<<',';
        std::cout<<quote(result.evidence.assumptions[i]);
    }
    std::cout<<"]}";
}

}

int main(int argc,char** argv) try {
    using namespace csl;
    const std::string method=argc==2?argv[1]:"quickhull";
    if(argc>2||(method!="quickhull"&&method!="btulshor"))
        throw std::runtime_error("usage: source_index_geometry_2d [quickhull|btulshor]");
    auto source=method=="quickhull"?geometry::make_quickhull_source_index_registration():
        geometry::make_legacy_kpabep_source_index_registration();
    auto hull=select(std::move(source));
    geometry::SourceIndexAffineSumDependencies dependencies{hull,{},
        geometry::HullCheckBudget{std::chrono::milliseconds{5000},64}};
    auto operation=geometry::make_affine_sum_registration(std::move(dependencies));
    const Method operation_method{operation.identity.id,operation.identity.version};
    Registry<GeometryPort> registry;
    if(registry.add(std::move(operation))) throw std::runtime_error("affine-sum registration failed");
    Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.relation=SetRelation::equivalent;
    const auto method_name=method=="quickhull"?"csl.hull.source.quickhull-2d":"csl.hull.source.btulshor-kpabep";
    const auto provider=registry::prepare_provider(registry::select_provider(registry,operation_method,requirements));
    if(!std::holds_alternative<PreparedProvider<GeometryPort>>(provider))
        throw std::runtime_error("affine-sum provider selection failed");
    auto prepared=std::get<PreparedProvider<GeometryPort>>(provider);

    // Original IDs 0-3 are square corners; IDs 4, 5, and 6 are edge, duplicate,
    // and non-dyadic interior points. These remain in the generated ordered cloud
    // until the selected method proposes IDs and the independent checker passes.
    const auto controls=vertices("source-index-control-cloud",
        Matrix{7,2,{0,0,1,0,1,1,0,1,0.5,0,0,0,1.0/3.0,1.0/3.0}});
    const Matrix image_map{2,2,{1,0,0.5,1}};
    const Vector image_offset{0.25,-0.5};
    const AffineImage image_operation{controls,image_map,image_offset};
    const auto image_request=OperationRequest{{{"source-index-2d-example"},{"affine-image"},{"unit-square"}},
        {"csl.geometry.affine-sum.source-index"},image_operation,
        SetRelation::equivalent,Assurance::numerical};
    const auto initial=take(sets::make_singleton({{"known-initial-state"},2,{"x","y"}},
        take(numeric::snapshot_vector(Vector{0.25,0.5}),"initial point")),"initial singleton");
    const auto sum_request=OperationRequest{{{"source-index-2d-example"},{"control-minkowski-sum"},{"one-step-tube"}},
        {"csl.geometry.affine-sum.source-index"},MinkowskiSum{initial.as_handle(),controls},
        SetRelation::equivalent,Assurance::numerical};

    auto execute=[&](const OperationRequest& request) -> OperationOutcome {
        const auto admitted=prepared.prepare(request);
        if(!std::holds_alternative<PreparedPipeline<GeometryPort>>(admitted))
            throw std::runtime_error("geometry operation preparation rejected");
        auto workspace=std::get<PreparedPipeline<GeometryPort>>(admitted).create();
        return std::get<0>(workspace)->run({{},{},{},{1e-8,1e-8},"source-index-2d-example"});
    };
    auto run=[&](const OperationRequest& request) {
        const auto outcome=execute(request);
        if(!std::holds_alternative<OperationResult>(outcome))
            throw std::runtime_error("selected operation did not complete");
        return std::get<OperationResult>(outcome);
    };
    const auto image=run(image_request);
    const auto sum=run(sum_request);
    std::cout<<"{\"schema\":\"csl.example.source-index-geometry-2d/1\",\"source_method\":"
        <<quote(method_name)<<",\"checker_budget\":{\"wall_ms\":5000,\"max_points\":64},\"results\":[";
    emit_result("affine_image",image_request,image,method_name);
    std::cout<<',';
    emit_result("control_minkowski_sum",sum_request,sum,method_name);
    std::cout<<"],\"raw_failures\":[";
    if(method=="btulshor") {
        const auto near_tolerance=vertices("legacy-near-tolerance-cloud",
            Matrix{5,2,{0,0,1,0,1,1,0,1,0.5,1.00000001}});
        const Matrix identity_map{2,2,{1,0,0,1}};
        const Vector identity_offset{0,0};
        const AffineImage near_operation{near_tolerance,identity_map,identity_offset};
        const OperationRequest near_request{{{"source-index-2d-example"},{"legacy-near-tolerance"},
            {"legacy-near-tolerance-result"}},{"csl.geometry.affine-sum.source-index"},
            near_operation,SetRelation::equivalent,Assurance::numerical};
        const auto outcome=execute(near_request);
        if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
            std::string raw;
            for(const auto& item:unsupported->diagnostics) {
                if(!raw.empty()) raw+="; ";
                raw+=item.field+": "+item.explanation;
            }
            std::cout<<"{\"case\":\"near_tolerance_legacy_proposal\",\"outcome\":\"unsupported\",\"raw\":"
                <<quote(raw)<<"}";
        } else if(const auto* stopped=std::get_if<OperationStopped>(&outcome)) {
            std::cout<<"{\"case\":\"near_tolerance_legacy_proposal\",\"outcome\":\"stopped\",\"raw\":"
                <<quote(stopped->diagnostics)<<"}";
        } else throw std::runtime_error("near-tolerance legacy probe unexpectedly completed");
    }
    std::cout<<"]}\n";
    return 0;
} catch(const std::exception& error) {
    std::cerr<<error.what()<<'\n';
    return 1;
}
