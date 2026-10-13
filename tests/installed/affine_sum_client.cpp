#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/sets/data.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
template<class T,class... R> T take(std::variant<T,R...> result) {
    if(!std::holds_alternative<T>(result)) {
        throw std::runtime_error("affine/sum client failed");
    }
    return std::get<T>(std::move(result));
}
template<class Port> csl::registry::PreparedProvider<Port> prepare(csl::registry::Registration<Port> registration) {
    csl::registry::Requirements requirements;
    if constexpr (std::is_same_v<Port,csl::registry::LPPort>) requirements.output.representation={"csl.program-result.v1"};
    csl::registry::Registry<Port> registry;
    const csl::registry::Method method{registration.identity.id,registration.identity.version};
    if(registry.add(std::move(registration)))throw std::runtime_error("registration failed");
    return take(csl::registry::prepare_provider(csl::registry::select_provider(registry,method,requirements)));
}
}
int main() {
    using namespace csl;
    using namespace csl::registry;
    const auto vertices=take(numeric::snapshot(Matrix{2,1,{0,1}}));
    const auto rays=take(numeric::snapshot(Matrix{0,1,{}}));
    const auto input=take(sets::make_v({{"unit-interval"},1,{}},{vertices,rays})).as_handle();
    geometry::AffineSumDependencies dependencies{
        prepare(geometry::make_lp_hull_reducer_registration()),
        prepare(take(adapters::lp::make_highs_registration())),{}};
    Registry<GeometryPort> registry;
    if(registry.add(geometry::make_affine_sum_registration(std::move(dependencies))))return 1;
    const OperationRequest request{{{"installed-affine"},{"sum"},{"twice-interval"}},
        {"csl.geometry.affine-sum"},MinkowskiSum{input,input},SetRelation::equivalent,Assurance::numerical};
    Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.relation=SetRelation::equivalent;
    auto prepared=take(prepare_pipeline(select(registry,{{"csl.geometry.affine-sum"},{}},request,requirements)));
    auto [workspace]=prepared.create();
    const auto result=take(workspace->run({{},{},{},{1e-8,1e-8},"installed-affine"}));
    if(!check_geometry_evidence(result.evidence,request).empty())return 2;
    const auto data=take(sets::from_handle(result.output));
    const auto representation=data.representation();
    const auto* output=std::get_if<sets::VRepresentation>(&representation);
    if(!output||output->vertices.rows()<2||output->vertices.cols()!=1)return 3;
    double low=output->vertices(0,0),high=low;
    for(std::size_t i=1;i<output->vertices.rows();++i) {
        low=std::min(low,output->vertices(i,0));
        high=std::max(high,output->vertices(i,0));
    }
    if(std::abs(low)<1e-8&&std::abs(high-2)<1e-8) {
        std::cout << "Installed affine/sum client: selected LP and hull providers produced a numerical set result\n";
        return 0;
    }
    return 4;
}
